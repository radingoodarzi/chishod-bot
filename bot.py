"""
بات «چی شد؟» - پیام‌های گروه رو جمع می‌کنه و با /chishod خلاصه می‌ده.

هر بار اجرا (تو GitHub Actions):
  1. فایل رمزشده‌ی state.enc رو باز می‌کنه
  2. پیام‌های جدید رو از تلگرام می‌گیره و ذخیره می‌کنه
  3. به دستورهای /chishod جواب می‌ده (خلاصه با Gemini)
  4. اگه چیزی عوض شده، state.enc رو دوباره رمز می‌کنه و می‌نویسه

متغیرهای محیطی لازم:
  TELEGRAM_TOKEN   توکن بات از BotFather
  GEMINI_API_KEY   کلید Google AI Studio
  DATA_KEY         کلید رمزنگاری (Fernet)
اختیاری:
  GEMINI_MODEL     پیش‌فرض gemini-flash-latest
  RETENTION_DAYS   چند روز پیام نگه داشته بشه (پیش‌فرض 7)
  STATE_FILE       مسیر فایل (پیش‌فرض state.enc)
"""

import html
import json
import os
import re
import sys
import time

import requests
from cryptography.fernet import Fernet, InvalidToken

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DATA_KEY = os.environ.get("DATA_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
# اگه مدل اصلی سهمیه‌اش پر شد یا در دسترس نبود، اینو امتحان می‌کنه
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "7"))
STATE_FILE = os.environ.get("STATE_FILE", "state.enc")

DEFAULT_WINDOW = 24 * 3600          # اولین بار: ۲۴ ساعت اخیر
MAX_PROMPT_CHARS = 120_000          # بیشتر از این، فقط آخرین پیام‌ها خلاصه می‌شن
TELEGRAM_LIMIT = 4000               # سقف طول هر پیام تلگرام (۴۰۹۶) با کمی حاشیه

HELP_TEXT = (
    "سلام! من پیام‌های گروه رو می‌خونم و وقتی بخوای خلاصه‌شون رو بهت می‌گم.\n\n"
    "/chishod - خلاصه‌ی پیام‌ها از آخرین باری که پرسیدی\n"
    "/chishod 3h - خلاصه‌ی ۳ ساعت اخیر (m دقیقه، h ساعت، d روز)\n"
    "/chishod full - خلاصه‌ی کامل و مفصل (با 3h هم می‌شه: /chishod full 3h)\n\n"
    "جواب ممکنه یکی دو دقیقه طول بکشه."
)

# قانون‌های مشترک هر دو حالت
_RULES = """- خلاصه کن، پیام‌ها رو تکرار نکن. پیام به پیام جلو نرو؛ بفهم درباره‌ی چی حرف زدن و نتیجه‌اش رو با حرف خودت بگو.
- هیچ ساعت و دقیقه‌ای ننویس (مثل 14:32)، مگه ساعت یه قرار یا برنامه باشه.
- متن پیام‌ها رو نقل‌قول نکن.
- فقط چیزی که تو پیام‌ها هست؛ هیچی از خودت نساز و حدس نزن.
- قرارها و تصمیم‌ها رو دقیق بگو: کی، کجا، چه روزی.
- «فردا» و «امشب» و مثل اینا رو با توجه به زمان پیام معنی کن.
- اسم آدم‌ها رو فقط جایی بیار که مهمه (مثلاً کی پیشنهاد داد یا کی قراره بیاد).
- فارسی محاوره‌ای و خودمونی، مثل یه رفیق که ماجرا رو برات تعریف می‌کنه.
- فقط تگ <b> مجازه و فقط برای تیترها. مارک‌داون (** یا #) ممنوع.
- هر آیتم یه خط جدا که با «• » شروع می‌شه."""

