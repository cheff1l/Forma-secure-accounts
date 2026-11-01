"""Run: python -m pytest -q test_app.py"""
import inspect
import importlib.util
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from starlette.requests import Request

def load(folder):
    os.environ["DB_PATH"]=str(folder/"test.sqlite3")
    os.environ["BASE_URL"]="http://127.0.0.1:5173"
    os.environ["DEMO_MODE"]="1"
    os.environ["TURNSTILE_SITE_KEY"]="test-site-key"
    os.environ["TURNSTILE_SECRET_KEY"]="test-secret-key"
    os.environ["CAPTCHA_PROVIDER"]="turnstile"
    spec=importlib.util.spec_from_file_location("account_app",Path(__file__).with_name("app.py"))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.GOOGLE_ID=""
    mod.GOOGLE_SECRET=""
    mod.HCAPTCHA_SITE_KEY=""
    mod.HCAPTCHA_SECRET_KEY=""
    mod.HCAPTCHA_ORIGIN=""
    async def fake_turnstile(token, ip, action="register"):
        return token == ("reset-token" if action == "reset" else "verified-token")
    mod.verify_turnstile = fake_turnstile
    return mod
class Browser:
    def __init__(self,mod,user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",ip="127.0.0.1"):
        self.mod=mod; self.sid=""; self.user_agent=user_agent; self.ip=ip
    def call(self,name,path,fields=None,auto_login_captcha=True):
        method="POST" if fields is not None else "GET"
        if name=="login" and fields is not None and auto_login_captcha:
            fields={"cf-turnstile-response":"verified-token",**fields}
        payload=urlencode(fields or {}).encode()
        async def receive(): return {"type":"http.request","body":payload,"more_body":False}
        parts=urlparse(path)
        headers=[(b"user-agent",self.user_agent.encode())]
        if self.sid: headers.append((b"cookie",f"sid={self.sid}".encode()))
        scope={"type":"http","method":method,"path":parts.path,"query_string":parts.query.encode(),"headers":headers,"client":(self.ip,1234)}
        req=Request(scope,receive)
        fn=getattr(self.mod,name)
        args={k:v[-1] for k,v in parse_qs(parts.query).items()}
        if name in ("admin_support_detail","admin_support_update","admin_support_unblock","admin_support_block","admin_support_delete","admin_support_reply"):
            args["request_id"]=int(parts.path.strip("/").split("/")[2])
        if name in ("admin_user_delete_page","admin_user_delete"):
            args["user_id"]=int(parts.path.strip("/").split("/")[2])
        if inspect.iscoroutinefunction(fn):
            task=fn(req,**args)
            try:
                task.send(None)
            except StopIteration as done:
                response=done.value
            else:
                raise RuntimeError("Unexpected async I/O in direct route test")
        else:
            response=fn(req,**args)
        cookie=response.headers.get("set-cookie","")
        if cookie.startswith("sid="): self.sid=cookie.split(";",1)[0].split("=",1)[1]
        return response
def body(r): return r.body.decode()
def csrf(r): return re.search(r'name="csrf" value="([^"]+)',body(r)).group(1)
def link(s): return re.search(r'http://127\.0\.0\.1:5173/\S+',s).group()

def test_hcaptcha_switch_and_server_verification(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        m.CAPTCHA_PROVIDER="hcaptcha"
        m.HCAPTCHA_SITE_KEY="h-site"
        assert m.captcha_provider()=="hcaptcha" and not m.captcha_ready()
        m.HCAPTCHA_SECRET_KEY="h-secret"
        assert not m.captcha_ready() and "HCAPTCHA_ORIGIN" in m.captcha_setup_notice()
        m.HCAPTCHA_ORIGIN="http://forma.localtest.me:5173"
        assert m.captcha_ready()
        browser=Browser(m,ip="192.0.2.5")
        registration=body(browser.call("register_page","/register?captcha_host=1"))
        assert 'class="h-captcha"' in registration and 'https://js.hcaptcha.com/1/api.js' in registration
        assert browser.call("login_page","/login").headers["location"]=="http://forma.localtest.me:5173/login?captcha_host=1"
        assert 'class="h-captcha"' in body(browser.call("login_page","/login?captcha_host=1"))
        m.GOOGLE_ID="client-id"
        m.GOOGLE_SECRET="client-secret"
        assert browser.call("google_start","/google/start").headers["location"]=="http://forma.localtest.me:5173/google/start?captcha_host=1"
        assert 'class="h-captcha"' in body(browser.call("google_start","/google/start?captcha_host=1"))
        assert 'class="cf-turnstile"' not in registration
        assert 'class="h-captcha"' in m.reset_body(m.session_from_raw(browser.sid),"sample-token")
        assert browser.call("register_page","/register").headers["location"]=="http://forma.localtest.me:5173/register?captcha_host=1"
        assert 'class="h-captcha"' in body(browser.call("register_page","/register?captcha_host=1"))
        assert browser.call("reset_page","/reset?token=abc").headers["location"]=="http://forma.localtest.me:5173/reset?token=abc&captcha_host=1"
        valid=True
        class FakeResponse:
            def raise_for_status(self): pass
            def json(self): return {"success":valid}
        class FakeClient:
            def __init__(self,timeout): assert timeout==10
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def post(self,url,data):
                assert url=="https://api.hcaptcha.com/siteverify"
                assert data=={"secret":"h-secret","sitekey":"h-site","response":"answer","remoteip":"192.0.2.5"}
                return FakeResponse()
        monkeypatch.setattr(m.httpx,"AsyncClient",FakeClient)
        def run(coro):
            try: coro.send(None)
            except StopIteration as result: return result.value
            raise AssertionError("Unexpected async I/O in fake verification")
        assert run(m.verify_captcha({"h-captcha-response":"answer"},"192.0.2.5","register"))
        valid=False
        assert not run(m.verify_captcha({"h-captcha-response":"answer"},"192.0.2.5","reset"))
        assert not run(m.verify_captcha({},"192.0.2.5","register"))
        with m.db() as c:
            c.execute("INSERT INTO users(email,password_hash,active,created_at) VALUES(?,?,1,?)",
                      ("hcaptcha@example.com",m.hash_password("StrongPass1!"),m.now()))
        login_page=browser.call("login_page","/login?captcha_host=1")
        missing=browser.call("login","/login",{"csrf":csrf(login_page),"email":"hcaptcha@example.com","password":"StrongPass1!"},auto_login_captcha=False)
        assert "Підтвердіть CAPTCHA" in body(missing)
        valid=True
        login_page=browser.call("login_page","/login?captcha_host=1")
        completed=browser.call("login","/login",{"csrf":csrf(login_page),"email":"hcaptcha@example.com","password":"StrongPass1!","h-captcha-response":"answer"},auto_login_captcha=False)
        assert completed.status_code==303 and completed.headers["location"]=="/profile"

def test_image_captcha_is_single_use_and_required(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        m.CAPTCHA_PROVIDER="image"
        assert m.captcha_ready()
        monkeypatch.setattr(m.secrets,"choice",lambda words: words[0])
        browser=Browser(m)
        page=browser.call("register_page","/register")
        assert "Введіть два слова з картинки" in body(page)
        assert 'name="captcha_text"' in body(page)
        assert 'class="h-captcha"' not in body(page)
        image=browser.call("captcha_image","/captcha/image?purpose=register")
        assert image.status_code==200 and image.body.startswith(b"\x89PNG\r\n\x1a\n")
        assert image.headers["cache-control"].startswith("no-store")
        fields={"csrf":csrf(page),"email":"words@example.com","password":"StrongPass1!","password_confirm":"StrongPass1!"}
        wrong=browser.call("register","/register",{**fields,"captcha_text":"ХИБА СЛОВА"})
        assert "CAPTCHA не підтверджено" in body(wrong)
        assert "CAPTCHA не підтверджено" in body(browser.call("register","/register",{**fields,"captcha_text":"ВЕСНА ВЕСНА"}))
        browser.call("captcha_image","/captcha/image?purpose=register")
        success=browser.call("register","/register",{**fields,"captcha_text":"весна   весна"})
        assert "Перевірте пошту" in body(success)
        assert "CAPTCHA не підтверджено" in body(browser.call("register","/register",{**fields,"captcha_text":"ВЕСНА ВЕСНА"}))
        assert browser.call("captcha_image","/captcha/image?purpose=invalid").status_code==400
        browser.call("captcha_image","/captcha/image?purpose=reset")
        session=m.session_from_raw(browser.sid)
        assert not m.verify_image_captcha(session,"ВЕСНА ВЕСНА","register")
        assert m.verify_image_captcha(session,"ВЕСНА ВЕСНА","reset")
        browser.call("captcha_image","/captcha/image?purpose=reset")
        current=m.now()
        m.now=lambda: current+301
        assert not m.verify_image_captcha(session,"ВЕСНА ВЕСНА","reset")

def test_totp_rfc_vector_and_code_spacing():
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        assert m.totp(secret,59)=="287082"
        m.now=lambda: 59
        assert m.verify_totp(secret,"287 082")
        assert not m.verify_totp(secret,"287083")
        drifted=m.totp(secret,59+120)
        assert not m.verify_totp(secret,drifted)
        assert m.totp_clock_drift(secret,drifted)==120

def test_project_flow():
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp)); m.local_pc_ip=lambda: "192.168.1.20"; b=Browser(m)
        p=b.call("register_page","/register")
        assert 'name="password_confirm"' in body(p)
        assert 'class="auth-main"' in body(p) and 'class="auth-mark"' in body(p)
        assert 'href="/login"' in body(p)
        weak=b.call("register","/register",{"csrf":csrf(p),"email":"student@example.com","password":"weak","password_confirm":"weak"})
        assert "8 символів" in body(weak) and "Реєстрація" in body(weak)
        p=b.call("register_page","/register")
        mismatch=b.call("register","/register",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!","password_confirm":"Different1!"})
        assert "Паролі не збігаються" in body(mismatch)
        p=b.call("register_page","/register")
        assert "CAPTCHA не підтверджено" in body(b.call("register","/register",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!","password_confirm":"StrongPass1!","cf-turnstile-response":"bad"}))
        p=b.call("register_page","/register")
        assert "Перевірте пошту" in body(b.call("register","/register",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!","password_confirm":"StrongPass1!","cf-turnstile-response":"verified-token"}))
        with m.db() as c:
            activation=link(c.execute("SELECT body FROM mail_outbox ORDER BY id DESC LIMIT 1").fetchone()[0])
        assert "активовано" in body(b.call("activate",activation))
        assert "недійсне" in body(b.call("activate",activation)).lower()
        p=b.call("login_page","/login")
        rejected=b.call("login","/login",{"csrf":csrf(p),"email":"student@example.com","password":"bad"},auto_login_captcha=False)
        assert "Підтвердіть CAPTCHA" in body(rejected)
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM login_log WHERE email='student@example.com'").fetchone()[0]==0
        for _ in range(5):
            p=b.call("login_page","/login")
            b.call("login","/login",{"csrf":csrf(p),"email":"student@example.com","password":"bad"})
        p=b.call("login_page","/login")
        assert "заблоковано" in body(b.call("login","/login",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!"}))
        with m.db() as c:
            assert c.execute("SELECT locked_until FROM users WHERE email='student@example.com'").fetchone()[0]>m.now()
            c.execute("UPDATE users SET locked_until=0 WHERE email='student@example.com'")
        p=b.call("login_page","/login")
        assert 'class="auth-main"' in body(p) and 'href="/register"' in body(p)
        assert b.call("login","/login",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!"}).status_code==303
        profile_response=b.call("profile","/profile")
        assert profile_response.status_code==303 and profile_response.headers["location"]=="/?view=profile"
        session_response=b.call("current_session","/session")
        assert session_response.status_code==200
        assert session_response.body and b'"csrf"' in session_response.body
        assert json.loads(body(session_response))["recent_events"]
        settings=b.call("profile_settings_page","/account/settings")
        assert 'name="display_name"' in body(settings) and 'name="birth_date"' in body(settings)
        invalid_info=b.call("update_profile_settings","/account/settings",{"csrf":csrf(settings),"display_name":"Марія","birth_date":"2026-02-30","bio":"Тести"})
        assert "коректну дату" in body(invalid_info)
        saved_info=b.call("update_profile_settings","/account/settings",{"csrf":csrf(settings),"display_name":"Марія","birth_date":"2002-05-10","bio":"Люблю тести <script>"})
        assert saved_info.headers["location"]=="/account/settings?saved=profile"
        account=json.loads(body(b.call("current_session","/session")))["user"]
        assert (account["display_name"],account["birth_date"],account["bio"])==("Марія","2002-05-10","Люблю тести <script>")
        assert "&lt;script&gt;" in body(b.call("profile_settings_page","/account/settings"))
        denied_login=b.call("update_account_login","/account/login",{"csrf":csrf(settings),"username":"Student_26","current_password":"wrong"})
        assert "поточний пароль" in body(denied_login)
        assert "зарезервовано" in body(b.call("update_account_login","/account/login",{"csrf":csrf(settings),"username":"admin","current_password":"StrongPass1!"}))
        changed_login=b.call("update_account_login","/account/login",{"csrf":csrf(settings),"username":"Student_26","current_password":"StrongPass1!"})
        assert changed_login.headers["location"]=="/account/settings?saved=login"
        assert json.loads(body(b.call("current_session","/session")))["user"]["username"]=="student_26"
        other=Browser(m,"Mozilla/5.0 (Android 14) Firefox/120.0","192.0.2.10")
        other_login=other.call("login_page","/login")
        assert other.call("login","/login",{"csrf":csrf(other_login),"email":"STUDENT_26","password":"StrongPass1!"}).status_code==303
        session_data=json.loads(body(b.call("current_session","/session")))
        assert len(session_data["sessions"])==2
        assert sum(item["current"] for item in session_data["sessions"])==1
        assert {item["device"] for item in session_data["sessions"]}=={"Chrome · Windows","Firefox · Android"}
        assert next(item for item in session_data["sessions"] if item["current"])["display_ip"]=="192.168.1.20"
        assert next(item for item in session_data["sessions"] if item["current"])["local_pc_ip"]
        assert next(item for item in session_data["sessions"] if not item["current"])["display_ip"]=="192.0.2.10"
        assert all(item["created_at"] and item["last_seen_at"] for item in session_data["sessions"])
        assert all("token_hash" not in item for item in session_data["sessions"])
        assert b.call("revoke_other_sessions","/sessions/revoke-others",{"csrf":"wrong"}).status_code==403
        revoked=b.call("revoke_other_sessions","/sessions/revoke-others",{"csrf":session_data["csrf"]})
        assert revoked.headers["location"]=="/?view=profile&sessions=revoked"
        assert other.call("current_session","/session").status_code==401
        assert len(json.loads(body(b.call("current_session","/session")))["sessions"])==1
        assert b.call("admin","/admin").status_code==403
        with m.db() as c:
            admin_id=c.execute("INSERT INTO users(email,username,password_hash,role,active,created_at) VALUES(?,'admin',?,'admin',1,?)",("admin@example.com",m.hash_password("AdminPass1!"),m.now())).lastrowid
            student_id=c.execute("SELECT id FROM users WHERE email='student@example.com'").fetchone()[0]
            c.execute("INSERT INTO users(email,username,created_at) VALUES(?,?,?)",("other@example.com","Taken",m.now()))
        collision=b.call("update_account_login","/account/login",{"csrf":csrf(settings),"username":"taken","current_password":"StrongPass1!"})
        assert "логін уже зайнятий" in body(collision)
        admin=Browser(m)
        p=admin.call("login_page","/login")
        assert admin.call("login","/login",{"csrf":csrf(p),"email":"admin","password":"AdminPass1!"}).status_code==303
        admin_settings=admin.call("profile_settings_page","/account/settings")
        assert "Логін адміністратора" in body(admin_settings)
        assert admin.call("update_account_login","/account/login",{"csrf":csrf(admin_settings),"username":"other","current_password":"AdminPass1!"}).status_code==403
        panel=admin.call("admin","/admin")
        assert "student@example.com" in body(panel) and "Усього акаунтів" in body(panel)
        assert "Останній IP входу" in body(panel) and "192.168.1.20" in body(panel)
        assert "Журнал аудиту" in body(panel) and "Останні події" in body(panel)
        assert "Невдала спроба входу" in body(admin.call("admin","/admin?tab=audit"))
        assert admin.call("admin_block","/admin/block",{"csrf":csrf(panel),"user_id":str(admin_id),"action":"block"}).status_code==400
        assert admin.call("admin_block","/admin/block",{"csrf":csrf(panel),"user_id":str(student_id),"action":"other"}).status_code==400
        assert admin.call("admin_block","/admin/block",{"csrf":csrf(panel),"user_id":str(student_id),"action":"block"}).status_code==303
        assert b.call("profile","/profile").status_code==303
        assert "Акаунти із захистом 2FA" in body(admin.call("admin","/admin?tab=twofa"))
        assert "Журнал аудиту спроб входу та атак" in body(admin.call("admin","/admin?tab=audit"))
        panel=admin.call("admin","/admin")
        assert admin.call("admin_block","/admin/block",{"csrf":csrf(panel),"user_id":str(student_id),"action":"unblock"}).status_code==303
        assert admin_id != student_id
        p=b.call("login_page","/login")
        assert b.call("login","/login",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!"}).status_code==303
        p=b.call("setup_2fa","/2fa/setup")
        assert "totp-qr" in body(p)
        assert "Ключ для ручного введення" in body(p)
        assert "otpauth://totp/" not in body(p)
        secret=re.search(r'<div class="secret">([^<]+)',body(p)).group(1)
        marker=m.hashlib.sha256(secret.encode()).hexdigest()[:4].upper()
        assert marker in body(p)
        refreshed=b.call("setup_2fa","/2fa/setup")
        assert re.search(r'<div class="secret">([^<]+)',body(refreshed)).group(1)==secret
        invalid=b.call("setup_2fa_post","/2fa/setup",{"csrf":csrf(refreshed),"code":"0000000"})
        assert "Код не відповідає поточному QR-коду" in body(invalid) and secret in body(invalid)
        drifted=b.call("setup_2fa_post","/2fa/setup",{"csrf":csrf(invalid),"code":m.totp(secret,m.now()+120)})
        assert "час телефону відрізняється" in body(drifted)
        assert b.call("restart_2fa_setup","/2fa/setup/restart",{"csrf":csrf(invalid)}).status_code==303
        refreshed=b.call("setup_2fa","/2fa/setup")
        new_secret=re.search(r'<div class="secret">([^<]+)',body(refreshed)).group(1)
        assert new_secret!=secret
        secret=new_secret
        spaced_code=m.totp(secret)
        assert b.call("setup_2fa_post","/2fa/setup",{"csrf":csrf(refreshed),"code":spaced_code[:3]+" "+spaced_code[3:]}).status_code==303
        protected_panel=admin.call("admin","/admin?tab=twofa")
        assert "student@example.com" in body(protected_panel)
        assert re.search(r'Захищені 2FA</span><strong>1</strong>',body(protected_panel))
        csrf_value=json.loads(body(b.call("current_session","/session")))["csrf"]
        b.call("logout","/logout",{"csrf":csrf_value})
        p=b.call("login_page","/login")
        assert b.call("login","/login",{"csrf":csrf(p),"email":"STUDENT_26","password":"StrongPass1!"}).headers["location"]=="/2fa"
        p=b.call("two_factor_page","/2fa")
        assert b.call("two_factor","/2fa",{"csrf":csrf(p),"code":m.totp(secret)}).headers["location"]=="/profile"
        protected_forgot=b.call("forgot_page","/forgot")
        assert 'name="email"' not in body(protected_forgot) and 'name="code"' in body(protected_forgot)
        with m.db() as c:
            mail_count=c.execute("SELECT count(*) FROM mail_outbox WHERE subject='Відновлення пароля'").fetchone()[0]
        invalid_forgot=b.call("forgot","/forgot",{"csrf":csrf(protected_forgot),"code":"000000"})
        assert "актуальний код" in body(invalid_forgot)
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM mail_outbox WHERE subject='Відновлення пароля'").fetchone()[0]==mail_count
        guest=Browser(m)
        guest_forgot=guest.call("forgot_page","/forgot")
        assert 'Email або логін акаунта' in body(guest_forgot)
        assert "актуальний код" in body(guest.call("forgot","/forgot",{"csrf":csrf(guest_forgot),"email":"STUDENT_26"}))
        protected_forgot=b.call("forgot_page","/forgot")
        assert "st*****@e******.com" in body(b.call("forgot","/forgot",{"csrf":csrf(protected_forgot),"code":m.totp(secret)}))
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM mail_outbox WHERE subject='Відновлення пароля'").fetchone()[0]==mail_count+1
        manage=b.call("disable_2fa_page","/2fa/disable")
        assert "Керування 2FA" in body(manage) and 'name="password"' in body(manage)
        assert 'class="security-main"' in body(manage) and 'class="security-panel"' in body(manage)
        invalid_disable=b.call("disable_2fa","/2fa/disable",{"csrf":csrf(manage),"password":"StrongPass1!","code":"0000000"})
        assert "Невірний пароль або код" in body(invalid_disable)
        assert b.call("disable_2fa","/2fa/disable",{"csrf":csrf(invalid_disable),"password":"StrongPass1!","code":m.totp(secret)}).headers["location"]=="/profile"
        assert b.call("disable_2fa_page","/2fa/disable").headers["location"]=="/profile"
        p=b.call("forgot_page","/forgot")
        assert 'name="email"' not in body(p)
        assert "student@example.com" not in body(p)
        result=b.call("forgot","/forgot",{"csrf":csrf(p),"email":"attacker@example.com"})
        assert "st*****@e******.com" in body(result)
        with m.db() as c: reset=link(c.execute("SELECT body FROM mail_outbox ORDER BY id DESC LIMIT 1").fetchone()[0])
        p=b.call("reset_page",reset)
        token=re.search(r'name="token" value="([^"]+)',body(p)).group(1)
        assert 'class="auth-main"' in body(p)
        assert 'name="password_confirm"' in body(p) and 'data-action="reset"' in body(p)
        reset_fields={"csrf":csrf(p),"token":token,"password":"NewStrong2!","password_confirm":"NewStrong2!","cf-turnstile-response":"reset-token"}
        mismatch_fields={**reset_fields,"password_confirm":"Different2!"}
        assert "Паролі не збігаються" in body(b.call("reset","/reset",mismatch_fields))
        assert "CAPTCHA не підтверджено" in body(b.call("reset","/reset",{**reset_fields,"cf-turnstile-response":"bad"}))
        assert "Пароль оновлено" in body(b.call("reset","/reset",reset_fields))
        assert "недійсне" in body(b.call("reset_page",reset)).lower()
        assert b.call("profile","/profile").status_code==303
        assert b.call("google_start","/google/start").status_code==503
        m.GOOGLE_ID="test-google-id"
        m.GOOGLE_SECRET="test-google-secret"
        google_page=b.call("google_start","/google/start")
        assert 'data-action="login"' in body(google_page)
        assert "Підтвердіть CAPTCHA" in body(b.call("google_start_submit","/google/start",{"csrf":csrf(google_page)}))
        google_page=b.call("google_start","/google/start")
        google_response=b.call("google_start_submit","/google/start",{"csrf":csrf(google_page),"cf-turnstile-response":"verified-token"})
        assert google_response.status_code==303 and google_response.headers["location"].startswith("https://accounts.google.com/")
        with m.db() as c:
            events={x[0] for x in c.execute("SELECT event FROM audit_log")}
        assert {"account_registered","captcha_failed","login_failure","login_lockout","admin_blocked",
                "other_sessions_revoked",
                "admin_unblocked","two_factor_enabled","password_reset_completed"} <= events

def test_real_smtp_delivery(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        m.DEMO_MODE=False
        for key,value in {"SMTP_HOST":"smtp.gmail.com","SMTP_PORT":"587",
                          "SMTP_USER":"sender@gmail.com","SMTP_PASSWORD":"app-password",
                          "SMTP_FROM":"sender@gmail.com"}.items():
            monkeypatch.setenv(key,value)
        delivered=[]
        class FakeSMTP:
            def __init__(self,host,port,timeout):
                assert host=="smtp.gmail.com" and port==587
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def ehlo(self): pass
            def starttls(self,context): assert context
            def login(self,user,password):
                assert user=="sender@gmail.com" and password=="app-password"
            def send_message(self,message): delivered.append(message)
        monkeypatch.setattr(m.smtplib,"SMTP",FakeSMTP)
        m.mail("recipient@example.com","Активація","https://example.com/activate")
        assert len(delivered)==1
        assert delivered[0]["To"]=="recipient@example.com"
        with m.db() as c:
            assert c.execute("SELECT body FROM mail_outbox").fetchone()[0]==""

def test_five_failed_logins_send_one_alert_and_admin_can_review_mail(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        with m.db() as c:
            c.execute("INSERT INTO users(email,username,password_hash,role,active,created_at) VALUES(?,'admin',?,'admin',1,?)",
                      ("admin@example.com",m.hash_password("AdminPass1!"),m.now()))
            c.execute("INSERT INTO users(email,password_hash,active,created_at) VALUES(?,?,1,?)",
                      ("student@example.com",m.hash_password("StrongPass1!"),m.now()))
        logged=Browser(m,ip="192.0.2.55")
        p=logged.call("login_page","/login")
        assert logged.call("login","/login",{"csrf":csrf(p),"email":"student@example.com","password":"StrongPass1!"}).status_code==303
        browser=Browser(m)
        login_page=browser.call("login_page","/login")
        fields={"csrf":csrf(login_page),"email":"student@example.com","password":"incorrect"}
        for _ in range(4):
            assert "Невірні облікові дані" in body(browser.call("login","/login",fields))
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM mail_outbox").fetchone()[0]==0
        browser.call("login","/login",fields)
        with m.db() as c:
            messages=c.execute("SELECT recipient,subject,body FROM mail_outbox").fetchall()
            locked=c.execute("SELECT locked_until FROM users WHERE email='student@example.com'").fetchone()[0]
        assert len(messages)==1 and messages[0]["recipient"]=="student@example.com"
        assert "5 разів" in messages[0]["body"] and "http://127.0.0.1:5173/support" in messages[0]["body"]
        assert locked>m.now()
        support=browser.call("support_page","/support")
        assert 'action="/support"' in body(support)
        assert "Ми переглянемо звернення в панелі адміністратора" not in body(support)
        assert browser.call("support_submit","/support",{"csrf":"wrong","email":"student@example.com","message":"Підозріла спроба входу"}).status_code==403
        submitted=browser.call("support_submit","/support",{"csrf":csrf(support),"email":"student@example.com","category":"security","subject":"Підозріла спроба входу","message":"Це був не мій вхід <script>","steps":"Отримав попередження на пошту"})
        assert "Звернення надіслано" in body(submitted)
        assert "Адміністратор побачить його у вкладці підтримки" not in body(submitted)
        browser.call("login","/login",fields)
        unknown={**fields,"email":"absent@example.com"}
        for _ in range(5): browser.call("login","/login",unknown)
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM mail_outbox").fetchone()[0]==1
        assert browser.call("admin","/admin?tab=mails").status_code==403
        admin=Browser(m,ip="192.0.2.30")
        p=admin.call("login_page","/login")
        assert admin.call("login","/login",{"csrf":csrf(p),"email":"admin","password":"AdminPass1!"}).status_code==303
        panel=body(admin.call("admin","/admin?tab=mails"))
        assert "Надіслані листи (1)" in panel
        assert "student@example.com" in panel and "Попередження про спроби входу" in panel
        support_panel=body(admin.call("admin","/admin?tab=support"))
        assert "Підтримка (1)" in support_panel and "Підозріла спроба входу" in support_panel
        assert 'href="/admin/support/1"' in support_panel
        assert browser.call("admin_support_detail","/admin/support/1").status_code==403
        detail_response=admin.call("admin_support_detail","/admin/support/1")
        detail=body(detail_response)
        assert "Отримав попередження на пошту" in detail and "Останні спроби входу" in detail
        assert "Тимчасово обмежено" in detail and "&lt;script&gt;" in detail and "<script>" not in detail
        assert "IP успішних входів" in detail and "192.0.2.55" in detail and "Невдалих спроб загалом" in detail
        assert 'action="/admin/support/1/unblock"' in detail and 'action="/admin/support/1/delete"' in detail
        assert 'action="/admin/support/1/reply"' in detail
        assert admin.call("admin_support_update","/admin/support/1",{"csrf":"wrong","status":"resolved","admin_note":"Перевірено"}).status_code==403
        assert admin.call("admin_support_update","/admin/support/1",{"csrf":csrf(detail_response),"status":"in_progress","admin_note":"Перевірити журнал входів"}).status_code==303
        updated=body(admin.call("admin_support_detail","/admin/support/1"))
        assert "У роботі" in updated and "Перевірити журнал входів" in updated
        assert browser.call("admin_support_unblock","/admin/support/1/unblock",{"csrf":csrf(detail_response)}).status_code==403
        assert admin.call("admin_support_unblock","/admin/support/1/unblock",{"csrf":csrf(detail_response)}).status_code==303
        with m.db() as c:
            assert c.execute("SELECT locked_until FROM users WHERE email='student@example.com'").fetchone()[0]==0
        assert logged.call("current_session","/session").status_code==200
        active_detail=body(admin.call("admin_support_detail","/admin/support/1"))
        assert 'action="/admin/support/1/block"' in active_detail
        assert 'action="/admin/support/1/unblock"' not in active_detail
        assert admin.call("admin_support_block","/admin/support/1/block",{"csrf":"wrong"}).status_code==403
        blocked=admin.call("admin_support_block","/admin/support/1/block",{"csrf":csrf(detail_response)})
        assert blocked.status_code==303 and "action=blocked" in blocked.headers["location"]
        assert logged.call("current_session","/session").status_code==401
        blocked_detail=body(admin.call("admin_support_detail","/admin/support/1"))
        assert 'action="/admin/support/1/unblock"' in blocked_detail
        assert 'action="/admin/support/1/block"' not in blocked_detail
        assert admin.call("admin_support_unblock","/admin/support/1/unblock",{"csrf":csrf(detail_response)}).status_code==303
        reply=admin.call("admin_support_reply","/admin/support/1/reply",{"csrf":csrf(detail_response),"reply_body":"Ми перевірили спроби входу. Змініть пароль."})
        assert reply.status_code==303 and "reply=sent" in reply.headers["location"]
        with m.db() as c:
            sent=c.execute("SELECT recipient,body,support_request_id FROM mail_outbox WHERE support_request_id=1").fetchone()
        assert tuple(sent)==("student@example.com","Вітаємо!\n\nМи перевірили спроби входу. Змініть пароль.\n\nForma · Підтримка",1)
        assert "Надіслані відповіді" in body(admin.call("admin_support_detail","/admin/support/1"))
        audit_panel=body(admin.call("admin","/admin?tab=audit"))
        assert "IP користувача" in audit_panel and "IP дії" in audit_panel
        assert re.search(r"support_reply_sent.*student@example.com.*192\.0\.2\.55.*192\.0\.2\.30",audit_panel,re.S)
        monkeypatch.setattr(m,"mail",lambda *args: (_ for _ in ()).throw(OSError("SMTP unavailable")))
        failed_reply=admin.call("admin_support_reply","/admin/support/1/reply",{"csrf":csrf(detail_response),"reply_body":"Повторна відповідь до користувача"})
        assert failed_reply.status_code==303 and "reply=failed" in failed_reply.headers["location"]
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM mail_outbox WHERE support_request_id=1").fetchone()[0]==1
            assert c.execute("SELECT count(*) FROM audit_log WHERE event='support_reply_failed'").fetchone()[0]==1
        assert admin.call("admin_support_delete","/admin/support/1/delete",{"csrf":csrf(detail_response),"confirm_email":"student@example.com","confirm_word":"wrong"}).status_code==400
        with m.db() as c:
            deleted_id=c.execute("SELECT id FROM users WHERE email='student@example.com'").fetchone()[0]
        assert admin.call("admin_support_delete","/admin/support/1/delete",{"csrf":csrf(detail_response),"confirm_email":"student@example.com","confirm_word":"ВИДАЛИТИ"}).status_code==303
        assert logged.call("current_session","/session").status_code==401
        with m.db() as c:
            assert c.execute("SELECT count(*) FROM users WHERE email='student@example.com'").fetchone()[0]==0
            assert m.next_user_id(c)>deleted_id
        assert "Акаунта з таким email не знайдено" in body(admin.call("admin_support_detail","/admin/support/1"))
        with m.db() as c:
            c.execute("INSERT INTO support_requests(email,message,ip,created_at) VALUES(?,?,?,?)",
                      ("admin@example.com","Питання адміністратора","192.0.2.30",m.now()))
        assert admin.call("admin_support_delete","/admin/support/2/delete",{"csrf":csrf(detail_response),"confirm_email":"admin@example.com","confirm_word":"ВИДАЛИТИ"}).status_code==403
        with m.db() as c:
            c.executemany("INSERT INTO mail_outbox(recipient,subject,body,created_at) VALUES(?,?,?,?)",
                          [("test@example.com",f"Лист {n}","",m.now()) for n in range(51)])
        assert "Наступна" in body(admin.call("admin","/admin?tab=mails"))
        assert "Попередня" in body(admin.call("admin","/admin?tab=mails&mail_page=2"))

def test_failed_alert_delivery_does_not_undo_lockout(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        with m.db() as c:
            c.execute("INSERT INTO users(email,password_hash,active,created_at) VALUES(?,?,1,?)",
                      ("student@example.com",m.hash_password("StrongPass1!"),m.now()))
        def fail_mail(*args): raise OSError("SMTP unavailable")
        monkeypatch.setattr(m,"mail",fail_mail)
        browser=Browser(m)
        p=browser.call("login_page","/login")
        fields={"csrf":csrf(p),"email":"student@example.com","password":"incorrect"}
        for _ in range(5): browser.call("login","/login",fields)
        with m.db() as c:
            assert c.execute("SELECT locked_until FROM users WHERE email='student@example.com'").fetchone()[0]>m.now()
            assert c.execute("SELECT count(*) FROM audit_log WHERE event='login_alert_delivery_failed'").fetchone()[0]==1

def test_existing_support_requests_survive_detail_migration():
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        folder=Path(tmp)
        c=sqlite3.connect(folder/"test.sqlite3")
        try:
            c.execute("CREATE TABLE support_requests(id INTEGER PRIMARY KEY,email TEXT NOT NULL,message TEXT NOT NULL,ip TEXT NOT NULL,created_at INTEGER NOT NULL)")
            c.execute("INSERT INTO support_requests(email,message,ip,created_at) VALUES(?,?,?,?)",
                      ("student@example.com","Старе звернення","127.0.0.1",1))
            c.commit()
        finally:
            c.close()
        m=load(folder)
        with m.db() as c:
            item=c.execute("SELECT message,category,subject,steps,status,admin_note FROM support_requests WHERE id=1").fetchone()
            mail_columns={row["name"] for row in c.execute("PRAGMA table_info(mail_outbox)")}
        assert tuple(item)==("Старе звернення","other","","","new","")
        assert "support_request_id" in mail_columns

def test_admin_can_delete_user_from_user_list():
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        with m.db() as c:
            admin_id=c.execute("INSERT INTO users(email,username,password_hash,role,active,created_at) VALUES(?,'admin',?,'admin',1,?)",("admin@example.com",m.hash_password("AdminPass1!"),m.now())).lastrowid
            user_id=c.execute("INSERT INTO users(email,username,password_hash,active,created_at) VALUES(?,?,?,1,?)",("student@example.com","student",m.hash_password("StrongPass1!"),m.now())).lastrowid
        user=Browser(m)
        login_page=user.call("login_page","/login")
        assert user.call("login","/login",{"csrf":csrf(login_page),"email":"student@example.com","password":"StrongPass1!"}).status_code==303
        admin=Browser(m)
        login_page=admin.call("login_page","/login")
        assert admin.call("login","/login",{"csrf":csrf(login_page),"email":"admin","password":"AdminPass1!"}).status_code==303
        panel=body(admin.call("admin","/admin?tab=users"))
        assert f'href="/admin/users/{user_id}/delete"' in panel
        assert f'href="/admin/users/{admin_id}/delete"' not in panel
        path=f"/admin/users/{user_id}/delete"
        assert user.call("admin_user_delete_page",path).status_code==403
        assert user.call("admin_user_delete",path,{"csrf":"bad","confirm_email":"student@example.com","confirm_word":"ВИДАЛИТИ"}).status_code==403
        confirmation=admin.call("admin_user_delete_page",path)
        assert "student@example.com" in body(confirmation)
        assert admin.call("admin_user_delete",path,{"csrf":"bad","confirm_email":"student@example.com","confirm_word":"ВИДАЛИТИ"}).status_code==403
        assert admin.call("admin_user_delete",path,{"csrf":csrf(confirmation),"confirm_email":"student@example.com","confirm_word":"wrong"}).status_code==400
        assert admin.call("admin_user_delete",f"/admin/users/{admin_id}/delete",{"csrf":csrf(confirmation),"confirm_email":"admin@example.com","confirm_word":"ВИДАЛИТИ"}).status_code==403
        deleted=admin.call("admin_user_delete",path,{"csrf":csrf(confirmation),"confirm_email":"student@example.com","confirm_word":"ВИДАЛИТИ"})
        assert deleted.status_code==303 and deleted.headers["location"]=="/admin?tab=users"
        assert user.call("current_session","/session").status_code==401
        with m.db() as c:
            assert c.execute("SELECT 1 FROM users WHERE id=?",(user_id,)).fetchone() is None
            assert c.execute("SELECT 1 FROM users WHERE id=?",(admin_id,)).fetchone() is not None
            assert tuple(c.execute("SELECT event,actor_email,target_email FROM audit_log WHERE event='admin_account_deleted'").fetchone())==("admin_account_deleted","admin@example.com","student@example.com")
            assert m.next_user_id(c)>user_id

def test_google_account_link_and_login(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp)); m.GOOGLE_ID="client-id"; m.GOOGLE_SECRET="client-secret"
        with m.db() as c:
            c.execute("INSERT INTO users(email,password_hash,active,created_at) VALUES(?,?,1,?)",
                      ("student@example.com",m.hash_password("StrongPass1!"),m.now()))
        browser=Browser(m)
        login_page=browser.call("login_page","/login")
        assert browser.call("login","/login",{"csrf":csrf(login_page),"email":"student@example.com","password":"StrongPass1!"}).status_code==303
        start=browser.call("google_link_start","/google/link/start")
        assert start.status_code==303
        state=parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        assert state.startswith("link.")
        nonce=m.session_from_raw(browser.sid)["oidc_nonce"]
        google_email="someone-else@example.com"
        google_sub="google-user-123"
        class FakeResponse:
            def __init__(self,payload): self.payload=payload
            def raise_for_status(self): pass
            def json(self): return self.payload
        class FakeClient:
            def __init__(self,timeout): pass
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def post(self,*args,**kwargs): return FakeResponse({"id_token":"signed-token"})
            async def get(self,*args,**kwargs):
                return FakeResponse({"aud":m.GOOGLE_ID,"iss":"https://accounts.google.com",
                    "nonce":nonce,"email_verified":"true","exp":str(m.now()+3600),
                    "sub":google_sub,"email":google_email})
        monkeypatch.setattr(m.httpx,"AsyncClient",FakeClient)
        callback=browser.call("google_callback","/google/callback?code=one-time-code&state="+state)
        assert "Адреси не збігаються" in body(callback)
        with m.db() as c:
            assert c.execute("SELECT google_sub FROM users WHERE email='student@example.com'").fetchone()[0] is None
        start=browser.call("google_link_start","/google/link/start")
        state=parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        cancelled=browser.call("google_callback","/google/callback?error=access_denied&state="+state)
        assert "Вхід через Google скасовано" in body(cancelled)
        assert browser.call("google_callback","/google/callback?code=replay&state="+state).status_code==403
        google_email="student@example.com"
        start=browser.call("google_link_start","/google/link/start")
        state=parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        nonce=m.session_from_raw(browser.sid)["oidc_nonce"]
        callback_browser=Browser(m)
        callback=callback_browser.call("google_callback","/google/callback?code=one-time-code&state="+state)
        assert callback.status_code==303 and callback.headers["location"]=="/profile"
        browser=callback_browser
        assert json.loads(body(browser.call("current_session","/session")))["user"]["google_connected"]
        with m.db() as c:
            assert c.execute("SELECT google_sub FROM users WHERE email='student@example.com'").fetchone()[0]=="google-user-123"
        browser=Browser(m)
        start=browser.call("google_start","/google/start")
        assert 'data-action="login"' in body(start)
        assert "Підтвердіть CAPTCHA" in body(browser.call("google_start_submit","/google/start",{"csrf":csrf(start)}))
        start=browser.call("google_start_submit","/google/start",{"csrf":csrf(start),"cf-turnstile-response":"verified-token"})
        state=parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        assert state.startswith("login.")
        nonce=m.session_from_raw(browser.sid)["oidc_nonce"]
        callback=browser.call("google_callback","/google/callback?code=one-time-code&state="+state)
        assert callback.status_code==303 and callback.headers["location"]=="/profile"
        assert json.loads(body(browser.call("current_session","/session")))["user"]["email"]=="student@example.com"
        google_email="new-google@example.com"
        google_sub="google-user-456"
        browser=Browser(m)
        start=browser.call("google_start","/google/start")
        start=browser.call("google_start_submit","/google/start",{"csrf":csrf(start),"cf-turnstile-response":"verified-token"})
        state=parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        nonce=m.session_from_raw(browser.sid)["oidc_nonce"]
        callback=browser.call("google_callback","/google/callback?code=one-time-code&state="+state)
        assert callback.status_code==303 and callback.headers["location"]=="/profile"
        assert json.loads(body(browser.call("current_session","/session")))["user"]["email"]=="new-google@example.com"
        with m.db() as c:
            account=c.execute("SELECT google_sub,password_hash,active FROM users WHERE email=?",(google_email,)).fetchone()
        assert tuple(account)==("google-user-456",None,1)

def test_admin_setup_uses_admin_login(monkeypatch):
    work=Path(__file__).resolve().parents[2]/"work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        m=load(Path(tmp))
        import getpass
        monkeypatch.setattr(getpass,"getpass",lambda prompt: "AdminStrong1!")
        m.init_admin()
        browser=Browser(m)
        p=browser.call("login_page","/login")
        assert browser.call("login","/login",{"csrf":csrf(p),"email":"admin","password":"AdminStrong1!"}).status_code==303
        panel=browser.call("admin","/admin")
        assert "Усього акаунтів" in body(panel)
        assert "Захищені 2FA" in body(panel)
        with m.db() as c:
            admin_user=c.execute("SELECT username,role FROM users WHERE email='admin@forma.local'").fetchone()
            assert tuple(admin_user)==("admin","admin")
