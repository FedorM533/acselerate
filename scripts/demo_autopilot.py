"""Автопилот демо «Фокус-фермы».

Проигрывает сценарий показа через dev-API и API сессии и печатает, что
происходит. Основная база не трогается: демо живёт в data/demo.db.

    python scripts/demo_autopilot.py                  # всё само, ×30, браузер откроется
    python scripts/demo_autopilot.py --step           # шаги по Enter — вести показ вручную
    python scripts/demo_autopilot.py --pause 2        # короче паузы между шагами
    python scripts/demo_autopilot.py --no-browser     # без браузера (например, для проверки)
    python scripts/demo_autopilot.py --attach http://127.0.0.1:8765   # к уже запущенному серверу

Сценарий:
 1. сброс демо-данных (+ стартовые монеты, открыта морковь);
 2. телефон в подставку → сессия, сажается морковь;
 3. работа — растение растёт;
 4. «Пишу в тетради» на 15 с — растение растёт дальше;
 5. отвлечение: жёлтый → красный → сорняк;
 6. возврат к работе, прополка;
 7. телефон вынут на 10 игровых секунд — льготный период, без последствий;
 8. морковь созрела → урожай → монеты;
 9. завершение сессии → статистика.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_DB = ROOT / "data" / "demo.db"
START_COINS = 120          # чтобы в магазине было что купить
POLL_S = 0.25


class DemoError(RuntimeError):
    pass


# ---------------- подготовка ----------------

def reset_demo_db(path: Path = DEMO_DB, coins: int = START_COINS):
    """Чистая демо-ферма: удаляем data/demo.db и кладём стартовые монеты + морковь."""
    from focusfarm.config import load_settings
    from focusfarm.game.engine import GameEngine
    from focusfarm.storage.db import Database

    if path.resolve() == (ROOT / "data" / "focusfarm.db").resolve():
        raise DemoError("Автопилот не трогает основную базу")
    path.unlink(missing_ok=True)
    db = Database(path)
    game = GameEngine(load_settings()["game"])
    game.coins = coins
    game.unlocks.add("carrot")
    db.save_farm(game.to_dict())
    db.conn.close()


def start_server(port: int, speed: float, db: Path = DEMO_DB, log_path: Path | None = None):
    """Запускает сервер отдельным процессом и ждёт, пока он ответит."""
    log_path = log_path or ROOT / "data" / "demo_server.log"
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "focusfarm", "--demo", str(speed), "--db", str(db),
         "--port", str(port), "--no-browser"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        if proc.poll() is not None:
            raise DemoError(f"Сервер не запустился, смотри {log_path}")
        try:
            urllib.request.urlopen(url + "/api/hello", timeout=1)
            return proc, url
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise DemoError("Сервер не ответил за 30 секунд")


# ---------------- автопилот ----------------

class Autopilot:
    def __init__(self, url: str, pause: float = 5.0, step_mode: bool = False, on_step=None):
        self.url = url.rstrip("/")
        self.pause = pause
        self.step_mode = step_mode
        self.on_step = on_step or (lambda name: None)   # для screenshots.py
        self.speed = 1.0
        self.step_no = 0

    # --- HTTP ---
    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise DemoError(f"{method} {path}: {e.code} {detail}") from None

    def state(self):
        return self.call("GET", "/api/state")

    def post(self, path, body=None):
        return self.call("POST", path, body if body is not None else {})

    # --- помощники ---
    def say(self, text):
        print(f"   {text}", flush=True)

    def step(self, title):
        self.step_no += 1
        if self.step_no > 1:
            if self.step_mode:
                input(f"\n⏎  Enter — шаг {self.step_no}: {title}")
            else:
                time.sleep(self.pause)
        print(f"\n[{self.step_no}/9] {title}", flush=True)

    def wait_until(self, check, what, timeout_s):
        """Ждёт, пока check(state) вернёт не False/None. timeout — в настоящих секундах."""
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            s = self.state()
            result = check(s)
            if result:
                return s if result is True else result
            time.sleep(POLL_S)
        raise DemoError(f"Не дождались: {what}")

    def game_s(self, seconds_game):
        """Игровые секунды → настоящие."""
        return seconds_game / self.speed

    def active_plot(self, s):
        return next((p for p in s["farm"]["plots"] if p.get("active")), None)

    # --- сценарий ---
    def run(self):
        s = self.state()
        if s["mode"] != "demo":
            raise DemoError("Сервер не в демо-режиме: запусти с --demo 30 или FOCUSFARM_DEMO_SPEED=30")
        if not s["dev_tools"]:
            raise DemoError("Нет панели разработчика — нужен режим demo или dev")
        self.speed = s["speed"]
        th = self.call("GET", "/api/settings")["thresholds"]
        print(f"Демо ×{self.speed:g}: 1 настоящая секунда = {self.speed:g} игровых.", flush=True)

        # 1. Сброс — сделан до запуска сервера (или пропущен при --attach).
        self.step("Чистая демо-ферма")
        if s["session"]:
            self.post("/api/session/end")
        self.post("/api/dev/phone", {"docked": False})
        self.say(f"Монет: {s['farm']['coins']}, открыты: "
                 + ", ".join(c["name"] for c in s["farm"]["crops"] if c["unlocked"]))
        self.on_step("start")

        # 2. Телефон в подставку → сессия.
        self.step("Кладём телефон в подставку")
        self.post("/api/dev/category", {"category": "work"})
        self.post("/api/dev/phone", {"docked": True})
        s = self.wait_until(lambda st: st["session"] is not None, "старт сессии", 10)
        plot = self.active_plot(s)
        self.say(f"Сессия началась, свет {s['device']['led']}. На грядке: {plot['crop_name'] if plot else '—'}")
        if plot and plot["crop"] != "carrot":
            self.say("(морковь не открыта — растёт то, что есть)")
        self.on_step("session_started")

        # 3. Работа.
        self.step("Работаем — растение растёт")
        time.sleep(15)
        plot = self.active_plot(self.state())
        self.say(f"{plot['crop_name']}: {round(plot['progress'] * 100)}% (стадия {plot['stage']})")
        self.on_step("focus")

        # 4. Тетрадь.
        self.step("«Пишу в тетради» 15 секунд")
        self.post("/api/session/notebook", {"on": True})
        self.post("/api/dev/category", {"category": "neutral"})
        self.wait_until(lambda st: st["state"] == "NOTEBOOK", "режим тетради", 5)
        self.say("Клавиатура не нужна — растение всё равно растёт")
        self.on_step("notebook")
        time.sleep(15)
        plot = self.active_plot(self.state())
        self.post("/api/session/notebook", {"on": False})
        self.post("/api/dev/category", {"category": "work"})
        self.say(f"{plot['crop_name']}: {round(plot['progress'] * 100)}%")

        # 5. Отвлечение.
        self.step("Открыли YouTube")
        self.post("/api/dev/category", {"category": "distraction"})
        self.wait_until(lambda st: st["state"] in ("MAYBE_DISTRACTED", "DISTRACTED"), "жёлтый", 5)
        self.say("Жёлтый: «Кажется, отвлёкся…»")
        self.on_step("maybe")
        self.wait_until(lambda st: st["state"] == "DISTRACTED", "красный", self.game_s(th["distraction_confirm_s"]) + 5)
        self.say("Красный: «Отвлёкся — огород ждёт», рост на паузе")
        s = self.wait_until(lambda st: any(p["weeds"] for p in st["farm"]["plots"]) and st,
                            "сорняк", self.game_s(60) + 5)
        weed = next(p for p in s["farm"]["plots"] if p["weeds"])
        self.say(f"Вырос сорняк на грядке ({weed['x'] + 1}, {weed['y'] + 1})")
        self.on_step("distracted")

        # 6. Возврат и прополка.
        self.step("Вернулись к работе и пропололи")
        self.post("/api/dev/category", {"category": "work"})
        s = self.wait_until(lambda st: st["state"] == "FOCUS" and st, "фокус", self.game_s(th["recover_s"]) + 5)
        self.say("Снова «Работаешь 🌱»")
        s = self.wait_until(lambda st: st["farm"]["can_weed"] and st, "право прополоть",
                            self.game_s(s["farm"]["weed_unlock_left_s"]) + 5)
        self.post("/api/farm/weed", {"x": weed["x"], "y": weed["y"]})
        self.say("Сорняк убран (5 минут фокуса уже набрано)")
        self.on_step("weeded")

        # 7. Телефон — льготный период.
        self.step("Достали телефон на 10 секунд и вернули")
        out_game = min(10, th["phone_grace_s"] / 2)
        self.post("/api/dev/phone", {"docked": False})
        time.sleep(max(0.2, self.game_s(out_game)))
        self.post("/api/dev/phone", {"docked": True})
        state_now = self.state()["state_label"]
        self.say(f"{out_game:g} игровых секунд вне подставки — «{state_now}», без последствий "
                 f"(льготный период {th['phone_grace_s']} с)")
        self.on_step("phone_back")

        # 8. Урожай.
        self.step("Ждём урожай")
        plot = self.active_plot(self.state())
        wait = self.game_s(plot["left_s"]) + 10
        self.say(f"До урожая ~{round(wait - 10)} настоящих секунд…")
        s = self.wait_until(lambda st: (p := self.active_plot(st)) and p["ripe"] and st, "созревание", wait)
        plot = self.active_plot(s)
        self.say(f"{plot['crop_name']} созрела! ★ × {plot['stars']}, стоимость {plot['value']}")
        coins_before = s["farm"]["coins"]
        self.on_step("ripe")
        after = self.state()
        if (p := self.active_plot(after)) and p["ripe"]:
            result = self.post("/api/farm/harvest", {"x": plot["x"], "y": plot["y"]})
            self.say(f"Собрали: +{result['coins']} монет ({coins_before} → {coins_before + result['coins']})")
        else:   # урожай уже собрали кликом в интерфейсе (так делает screenshots.py)
            self.say(f"Собрали в интерфейсе: {coins_before} → {after['farm']['coins']} монет")
        self.on_step("harvested")

        # 9. Завершение и статистика.
        self.step("Завершаем сессию и смотрим статистику")
        self.post("/api/session/end")
        st = self.call("GET", "/api/stats?range=day")
        self.say(f"Фокус: {round(st['focus_s'] / 60)} мин, отвлечений: {st['distractions']} "
                 f"(окно {st['distraction_reasons']['window']}, телефон {st['distraction_reasons']['phone']})")
        self.say(f"Статистика: {self.url}/#stats")
        self.on_step("stats")
        print("\nГотово! Сценарий пройден.", flush=True)


def main():
    from focusfarm import fix_console_encoding
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Автопилот демо «Фокус-фермы»")
    parser.add_argument("--speed", type=float, default=30, help="ускорение демо (по умолчанию 30)")
    parser.add_argument("--port", type=int, default=8766, help="порт демо-сервера (по умолчанию 8766)")
    parser.add_argument("--pause", type=float, default=5, help="пауза между шагами, с (по умолчанию 5)")
    parser.add_argument("--step", action="store_true", help="переходить к следующему шагу по Enter")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    parser.add_argument("--attach", metavar="URL", help="не запускать свой сервер, а подключиться к этому")
    parser.add_argument("--keep", action="store_true", help="не останавливать сервер после сценария")
    args = parser.parse_args()

    proc = None
    try:
        if args.attach:
            url = args.attach
            print(f"Подключаюсь к {url} (данные не сбрасываю)")
        else:
            print("Готовлю чистую демо-ферму в data/demo.db …")
            reset_demo_db()
            proc, url = start_server(args.port, args.speed)
            print(f"Сервер запущен: {url}/")
        if not args.no_browser:
            webbrowser.open(url + "/#farm")
            time.sleep(2)
        Autopilot(url, pause=args.pause, step_mode=args.step).run()
        if proc and not args.keep:
            try:
                input("\nEnter — остановить демо-сервер… ")
            except EOFError:
                pass
    except DemoError as exc:
        print(f"\nОшибка: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        if proc and not args.keep:
            proc.terminate()


if __name__ == "__main__":
    main()