SHORT_PROMPT = """تو دستیار یه گروه تلگرامی دوستانه‌ای. {name} یه مدت نبوده و می‌خواد تو چند خط بفهمه تو گروه چی گذشته.

""" + _RULES + """
- هر خط = یه موضوع، یکی دو جمله. بین ۳ تا ۸ خط، بسته به اینکه چند تا موضوع بوده.
- موضوع‌های بی‌اهمیت (سلام، استیکر، شوخی‌های کوتاه) رو ننویس.

قالب:
اول خط‌های موضوع‌ها، بدون تیتر.
اگه جایی اسم {name} اومده، ازش سوال شده، بهش ریپلای شده یا ازش کاری خواستن، بعد از یه خط خالی:
<b>📌 مربوط به تو</b>
و زیرش همون موارد. اگه چیزی نبود، این بخش رو ننویس.

نمونه‌ی یه جواب خوب (فقط برای نشون دادن سبک، محتواش رو کپی نکن):
• بچه‌ها برای جمعه برنامه‌ی کوه چیدن؛ قرار شد ۷ صبح میدون تجریش جمع شن.
• علی گوشی جدید خریده و همه داشتن درباره‌ی دوربینش نظر می‌دادن.
• سر اینکه شنبه سینما برن یا نه هنوز به نتیجه نرسیدن.

<b>📌 مربوط به تو</b>
• سارا پرسیده جمعه ماشین میاری یا نه.
"""

FULL_PROMPT = """تو دستیار یه گروه تلگرامی دوستانه‌ای. {name} یه مدت نبوده و می‌خواد کامل و مرتب بدونه تو گروه چی گذشته.

""" + _RULES + """
- همه‌ی موضوع‌های مهم رو پوشش بده، با جزئیات بیشتر از یه خلاصه‌ی کوتاه.
- اگه نظرها فرق داشته، خلاصه بگو هر کی چه نظری داشت. اگه بحثی به نتیجه نرسیده، صریح بگو.
- مرتب و تمیز: هر آیتم یکی دو جمله. اگه یه موضوع چند تا نکته داره، نکته‌ها رو با «  ◦ » زیرش بیار.
- بین بخش‌ها یه خط خالی بذار. بخشی که چیزی نداره رو ننویس.

بخش‌ها به این ترتیب:
<b>🗣 موضوع‌ها</b>
هر موضوع یه آیتم: درباره‌ی چی بود و به کجا رسید.

<b>✅ قرارها و تصمیم‌ها</b>
چیزهایی که قطعی شد: کی، کجا، چی، با کی.

<b>📌 مربوط به تو</b>
جاهایی که اسم {name} اومده، ازش سوال شده، بهش ریپلای شده یا ازش کاری خواستن. اگه منتظر جوابشن، بگو.

<b>❓ هنوز باز</b>
سوال‌ها یا بحث‌هایی که تموم نشده.
"""


# ---------- ذخیره‌سازی رمزشده ----------

def empty_state():
    return {"offset": 0, "messages": [], "last_seen": {}}


def load_state(path=STATE_FILE, key=DATA_KEY):
    if not os.path.exists(path):
        return empty_state()
    with open(path, "rb") as f:
        blob = f.read()
    try:
        raw = Fernet(key.encode()).decrypt(blob)
    except InvalidToken:
        sys.exit("DATA_KEY اشتباهه یا فایل state.enc خرابه.")
    state = json.loads(raw)
    for k, v in empty_state().items():
        state.setdefault(k, v)
    return state


def save_state(state, path=STATE_FILE, key=DATA_KEY):
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()
    with open(path, "wb") as f:
        f.write(Fernet(key.encode()).encrypt(raw))


def state_fingerprint(state):
    return json.dumps(state, sort_keys=True, ensure_ascii=False)


# ---------- تلگرام ----------

def tg(method, **params):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
        json=params,
        timeout=30,
    )
    data = r.json()
    if r.status_code in (401, 404):
        sys.exit("TELEGRAM_TOKEN اشتباهه. توکن کامل رو از BotFather کپی کن "
                 "(شکلش اینه: 1234567890:AAH...).")
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
    return data["result"]


def fetch_updates(offset):
    updates = []
    while True:
        batch = tg("getUpdates", offset=offset, limit=100, timeout=0,
                   allowed_updates=["message", "edited_message"])
        if not batch:
            return updates
        updates.extend(batch)
        offset = batch[-1]["update_id"] + 1


def split_text(text, limit=TELEGRAM_LIMIT):
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def reply(chat_id, reply_to, text, as_html=False):
    for i, part in enumerate(split_text(text)):
        params = {"chat_id": chat_id, "text": part}
        if i == 0 and reply_to:
            params["reply_parameters"] = {"message_id": reply_to,
                                          "allow_sending_without_reply": True}
        if as_html:
            params["parse_mode"] = "HTML"
        try:
            tg("sendMessage", **params)
        except RuntimeError as e:
            # اگه HTML خراب بود (مثلاً تگ نصفه موند)، ساده بفرست
            if not as_html or "parse" not in str(e).lower():
                raise
            params.pop("parse_mode")
            params["text"] = html.unescape(re.sub(r"</?[bi]>", "", part))
            tg("sendMessage", **params)


