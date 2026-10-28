# بات «چی شد؟»

پیام‌های گروه تلگرام رو جمع می‌کنه و وقتی `/chishod` می‌زنی، خلاصه‌ی چیزایی که از دست دادی رو بهت می‌گه.

- `/chishod` ← خلاصه از آخرین باری که پرسیدی (بار اول: ۲۴ ساعت اخیر)
- `/chishod 3h` ← خلاصه‌ی ۳ ساعت اخیر (`m` دقیقه، `h` ساعت، `d` روز)

بات روی GitHub Actions اجرا می‌شه (رایگان) و cron-job.org هر چند دقیقه صداش می‌زنه، پس جواب ۱ تا ۳ دقیقه طول می‌کشه.
پیام‌ها رمزشده تو شاخه‌ی `bot-data` ذخیره می‌شن و بعد از ۷ روز پاک می‌شن.

---

## راه‌اندازی

### ۱. بات تلگرام
1. تو تلگرام به `@BotFather` پیام بده، `/newbot` بزن و اسم بده. **توکن** رو نگه دار.
2. `/setprivacy` ← باتت رو انتخاب کن ← **Disable**.
   (اگه قبلاً بات رو تو گروه اد کردی، یه بار ریموو کن و دوباره اد کن، وگرنه این تغییر اعمال نمی‌شه.)

### ۲. کلید رمزنگاری
تو همین پوشه:
```bash
pip install -r requirements.txt
```
```bash
python bot.py --genkey
```
خروجی رو یه جای امن نگه دار. این **DATA_KEY** هست. اگه گمش کنی پیام‌های ذخیره‌شده دیگه باز نمی‌شن (کافیه شاخه‌ی `bot-data` رو پاک کنی و یه کلید جدید بسازی).

### ۳. ریپوی GitHub
1. یه ریپوی **Public** جدید بساز، مثلاً `chishod-bot` (بدون README).
2. فایل‌های این پوشه رو آپلود کن (`bot.py`، `requirements.txt`، `.gitignore`، `README.md` و پوشه‌ی `.github`). با git:
```bash
git init -b main
```
```bash
git add .
```
```bash
git commit -m "first"
```
```bash
git remote add origin https://github.com/USERNAME/chishod-bot.git
```
```bash
git push -u origin main
```

### ۴. Secrets
تو ریپو: **Settings ← Secrets and variables ← Actions ← New repository secret**، سه تا بساز:

| اسم | مقدار |
|---|---|
| `TELEGRAM_TOKEN` | توکن BotFather |
| `GEMINI_API_KEY` | کلید Google AI Studio |
| `DATA_KEY` | خروجی مرحله‌ی ۲ |

### ۵. تست
بات رو تو گروه اد کن و چند تا پیام بفرست، بعد `/chishod` بزن.
تو ریپو برو **Actions ← bot ← Run workflow**. بعد از اجرا باید جواب تو گروه بیاد. اگه قرمز شد، روش کلیک کن تا ارور رو ببینی.

### ۶. توکن GitHub برای cron-job.org
**Settings (پروفایل خودت) ← Developer settings ← Personal access tokens ← Fine-grained tokens ← Generate new token**
- Repository access: **Only select repositories** ← فقط `chishod-bot`
- Permissions ← Repository ← **Actions: Read and write**
- Expiration رو طولانی بذار (موقع تموم شدن باید عوضش کنی)

### ۷. cron-job.org
ثبت‌نام کن و **Create cronjob**:
- **URL:** `https://api.github.com/repos/USERNAME/chishod-bot/actions/workflows/bot.yml/dispatches`
- **Schedule:** هر ۲ یا ۳ دقیقه
- تب **Advanced**:
  - Request method: **POST**
  - Headers:
    - `Authorization` ← `Bearer توکن_مرحله_۶`
    - `Accept` ← `application/vnd.github+json`
    - `X-GitHub-Api-Version` ← `2022-11-28`
  - Request body: `{"ref":"main"}`

اگه درست باشه، cron-job.org جواب `204` می‌گیره و تو تب Actions اجراها رو می‌بینی.

---

## نکته‌ها
- بات فقط پیام‌های **بعد از** اد شدنش رو می‌بینه.
- اگه چند روز هیچ اجرایی نشه، تلگرام پیام‌های بیشتر از ۲۴ ساعت رو نگه نمی‌داره و اونا از دست می‌رن.
- متن پیام‌ها برای خلاصه شدن به Gemini فرستاده می‌شه و گوگل ممکنه از داده‌های پلن رایگان استفاده کنه. به دوستات بگو.
- مدل پیش‌فرض `gemini-flash-latest` هست و اگه سهمیه‌اش پر شد `gemini-flash-lite-latest` امتحان می‌شه. برای عوض کردن، تو `bot.yml` متغیر `GEMINI_MODEL` اضافه کن.
