"""Educational account security project. Run: python app.py"""
import base64
import hashlib
import hmac
import html
import json
import io
import os
import re
import secrets
import socket
import smtplib
import ssl
import sqlite3
import sys
import time
import urllib.parse
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path


import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

ROOT = Path(__file__).resolve().parent
for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
DB = Path(os.getenv("DB_PATH", str(ROOT / "accounts.sqlite3")))
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5173").rstrip("/")
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
GOOGLE_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
HCAPTCHA_SITE_KEY = os.getenv("HCAPTCHA_SITE_KEY", "")
HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY", "")
HCAPTCHA_ORIGIN = os.getenv("HCAPTCHA_ORIGIN", "").rstrip("/")
CAPTCHA_PROVIDER = os.getenv("CAPTCHA_PROVIDER", "").strip().lower()
CAPTCHA_PEPPER = secrets.token_bytes(32)
app = FastAPI(title="Безпечні облікові записи", docs_url=None, redoc_url=None)

def now(): return int(time.time())
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def esc(value): return html.escape(str(value if value is not None else ""), quote=True)
def mask_email(email):
    local, domain = email.rsplit("@", 1)
    visible = min(2, max(1, len(local) // 3))
    masked_local = local[:visible] + "*" * max(1, len(local) - visible)
    parts = domain.split(".")
    masked_domain = ".".join(part[0] + "*" * (len(part) - 1) if index < len(parts) - 1 else part
                             for index, part in enumerate(parts))
    return masked_local + "@" + masked_domain
def url(path): return BASE_URL + path
class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
def db():
    c = sqlite3.connect(DB, timeout=10, factory=ClosingConnection)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c
def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
          password_hash TEXT, role TEXT NOT NULL DEFAULT 'user', active INTEGER NOT NULL DEFAULT 0,
          blocked INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0,
          failed_count INTEGER NOT NULL DEFAULT 0, totp_secret TEXT, google_sub TEXT UNIQUE,
          created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS user_id_sequence(id INTEGER PRIMARY KEY AUTOINCREMENT);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER,
          csrf TEXT NOT NULL, captcha_answer TEXT, captcha_until INTEGER, pending_2fa INTEGER NOT NULL DEFAULT 0,
          oidc_state TEXT, oidc_nonce TEXT, oidc_verifier TEXT, expires_at INTEGER NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS tokens(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
          purpose TEXT NOT NULL, expires_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS captcha_challenges(token_hash TEXT NOT NULL, purpose TEXT NOT NULL,
          answer_hash TEXT NOT NULL, expires_at INTEGER NOT NULL,
          PRIMARY KEY(token_hash,purpose), FOREIGN KEY(token_hash) REFERENCES sessions(token_hash) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS login_log(id INTEGER PRIMARY KEY, email TEXT NOT NULL,
          ip TEXT NOT NULL, result TEXT NOT NULL, happened_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS mail_outbox(id INTEGER PRIMARY KEY, recipient TEXT NOT NULL,
          subject TEXT NOT NULL, body TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS support_requests(id INTEGER PRIMARY KEY, email TEXT NOT NULL,
          message TEXT NOT NULL, ip TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, happened_at INTEGER NOT NULL,
          actor_email TEXT NOT NULL, target_email TEXT NOT NULL, ip TEXT NOT NULL,
          event TEXT NOT NULL, details TEXT NOT NULL DEFAULT '');
        """)
        columns={row["name"] for row in c.execute("PRAGMA table_info(users)")}
        if "username" not in columns:
            c.execute("ALTER TABLE users ADD COLUMN username TEXT")
        for column in ("display_name", "birth_date", "bio"):
            if column not in columns:
                c.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_unique ON users(username)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_ci_unique ON users(lower(username)) WHERE username IS NOT NULL")
        session_columns={row["name"] for row in c.execute("PRAGMA table_info(sessions)")}
        for column,definition in (("created_at","INTEGER NOT NULL DEFAULT 0"),
                                  ("last_seen_at","INTEGER NOT NULL DEFAULT 0"),
                                  ("ip","TEXT NOT NULL DEFAULT ''"),
                                  ("user_agent","TEXT NOT NULL DEFAULT ''")):
            if column not in session_columns:
                c.execute(f"ALTER TABLE sessions ADD COLUMN {column} {definition}")
        c.execute("UPDATE sessions SET created_at=MAX(0,expires_at-86400) WHERE created_at=0")
        c.execute("UPDATE sessions SET last_seen_at=created_at WHERE last_seen_at=0")
        support_columns={row["name"] for row in c.execute("PRAGMA table_info(support_requests)")}
        for column,definition in (("category","TEXT NOT NULL DEFAULT 'other'"),
                                  ("subject","TEXT NOT NULL DEFAULT ''"),
                                  ("steps","TEXT NOT NULL DEFAULT ''"),
                                  ("status","TEXT NOT NULL DEFAULT 'new'"),
                                  ("admin_note","TEXT NOT NULL DEFAULT ''"),
                                  ("updated_at","INTEGER NOT NULL DEFAULT 0")):
            if column not in support_columns:
                c.execute(f"ALTER TABLE support_requests ADD COLUMN {column} {definition}")
        mail_columns={row["name"] for row in c.execute("PRAGMA table_info(mail_outbox)")}
        if "support_request_id" not in mail_columns:
            c.execute("ALTER TABLE mail_outbox ADD COLUMN support_request_id INTEGER")
        highest_user_id=c.execute("SELECT max(id) FROM users").fetchone()[0]
        if highest_user_id:
            c.execute("INSERT OR IGNORE INTO user_id_sequence(id) VALUES(?)",(highest_user_id,))
        c.execute("CREATE INDEX IF NOT EXISTS audit_log_latest ON audit_log(happened_at DESC)")
init_db()
def next_user_id(c):
    highest=c.execute("SELECT max(id) FROM users").fetchone()[0]
    if highest: c.execute("INSERT OR IGNORE INTO user_id_sequence(id) VALUES(?)",(highest,))
    return c.execute("INSERT INTO user_id_sequence DEFAULT VALUES").lastrowid

def password_error(p):
    if len(p) < 8: return "Пароль має містити щонайменше 8 символів."
    if not re.search(r"[A-ZА-ЯІЇЄҐ]", p): return "Додайте велику літеру."
    if not re.search(r"[a-zа-яіїєґ]", p): return "Додайте малу літеру."
    if not re.search(r"\d", p): return "Додайте цифру."
    if not re.search(r"[^\w\s]|_", p): return "Додайте спеціальний символ."
    return None
def hash_password(p):
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + salt.hex() + "$" + hashed.hex()
def verify_password(p, stored):
    if not stored: return False
    try:
        _, n, r, parallel, salt, expected = stored.split("$")
        actual = hashlib.scrypt(p.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(parallel))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError): return False
def totp(secret, at=None):
    key = base64.b32decode(secret)
    counter = int((now() if at is None else at) / 30).to_bytes(8, "big")
    raw = hmac.new(key, counter, hashlib.sha1).digest()
    offset = raw[-1] & 15
    return str((int.from_bytes(raw[offset:offset+4], "big") & 0x7fffffff) % 1000000).zfill(6)
def verify_totp(secret, code):
    code = re.sub(r"[\s-]", "", code or "")
    return bool(re.fullmatch(r"[0-9]{6}", code)) and any(
        hmac.compare_digest(totp(secret, now() + shift), code) for shift in (-30, 0, 30))
def totp_clock_drift(secret, code):
    code = re.sub(r"[\s-]", "", code or "")
    if not re.fullmatch(r"[0-9]{6}", code): return None
    current = now()
    for steps in range(2, 21):
        for direction in (-1, 1):
            candidate_time = current + direction * steps * 30
            if candidate_time >= 0 and hmac.compare_digest(totp(secret, candidate_time), code):
                return direction * steps * 30
    return None
def totp_qr(uri):
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
        image = qrcode.make(uri, image_factory=SvgPathImage)
        return '<img class="totp-qr" alt="QR-код для застосунку автентифікації" src="data:image/svg+xml;base64,' + base64.b64encode(image.to_string()).decode() + '">'
    except ImportError:
        return ""
def smtp_ready():
    return all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"))
def mail(recipient, subject, body, support_request_id=None):
    if not DEMO_MODE:
        if not smtp_ready():
            raise RuntimeError("SMTP не налаштовано")
        msg = EmailMessage()
        msg["From"] = os.environ["SMTP_FROM"]
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)
        host = os.environ["SMTP_HOST"]
        port = int(os.getenv("SMTP_PORT", "587"))
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as server:
                server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                server.send_message(msg)
    with db() as c:
        c.execute("INSERT INTO mail_outbox(recipient,subject,body,created_at,support_request_id) VALUES(?,?,?,?,?)",
                  (recipient, subject, body if DEMO_MODE else "", now(), support_request_id))
def login_alert_body(ip):
    return ("Вітаємо!\n\nХтось 5 разів ввів неправильний логін або пароль вашого акаунта Forma. "
            "Для захисту вхід до акаунта тимчасово заблоковано на 15 хвилин.\n"
            f"Час: {moment(now())}. Адреса з’єднання: {ip}.\n\n"
            "Якщо це були ви, зачекайте 15 хвилин і спробуйте знову або відновіть пароль на сайті.\n"
            "Якщо це були не ви і ваш акаунт намагаються зламати, змініть пароль та "
            f"напишіть у підтримку через цю сторінку: {url('/support')}\n\nForma")
async def verify_turnstile(token, ip, action="register"):
    if not TURNSTILE_SECRET_KEY or not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip})
            response.raise_for_status()
            result = response.json()
        return (result.get("success") is True and result.get("action") == action
                and result.get("hostname") == urllib.parse.urlparse(BASE_URL).hostname)
    except (httpx.HTTPError, ValueError):
        return False
def captcha_provider():
    if CAPTCHA_PROVIDER in ("image","hcaptcha","turnstile"): return CAPTCHA_PROVIDER
    return "hcaptcha" if HCAPTCHA_SITE_KEY or HCAPTCHA_SECRET_KEY else "turnstile"
def captcha_ready():
    if captcha_provider()=="image": return Image is not None
    if captcha_provider()=="hcaptcha":
        hostname=urllib.parse.urlparse(HCAPTCHA_ORIGIN or BASE_URL).hostname
        return bool(HCAPTCHA_SITE_KEY and HCAPTCHA_SECRET_KEY and hostname not in ("localhost","127.0.0.1","::1"))
    return bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
def captcha_setup_notice():
    if captcha_provider()=="image": return "Для CAPTCHA із словами встановіть Pillow: python -m pip install -r backend/requirements.txt."
    if captcha_provider()=="hcaptcha":
        if not HCAPTCHA_SITE_KEY or not HCAPTCHA_SECRET_KEY:
            return "hCaptcha ще не налаштовано. Додайте sitekey і secret key у backend/.env."
        return "hCaptcha не працює на localhost або 127.0.0.1. Налаштуйте HCAPTCHA_ORIGIN з локальною доменною назвою."
    return "Cloudflare Turnstile ще не налаштовано. Додайте два ключі у backend/.env."
def captcha_widget(action):
    if captcha_provider()=="image":
        return (f'<div class="image-captcha"><p>Введіть два слова з картинки через пробіл</p>'
                f'<img src="/captcha/image?purpose={esc(action)}" alt="Зображення з двома словами для перевірки" width="480" height="150" data-captcha-image="{esc(action)}">'
                f'<button type="button" class="secondary smallbtn" data-captcha-refresh="{esc(action)}">Інша картинка</button>'
                +field("Слова з картинки","captcha_text",autocomplete="off")+'</div>')
    if captcha_provider()=="hcaptcha":
        return f'<div class="h-captcha" data-sitekey="{esc(HCAPTCHA_SITE_KEY)}"></div>' if HCAPTCHA_SITE_KEY else ""
    return f'<div class="cf-turnstile" data-sitekey="{esc(TURNSTILE_SITE_KEY)}" data-action="{esc(action)}"></div>' if TURNSTILE_SITE_KEY else ""
def captcha_script():
    if captcha_provider()=="image":
        return '''<script>document.addEventListener("click",function(event){const button=event.target.closest("[data-captcha-refresh]");if(!button)return;const purpose=button.dataset.captchaRefresh;const image=document.querySelector('[data-captcha-image="'+purpose+'"]');if(image){image.src="/captcha/image?purpose="+encodeURIComponent(purpose)+"&v="+Date.now();const input=document.querySelector('input[name="captcha_text"]');if(input)input.value="";}});</script>'''
    source="https://js.hcaptcha.com/1/api.js?hl=uk" if captcha_provider()=="hcaptcha" else "https://challenges.cloudflare.com/turnstile/v0/api.js"
    return f'<script src="{source}" async defer></script>'
def login_captcha_ready():
    return captcha_provider() in ("hcaptcha","turnstile") and captcha_ready()
def login_captcha_widget():
    return captcha_widget("login")
def login_captcha_script():
    return captcha_script()
async def verify_hcaptcha(token, ip):
    if not HCAPTCHA_SITE_KEY or not HCAPTCHA_SECRET_KEY or not token: return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response=await client.post("https://api.hcaptcha.com/siteverify",data={"secret":HCAPTCHA_SECRET_KEY,"sitekey":HCAPTCHA_SITE_KEY,"response":token,"remoteip":ip})
            response.raise_for_status()
            return response.json().get("success") is True
    except (httpx.HTTPError, ValueError): return False
async def verify_captcha(data, ip, action, s=None):
    if captcha_provider()=="image": return verify_image_captcha(s,data.get("captcha_text",""),action)
    if captcha_provider()=="hcaptcha": return await verify_hcaptcha(data.get("h-captcha-response",""),ip)
    return await verify_turnstile(data.get("cf-turnstile-response",""),ip,action)
CAPTCHA_WORDS="ВЕСНА МРІЯ КНИГА ДЕРЕВО РІЧКА СОНЦЕ КВІТКА ЗІРКА ХМАРА МУЗИКА ШКОЛА ДРУЖБА ПЛАНЕТА ЯБЛУКО КАВА МОРЕ ПТАШКА ВІТЕР ДОРОГА МІСТО ОСТРІВ САДОК РАНОК ВЕЧІР ЛІТО ОСІНЬ ЗИМА КОШИК ГОДИНА ЗНАННЯ УСМІШКА ПОДОРОЖ РОБОТА ПЕРЕМОГА МАЙСТЕРНЯ ОЛІВЕЦЬ ПАПІР СЛОВО ГОЛОС ТЕПЛО ВОГОНЬ ДОЛОНЯ ВЕСЕЛКА ДЗВІНОК СТЕЖКА КАЛИНА ВИШНЯ ПОЛЕ НЕБО КРАЇНА СВІТЛО ТИША ДЖЕРЕЛО КАМІНЬ ГОРИ СКАРБ ПАРУС МІСЯЦЬ ЗОРІ КРОКУС ПОЛУНИЦЯ МАЛЮНОК ПОДАРУНОК ПРИГОДА ЛАСТІВКА".split()
def normalized_captcha_words(value): return " ".join((value or "").strip().upper().split())[:80]
def captcha_answer_hash(answer):
    return hmac.new(CAPTCHA_PEPPER,normalized_captcha_words(answer).encode(),hashlib.sha256).hexdigest()
def render_captcha_image(answer):
    image=Image.new("RGB",(480,150),(247,249,242))
    draw=ImageDraw.Draw(image)
    for _ in range(11):
        x1,y1=secrets.randbelow(480),secrets.randbelow(150)
        x2,y2=secrets.randbelow(480),secrets.randbelow(150)
        draw.line((x1,y1,x2,y2),fill=(175,200,181),width=1)
    for _ in range(200):
        x,y=secrets.randbelow(480),secrets.randbelow(150)
        draw.point((x,y),fill=(140,170,151))
    font_path=next((p for p in ("C:/Windows/Fonts/arialbd.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if Path(p).exists()),None)
    font=ImageFont.truetype(font_path,43) if font_path else ImageFont.load_default(size=36)
    first,second=answer.split()
    draw.text((26+secrets.randbelow(16),8+secrets.randbelow(9)),first,font=font,fill=(28,65,54),stroke_width=1)
    draw.text((125+secrets.randbelow(16),75+secrets.randbelow(9)),second,font=font,fill=(35,74,64),stroke_width=1)
    data=io.BytesIO()
    image.save(data,format="PNG")
    return data.getvalue()
def verify_image_captcha(s,answer,purpose):
    if not s or purpose not in ("register","reset") or not answer: return False
    with db() as c:
        challenge=c.execute("SELECT answer_hash,expires_at FROM captcha_challenges WHERE token_hash=? AND purpose=?",(s["token_hash"],purpose)).fetchone()
        c.execute("DELETE FROM captcha_challenges WHERE token_hash=? AND purpose=?",(s["token_hash"],purpose))
    return bool(challenge and challenge["expires_at"]>now() and hmac.compare_digest(challenge["answer_hash"],captcha_answer_hash(answer)))
@app.get("/captcha/image")
def captcha_image(req: Request, purpose: str=""):
    if captcha_provider()!="image" or not captcha_ready(): return HTMLResponse("CAPTCHA недоступна",status_code=503)
    if purpose not in ("register","reset"): return HTMLResponse("Невірний тип CAPTCHA",status_code=400)
    s,raw=ensure_session(req)
    first=secrets.choice(CAPTCHA_WORDS)
    second=secrets.choice(CAPTCHA_WORDS)
    answer=first+" "+second
    with db() as c:
        c.execute("INSERT OR REPLACE INTO captcha_challenges(token_hash,purpose,answer_hash,expires_at) VALUES(?,?,?,?)",
                  (s["token_hash"],purpose,captcha_answer_hash(answer),now()+300))
    response=Response(render_captcha_image(answer),media_type="image/png",headers={"Cache-Control":"no-store, max-age=0","X-Content-Type-Options":"nosniff"})
    return cookie(response,raw) if raw else response
def issue_token(user_id, purpose, ttl=1800):
    raw = secrets.token_urlsafe(32)
    with db() as c:
        c.execute("DELETE FROM tokens WHERE user_id=? AND purpose=?", (user_id, purpose))
        c.execute("INSERT INTO tokens VALUES(?,?,?,?)", (digest(raw), user_id, purpose, now()+ttl))
    return raw
def consume_token(raw, purpose):
    with db() as c:
        row = c.execute("SELECT user_id FROM tokens WHERE token_hash=? AND purpose=? AND expires_at>?",
                        (digest(raw), purpose, now())).fetchone()
        if row: c.execute("DELETE FROM tokens WHERE token_hash=?", (digest(raw),))
        return row["user_id"] if row else None
def log(email, ip, result):
    with db() as c:
        c.execute("INSERT INTO login_log(email,ip,result,happened_at) VALUES(?,?,?,?)",
                  (email, ip, result, now()))
        c.execute("INSERT INTO audit_log(happened_at,actor_email,target_email,ip,event,details) VALUES(?,?,?,?,?,?)",
                  (now(), email, email, ip, "login_"+result, ""))
def audit(event, actor="", target="", ip="", details=""):
    with db() as c:
        c.execute("INSERT INTO audit_log(happened_at,actor_email,target_email,ip,event,details) VALUES(?,?,?,?,?,?)",
                  (now(), actor, target, ip, event, details))
EVENT_LABELS={
    "account_registered":"Реєстрація", "account_activated":"Активація email",
    "login_success":"Успішний вхід", "login_failure":"Невдала спроба входу",
    "login_lockout":"Тимчасове блокування після 5 спроб",
    "login_alert_sent":"Лист про підозрілий вхід надіслано",
    "login_alert_delivery_failed":"Не вдалося надіслати лист про підозрілий вхід",
    "support_request":"Звернення до підтримки",
    "support_updated":"Звернення до підтримки оновлено",
    "support_reply_sent":"Підтримка надіслала відповідь",
    "support_reply_failed":"Не вдалося надіслати відповідь підтримки",
    "support_account_unblocked":"Підтримка розблокувала акаунт",
    "support_account_blocked":"Підтримка заблокувала акаунт",
    "support_account_deleted":"Підтримка видалила акаунт",
    "login_blocked":"Вхід заблоковано", "login_ip_limit":"Обмеження за IP",
    "login_inactive":"Акаунт не активовано", "login_2fa_pending":"Очікування 2FA",
    "login_2fa_failure":"Невірний код 2FA", "login_success_2fa":"Успішний вхід із 2FA",
    "two_factor_lockout":"Блокування після помилок 2FA",
    "login_success_google":"Вхід через Google", "login_2fa_pending_google":"Google: очікування 2FA",
    "login_blocked_google":"Google: вхід заблоковано", "logout":"Вихід",
    "captcha_failed":"CAPTCHA відхилено", "csrf_rejected":"CSRF відхилено",
    "two_factor_enabled":"2FA увімкнено", "two_factor_disabled":"2FA вимкнено",
    "two_factor_disable_failure":"Невдала спроба вимкнути 2FA",
    "password_reset_requested":"Запит відновлення пароля", "password_reset_unknown":"Запит для невідомої адреси",
    "password_reset_completed":"Пароль змінено", "password_reset_2fa_failed":"Невірний код 2FA для відновлення пароля",
    "google_linked":"Google-акаунт підключено",
    "admin_blocked":"Адміністратор заблокував акаунт", "admin_unblocked":"Адміністратор розблокував акаунт",
    "admin_account_deleted":"Адміністратор видалив акаунт",
    "admin_created":"Налаштовано адміністратора",
    "profile_updated":"Профіль оновлено", "username_changed":"Логін змінено",
    "other_sessions_revoked":"Інші сеанси завершено",
}
def event_label(event): return EVENT_LABELS.get(event, event.replace("_", " "))
def client_ip(req): return req.client.host if req.client else "unknown"
def local_pc_ip():
    """Find the IPv4 address used by this computer's default network route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # UDP connect selects an interface without sending a packet.
            sock.connect(("1.1.1.1", 80))
            address=sock.getsockname()[0]
            return address if address != "0.0.0.0" else None
    except OSError:
        return None
def browser_label(user_agent):
    agent=(user_agent or "").lower()
    browser=("Edge" if "edg/" in agent else "Firefox" if "firefox/" in agent else
             "Chrome" if "chrome/" in agent else "Safari" if "safari/" in agent else "Браузер")
    device=("Android" if "android" in agent else "iPhone" if "iphone" in agent else
            "iPad" if "ipad" in agent else "Windows" if "windows" in agent else
            "Mac" if "macintosh" in agent else "Linux" if "linux" in agent else "Невідомий пристрій")
    return browser+" · "+device
def request_agent(req): return req.headers.get("user-agent", "")[:255]
def session(req):
    raw = req.cookies.get("sid", "")
    if not raw: return None
    with db() as c:
        row=c.execute("SELECT * FROM sessions WHERE token_hash=? AND expires_at>?",
                      (digest(raw), now())).fetchone()
        if row and row["user_id"] and row["last_seen_at"]<now()-60:
            c.execute("UPDATE sessions SET last_seen_at=?,ip=?,user_agent=? WHERE token_hash=?",
                      (now(),client_ip(req),request_agent(req),row["token_hash"]))
        return row
def user_for(s):
    if not s or not s["user_id"]: return None
    with db() as c: return c.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
def ensure_session(req):
    existing = session(req)
    if existing: return existing, None
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db() as c:
        c.execute("INSERT INTO sessions(token_hash,csrf,expires_at,created_at,last_seen_at,ip,user_agent) VALUES(?,?,?,?,?,?,?)",
                  (digest(raw),csrf,now()+86400,now(),now(),client_ip(req),request_agent(req)))
    return session_from_raw(raw), raw
def session_from_raw(raw):
    with db() as c: return c.execute("SELECT * FROM sessions WHERE token_hash=?", (digest(raw),)).fetchone()
def rotate_session(s, user_id=None, pending=0, req=None):
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    ip=client_ip(req) if req else s["ip"]
    agent=request_agent(req) if req else s["user_agent"]
    with db() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (s["token_hash"],))
        c.execute("INSERT INTO sessions(token_hash,user_id,csrf,pending_2fa,expires_at,created_at,last_seen_at,ip,user_agent) VALUES(?,?,?,?,?,?,?,?,?)",
                  (digest(raw),user_id,csrf,pending,now()+86400,now(),now(),ip,agent))
    return raw
def cookie(response, raw):
    response.set_cookie("sid", raw, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=86400)
    return response
def page(title, body, s, flash=""):
    u = user_for(s)
    signed = bool(u and not s["pending_2fa"])
    nav = '<a href="/">Тести</a>'
    if signed:
        nav += '<a href="/profile">Профіль</a>'
        if u["role"] == "admin": nav += '<a href="/admin">Адміністрування</a>'
        nav += f'<form action="/logout" method="post"><input type="hidden" name="csrf" value="{esc(s["csrf"])}"><button>Вийти</button></form>'
    else: nav += '<a href="/login">Вхід</a><a href="/register">Реєстрація</a>'
    nav += '<a href="/support">Підтримка</a>'
    if DEMO_MODE: nav += '<a href="/dev-mail">Листи для демонстрації</a>'
    notice = f'<div class="notice">{esc(flash)}</div>' if flash else ""
    auth_titles={"Реєстрація","Вхід","Вхід через Google","Підтвердження 2FA","Налаштування 2FA","Відновлення пароля","Новий пароль",
                 "Перевірте пошту","Активація","Пароль оновлено","Помилка входу","Вхід обмежено","Потрібна активація",
                 "Ключ прострочено","Недійсне посилання","Помилка Google","Адреси не збігаються","Google-акаунт уже підключено",
                 "Потрібне підтвердження","2FA вже увімкнено","Налаштування профілю","Підтримка"}
    main_class="admin-main" if title=="Панель адміністратора" else "security-main" if title=="Керування 2FA" else "auth-main" if title in auth_titles else ""
    auth_mark='<span class="auth-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><rect x="7" y="13" width="18" height="14" rx="4" stroke="currentColor" stroke-width="2.4"/><path d="M11 13V9a5 5 0 0 1 10 0v4" stroke="currentColor" stroke-width="2.4"/><circle cx="16" cy="20" r="2" fill="currentColor"/></svg></span>' if main_class=="auth-main" else ""
    subtitles={"Реєстрація":"Створіть акаунт і захистіть його з першого входу.",
               "Вхід":"Раді бачити вас знову у Forma.",
               "Підтвердження 2FA":"Ще один крок для безпечного входу.",
               "Відновлення пароля":"Ми допоможемо повернути доступ до акаунта.",
               "Новий пароль":"Створіть новий надійний пароль для акаунта.",
               "Налаштування профілю":"Ваші особисті дані та логін для входу.",
               "Підтримка":"Повідомте нам, якщо помітили підозрілу активність."}
    subtitle=f'<p class="auth-subtitle">{esc(subtitles[title])}</p>' if main_class=="auth-main" and title in subtitles else ""
    return HTMLResponse(f'''<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Forma</title><link rel="stylesheet" href="/style.css"></head><body><header><strong><a href="/">forma<span>.</span></a></strong><nav>{nav}</nav></header><main class="{main_class}"><div class="eyebrow">FORMA · БЕЗПЕКА АКАУНТА</div>{auth_mark}<h1>{esc(title)}</h1>{subtitle}{notice}{body}</main><footer>Forma · Навчальний проєкт</footer></body></html>''')
def form(body, action, s):
    return f'<form action="{action}" method="post"><input type="hidden" name="csrf" value="{esc(s["csrf"])}">{body}</form>'
def field(label, name, typ="text", required=True, value="", autocomplete=""):
    return f'<label>{esc(label)}<input name="{esc(name)}" type="{typ}" value="{esc(value)}" {"required" if required else ""} autocomplete="{esc(autocomplete)}"></label>'
def revealable_password_field(label, name):
    input_id=f'register-{name}'
    accessible_name="підтвердження пароля" if name=="password_confirm" else "пароль"
    return (f'<div class="password-field"><label for="{input_id}">{esc(label)}</label>'
            f'<div class="password-input-wrap"><input id="{input_id}" name="{esc(name)}" type="password" required autocomplete="new-password">'
            f'<button type="button" class="password-visibility" data-password-toggle="{input_id}" aria-label="Показати {accessible_name}" aria-pressed="false" title="Показати пароль">'
            '<svg class="eye-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>'
            '<svg class="eye-closed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden><path d="M3 3l18 18M9.8 5.8A11.7 11.7 0 0 1 12 5.5c6.5 0 10 6.5 10 6.5a13 13 0 0 1-3.1 3.7M6.4 6.5C3.5 8.1 2 12 2 12s3.5 6.5 10 6.5c1.2 0 2.4-.2 3.4-.6M10 10a3 3 0 0 0 4 4"/></svg>'
            '</button></div></div>')
def redirect(path, raw=None):
    r = RedirectResponse(path, status_code=303)
    return cookie(r, raw) if raw else r
async def data(req):
    content = (await req.body()).decode("utf-8", "replace")
    return {k:v[-1] for k,v in urllib.parse.parse_qs(content, keep_blank_values=True).items()}
def csrf_ok(s, d): return s and hmac.compare_digest(s["csrf"], d.get("csrf", ""))
def auth(s):
    u = user_for(s)
    return u if u and not s["pending_2fa"] and not u["blocked"] and u["locked_until"]<=now() else None
def moment(t): return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

@app.get("/style.css")
def style():
    from fastapi.responses import Response
    return Response((ROOT / "style.css").read_text(encoding="utf-8"), media_type="text/css")
@app.get("/register.js")
def register_script():
    from fastapi.responses import Response
    return Response((ROOT / "register.js").read_text(encoding="utf-8"), media_type="application/javascript")
@app.get("/session")
def current_session(req: Request):
    s=session(req); u=auth(s)
    if not u: return JSONResponse({"message":"Потрібен вхід"},status_code=401)
    with db() as c:
        recent=c.execute("SELECT happened_at,event,ip FROM audit_log WHERE target_email=? ORDER BY id DESC LIMIT 5",(u["email"],)).fetchall()
        active=c.execute("SELECT token_hash,created_at,last_seen_at,ip,user_agent FROM sessions WHERE user_id=? AND pending_2fa=0 AND expires_at>? ORDER BY last_seen_at DESC,created_at DESC",(u["id"],now())).fetchall()
    events=[{"at":x["happened_at"],"event":event_label(x["event"]),"ip":x["ip"]} for x in recent]
    pc_ip=local_pc_ip() if any(x["ip"] in ("127.0.0.1","::1") for x in active) else None
    sessions=[{"current":hmac.compare_digest(x["token_hash"],s["token_hash"]),"device":browser_label(x["user_agent"]),
               "ip":x["ip"] or "Невідомо",
               "display_ip":pc_ip if x["ip"] in ("127.0.0.1","::1") and pc_ip else x["ip"] or "Невідомо",
               "local_pc_ip":bool(x["ip"] in ("127.0.0.1","::1") and pc_ip),
               "created_at":x["created_at"],"last_seen_at":x["last_seen_at"]} for x in active]
    return JSONResponse({"user":{"id":u["id"],"username":u["username"],"display_name":u["display_name"],
                                 "birth_date":u["birth_date"],"bio":u["bio"],"email":u["email"],"role":u["role"],
                                 "active":bool(u["active"]),"totp_enabled":bool(u["totp_secret"]),
                                 "google_connected":bool(u["google_sub"]),"google_available":bool(GOOGLE_ID and GOOGLE_SECRET),
                                 "has_password":bool(u["password_hash"])},"csrf":s["csrf"],"recent_events":events,
                         "sessions":sessions})
@app.post("/sessions/revoke-others")
async def revoke_other_sessions(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or not csrf_ok(s,d): return HTMLResponse("Невірний запит",status_code=403)
    with db() as c:
        removed=c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?",(u["id"],s["token_hash"])).rowcount
    audit("other_sessions_revoked",actor=u["email"],target=u["email"],ip=client_ip(req),details=f"{removed} сеансів")
    return redirect("/?view=profile&sessions=revoked")
@app.get("/")
def home(req: Request):
    s, raw = ensure_session(req)
    body = '''<p class="lead">Реєстрація, контроль доступу, захист входу та відновлення пароля в одному застосунку.</p><div class="grid"><article><h2>Реєстрація</h2><p>Політика пароля, CAPTCHA й активація адреси електронної пошти.</p></article><article><h2>Безпечний вхід</h2><p>Тимчасове блокування, журнал спроб і TOTP двофакторна перевірка.</p></article><article><h2>Керування</h2><p>Власний профіль, ролі користувача й адміністратора, скидання пароля.</p></article></div><p><a class="button" href="/register">Створити обліковий запис</a></p>'''
    r = page("Безпечне управління обліковими записами", body, s)
    return cookie(r, raw) if raw else r
@app.get("/register")
def register_page(req: Request, captcha_host: str=""):
    if captcha_provider()=="hcaptcha" and HCAPTCHA_ORIGIN and captcha_host!="1":
        return redirect(HCAPTCHA_ORIGIN+"/register?captcha_host=1")
    s, raw = ensure_session(req)
    r = page("Реєстрація", register_body(s), s)
    return cookie(r, raw) if raw else r
def register_body(s, email="", error=""):
    notice = f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    if not smtp_ready() and not DEMO_MODE:
        notice += '<div class="notice error">Надсилання пошти ще не налаштовано. Заповніть SMTP у backend/.env.</div>'
    if not captcha_ready():
        notice += f'<div class="notice error">{esc(captcha_setup_notice())}</div>'
    fields = field("Email", "email", "email", value=email, autocomplete="email") + revealable_password_field("Пароль", "password")
    fields += '<ul id="password-rules" class="password-rules" aria-live="polite"><li data-rule="length">Щонайменше 8 символів</li><li data-rule="upper">Велика літера</li><li data-rule="lower">Мала літера</li><li data-rule="digit">Цифра</li><li data-rule="special">Спеціальний символ</li></ul>'
    fields += revealable_password_field("Підтвердіть пароль", "password_confirm")
    fields += '<p id="password-match" class="password-match" aria-live="polite"></p>'
    fields += captcha_widget("register") + f'<button id="register-submit" {"" if (smtp_ready() or DEMO_MODE) and captcha_ready() else "disabled"}>Зареєструватися</button>'
    return notice + form(fields, "/register", s) + f'<p class="auth-switch">Уже маєте акаунт? <a href="{esc(url("/login"))}">Увійти</a></p>'+captcha_script()+'<script src="/register.js" defer></script>'
@app.post("/register")
async def register(req: Request):
    s = session(req); d = await data(req)
    if not csrf_ok(s,d):
        audit("csrf_rejected",target=d.get("email","").strip().lower(),ip=client_ip(req),details="register")
        return HTMLResponse("Невірний CSRF токен",status_code=403)
    email = d.get("email", "").strip().lower(); p = d.get("password", "")
    error = password_error(p)
    if p != d.get("password_confirm", ""): error = "Паролі не збігаються."
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email): error = "Вкажіть коректний email."
    if error: return page("Реєстрація",register_body(s,email,error),s)
    if not (smtp_ready() or DEMO_MODE): return page("Реєстрація",register_body(s,email,"Надсилання пошти не налаштовано."),s)
    if not captcha_ready():
        return page("Реєстрація",register_body(s,email,"CAPTCHA не налаштовано."),s)
    if not await verify_captcha(d, client_ip(req),"register",s):
        audit("captcha_failed",target=email,ip=client_ip(req))
        return page("Реєстрація",register_body(s,email,"CAPTCHA не підтверджено. Спробуйте ще раз."),s)
    try:
        with db() as c:
            uid=next_user_id(c)
            c.execute("INSERT INTO users(id,email,password_hash,created_at) VALUES(?,?,?,?)",(uid,email,hash_password(p),now()))
    except sqlite3.IntegrityError:
        return page("Реєстрація",register_body(s,email,"Цю адресу вже зареєстровано."),s)
    token=issue_token(uid,"activation",1800)
    try:
        mail(email,"Активація облікового запису",f"Перейдіть за посиланням протягом 30 хвилин:\n{url('/activate?token='+token)}")
    except (OSError, smtplib.SMTPException, RuntimeError):
        with db() as c:
            c.execute("DELETE FROM tokens WHERE user_id=?",(uid,))
            c.execute("DELETE FROM users WHERE id=?",(uid,))
        return page("Реєстрація",register_body(s,email,"Не вдалося надіслати лист. Перевірте SMTP у backend/.env і спробуйте ще раз."),s)
    audit("account_registered",actor=email,target=email,ip=client_ip(req))
    return page("Перевірте пошту",f'<p>Ми надіслали одноразове посилання активації. Воно діє 30 хвилин.</p><a class="button" href="{esc(url("/login"))}">До входу</a>',s)
@app.get("/activate")
def activate(req: Request, token: str=""):
    s, raw=ensure_session(req); uid=consume_token(token,"activation") if token else None
    if uid:
        with db() as c:
            c.execute("UPDATE users SET active=1 WHERE id=?",(uid,))
            activated=c.execute("SELECT email FROM users WHERE id=?",(uid,)).fetchone()
        if activated: audit("account_activated",actor=activated["email"],target=activated["email"],ip=client_ip(req))
    r=page("Активація",'<p>Обліковий запис активовано.</p><a class="button" href="/login">Увійти</a>' if uid else '<p>Посилання недійсне або термін дії минув.</p>',s)
    return cookie(r,raw) if raw else r
@app.get("/login")
def login_page(req: Request,captcha_host: str=""):
    if captcha_provider()=="hcaptcha" and HCAPTCHA_ORIGIN and captcha_host!="1":
        return redirect(HCAPTCHA_ORIGIN+"/login?captcha_host=1")
    s,raw=ensure_session(req)
    body=login_body(s)
    r=page("Вхід",body,s); return cookie(r,raw) if raw else r
def login_body(s, identifier="", error=""):
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    if not login_captcha_ready():
        notice+='<div class="notice error">CAPTCHA для входу не налаштовано. Перевірте ключі hCaptcha у backend/.env.</div>'
    fields=field("Email або логін","email",value=identifier,autocomplete="username")+field("Пароль","password","password",autocomplete="current-password")
    fields+=login_captcha_widget()+f'<button {"" if login_captcha_ready() else "disabled"}>Увійти</button>'
    body=notice+form(fields,"/login",s)+login_captcha_script()
    body+='<p><a class="button secondary" href="/google/start">Увійти через Google</a></p>'
    if not GOOGLE_ID or not GOOGLE_SECRET: body+='<p class="small">Для Google-входу заповніть GOOGLE_CLIENT_ID та GOOGLE_CLIENT_SECRET у backend/.env.</p>'
    else: body+='<p class="small">Маєте акаунт Forma з цією поштою? Спочатку увійдіть паролем і підключіть Google у профілі.</p>'
    body+='<p><a href="/forgot">Забули пароль?</a></p>'
    body+='<p class="auth-switch">Ще немає акаунта? <a href="/register">Зареєструватися</a></p>'
    return body
SUPPORT_CATEGORIES={"security":"Підозріла активність","login":"Проблема зі входом","two_factor":"Проблема з 2FA","other":"Інше"}
SUPPORT_STATUSES={"new":"Нове","in_progress":"У роботі","resolved":"Вирішено"}
def support_body(s, email="", error="", category="security", subject="", message="", steps=""):
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    fields=field("Ваш email","email","email",value=email,autocomplete="email")
    options=''.join(f'<option value="{key}" {"selected" if category==key else ""}>{label}</option>' for key,label in SUPPORT_CATEGORIES.items())
    fields+=f'<label>Тип проблеми<select name="category">{options}</select></label>'
    fields+=field("Коротка тема","subject",value=subject)
    fields+=f'<label>Що сталося?<textarea name="message" required minlength="10" maxlength="2000" rows="6" placeholder="Опишіть помилку та що ви побачили">{esc(message)}</textarea></label>'
    fields+=f'<label>Як повторити проблему? <span class="small">(необов’язково)</span><textarea name="steps" maxlength="1000" rows="4" placeholder="Які дії ви виконали перед проблемою?">{esc(steps)}</textarea></label>'
    fields+='<button>Надіслати звернення</button>'
    return notice+'<p class="small">Опишіть проблему якомога точніше. Не надсилайте пароль чи коди 2FA.</p>'+form(fields,"/support",s)
@app.get("/support")
def support_page(req: Request):
    s,raw=ensure_session(req)
    u=user_for(s)
    r=page("Підтримка",support_body(s,u["email"] if u else ""),s)
    return cookie(r,raw) if raw else r
@app.post("/support")
async def support_submit(req: Request):
    s=session(req); d=await data(req)
    if not csrf_ok(s,d): return HTMLResponse("Невірний CSRF токен",status_code=403)
    email=d.get("email","").strip().lower()
    category=d.get("category","")
    subject=d.get("subject","").strip()
    message=d.get("message","").strip()
    steps=d.get("steps","").strip()
    draft=lambda error: support_body(s,email,error,category,subject,message,steps)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email):
        return page("Підтримка",draft("Вкажіть коректний email."),s)
    if category not in SUPPORT_CATEGORIES:
        return page("Підтримка",draft("Виберіть тип проблеми."),s)
    if not 5<=len(subject)<=120:
        return page("Підтримка",draft("Тема має містити від 5 до 120 символів."),s)
    if not 10<=len(message)<=2000:
        return page("Підтримка",draft("Повідомлення має містити від 10 до 2000 символів."),s)
    if len(steps)>1000:
        return page("Підтримка",draft("Кроки відтворення надто довгі."),s)
    ip=client_ip(req)
    with db() as c:
        recent=c.execute("SELECT count(*) FROM support_requests WHERE ip=? AND created_at>?",(ip,now()-900)).fetchone()[0]
        if recent>=3:
            return page("Підтримка",draft("Забагато звернень. Спробуйте через 15 хвилин."),s)
        c.execute("INSERT INTO support_requests(email,category,subject,message,steps,ip,created_at) VALUES(?,?,?,?,?,?,?)",(email,category,subject,message,steps,ip,now()))
    audit("support_request",actor=email,target=email,ip=ip)
    return page("Підтримка",'<div class="notice" role="status">Звернення надіслано. Дякуємо за подробиці.</div><p><a href="/login">До входу</a></p>',s)
@app.post("/login")
async def login(req: Request):
    s=session(req); d=await data(req)
    if not csrf_ok(s,d):
        audit("csrf_rejected",target=d.get("email","").strip().lower(),ip=client_ip(req),details="login")
        return HTMLResponse("Невірний CSRF токен",status_code=403)
    identifier=d.get("email","").strip().lower(); ip=client_ip(req)
    if not login_captcha_ready():
        return page("Вхід",login_body(s,identifier,"CAPTCHA для входу не налаштовано."),s)
    if not await verify_captcha(d,ip,"login",s):
        audit("captcha_failed",target=identifier,ip=ip,details="login")
        return page("Вхід",login_body(s,identifier,"Підтвердіть CAPTCHA перед входом."),s)
    alert_email=None
    with db() as c:
        u=c.execute("SELECT * FROM users WHERE email=? OR lower(username)=?",(identifier,identifier)).fetchone()
        email=u["email"] if u else identifier
        failures=c.execute("SELECT count(*) FROM login_log WHERE ip=? AND result='failure' AND happened_at>?",(ip,now()-900)).fetchone()[0]
        if failures>=20:
            log(email,ip,"ip_limit")
            return page("Вхід обмежено",'<p>Забагато спроб із цієї адреси. Спробуйте через 15 хвилин.</p>',s)
        if u and (u["blocked"] or u["locked_until"]>now()):
            log(email,ip,"blocked")
            return page("Вхід обмежено",'<p>Обліковий запис заблоковано. Спробуйте пізніше або зверніться до адміністратора.</p>',s)
        if not u or not verify_password(d.get("password",""),u["password_hash"]):
            log(email,ip,"failure")
            if u:
                n=u["failed_count"]+1
                c.execute("UPDATE users SET failed_count=?,locked_until=? WHERE id=?",(0 if n>=5 else n,now()+900 if n>=5 else 0,u["id"]))
                if n>=5:
                    c.execute("INSERT INTO audit_log(happened_at,actor_email,target_email,ip,event,details) VALUES(?,?,?,?,?,?)",
                              (now(),email,email,ip,"login_lockout","5 невдалих спроб"))
                    alert_email=email
            failed=True
        else:
            failed=False
            c.execute("UPDATE users SET failed_count=0,locked_until=0 WHERE id=?",(u["id"],))
    if failed:
        if alert_email:
            try:
                mail(alert_email,"Попередження про спроби входу до Forma",login_alert_body(ip))
                audit("login_alert_sent",target=alert_email,ip=ip)
            except (OSError, smtplib.SMTPException, RuntimeError, ValueError):
                audit("login_alert_delivery_failed",target=alert_email,ip=ip)
        return page("Помилка входу",'<p>Невірні облікові дані. Після 5 помилок обліковий запис блокується на 15 хвилин.</p><a href="/login">Назад</a>',s)
    if not u["active"]:
        log(email,ip,"inactive")
        return page("Потрібна активація",'<p>Спочатку активуйте обліковий запис за посиланням у листі.</p>',s)
    if u["totp_secret"]:
        raw=rotate_session(s,u["id"],1,req)
        log(email,ip,"2fa_pending")
        return redirect("/2fa",raw)
    raw=rotate_session(s,u["id"],req=req)
    log(email,ip,"success")
    return redirect("/profile",raw)
@app.get("/2fa")
def two_factor_page(req: Request):
    s=session(req)
    if not s or not s["pending_2fa"]: return redirect("/login")
    return page("Підтвердження 2FA",two_factor_body(s),s)
def two_factor_body(s,error=""):
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    hint='<p class="small">Введіть код із запису Forma у застосунку. Якщо він не підходить, перевірте автоматичний час телефону та чи немає старого запису Forma.</p>'
    return notice+hint+form(field("Шестизначний код","code",autocomplete="one-time-code")+'<button>Підтвердити</button>',"/2fa",s)
@app.post("/2fa")
async def two_factor(req: Request):
    s=session(req); d=await data(req)
    if not csrf_ok(s,d) or not s["pending_2fa"]: return HTMLResponse("Невірний запит",status_code=403)
    u=user_for(s)
    with db() as c:
        recent=c.execute("SELECT count(*) FROM login_log WHERE email=? AND result='2fa_failure' AND happened_at>?",(u["email"] if u else "?",now()-900)).fetchone()[0]
    if recent>=5:
        with db() as c: c.execute("DELETE FROM sessions WHERE token_hash=?",(s["token_hash"],))
        return page("Вхід обмежено",'<p>Забагато помилок 2FA. Спробуйте через 15 хвилин.</p>',s)
    if not u or u["blocked"] or not verify_totp(u["totp_secret"],d.get("code","")):
        log(u["email"] if u else "?",client_ip(req),"2fa_failure")
        if recent==4:
            with db() as c:
                c.execute("UPDATE users SET locked_until=? WHERE id=?",(now()+900,u["id"]))
                c.execute("DELETE FROM sessions WHERE user_id=?",(u["id"],))
            audit("two_factor_lockout",target=u["email"],ip=client_ip(req),details="5 невдалих кодів")
        return page("Підтвердження 2FA",two_factor_body(s,"Невірний код. Спробуйте новий шестизначний код."),s)
    raw=rotate_session(s,u["id"],req=req)
    log(u["email"],client_ip(req),"success_2fa")
    return redirect("/profile",raw)
@app.post("/logout")
async def logout(req: Request):
    s=session(req); d=await data(req)
    if not csrf_ok(s,d): return HTMLResponse("Невірний CSRF токен",status_code=403)
    u=user_for(s)
    with db() as c: c.execute("DELETE FROM sessions WHERE token_hash=?",(s["token_hash"],))
    if u: audit("logout",actor=u["email"],target=u["email"],ip=client_ip(req))
    r=redirect("/"); r.delete_cookie("sid"); return r
@app.get("/profile")
def profile(req: Request):
    s=session(req); u=auth(s)
    if not u: return redirect("/login")
    return redirect("/?view=profile")
@app.get("/account/settings")
def profile_settings_page(req: Request, saved: str=""):
    s=session(req); u=auth(s)
    if not u: return redirect("/login")
    return page("Налаштування профілю",profile_settings_body(s,u,saved=saved),s)
def profile_settings_body(s,u,info_error="",login_error="",saved="",values=None,login_value=None):
    values=values or {"display_name":u["display_name"] or "", "birth_date":u["birth_date"] or "", "bio":u["bio"] or ""}
    notice='<div class="notice" role="status">Зміни збережено.</div>' if saved in ("profile","login") else ""
    info_notice=f'<div class="notice error" role="alert">{esc(info_error)}</div>' if info_error else ""
    login_notice=f'<div class="notice error" role="alert">{esc(login_error)}</div>' if login_error else ""
    info='<h2>Особисті дані</h2><p class="settings-help">Ці дані відображаються у вашому профілі. Дату народження бачите лише ви.</p>'
    info+=field("Відображуване ім’я","display_name",required=False,value=values["display_name"],autocomplete="name")
    info+=field("Дата народження","birth_date","date",required=False,value=values["birth_date"],autocomplete="bday")
    info+=f'<label>Про себе<textarea name="bio" rows="4" maxlength="240" placeholder="Коротко про себе">{esc(values["bio"])}</textarea></label>'
    info+='<p class="settings-help">До 240 символів. Це поле можна залишити порожнім.</p><button>Зберегти дані</button>'
    body=notice+info_notice+form(info,"/account/settings",s)
    if u["role"]=="admin":
        body+='<div class="settings-locked"><h2>Логін для входу</h2><p>Логін адміністратора <strong>admin</strong> закріплено за цим акаунтом.</p></div>'
    else:
        login='<h2>Логін для входу</h2><p class="settings-help">Від 3 до 30 символів: латинські літери, цифри, крапка, дефіс або підкреслення. Email теж залишиться способом входу.</p>'
        login+=field("Новий логін","username",value=(u["username"] or "") if login_value is None else login_value,autocomplete="username")
        if u["password_hash"]:
            login+=field("Поточний пароль для підтвердження","current_password","password",autocomplete="current-password")
        login+='<button>Зберегти логін</button>'
        body+=login_notice+form(login,"/account/login",s)
    return body+'<p class="auth-switch"><a href="/profile">Повернутися до профілю</a></p>'
@app.post("/account/settings")
async def update_profile_settings(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or not csrf_ok(s,d): return HTMLResponse("Невірний запит",status_code=403)
    name=d.get("display_name","").strip()
    birthday=d.get("birth_date","").strip()
    bio=d.get("bio","").strip()
    values={"display_name":name,"birth_date":birthday,"bio":bio}
    error=""
    if len(name)>80 or (name and not name.isprintable()): error="Ім’я має містити не більше 80 друкованих символів."
    if len(bio)>240: error="Опис має містити не більше 240 символів."
    if birthday:
        try:
            parsed=date.fromisoformat(birthday) if re.fullmatch(r"\d{4}-\d{2}-\d{2}",birthday) else None
            if not parsed or parsed<date(1900,1,1) or parsed>date.today(): raise ValueError
        except ValueError:
            error="Вкажіть коректну дату народження від 1900 року до сьогодні."
    if error: return page("Налаштування профілю",profile_settings_body(s,u,info_error=error,values=values),s)
    with db() as c:
        c.execute("UPDATE users SET display_name=?,birth_date=?,bio=? WHERE id=?",(name or None,birthday or None,bio or None,u["id"]))
    audit("profile_updated",actor=u["email"],target=u["email"],ip=client_ip(req))
    return redirect("/account/settings?saved=profile")
@app.post("/account/login")
async def update_account_login(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or not csrf_ok(s,d): return HTMLResponse("Невірний запит",status_code=403)
    if u["role"]=="admin": return HTMLResponse("Логін адміністратора не змінюється",status_code=403)
    username=d.get("username","").strip().lower()
    error=""
    if not re.fullmatch(r"[a-z][a-z0-9._-]{2,29}",username):
        error="Логін: 3–30 символів, починається з латинської літери; дозволені цифри, крапка, дефіс і підкреслення."
    elif username=="admin": error="Логін admin зарезервовано."
    elif username!=(u["username"] or "").lower() and u["password_hash"] and not verify_password(d.get("current_password",""),u["password_hash"]):
        error="Для зміни логіну введіть поточний пароль."
    if error: return page("Налаштування профілю",profile_settings_body(s,u,login_error=error,login_value=username),s)
    try:
        with db() as c:
            c.execute("UPDATE users SET username=? WHERE id=?",(username,u["id"]))
    except sqlite3.IntegrityError:
        return page("Налаштування профілю",profile_settings_body(s,u,login_error="Цей логін уже зайнятий.",login_value=username),s)
    audit("username_changed",actor=u["email"],target=u["email"],ip=client_ip(req))
    return redirect("/account/settings?saved=login")
@app.get("/2fa/setup")
def setup_2fa(req: Request):
    s=session(req); u=auth(s)
    if not u: return redirect("/login")
    if u["totp_secret"]: return page("2FA вже увімкнено",'<p>Для вимкнення скористайтеся формою у профілі.</p>',s)
    secret=s["captcha_answer"] if s["captcha_answer"] and (s["captcha_until"] or 0)>now() else None
    if not secret:
        secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        with db() as c: c.execute("UPDATE sessions SET captcha_answer=?,captcha_until=? WHERE token_hash=?",(secret,now()+600,s["token_hash"]))
    return page("Налаштування 2FA",setup_2fa_body(s,u,secret),s)
def setup_2fa_body(s,u,secret,error=""):
    marker=hashlib.sha256(secret.encode()).hexdigest()[:4].upper()
    label=f'{u["email"]} [{marker}]'
    uri="otpauth://totp/Forma:"+urllib.parse.quote(label)+"?"+urllib.parse.urlencode({"secret":secret,"issuer":"Forma","algorithm":"SHA1","digits":6,"period":30})
    body=f'<p>Відскануйте поточний QR-код у Google Authenticator. У застосунку виберіть запис Forma з позначкою <strong>{marker}</strong>. Ключ діє 10 хвилин до підтвердження.</p>{totp_qr(uri)}<details><summary>Ключ для ручного введення</summary><div class="secret">{esc(secret)}</div></details>'
    if error: body+=f'<div class="notice error" role="alert">{esc(error)}</div>'
    server_time=datetime.fromtimestamp(now(),timezone.utc).strftime("%H:%M:%S UTC")
    body+=f'<p class="small">Якщо код не підходить, перевірте позначку запису й автоматичний час телефону. Час сервера: {server_time}.</p>'
    body+=form(field("Код із застосунку","code",autocomplete="one-time-code")+'<button>Увімкнути 2FA</button>',"/2fa/setup",s)
    body+=form('<button type="submit" class="secondary">Створити новий QR-код</button>',"/2fa/setup/restart",s)
    return body
@app.post("/2fa/setup/restart")
async def restart_2fa_setup(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or not csrf_ok(s,d): return HTMLResponse("Невірний запит",status_code=403)
    if u["totp_secret"]: return redirect("/profile")
    with db() as c:
        c.execute("UPDATE sessions SET captcha_answer=NULL,captcha_until=NULL WHERE token_hash=?",(s["token_hash"],))
    return redirect("/2fa/setup")
@app.post("/2fa/setup")
async def setup_2fa_post(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or not csrf_ok(s,d): return HTMLResponse("Невірний запит",status_code=403)
    secret=s["captcha_answer"]
    if not secret or (s["captcha_until"] or 0)<now():
        return page("Ключ прострочено",'<p>Час налаштування минув. Відкрийте новий QR-код і відскануйте його повторно.</p><a href="/2fa/setup">Новий QR-код</a>',s)
    if not verify_totp(secret,d.get("code","")):
        audit("two_factor_setup_failure",actor=u["email"],target=u["email"],ip=client_ip(req))
        drift=totp_clock_drift(secret,d.get("code",""))
        error=("Ключ QR-коду збігається, але час телефону відрізняється від сервера приблизно на "
               f"{abs(drift) // 60} хв {abs(drift) % 60} с. Увімкніть автоматичні дату й час на телефоні.") if drift else (
               "Код не відповідає поточному QR-коду. Звірте позначку запису Forma в застосунку або створіть новий QR-код.")
        return page("Налаштування 2FA",setup_2fa_body(s,u,secret,error),s)
    with db() as c:
        c.execute("UPDATE users SET totp_secret=? WHERE id=?",(secret,u["id"]))
        c.execute("DELETE FROM tokens WHERE user_id=? AND purpose='reset'",(u["id"],))
        c.execute("UPDATE sessions SET captcha_answer=NULL,captcha_until=NULL WHERE token_hash=?",(s["token_hash"],))
    audit("two_factor_enabled",actor=u["email"],target=u["email"],ip=client_ip(req))
    return redirect("/profile")
@app.get("/2fa/disable")
def disable_2fa_page(req: Request):
    s=session(req); u=auth(s)
    if not u: return redirect("/login")
    if not u["totp_secret"]: return redirect("/profile")
    return page("Керування 2FA",disable_2fa_body(s,u),s)
def disable_2fa_body(s,u,error=""):
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    fields=field("Пароль","password","password",autocomplete="current-password") if u["password_hash"] else ""
    fields+=field("Код з автентифікатора","code",autocomplete="one-time-code")
    fields+='<div class="security-actions"><button class="disable-submit">Вимкнути 2FA</button><a href="/profile">Скасувати</a></div>'
    emblem='<span class="security-emblem" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M16 3 27 7v8c0 7-4.5 11.8-11 14C9.5 26.8 5 22 5 15V7l11-4Z" stroke="currentColor" stroke-width="2"/><rect x="11" y="14" width="10" height="8" rx="2" fill="currentColor"/><path d="M13 14v-2a3 3 0 0 1 6 0v2" stroke="currentColor" stroke-width="2"/></svg></span>'
    intro=f'<div class="security-intro">{emblem}<p>Керування двофакторним захистом вашого акаунта</p></div>'
    status='<div class="security-status"><span class="security-status-dot"></span><span>Двофакторний захист</span><strong>Активний</strong></div>'
    content='<h2>Підтвердіть зміну</h2><p class="security-description">Введіть дані акаунта, щоб вимкнути перевірку кодом під час входу.</p>'
    return intro+'<section class="security-panel">'+status+content+notice+form(fields,"/2fa/disable",s)+'</section><p class="security-footnote">Поки 2FA увімкнено, вхід до акаунта потребує коду з автентифікатора.</p>'
@app.post("/2fa/disable")
async def disable_2fa(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or not csrf_ok(s,d): return HTMLResponse("Невірний запит",status_code=403)
    if not u["totp_secret"]: return redirect("/profile")
    if (u["password_hash"] and not verify_password(d.get("password",""),u["password_hash"])) or not verify_totp(u["totp_secret"],d.get("code","")):
        audit("two_factor_disable_failure",actor=u["email"],target=u["email"],ip=client_ip(req))
        return page("Керування 2FA",disable_2fa_body(s,u,"Невірний пароль або код з автентифікатора."),s)
    with db() as c: c.execute("UPDATE users SET totp_secret=NULL WHERE id=?",(u["id"],))
    audit("two_factor_disabled",actor=u["email"],target=u["email"],ip=client_ip(req))
    return redirect("/profile")
@app.get("/forgot")
def forgot_page(req: Request):
    s,raw=ensure_session(req)
    r=page("Відновлення пароля",forgot_body(s,auth(s)),s)
    return cookie(r,raw) if raw else r
def forgot_body(s, current_user=None, identifier="", error=""):
    warning='<div class="notice error">Надсилання пошти ще не налаштовано. Заповніть Gmail SMTP у backend/.env.</div>' if not smtp_ready() and not DEMO_MODE else ''
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    if current_user:
        content=f'<p>Посилання для зміни пароля надійде лише на адресу <strong>{esc(mask_email(current_user["email"]))}</strong>.</p>'
        fields=''
    else:
        content='<p>Вкажіть email або логін свого акаунта. Адресу для листа визначить сайт.</p>'
        fields=field("Email або логін акаунта","email",value=identifier,autocomplete="username")
    if not current_user or current_user["totp_secret"]:
        fields+=field("Код з автентифікатора (якщо 2FA увімкнено)","code",required=False,autocomplete="one-time-code")
    fields+=f'<button {"disabled" if warning else ""}>Надіслати посилання</button>'
    return warning+notice+content+form(fields,"/forgot",s)
@app.post("/forgot")
async def forgot(req: Request):
    s=session(req); d=await data(req)
    if not csrf_ok(s,d): return HTMLResponse("Невірний CSRF токен",status_code=403)
    if not smtp_ready() and not DEMO_MODE:
        return page("Відновлення пароля",'<div class="notice error">Надсилання пошти не налаштовано в backend/.env.</div><a href="/forgot">Назад</a>',s)
    current_user=auth(s)
    identifier=d.get("email","").strip().lower()
    with db() as c:
        u=current_user if current_user else c.execute("SELECT * FROM users WHERE email=? OR lower(username)=?",(identifier,identifier)).fetchone()
        email=u["email"] if u else identifier
        recent=c.execute("SELECT count(*) FROM mail_outbox WHERE recipient=? AND subject=? AND created_at>?",(email,"Відновлення пароля",now()-900)).fetchone()[0]
        totp_failures=c.execute("SELECT count(*) FROM audit_log WHERE event='password_reset_2fa_failed' AND target_email=? AND ip=? AND happened_at>?",(email,client_ip(req),now()-900)).fetchone()[0]
    if current_user and recent>=3:
        return page("Відновлення пароля",'<div class="notice error">Забагато запитів. Спробуйте ще раз через 15 хвилин.</div>',s)
    if u and u["totp_secret"]:
        if totp_failures>=5:
            return page("Відновлення пароля",forgot_body(s,current_user,identifier,"Забагато спроб із кодом. Спробуйте через 15 хвилин."),s)
        if not verify_totp(u["totp_secret"],d.get("code","")):
            audit("password_reset_2fa_failed",target=email,ip=client_ip(req))
            return page("Відновлення пароля",forgot_body(s,current_user,identifier,"Введіть актуальний код з автентифікатора, щоб надіслати лист."),s)
    if u and recent<3:
        token=issue_token(u["id"],"reset",1800)
        try:
            mail(email,"Відновлення пароля",f"Посилання діє 30 хвилин і використовується один раз:\n{url('/reset?token='+token)}")
        except (OSError, smtplib.SMTPException, RuntimeError):
            with db() as c: c.execute("DELETE FROM tokens WHERE user_id=? AND purpose='reset'",(u["id"],))
            return page("Відновлення пароля",'<div class="notice error">Не вдалося надіслати лист. Перевірте налаштування Gmail SMTP.</div><a href="/forgot">Назад</a>',s)
        audit("password_reset_requested",target=email,ip=client_ip(req))
    elif not u:
        audit("password_reset_unknown",target=email,ip=client_ip(req))
    if current_user:
        return page("Перевірте пошту",f'<p>Посилання для зміни пароля надіслано на <strong>{esc(mask_email(email))}</strong>.</p>',s)
    return page("Перевірте пошту",'<p>Якщо адреса існує, ми надіслали посилання для скидання пароля.</p>',s)
@app.get("/reset")
def reset_page(req: Request,token: str="",captcha_host: str=""):
    if captcha_provider()=="hcaptcha" and HCAPTCHA_ORIGIN and captcha_host!="1":
        query=urllib.parse.urlencode({"token":token,"captcha_host":"1"})
        return redirect(HCAPTCHA_ORIGIN+"/reset?"+query)
    s,raw=ensure_session(req)
    with db() as c: valid=c.execute("SELECT 1 FROM tokens WHERE token_hash=? AND purpose='reset' AND expires_at>?",(digest(token),now())).fetchone()
    body=reset_body(s,token) if valid else '<p>Посилання недійсне або прострочене.</p>'
    r=page("Новий пароль",body,s); return cookie(r,raw) if raw else r
def reset_body(s,token,error=""):
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    if not captcha_ready():
        notice+=f'<div class="notice error">{esc(captcha_setup_notice())}</div>'
    rules='<ul id="password-rules" class="password-rules" aria-live="polite"><li data-rule="length">Щонайменше 8 символів</li><li data-rule="upper">Велика літера</li><li data-rule="lower">Мала літера</li><li data-rule="digit">Цифра</li><li data-rule="special">Спеціальний символ</li></ul>'
    fields=f'<input type="hidden" name="token" value="{esc(token)}">'+field("Новий пароль","password","password",autocomplete="new-password")+rules
    fields+=field("Підтвердіть новий пароль","password_confirm","password",autocomplete="new-password")+'<p id="password-match" class="password-match" aria-live="polite"></p>'
    fields+=captcha_widget("reset")
    fields+=f'<button {"" if captcha_ready() else "disabled"}>Зберегти пароль</button>'
    return notice+form(fields,"/reset",s)+captcha_script()+'<script src="/register.js" defer></script>'
@app.post("/reset")
async def reset(req: Request):
    s=session(req); d=await data(req)
    if not csrf_ok(s,d): return HTMLResponse("Невірний CSRF токен",status_code=403)
    error=password_error(d.get("password",""))
    if d.get("password","")!=d.get("password_confirm",""): error="Паролі не збігаються."
    if error: return page("Новий пароль",reset_body(s,d.get("token",""),error),s)
    if not captcha_ready():
        return page("Новий пароль",reset_body(s,d.get("token",""),"CAPTCHA не налаштовано."),s)
    if not await verify_captcha(d,client_ip(req),"reset",s):
        audit("captcha_failed",ip=client_ip(req),details="reset")
        return page("Новий пароль",reset_body(s,d.get("token",""),"CAPTCHA не підтверджено. Спробуйте ще раз."),s)
    uid=consume_token(d.get("token",""),"reset")
    if not uid: return page("Недійсне посилання",'<p>Посилання вже використане або прострочене.</p>',s)
    with db() as c:
        c.execute("UPDATE users SET password_hash=?,failed_count=0,locked_until=0 WHERE id=?",(hash_password(d["password"]),uid))
        c.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
        changed=c.execute("SELECT email FROM users WHERE id=?",(uid,)).fetchone()
    if changed: audit("password_reset_completed",actor=changed["email"],target=changed["email"],ip=client_ip(req))
    return page("Пароль оновлено",f'<p>Усі попередні сесії завершено.</p><a class="button" href="{esc(url("/login"))}">Увійти</a>',s)
@app.get("/admin")
def admin(req: Request, tab: str="users", mail_page: int=1):
    s=session(req); u=auth(s)
    if not u or u["role"]!="admin": return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c:
        users=c.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        events=c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200").fetchall()
        last_logins=c.execute("SELECT l.email,l.ip FROM login_log l JOIN (SELECT email,max(id) AS id FROM login_log WHERE result IN ('success','success_2fa','success_google') GROUP BY email) latest ON l.id=latest.id").fetchall()
        mail_count=c.execute("SELECT count(*) FROM mail_outbox").fetchone()[0]
        request_count=c.execute("SELECT count(*) FROM support_requests").fetchone()[0]
        requests=c.execute("SELECT * FROM support_requests ORDER BY id DESC LIMIT 100").fetchall() if tab=="support" else []
        try: page_number=max(1,min(int(mail_page),(mail_count+49)//50 or 1))
        except (TypeError,ValueError): page_number=1
        mails=c.execute("SELECT id,recipient,subject,created_at FROM mail_outbox ORDER BY id DESC LIMIT 50 OFFSET ?",((page_number-1)*50,)).fetchall() if tab=="mails" else []
    blocked=sum(bool(x["blocked"] or x["locked_until"]>now()) for x in users)
    protected=sum(bool(x["totp_secret"]) for x in users)
    active=sum(bool(x["active"]) for x in users)
    stats='<div class="admin-stats">'+''.join(
        f'<div class="admin-stat {kind}"><span>{label}</span><strong>{value}</strong></div>'
        for kind,label,value in (("blue","Усього акаунтів",len(users)),("green","Активовані email",active),
                                 ("red","Заблоковані",blocked),("yellow","Захищені 2FA",protected)))+'</div>'
    selected=tab if tab in ("users","twofa","audit","mails","support") else "users"
    user_ips={x["email"]:x["ip"] for x in last_logins}
    pc_ip=local_pc_ip() if any(ip in ("127.0.0.1","::1") for ip in user_ips.values()) else None
    def user_ip_cell(email):
        ip=user_ips.get(email)
        if not ip: return "—"
        if ip in ("127.0.0.1","::1") and pc_ip:
            return f'{esc(pc_ip)}<small>IP цього ПК зараз · локальний вхід</small>'
        return esc(ip)
    tabs='<div class="admin-tabs">'+''.join(
        f'<a class="{"selected" if selected==key else ""}" href="/admin?tab={key}">{label}</a>'
        for key,label in (("users",f"Користувачі ({len(users)})"),("twofa",f"Захищені 2FA ({protected})"),("audit",f"Журнал аудиту ({len(events)})"),("mails",f"Надіслані листи ({mail_count})"),("support",f"Підтримка ({request_count})")))+'</div>'
    def user_row(x):
        username=x["username"] or x["email"].split("@",1)[0]
        locked=bool(x["blocked"] or x["locked_until"]>now())
        status="Заблоковано" if x["blocked"] else "Тимчасова блокада" if x["locked_until"]>now() else "Активний"
        action="unblock" if locked else "block"
        if x["id"]!=u["id"] and x["role"]!="admin":
            block_button=form(f'<input type="hidden" name="user_id" value="{x["id"]}"><input type="hidden" name="action" value="{action}"><button class="smallbtn {"secondary" if locked else "danger"}">{"Розблокувати" if locked else "Заблокувати"}</button>',"/admin/block",s)
            button=f'<div class="admin-user-actions">{block_button}<a class="smallbtn delete-link" href="/admin/users/{x["id"]}/delete">Видалити</a></div>'
        else:
            button='<span class="small">Поточний сеанс</span>' if x["id"]==u["id"] else '<span class="small">Адміністратор</span>'
        return f'<tr><td>#{x["id"]}</td><td><strong>{esc(username)}</strong></td><td>{esc(x["email"])}</td><td>{"Адміністратор" if x["role"]=="admin" else "Користувач"}</td><td>{"Так" if x["active"] else "Ні"}</td><td><span class="badge {"" if locked else "good"}">{status}</span></td><td>{"Увімкнено" if x["totp_secret"] else "—"}</td><td>{user_ip_cell(x["email"])}</td><td>{x["failed_count"]}</td><td>{button}</td></tr>'
    def audit_table(items):
        rows=''.join(f'<tr><td>{moment(x["happened_at"])}</td><td><strong>{esc(event_label(x["event"]))}</strong><small>{esc(x["event"])}</small></td><td>{esc(x["actor_email"] or "—")}</td><td>{esc(x["target_email"] or "—")}</td><td>{user_ip_cell(x["target_email"])}</td><td>{esc(x["ip"] or "—")}</td></tr>' for x in items)
        return '<div class="scroll admin-table"><table><thead><tr><th>Час (UTC)</th><th>Подія</th><th>Хто</th><th>Акаунт</th><th>IP користувача</th><th>IP дії</th></tr></thead><tbody>'+rows+'</tbody></table></div>' if rows else '<p class="small">Подій поки немає.</p>'
    if selected=="support":
        cards=''.join(f'<article class="admin-support-card"><div class="small">#{x["id"]} · {moment(x["created_at"])} · {esc(SUPPORT_CATEGORIES.get(x["category"],"Інше"))}</div><h2>{esc(x["subject"] or "Без теми")}</h2><p>{esc(x["email"])} · <span class="badge">{esc(SUPPORT_STATUSES.get(x["status"],"Нове"))}</span></p><p>{esc(x["message"][:180])}{"…" if len(x["message"])>180 else ""}</p><a class="button secondary" href="/admin/support/{x["id"]}">Детальніше</a></article>' for x in requests)
        section='<h2>Звернення до підтримки</h2><p class="small">Останні 100 звернень. Відкрийте картку для опису, пов’язаних подій входу й службових нотаток.</p>'+(cards or '<p class="small">Звернень поки немає.</p>')
    elif selected=="mails":
        rows=''.join(f'<tr><td>#{x["id"]}</td><td>{moment(x["created_at"])}</td><td>{esc(x["recipient"])}</td><td>{esc(x["subject"])}</td><td><span class="badge good">Надіслано</span></td></tr>' for x in mails)
        section='<h2>Надіслані листи</h2><p class="small">Тут показано всі успішні відправлення, по 50 на сторінку. Текст листів із одноразовими посиланнями не зберігається в робочому режимі.</p>'
        section+=('<div class="scroll admin-table"><table><thead><tr><th>ID</th><th>Час (UTC)</th><th>Кому</th><th>Тема</th><th>Статус</th></tr></thead><tbody>'+rows+'</tbody></table></div>') if rows else '<p class="small">Надісланих листів поки немає.</p>'
        if mail_count>50:
            previous=f'<a href="/admin?tab=mails&mail_page={page_number-1}">← Попередня</a>' if page_number>1 else ''
            following=f'<a href="/admin?tab=mails&mail_page={page_number+1}">Наступна →</a>' if page_number*50<mail_count else ''
            section+=f'<nav class="admin-pagination">{previous}<span>Сторінка {page_number}</span>{following}</nav>'
    elif selected=="audit":
        section='<h2>Журнал аудиту спроб входу та атак</h2><p class="small">Останні 200 подій. «IP користувача» — адреса його останнього успішного входу; «IP дії» — адреса конкретної події. Для локального входу показано поточний IP цього ПК із відповідною позначкою.</p>'+audit_table(events)
    else:
        chosen=[x for x in users if x["totp_secret"]] if selected=="twofa" else users
        rows=''.join(user_row(x) for x in chosen)
        section=f'<h2>{"Акаунти із захистом 2FA" if selected=="twofa" else "Керування користувачами"}</h2>'
        section+='<div class="scroll admin-table"><table><thead><tr><th>ID</th><th>Логін</th><th>Email</th><th>Роль</th><th>Активація</th><th>Статус</th><th>2FA</th><th>Останній IP входу</th><th>Помилки входу</th><th>Дія</th></tr></thead><tbody>'+rows+'</tbody></table></div>' if rows else '<p class="small">Акаунтів у цій категорії поки немає.</p>'
        if selected=="users": section+='<h2>Останні події</h2>'+audit_table(events[:8])
    body='<p class="lead">Керування акаунтами, доступом і журналом подій безпеки.</p>'+stats+tabs+section
    return page("Панель адміністратора",body,s)
@app.get("/admin/users/{user_id}/delete")
def admin_user_delete_page(req: Request, user_id: int):
    s=session(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin": return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c: target=c.execute("SELECT id,email,username,role FROM users WHERE id=?",(user_id,)).fetchone()
    if not target: return HTMLResponse("Користувача не знайдено",status_code=404)
    if target["role"]=="admin" or target["id"]==admin_user["id"]: return HTMLResponse("Дію заборонено",status_code=403)
    fields=f'<p>Акаунт <strong>{esc(target["username"] or target["email"])}</strong> ({esc(target["email"])}) буде видалено без можливості відновлення. Усі його сеанси завершаться. Журнал аудиту й історія листів залишаться.</p>'
    fields+=f'<p>Для підтвердження введіть email <strong>{esc(target["email"])}</strong> та слово <strong>ВИДАЛИТИ</strong>.</p>'
    fields+=field("Email акаунта","confirm_email",autocomplete="off")+field("Введіть ВИДАЛИТИ","confirm_word",autocomplete="off")
    fields+='<button class="danger">Видалити акаунт</button>'
    return page("Видалення акаунта",form(fields,f'/admin/users/{user_id}/delete',s)+'<p><a href="/admin?tab=users">Повернутися до користувачів</a></p>',s)
@app.post("/admin/users/{user_id}/delete")
async def admin_user_delete(req: Request, user_id: int):
    s=session(req); d=await data(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c:
        target=c.execute("SELECT id,email,role FROM users WHERE id=?",(user_id,)).fetchone()
        if not target: return HTMLResponse("Користувача не знайдено",status_code=404)
        if target["role"]=="admin" or target["id"]==admin_user["id"]: return HTMLResponse("Дію заборонено",status_code=403)
        if d.get("confirm_email","").strip().lower()!=target["email"] or d.get("confirm_word","").strip()!="ВИДАЛИТИ":
            return HTMLResponse("Для видалення введіть точний email акаунта та слово ВИДАЛИТИ",status_code=400)
        c.execute("INSERT OR IGNORE INTO user_id_sequence(id) VALUES(?)",(target["id"],))
        c.execute("DELETE FROM sessions WHERE user_id=?",(target["id"],))
        c.execute("DELETE FROM tokens WHERE user_id=?",(target["id"],))
        c.execute("DELETE FROM users WHERE id=?",(target["id"],))
    audit("admin_account_deleted",actor=admin_user["email"],target=target["email"],ip=client_ip(req))
    return redirect("/admin?tab=users")
@app.get("/admin/support/{request_id}")
def admin_support_detail(req: Request, request_id: int, saved: str="", reply: str="", action: str=""):
    s=session(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin": return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c:
        item=c.execute("SELECT * FROM support_requests WHERE id=?",(request_id,)).fetchone()
        if not item: return HTMLResponse("Звернення не знайдено",status_code=404)
        account=c.execute("SELECT id,email,username,role,active,blocked,locked_until,failed_count,totp_secret FROM users WHERE email=?",(item["email"],)).fetchone()
        logins=c.execute("SELECT happened_at,ip,result FROM login_log WHERE email=? ORDER BY id DESC LIMIT 12",(item["email"],)).fetchall()
        events=c.execute("SELECT happened_at,event,ip FROM audit_log WHERE target_email=? ORDER BY id DESC LIMIT 12",(item["email"],)).fetchall()
        successful_ips=c.execute("SELECT ip,max(happened_at) AS last_at,count(*) AS total FROM login_log WHERE email=? AND result IN ('success','success_2fa','success_google') GROUP BY ip ORDER BY last_at DESC",(item["email"],)).fetchall()
        failed_total=c.execute("SELECT count(*) FROM login_log WHERE email=? AND result IN ('failure','2fa_failure')",(item["email"],)).fetchone()[0]
        replies=c.execute("SELECT created_at,subject FROM mail_outbox WHERE support_request_id=? ORDER BY id DESC",(request_id,)).fetchall()
    status=SUPPORT_STATUSES.get(item["status"],"Нове")
    body=f'<p><a href="/admin?tab=support">← До звернень</a></p><h2>Звернення #{item["id"]}: {esc(item["subject"] or "Без теми")}</h2>'
    if saved: body+='<div class="notice" role="status">Зміни збережено.</div>'
    if action=="unblocked": body+='<div class="notice" role="status">Акаунт розблоковано.</div>'
    if action=="blocked": body+='<div class="notice" role="status">Акаунт заблоковано; активні сеанси завершено.</div>'
    if action=="deleted": body+='<div class="notice" role="status">Акаунт видалено.</div>'
    if reply=="sent": body+='<div class="notice" role="status">Відповідь надіслано на зареєстровану пошту.</div>'
    if reply=="failed": body+='<div class="notice error" role="alert">Не вдалося надіслати лист. Перевірте налаштування SMTP.</div>'
    body+=f'<div class="admin-support-grid"><article><div class="small">{moment(item["created_at"])} · IP: {esc(item["ip"])}</div><p><strong>Категорія:</strong> {esc(SUPPORT_CATEGORIES.get(item["category"],"Інше"))}</p><p><strong>Email із форми (не перевірений):</strong> {esc(item["email"])}</p><p><strong>Статус:</strong> {esc(status)}</p><h3>Опис проблеми</h3><pre>{esc(item["message"])}</pre><h3>Кроки відтворення</h3><pre>{esc(item["steps"] or "Не вказано")}</pre></article>'
    if account:
        account_status="Заблоковано адміністратором" if account["blocked"] else "Тимчасово обмежено" if account["locked_until"]>now() else "Активний"
        body+=f'<article><h3>Пов’язаний акаунт</h3><p class="small">Збіг за введеним email; власність адреси не підтверджена формою підтримки.</p><p>ID: #{account["id"]} · Логін: {esc(account["username"] or "—")}</p><p>Стан: {account_status} · Email активовано: {"Так" if account["active"] else "Ні"}</p><p>2FA: {"Увімкнено" if account["totp_secret"] else "Вимкнено"} · Невдалих спроб загалом: {failed_total}</p></article>'
    else: body+='<article><h3>Пов’язаний акаунт</h3><p>Акаунта з таким email не знайдено.</p></article>'
    body+='</div>'
    pc_ip=local_pc_ip() if any(x["ip"] in ("127.0.0.1","::1") for x in successful_ips) else None
    ip_rows=''.join(f'<tr><td>{esc(x["ip"])}{f"<small>IP цього ПК зараз: {esc(pc_ip)}</small>" if pc_ip and x["ip"] in ("127.0.0.1","::1") else ""}</td><td>{x["total"]}</td><td>{moment(x["last_at"])}</td></tr>' for x in successful_ips)
    body+='<h2>IP успішних входів</h2>'+(('<div class="scroll"><table><thead><tr><th>IP з’єднання</th><th>Входів</th><th>Останній вхід (UTC)</th></tr></thead><tbody>'+ip_rows+'</tbody></table></div>') if ip_rows else '<p class="small">Успішних входів поки немає.</p>')
    body+='<p class="small">Для входів на цьому ж ПК локальний проксі може записувати 127.0.0.1. Це фактична адреса з’єднання, а не зовнішня адреса користувача.</p>'
    options=''.join(f'<option value="{key}" {"selected" if item["status"]==key else ""}>{label}</option>' for key,label in SUPPORT_STATUSES.items())
    fields=f'<label>Статус<select name="status">{options}</select></label><label>Службова примітка<textarea name="admin_note" maxlength="2000" rows="5">{esc(item["admin_note"])}</textarea></label><button>Зберегти</button>'
    body+='<h2>Опрацювання</h2><p class="small">Службову примітку бачать лише адміністратори.</p>'+form(fields,f'/admin/support/{request_id}',s)
    if account and account["id"]!=admin_user["id"] and account["role"]!="admin":
        body+='<h2>Дії з акаунтом</h2>'
        if account["blocked"] or account["locked_until"]>now():
            body+='<p>Розблокування скине тимчасову заборону входу та лічильник помилок.</p>'+form('<button class="secondary">Розблокувати акаунт</button>',f'/admin/support/{request_id}/unblock',s)
        else:
            body+='<p>Блокування заборонить вхід і завершить усі активні сеанси цього акаунта.</p>'+form('<button class="danger">Заблокувати акаунт</button>',f'/admin/support/{request_id}/block',s)
        delete_fields=f'<p class="small">Акаунт буде видалено без можливості відновлення, усі його сеанси завершаться. Журнал безпеки та історія листів залишаться. Для підтвердження введіть email <strong>{esc(account["email"])}</strong> та слово ВИДАЛИТИ.</p>'
        delete_fields+=field("Email акаунта","confirm_email",autocomplete="off")+field("Введіть ВИДАЛИТИ","confirm_word",autocomplete="off")+'<button class="danger">Видалити акаунт</button>'
        body+='<details class="admin-delete"><summary>Видалити акаунт</summary>'+form(delete_fields,f'/admin/support/{request_id}/delete',s)+'</details>'
    body+='<h2>Відповідь користувачу</h2>'
    if account:
        warning='' if DEMO_MODE or smtp_ready() else '<div class="notice error">Пошта не налаштована. Заповніть SMTP у backend/.env.</div>'
        reply_fields=f'<p class="small">Лист буде надіслано на зареєстровану адресу <strong>{esc(account["email"])}</strong>.</p><label>Текст відповіді<textarea name="reply_body" required minlength="10" maxlength="2000" rows="6"></textarea></label><button {"disabled" if warning else ""}>Надіслати відповідь</button>'
        body+=warning+form(reply_fields,f'/admin/support/{request_id}/reply',s)
    else: body+='<p class="small">Для відповіді потрібен зареєстрований акаунт із цією адресою.</p>'
    if replies:
        body+='<h3>Надіслані відповіді</h3><ul>'+''.join(f'<li>{moment(x["created_at"])} · {esc(x["subject"])}</li>' for x in replies)+'</ul>'
    def recent_table(rows,kind):
        if not rows: return '<p class="small">Записів поки немає.</p>'
        cells=''.join(f'<tr><td>{moment(x["happened_at"])}</td><td>{esc(event_label(x["event"] if kind=="audit" else "login_"+x["result"]))}</td><td>{esc(x["ip"])}</td></tr>' for x in rows)
        return '<div class="scroll"><table><thead><tr><th>Час (UTC)</th><th>Подія</th><th>IP</th></tr></thead><tbody>'+cells+'</tbody></table></div>'
    body+='<h2>Останні спроби входу</h2>'+recent_table(logins,"login")+'<h2>Події безпеки</h2>'+recent_table(events,"audit")
    return page("Панель адміністратора",body,s)
@app.post("/admin/support/{request_id}")
async def admin_support_update(req: Request, request_id: int):
    s=session(req); d=await data(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    status=d.get("status",""); note=d.get("admin_note","").strip()
    if status not in SUPPORT_STATUSES or len(note)>2000: return HTMLResponse("Невірні дані",status_code=400)
    with db() as c:
        item=c.execute("SELECT email FROM support_requests WHERE id=?",(request_id,)).fetchone()
        if not item: return HTMLResponse("Звернення не знайдено",status_code=404)
        c.execute("UPDATE support_requests SET status=?,admin_note=?,updated_at=? WHERE id=?",(status,note,now(),request_id))
    audit("support_updated",actor=admin_user["email"],target=item["email"],ip=client_ip(req),details=f"#{request_id}: {status}")
    return redirect(f"/admin/support/{request_id}?saved=1")
@app.post("/admin/support/{request_id}/unblock")
async def admin_support_unblock(req: Request, request_id: int):
    s=session(req); d=await data(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c:
        item=c.execute("SELECT email FROM support_requests WHERE id=?",(request_id,)).fetchone()
        if not item: return HTMLResponse("Звернення не знайдено",status_code=404)
        target=c.execute("SELECT id,role FROM users WHERE email=?",(item["email"],)).fetchone()
        if not target or target["role"]=="admin" or target["id"]==admin_user["id"]: return HTMLResponse("Дію заборонено",status_code=403)
        c.execute("UPDATE users SET blocked=0,locked_until=0,failed_count=0 WHERE id=?",(target["id"],))
    audit("support_account_unblocked",actor=admin_user["email"],target=item["email"],ip=client_ip(req),details=f"Звернення #{request_id}")
    return redirect(f"/admin/support/{request_id}?action=unblocked")
@app.post("/admin/support/{request_id}/block")
async def admin_support_block(req: Request, request_id: int):
    s=session(req); d=await data(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c:
        item=c.execute("SELECT email FROM support_requests WHERE id=?",(request_id,)).fetchone()
        if not item: return HTMLResponse("Звернення не знайдено",status_code=404)
        target=c.execute("SELECT id,role FROM users WHERE email=?",(item["email"],)).fetchone()
        if not target or target["role"]=="admin" or target["id"]==admin_user["id"]: return HTMLResponse("Дію заборонено",status_code=403)
        c.execute("UPDATE users SET blocked=1,failed_count=0,locked_until=0 WHERE id=?",(target["id"],))
        c.execute("DELETE FROM sessions WHERE user_id=?",(target["id"],))
    audit("support_account_blocked",actor=admin_user["email"],target=item["email"],ip=client_ip(req),details=f"Звернення #{request_id}")
    return redirect(f"/admin/support/{request_id}?action=blocked")
@app.post("/admin/support/{request_id}/delete")
async def admin_support_delete(req: Request, request_id: int):
    s=session(req); d=await data(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    with db() as c:
        item=c.execute("SELECT email FROM support_requests WHERE id=?",(request_id,)).fetchone()
        if not item: return HTMLResponse("Звернення не знайдено",status_code=404)
        target=c.execute("SELECT id,email,role FROM users WHERE email=?",(item["email"],)).fetchone()
        if not target or target["role"]=="admin" or target["id"]==admin_user["id"]: return HTMLResponse("Дію заборонено",status_code=403)
        if d.get("confirm_email","").strip().lower()!=target["email"] or d.get("confirm_word","").strip()!="ВИДАЛИТИ":
            return HTMLResponse("Для видалення введіть точний email акаунта та слово ВИДАЛИТИ",status_code=400)
        c.execute("INSERT OR IGNORE INTO user_id_sequence(id) VALUES(?)",(target["id"],))
        c.execute("DELETE FROM sessions WHERE user_id=?",(target["id"],))
        c.execute("DELETE FROM tokens WHERE user_id=?",(target["id"],))
        c.execute("DELETE FROM users WHERE id=?",(target["id"],))
    audit("support_account_deleted",actor=admin_user["email"],target=item["email"],ip=client_ip(req),details=f"Звернення #{request_id}")
    return redirect(f"/admin/support/{request_id}?action=deleted")
@app.post("/admin/support/{request_id}/reply")
async def admin_support_reply(req: Request, request_id: int):
    s=session(req); d=await data(req); admin_user=auth(s)
    if not admin_user or admin_user["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    message=d.get("reply_body","").strip()
    if not 10<=len(message)<=2000: return HTMLResponse("Відповідь має містити від 10 до 2000 символів",status_code=400)
    with db() as c:
        item=c.execute("SELECT email FROM support_requests WHERE id=?",(request_id,)).fetchone()
        if not item: return HTMLResponse("Звернення не знайдено",status_code=404)
        target=c.execute("SELECT email FROM users WHERE email=?",(item["email"],)).fetchone()
        if not target: return HTMLResponse("Акаунт не знайдено",status_code=409)
    subject=f"Відповідь підтримки Forma щодо звернення #{request_id}"
    try:
        mail(target["email"],subject,f"Вітаємо!\n\n{message}\n\nForma · Підтримка",request_id)
    except (OSError,smtplib.SMTPException,RuntimeError,ValueError):
        audit("support_reply_failed",actor=admin_user["email"],target=target["email"],ip=client_ip(req),details=f"Звернення #{request_id}")
        return redirect(f"/admin/support/{request_id}?reply=failed")
    audit("support_reply_sent",actor=admin_user["email"],target=target["email"],ip=client_ip(req),details=f"Звернення #{request_id}")
    return redirect(f"/admin/support/{request_id}?reply=sent")
@app.post("/admin/block")
async def admin_block(req: Request):
    s=session(req); d=await data(req); u=auth(s)
    if not u or u["role"]!="admin" or not csrf_ok(s,d): return HTMLResponse("Доступ заборонено",status_code=403)
    try: target=int(d.get("user_id","0"))
    except ValueError: return HTMLResponse("Невірний користувач",status_code=400)
    if target==u["id"]: return HTMLResponse("Не можна блокувати себе",status_code=400)
    action=d.get("action")
    if action not in ("block","unblock"): return HTMLResponse("Невірна дія",status_code=400)
    with db() as c:
        victim=c.execute("SELECT email FROM users WHERE id=?",(target,)).fetchone()
        if not victim: return HTMLResponse("Користувача не знайдено",status_code=404)
        c.execute("UPDATE users SET blocked=?,failed_count=0,locked_until=0 WHERE id=?",(1 if action=="block" else 0,target))
        if action=="block": c.execute("DELETE FROM sessions WHERE user_id=?",(target,))
    audit("admin_blocked" if action=="block" else "admin_unblocked",actor=u["email"],target=victim["email"],ip=client_ip(req))
    return redirect("/admin")
@app.get("/dev-mail")
def dev_mail(req: Request):
    if not DEMO_MODE or client_ip(req) not in ("127.0.0.1","::1","testclient"): return HTMLResponse("Доступ заборонено",status_code=403)
    s,raw=ensure_session(req)
    with db() as c: mails=c.execute("SELECT * FROM mail_outbox ORDER BY id DESC LIMIT 30").fetchall()
    cards="".join(f'<article><div class="small">{moment(m["created_at"])} · {esc(m["recipient"])}</div><h2>{esc(m["subject"])}</h2><pre>{esc(m["body"])}</pre></article>' for m in mails)
    r=page("Листи для демонстрації",'<p>Локальна скринька доступна лише на цьому комп’ютері. Для реального надсилання заповніть SMTP у .env.</p>'+cards,s)
    return cookie(r,raw) if raw else r
@app.get("/google/start")
def google_start(req: Request,captcha_host: str=""):
    if not GOOGLE_ID or not GOOGLE_SECRET: return HTMLResponse("Google OpenID Connect не налаштовано в backend/.env",status_code=503)
    if captcha_provider()=="hcaptcha" and HCAPTCHA_ORIGIN and captcha_host!="1":
        return redirect(HCAPTCHA_ORIGIN+"/google/start?captcha_host=1")
    s,raw=ensure_session(req)
    if auth(s): return redirect("/profile")
    r=page("Вхід через Google",google_start_body(s),s)
    return cookie(r,raw) if raw else r
def google_start_body(s,error=""):
    notice=f'<div class="notice error" role="alert">{esc(error)}</div>' if error else ""
    if not login_captcha_ready():
        notice+='<div class="notice error">CAPTCHA для входу не налаштовано. Перевірте ключі hCaptcha у backend/.env.</div>'
    fields=login_captcha_widget()+f'<button {"" if login_captcha_ready() else "disabled"}>Продовжити з Google</button>'
    return notice+'<p>Підтвердіть перевірку, щоб продовжити вхід через Google.</p>'+form(fields,"/google/start",s)+login_captcha_script()
@app.post("/google/start")
async def google_start_submit(req: Request):
    if not GOOGLE_ID or not GOOGLE_SECRET: return HTMLResponse("Google OpenID Connect не налаштовано в backend/.env",status_code=503)
    s=session(req); d=await data(req)
    if not csrf_ok(s,d): return HTMLResponse("Невірний CSRF токен",status_code=403)
    if auth(s): return redirect("/profile")
    if not login_captcha_ready():
        return page("Вхід через Google",google_start_body(s,"CAPTCHA для входу не налаштовано."),s)
    if not await verify_captcha(d,client_ip(req),"login",s):
        audit("captcha_failed",ip=client_ip(req),details="google_login")
        return page("Вхід через Google",google_start_body(s,"Підтвердіть CAPTCHA перед входом."),s)
    return google_authorize(s,None,"login")
@app.get("/google/link/start")
def google_link_start(req: Request):
    s=session(req); u=auth(s)
    if not u: return redirect("/login")
    if u["google_sub"]: return redirect("/profile")
    if not GOOGLE_ID or not GOOGLE_SECRET: return HTMLResponse("Google OpenID Connect не налаштовано в backend/.env",status_code=503)
    return google_authorize(s,None,"link")
def google_authorize(s,raw,purpose):
    state,nonce,verifier=purpose+"."+secrets.token_urlsafe(32),secrets.token_urlsafe(32),secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    with db() as c: c.execute("UPDATE sessions SET oidc_state=?,oidc_nonce=?,oidc_verifier=? WHERE token_hash=?",(state,nonce,verifier,s["token_hash"]))
    params={"client_id":GOOGLE_ID,"redirect_uri":url("/google/callback"),"response_type":"code","scope":"openid email profile","state":state,"nonce":nonce,"code_challenge":challenge,"code_challenge_method":"S256","prompt":"select_account"}
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?"+urllib.parse.urlencode(params),raw)
@app.get("/google/callback")
async def google_callback(req: Request, code: str="", state: str="", error: str=""):
    s=session(req)
    cross_origin=False
    if state and (not s or not hmac.compare_digest(state,s["oidc_state"] or "")):
        with db() as c:
            s=c.execute("SELECT * FROM sessions WHERE oidc_state=? AND expires_at>?",(state,now())).fetchone()
        cross_origin=bool(s)
    if not s or not state or not hmac.compare_digest(state,s["oidc_state"] or ""):
        return HTMLResponse("Невірний стан OAuth",status_code=403)
    linking=state.startswith("link.")
    current_user=auth(s) if linking else None
    if linking and not current_user: return HTMLResponse("Потрібен вхід для підключення Google-акаунта",status_code=403)
    with db() as c: c.execute("UPDATE sessions SET oidc_state=NULL,oidc_nonce=NULL,oidc_verifier=NULL WHERE token_hash=?",(s["token_hash"],))
    if error:
        destination=(HCAPTCHA_ORIGIN+"/profile" if cross_origin else "/profile") if linking else "/login"
        return page("Вхід через Google скасовано",f'<p>Google не підтвердив вхід. Спробуйте ще раз, коли будете готові.</p><a class="button" href="{destination}">Повернутися</a>',s)
    if not code: return HTMLResponse("Google не повернув код авторизації",status_code=400)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_response=await client.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":GOOGLE_ID,"client_secret":GOOGLE_SECRET,"redirect_uri":url("/google/callback"),"grant_type":"authorization_code","code_verifier":s["oidc_verifier"]})
            token_response.raise_for_status()
            id_token=token_response.json()["id_token"]
            info_response=await client.get("https://oauth2.googleapis.com/tokeninfo",params={"id_token":id_token})
            info_response.raise_for_status()
            info=info_response.json()
    except (httpx.HTTPError,KeyError,ValueError): return page("Помилка Google",'<p>Не вдалося підтвердити вхід. Спробуйте ще раз.</p>',s)
    try: expires=int(info.get("exp",0))
    except (TypeError,ValueError): expires=0
    if info.get("aud")!=GOOGLE_ID or info.get("iss") not in ("accounts.google.com","https://accounts.google.com") or info.get("nonce")!=s["oidc_nonce"] or info.get("email_verified") not in ("true",True) or expires<=now() or not info.get("sub") or not info.get("email"):
        return HTMLResponse("Недійсний OIDC токен",status_code=403)
    sub=info["sub"]; email=info["email"].lower()
    if linking:
        if email!=current_user["email"]:
            destination=HCAPTCHA_ORIGIN+"/profile" if cross_origin else "/profile"
            return page("Адреси не збігаються",f'<p>Для підключення виберіть Google-акаунт із тією самою поштовою адресою, що й у профілі Forma.</p><a class="button" href="{esc(destination)}">До профілю</a>',s)
        with db() as c:
            linked=c.execute("SELECT id FROM users WHERE google_sub=?",(sub,)).fetchone()
            if linked and linked["id"]!=current_user["id"]:
                return page("Google-акаунт уже підключено",'<p>Цей Google-акаунт уже належить іншому користувачу Forma.</p><a class="button" href="/profile">До профілю</a>',s)
            c.execute("UPDATE users SET google_sub=? WHERE id=? AND google_sub IS NULL",(sub,current_user["id"]))
        audit("google_linked",actor=current_user["email"],target=current_user["email"],ip=client_ip(req))
        return redirect("/profile",rotate_session(s,current_user["id"],req=req)) if cross_origin else redirect("/profile")
    with db() as c:
        u=c.execute("SELECT * FROM users WHERE google_sub=?",(sub,)).fetchone()
        if not u:
            existing=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
            if existing: return page("Потрібне підтвердження",'<p>Ця адреса вже має акаунт Forma. Увійдіть паролем, відкрийте профіль і натисніть «Підключити Google-акаунт». Після цього зможете входити через Google до того самого профілю.</p><a class="button" href="/login">До входу</a>',s)
            uid=next_user_id(c)
            c.execute("INSERT INTO users(id,email,google_sub,active,created_at) VALUES(?,?,?,1,?)",(uid,email,sub,now()))
            u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if u["blocked"]:
        log(email,client_ip(req),"blocked_google")
        return HTMLResponse("Обліковий запис заблоковано",status_code=403)
    if u["totp_secret"]:
        raw=rotate_session(s,u["id"],1,req); log(email,client_ip(req),"2fa_pending_google")
        return redirect("/2fa",raw)
    raw=rotate_session(s,u["id"],req=req); log(email,client_ip(req),"success_google")
    return redirect("/profile",raw)

def init_admin(email="admin@forma.local"):
    import getpass
    p=getpass.getpass("Новий пароль адміністратора: ")
    error=password_error(p)
    if error: raise SystemExit(error)
    with db() as c:
        u=c.execute("SELECT id,email FROM users WHERE username='admin'").fetchone()
        if not u: u=c.execute("SELECT id,email FROM users WHERE email=?",(email.lower(),)).fetchone()
        if u:
            c.execute("UPDATE users SET username='admin',password_hash=?,role='admin',active=1,blocked=0,locked_until=0,failed_count=0 WHERE id=?",(hash_password(p),u["id"]))
            admin_email=u["email"]
        else:
            c.execute("INSERT INTO users(id,email,username,password_hash,role,active,created_at) VALUES(?,?,'admin',?,'admin',1,?)",(next_user_id(c),email.lower(),hash_password(p),now()))
            admin_email=email.lower()
    audit("admin_created",actor="system",target=admin_email,ip="local")
    print("Адміністратор готовий. Логін: admin")
if __name__=="__main__":
    if len(sys.argv) in (2,3) and sys.argv[1]=="init-admin": init_admin(sys.argv[2] if len(sys.argv)==3 else "admin@forma.local")
    else:
        import uvicorn
        uvicorn.run(app,host="127.0.0.1",port=8000)