def to_telegram_html(text):
    """جواب مدل رو امن می‌کنه: فقط <b> و <i> می‌مونن، بقیه escape می‌شن."""
    text = re.sub(r"^```\w*\n?|\n?```$", "", text.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)      # اگه مارک‌داون نوشت
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = html.escape(text, quote=False)
    return re.sub(r"&lt;(/?)([bi])&gt;", r"<\1\2>", text)


def tehran_time(ts, with_date=False):
    fmt = "%m/%d %H:%M" if with_date else "%H:%M"
    return time.strftime(fmt, time.gmtime(ts + 3.5 * 3600))


def display_name(user):
    name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
    return name or user.get("username") or "ناشناس"


# ---------- پردازش پیام‌ها ----------

COMMAND_RE = re.compile(r"^/chishod(?:@\w+)?(?:\s+(.*))?", re.IGNORECASE)
FULL_WORDS = ("full", "کامل")
START_RE = re.compile(r"^/(start|help)(?:@\w+)?\b", re.IGNORECASE)
WINDOW_RE = re.compile(r"^(\d+)\s*([mhd])$", re.IGNORECASE)


def parse_window(arg):
    """'3h' -> ثانیه. اگه نامعتبر باشه None."""
    if not arg:
        return None
    m = WINDOW_RE.match(arg)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * {"m": 60, "h": 3600, "d": 86400}[unit]


def record(state, msg):
    """پیام رو ذخیره می‌کنه (یا اگه ادیت شده، آپدیتش می‌کنه)."""
    text = msg.get("text") or msg.get("caption") or ""
    if not text:
        kind = next((k for k in ("photo", "video", "voice", "sticker", "document",
                                 "animation", "audio", "video_note", "poll")
                     if k in msg), None)
        if not kind:
            return
        text = f"[{kind}]"
    if text.startswith("/"):
        return  # دستورها رو تو خلاصه نمیاریم

    user = msg.get("from", {})
    entry = {
        "chat": msg["chat"]["id"],
        "id": msg["message_id"],
        "date": msg["date"],
        "uid": user.get("id"),
        "name": display_name(user),
        "user": user.get("username"),
        "text": text,
    }
    rt = msg.get("reply_to_message")
    if rt and rt.get("from"):
        entry["reply_to"] = display_name(rt["from"])

    for i, old in enumerate(state["messages"]):
        if old["chat"] == entry["chat"] and old["id"] == entry["id"]:
            state["messages"][i] = entry
            return
    state["messages"].append(entry)


def format_transcript(messages):
    multi_day = messages[-1]["date"] - messages[0]["date"] > 20 * 3600
    lines = []
    for m in messages:
        t = tehran_time(m["date"], multi_day)
        who = m["name"] + (f" (@{m['user']})" if m.get("user") else "")
        to = f" ← در جواب {m['reply_to']}" if m.get("reply_to") else ""
        lines.append(f"[{t}] {who}{to}: {m['text']}")
    return "\n".join(lines)


def gemini(model, system, prompt):
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": GEMINI_API_KEY},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            },
            timeout=60,
        )
    except requests.RequestException as e:  # تایم‌اوت یا قطعی شبکه
        raise GeminiError(0, str(e))
    if r.status_code != 200:
        raise GeminiError(r.status_code, r.text[:300])
    parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


class GeminiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"Gemini {status}: {body}")
        self.status = status


def summarize(messages, requester, full=False):
    transcript = format_transcript(messages)
    note = ""
    if len(transcript) > MAX_PROMPT_CHARS:
        transcript = transcript[-MAX_PROMPT_CHARS:]
        transcript = transcript[transcript.find("\n") + 1:]
        note = "\n\n(پیام‌ها خیلی زیاد بودن؛ فقط آخرین‌هاشون خلاصه شد.)"

    system = (FULL_PROMPT if full else SHORT_PROMPT).format(name=requester)
    now = tehran_time(time.time(), with_date=True)
    prompt = (f"الان {now} به وقت تهرانه (ساعت‌های زیر هم به وقت تهرانن).\n"
              f"این پیام‌های گروهه؛ برای {requester} خلاصه‌شون کن:\n\n{transcript}")
    last_error = None
    for model in dict.fromkeys((GEMINI_MODEL, GEMINI_FALLBACK_MODEL)):
        try:
            return to_telegram_html(gemini(model, system, prompt)) + note
        except GeminiError as e:
            last_error = e
            print(e, file=sys.stderr)
            if e.status not in (0, 404, 429, 500, 503):
                break
    if last_error and last_error.status == 429:
        return "سهمیه‌ی رایگان Gemini فعلاً پر شده. یه کم بعد دوباره /chishod بزن."
    if last_error and last_error.status in (0, 503):
        return "Gemini الان خیلی شلوغه و جواب نداد 😕 چند دقیقه بعد دوباره /chishod بزن."
    return "نشد خلاصه کنم، یه مشکلی با Gemini پیش اومد. یه کم بعد دوباره امتحان کن."


