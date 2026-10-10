"""Проверка расширения браузера в настоящем Chromium (10 проверок).

Запускает «Фокус-пруд» на порту 8765 с временной базой, загружает папку
extension/ в Chromium и проверяет блокировку. Не трогает вашу базу и правила.

    pip install -r requirements-dev.txt && python -m playwright install chromium
    python scripts/check_extension.py
"""
import json, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent; EXT = str(ROOT / "extension")
BASE = "http://127.0.0.1:8765"; tmp = Path(tempfile.mkdtemp(prefix="ffe2e_"))

def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")

server = subprocess.Popen([str(ROOT / ".venv/Scripts/python.exe"), "-m", "focusfarm", "--dev",
    "--no-browser", "--db", str(tmp / "t.db"), "--fresh"], cwd=ROOT,
    stdout=open(tmp / "server.log", "w"), stderr=subprocess.STDOUT)
results = []
def check(name, ok, extra=""):
    results.append(ok); print(("PASS" if ok else "FAIL"), name, extra)

try:
    for _ in range(40):
        try: call("GET", "/api/state"); break
        except Exception: time.sleep(0.5)
    call("PUT", "/api/settings", {"protection": {"strictness": "hard", "targets": "pc"}})

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(tmp / "profile"), headless=False,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=10000)

        def tab_urls():     # адреса всех вкладок — прямо из браузера
            return json.loads(sw.evaluate("chrome.tabs.query({}).then(ts=>JSON.stringify(ts.map(t=>t.url||t.pendingUrl||'')))"))
        def wait_blocked(site, secs=15):
            for _ in range(int(secs * 2)):
                if any("blocked.html" in u and site in u for u in tab_urls()): return True
                time.sleep(0.5)
            return False
        def open_tab(url):
            pg = ctx.new_page()
            try: pg.goto(url, timeout=8000)
            except Exception: pass
            return pg

        # A. нет сессии — не блокируем
        a = open_tab("http://youtube.com/"); time.sleep(2)
        check("A нет сессии: youtube.com не заблокирован", not any("blocked.html" in u for u in tab_urls()), str(tab_urls()))
        a.close()

        # B. жёсткая сессия — блокируем
        call("POST", "/api/session/start", {"without_phone": True})
        b = open_tab("http://youtube.com/")
        check("B сессия: youtube.com заблокирован", wait_blocked("youtube.com"))
        b2 = open_tab("http://www.youtube.com/watch?v=1")
        check("B поддомен www.youtube.com заблокирован", wait_blocked("www.youtube.com"))
        blocked_page = next((pg for pg in ctx.pages if "blocked.html" in pg.url), None)
        if blocked_page:
            check("B на странице видно название сайта", "youtube.com" in blocked_page.inner_text("#site"))
            check("B на странице видно время до конца", "мин" in blocked_page.inner_text("#left"), blocked_page.inner_text("#left"))
        for pg in list(ctx.pages)[1:]:
            try: pg.close()
            except Exception: pass

        # C. сайт не из списка открывается
        c = open_tab(BASE + "/"); time.sleep(1.5)
        check("C сайт не из списка (127.0.0.1) открывается", BASE in " ".join(tab_urls()))
        c.close()
        check("D сервер видит расширение", call("GET", "/api/state")["protection"]["extension_connected"] is True)

        # E. пауза — не блокируем
        call("POST", "/api/session/pause")
        e = open_tab("http://youtube.com/"); time.sleep(2)
        check("E пауза: youtube.com не заблокирован", not any("blocked.html" in u for u in tab_urls()), str(tab_urls()))

        # F. вкладка уже открыта; пауза снята → будильник (раз в 30 с) закрывает её
        call("POST", "/api/session/resume")
        t0 = time.time()
        ok = wait_blocked("youtube.com", secs=50)
        check("F открытая вкладка блокируется будильником", ok, f"через {time.time()-t0:.0f} с")

        # G. мягкий режим — страницу не закрываем
        for pg in list(ctx.pages)[1:]:
            try: pg.close()
            except Exception: pass
        call("PUT", "/api/settings", {"protection": {"strictness": "soft"}})
        g = open_tab("http://youtube.com/"); time.sleep(3)
        check("G мягкий режим: страница не заменена", not any("blocked.html" in u for u in tab_urls()), str(tab_urls()))
        ctx.close()
finally:
    server.terminate()
print("ИТОГО:", sum(results), "из", len(results))
sys.exit(0 if all(results) else 1)
