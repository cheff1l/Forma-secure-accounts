# Налаштування справжньої пошти, CAPTCHA та Google-входу

У поточній папці вже є `backend/.env`. Відкрийте його командою `notepad backend\.env`. **Не надсилайте в чат і не публікуйте цей файл.** Після зміни `.env` перезапустіть сервер командою `.\.venv\Scripts\python.exe backend\app.py`.

## 1. Надсилання з Gmail

1. Увімкніть [двоетапну перевірку Google-акаунта](https://myaccount.google.com/security).
2. Створіть [пароль застосунку](https://myaccount.google.com/apppasswords) для цього сайту. Google вимагає двоетапну перевірку; інколи пункт «Паролі додатків» недоступний для робочих/навчальних акаунтів або Advanced Protection. Використовуйте **пароль застосунку**, а не звичайний пароль Gmail. [Довідка Google](https://support.google.com/accounts/answer/185833).
3. У `backend/.env` заповніть:

```dotenv
DEMO_MODE=0
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=ваша_адреса@gmail.com
SMTP_PASSWORD=16-символьний_пароль_застосунку
SMTP_FROM=ваша_адреса@gmail.com
```

Лист про 5 невдалих спроб входу містить посилання на сторінку підтримки `/support`. Там користувач може залишити повідомлення, яке з’явиться в адмінпанелі.

Після реєстрації лист активації надійде на адресу, введену у формі. Лист скидання пароля надходить на адресу вже зареєстрованого акаунта. Перевірте також папку «Спам». Без заповнених SMTP-полів реєстрація і запит відновлення покажуть повідомлення про налаштування, а не вдаватимуть успішне надсилання.

## 2. Сервісний віджет hCaptcha

Поточний режим Forma — `CAPTCHA_PROVIDER=hcaptcha`. На реєстрації, вході з паролем, вході через Google та сторінці нового пароля з’являється віджет hCaptcha. Після перевірки сервер надсилає його токен до hCaptcha Siteverify. Віджет завантажується з параметром української мови `hl=uk`. Тип завдання визначає сервіс: введення слів із картинки він не гарантує.

1. У [hCaptcha Dashboard](https://dashboard.hcaptcha.com/) відкрийте **Sites** і переконайтеся, що ваш sitekey дозволяє `forma.localtest.me`. За бажанням виберіть **Always Challenge** у налаштуваннях сайту. Sitekey і secret key уже потрібно вписати в `backend/.env`; секрет не публікуйте. [Документація hCaptcha](https://docs.hcaptcha.com/).
2. Локальна назва `forma.localtest.me` має вказувати на `127.0.0.1`. У Windows перевірте файл `C:\Windows\System32\drivers\etc\hosts`: рядок `127.0.0.1 forma.localtest.me`. hCaptcha не приймає `localhost` і `127.0.0.1` як hostname віджета. [Офіційна інструкція для локальної розробки](https://docs.hcaptcha.com/#local-development).
3. У `backend/.env` мають бути:

```dotenv
HCAPTCHA_SITE_KEY=ваш_sitekey
HCAPTCHA_SECRET_KEY=ваш_secret
HCAPTCHA_ORIGIN=http://forma.localtest.me:5173
CAPTCHA_PROVIDER=hcaptcha
```

4. Перезапустіть **обидва** сервери. Сторінки реєстрації та входу, відкриті з `127.0.0.1:5173`, автоматично перейдуть на `forma.localtest.me` для hCaptcha. Так само відкриється посилання скидання пароля з листа. `BASE_URL` і Google redirect URI залишаються `http://127.0.0.1:5173`; після Google OAuth сервер відновлює сесію за одноразовим станом. Для роботи віджета потрібен інтернет. У статистиці hCaptcha шукайте саме sitekey, указаний у `.env`; дані можуть з’являтися із затримкою.

В акаунті з увімкненим TOTP перед надсиланням листа для зміни пароля потрібно ввести код з автентифікатора. Після цього користувач підтверджує запит посиланням із пошти. Якщо користувач уже ввійшов, сайт сам визначає адресу й показує її замаскованою; після виходу треба вказати email або логін акаунта, щоб сайт знайшов адресу.

### Альтернатива: Cloudflare Turnstile

Щоб повернути Turnstile, змініть `CAPTCHA_PROVIDER=turnstile` у `backend/.env` і перезапустіть сервер.

1. У [Cloudflare Turnstile](https://dash.cloudflare.com/?to=/:account/turnstile) створіть widget. Для локальної роботи додайте hostname `127.0.0.1` до дозволених адрес. [Довідка Cloudflare про локальні адреси](https://developers.cloudflare.com/turnstile/troubleshooting/testing/).
2. Скопіюйте **site key** і **secret key** у `backend/.env`:

```dotenv
TURNSTILE_SITE_KEY=ваш_site_key
TURNSTILE_SECRET_KEY=ваш_secret_key
```

Site key показується в браузері; secret key залишається лише на сервері. Під час реєстрації сервер перевіряє одноразовий токен через Cloudflare Siteverify. Потрібен інтернет. [Документація Siteverify](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).

## 3. Вхід через Google

1. У [Google Auth Platform](https://console.cloud.google.com/auth/overview) створіть або виберіть проєкт. У **Branding** вкажіть назву застосунку `Forma`, адресу підтримки й контактну адресу розробника. У **Audience** виберіть **External**. Якщо застосунок має статус **Testing**, додайте Google-адресу, з якої будете входити, до **Test users**.
2. У [Clients](https://console.cloud.google.com/auth/clients) створіть клієнт типу **Web application**. Назва може бути `Forma local`. У **Authorized redirect URIs** додайте точно `http://127.0.0.1:5173/google/callback`. **Authorized JavaScript origins** для цього серверного входу заповнювати не потрібно.
3. Скопіюйте видані **Client ID** та **Client secret**. Не надсилайте секрет у чат і не додавайте `backend/.env` до Git.
4. У `backend/.env` заповніть:

```dotenv
BASE_URL=http://127.0.0.1:5173
GOOGLE_CLIENT_ID=ваш_client_id
GOOGLE_CLIENT_SECRET=ваш_client_secret
```

Перезапустіть Python-сервер. Якщо у вас уже є профіль Forma, увійдіть паролем, відкрийте профіль і натисніть **«Підключити Google-акаунт»**. Виберіть Google-акаунт із **тією самою поштовою адресою**. Потім вийдіть із Forma й натисніть **«Увійти через Google»** на сторінці входу: відкриється той самий профіль. Новий користувач може одразу натиснути «Увійти через Google» — профіль створиться після підтвердження Google. Автоматичне злиття акаунтів за однаковим email без підключення у профілі вимкнено. [Документація Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

## 4. Двофакторна перевірка

Після входу відкрийте **Безпека акаунта → Налаштувати 2FA**, відскануйте QR-код застосунком автентифікації або введіть ключ вручну, потім підтвердьте шестизначним кодом. Наступний вхід вимагатиме пароль і код. QR-код з’являється після встановлення залежностей із `backend\requirements.txt`.

## Запуск після налаштування

У першому PowerShell:

```powershell
cd "C:\Users\User\Documents\Codex\2026-10-31\ghb\outputs\Forma-secure-accounts"
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe backend\app.py
```

У другому PowerShell у цій же папці:

```powershell
npm.cmd ci
npm.cmd run dev
```

Відкрийте [http://127.0.0.1:5173](http://127.0.0.1:5173). Обидва сервери мають залишатися запущеними.