def handle_command(state, msg, arg):
    chat_id = msg["chat"]["id"]
    user = msg.get("from", {})
    key = f"{chat_id}:{user.get('id')}"
    now = msg["date"]

    full, window = False, None
    for word in (arg or "").split():
        if word.lower() in FULL_WORDS:
            full = True
        elif parse_window(word):
            window = parse_window(word)
        else:
            reply(chat_id, msg["message_id"],
                  "نفهمیدم. مثلاً بنویس /chishod 3h یا /chishod full یا /chishod full 2d")
            return

    if window:
        since = now - window
    else:
        since = state["last_seen"].get(key, now - DEFAULT_WINDOW)

    picked = [m for m in state["messages"]
              if m["chat"] == chat_id and since < m["date"] <= now]
    state["last_seen"][key] = now

    if not picked:
        reply(chat_id, msg["message_id"], "از آخرین باری که پرسیدی خبر خاصی نبوده.")
        return

    name = display_name(user)
    summary = summarize(picked, name, full)
    title = "خلاصه‌ی کامل" if full else "خلاصه"
    header = f"📋 <b>{title}</b> برای {html.escape(name)} · {len(picked)} پیام\n\n"
    reply(chat_id, msg["message_id"], header + summary, as_html=True)


def process(state, updates):
    commands = []
    for upd in updates:
        state["offset"] = max(state["offset"], upd["update_id"] + 1)
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        chat_type = msg["chat"]["type"]
        text = msg.get("text") or ""

        if chat_type == "private":
            if "message" in upd:
                reply(msg["chat"]["id"], None,
                      HELP_TEXT + "\n\nمن رو تو گروه اد کن تا کار کنم.")
            continue
        if chat_type not in ("group", "supergroup"):
            continue

        record(state, msg)
        if "message" not in upd:
            continue  # به ادیت دستورها جواب نمیدیم
        m = COMMAND_RE.match(text)
        if m:
            commands.append((msg, m.group(1)))
        elif START_RE.match(text):
            reply(msg["chat"]["id"], msg["message_id"], HELP_TEXT)

    # اگه یه نفر چند بار پشت هم /chishod زده، فقط به آخریش جواب بده
    latest = {}
    for msg, arg in commands:
        latest[(msg["chat"]["id"], msg.get("from", {}).get("id"))] = (msg, arg)

    # اول همه‌ی پیام‌ها ذخیره بشن، بعد خلاصه، تا پیام‌های همین دور هم حساب بشن.
    # بعد از هر جواب ذخیره می‌کنیم که اگه اجرا وسطش قطع شد، دوباره جواب نده.
    if latest:
        save_state(state)
    for msg, arg in latest.values():
        try:
            handle_command(state, msg, arg)
        except Exception as e:  # یه دستور خراب نباید بقیه رو خراب کنه
            print(f"command failed: {e}", file=sys.stderr)
        save_state(state)


def prune(state, now=None):
    cutoff = (now or time.time()) - RETENTION_DAYS * 86400
    state["messages"] = [m for m in state["messages"] if m["date"] >= cutoff]


def main():
    missing = [n for n in ("TELEGRAM_TOKEN", "GEMINI_API_KEY", "DATA_KEY")
               if not os.environ.get(n)]
    if missing:
        sys.exit("این متغیرها تنظیم نشدن: " + ", ".join(missing))

    state = load_state()
    before = state_fingerprint(state)

    updates = fetch_updates(state["offset"])
    process(state, updates)
    prune(state)

    if state_fingerprint(state) != before or not os.path.exists(STATE_FILE):
        save_state(state)
        print(f"saved: {len(updates)} new updates, {len(state['messages'])} stored")
    else:
        print("nothing new")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--genkey":
        print(Fernet.generate_key().decode())
    else:
        main()
