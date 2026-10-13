"""Проверка расширения браузера в настоящем Firefox (Linux, Windows, macOS).

Запускает «Фокус-пруд» на порту 8765 с временной базой, ставит расширение из extension/
во временный профиль Firefox (ваш профиль не трогает) и проверяет блокировку сайта.
Браузером управляем через встроенный в Firefox протокол Marionette — без новых зависимостей.

    python scripts/check_extension_firefox.py            (FIREFOX=путь, если firefox не в PATH)
"""
import http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"
EXT_ID = "focus-pond@carpo.local"
SITE = "twitch.tv"            # запретный сайт из правил; Firefox отправит его на 127.0.0.1
MARIONETTE_PORT = 2839
tmp = Path(tempfile.mkdtemp(prefix="ffx_"))


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")


class Marionette:
    """Самый простой клиент Marionette: сообщения вида «длина:json»."""

    def __init__(self, port):
        for _ in range(60):
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=30)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Firefox не открыл Marionette")
        self.buf, self.msg_id = b"", 0
        self._read()                                      # приветствие
        self.cmd("WebDriver:NewSession", {"capabilities": {}})

    def _read(self):
        while b":" not in self.buf:
            self.buf += self.sock.recv(65536)
        size, _, rest = self.buf.partition(b":")
        while len(rest) < int(size):
            rest += self.sock.recv(65536)
        self.buf = rest[int(size):]
        return json.loads(rest[:int(size)])

    def cmd(self, name, params=None):
        self.msg_id += 1
        data = json.dumps([0, self.msg_id, name, params or {}]).encode()
        self.sock.sendall(str(len(data)).encode() + b":" + data)
        while True:
            reply = self._read()
            if reply[1] == self.msg_id:
                if reply[2]:
                    raise RuntimeError(reply[2].get("message", reply[2]))
                return reply[3]


class Quiet(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write("<title>тестовая страница</title>ok".encode())
    def log_message(self, *args): pass


def make_profile() -> Path:
    profile = tmp / "profile"
    (profile / "extensions").mkdir(parents=True)
    with zipfile.ZipFile(profile / "extensions" / f"{EXT_ID}.xpi", "w") as xpi:
        for f in (ROOT / "extension").rglob("*"):
            if f.is_file():
                xpi.write(f, f.relative_to(ROOT / "extension"))
    prefs = {
        "xpinstall.signatures.required": False,       # расширение не подписано Mozilla
        "extensions.autoDisableScopes": 0, "extensions.enabledScopes": 15,
        "network.dns.localDomains": f"{SITE},www.{SITE}",
        "network.stricttransportsecurity.preloadlist": False, "dom.security.https_first": False,
        "marionette.port": MARIONETTE_PORT, "browser.shell.checkDefaultBrowser": False,
        "datareporting.policy.dataSubmissionEnabled": False, "browser.aboutwelcome.enabled": False,
    }
    (profile / "user.js").write_text("".join(f"user_pref({json.dumps(k)}, {json.dumps(v)});\n"
                                             for k, v in prefs.items()))
    return profile


results = []
def check(name, ok, extra=""):
    results.append(ok); print(("PASS" if ok else "FAIL"), name, extra, flush=True)


def main():
    firefox = os.environ.get("FIREFOX") or shutil.which("firefox") or shutil.which("firefox-esr")
    if not firefox:
        print("Firefox не найден (укажите путь в переменной FIREFOX)"); return 2
    fake = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    fake_url = f"http://{SITE}:{fake.server_address[1]}/"
    server = subprocess.Popen([sys.executable, "-m", "focusfarm", "--dev", "--no-browser",
                               "--db", str(tmp / "t.db"), "--fresh"], cwd=ROOT,
                              stdout=open(tmp / "server.log", "w"), stderr=subprocess.STDOUT)
    browser = None
    try:
        for _ in range(40):
            try: call("GET", "/api/state"); break
            except Exception: time.sleep(0.5)
        call("PUT", "/api/strict/password", {"new": "pw12345"})   # в жёстком режиме конец — по паролю
        call("PUT", "/api/settings", {"protection": {"strictness": "hard", "targets": "pc"}})
        browser = subprocess.Popen([firefox, "--headless", "--no-remote", "--marionette",
                                    "--profile", str(make_profile())],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ff = Marionette(MARIONETTE_PORT)

        def visit(url):
            try: ff.cmd("WebDriver:Navigate", {"url": url})
            except RuntimeError: pass          # расширение подменило страницу во время загрузки
            time.sleep(1)
            return ff.cmd("WebDriver:GetCurrentURL")["value"]

        connected = False
        for _ in range(40):                    # расширение опрашивает программу сразу после запуска
            connected = call("GET", "/api/extension/browsers")["connected"]
            if connected: break
            time.sleep(0.5)
        check("A расширение установилось и нашло программу", connected)

        url = visit(fake_url)
        check("B нет сессии: сайт открывается", "blocked.html" not in url, url)

        call("POST", "/api/session/start", {"without_phone": True})
        url = ""
        for _ in range(10):
            url = visit(fake_url)
            if "blocked.html" in url: break
        check("C сессия: сайт заменён страницей «время учёбы»", "blocked.html" in url and SITE in url, url)

        url = visit(fake_url.replace("//", "//www.") + "watch?v=1")
        check("D поддомен тоже блокируется", "blocked.html" in url, url)

        call("POST", "/api/session/end", {"password": "pw12345"})
        time.sleep(1)
        url = visit(fake_url)
        check("E после сессии сайт снова открывается", "blocked.html" not in url, url)
    finally:
        try:      # строгую сессию закрываем по паролю, иначе сторож (watchdog) перезапустит программу
            call("POST", "/api/session/end", {"password": "pw12345"})
        except Exception:
            pass
        if browser:
            browser.terminate()
        server.terminate()
    print(f"\n{sum(results)}/{len(results)} проверок прошло")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
