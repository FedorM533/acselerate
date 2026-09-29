"""Скриншоты интерфейса для самопроверки.

Проходит автопилот демо и на ключевых шагах снимает экран в двух
разрешениях: 1920×1080 (проектор) и 1366×768 (ноутбук).
Результат — docs/screenshots/*.png и список docs/screenshots/README.md.

    pip install -r requirements-dev.txt
    python scripts/screenshots.py              # ускорение ×15, чтобы успеть снять «жёлтый»
    python scripts/screenshots.py --speed 30

Браузер: установленный Google Chrome, иначе Chromium из Playwright
(python -m playwright install chromium).
"""
import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_autopilot import ROOT, Autopilot, DemoError, reset_demo_db, start_server  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
SIZES = [(1920, 1080), (1366, 768)]
UI_UPDATE_S = 1.2   # сервер присылает состояние раз в секунду

# Шаг автопилота → какие вкладки снять: (вкладка, имя файла, описание).
SHOTS = {
    "session_started": [("farm", "01_farm_start", "Сессия началась: морковь посажена, солнечно"),
                        ("session", "02_session_focus", "Вкладка «Сессия»: кольцо-таймер, «Работаешь 🌱», подставка горит зелёным")],
    "focus": [("farm", "03_farm_growing", "Морковь подросла, под грядкой полоска прогресса")],
    "notebook": [("session", "04_session_notebook", "Режим «Пишу в тетради ✏️» — рост продолжается")],
    "maybe": [("farm", "05_farm_maybe", "«Кажется, отвлёкся…»: набегает облако")],
    "distracted": [("farm", "06_farm_distracted_weed", "«Отвлёкся»: пасмурно, растения поникли, вырос сорняк"),
                   ("session", "07_session_distracted", "«Сессия» в состоянии «Отвлёкся — огород ждёт», подставка красная")],
    "weeded": [("farm", "08_farm_weeded", "Вернулись к работе: снова солнце, сорняк прополот")],
    "phone_back": [("session", "09_session_phone_back", "Телефон вернули в подставку в льготный период")],
    "ripe": [("farm", "10_farm_ripe", "Морковь созрела: подпрыгивает, блестит, кнопка «Собрать»")],
    "harvested": [("farm", "12_farm_after_harvest", "После сбора: монеты в шапке, грядка засажена заново")],
    "stats": [("stats", "13_stats", "«Статистика»: карточки, хронология сессии по состояниям"),
              ("shop", "14_shop", "«Магазин»: закрытые растения с замочком и ценой"),
              ("settings", "15_settings", "«Настройки»: пороги понятными словами, правила окон")],
}


class Shooter:
    def __init__(self, browser, url):
        self.pages = []
        for w, h in SIZES:
            page = browser.new_context(viewport={"width": w, "height": h}).new_page()
            page.goto(url + "/#farm")
            page.wait_for_selector("#farm-grid .plot")
            self.pages.append(page)
        self.tab = {page: "farm" for page in self.pages}
        self.index = []   # (файл, описание)

    def switch(self, tab):
        for page in self.pages:
            if self.tab[page] != tab:
                page.click(f"nav.tabs button[data-tab='{tab}']")
                self.tab[page] = tab

    def snap(self, name, desc):
        for page, (w, h) in zip(self.pages, SIZES):
            file = f"{name}_{w}x{h}.png"
            page.screenshot(path=str(OUT / file))
            self.index.append((file, desc))
        print(f"   📸 {name}", flush=True)

    def on_step(self, step):
        for tab, name, desc in SHOTS.get(step, []):
            self.switch(tab)
            time.sleep(UI_UPDATE_S)
            self.snap(name, desc)
        if step == "ripe":
            self.harvest_with_animation()

    def harvest_with_animation(self):
        """Собираем урожай кликом на большом экране и ловим летящие монеты."""
        big = self.pages[0]
        big.click("#farm-grid .plot.ripe")
        time.sleep(0.6)
        file = f"11_farm_harvest_coins_{SIZES[0][0]}x{SIZES[0][1]}.png"
        big.screenshot(path=str(OUT / file))
        self.index.append((file, "Сбор урожая: монеты летят к счётчику, всплывает «+15 ★★»"))
        print("   📸 11_farm_harvest_coins", flush=True)

    def write_index(self):
        lines = ["# Скриншоты интерфейса", "",
                 "Сняты скриптом `scripts/screenshots.py` во время автопилота демо.", ""]
        lines += [f"- `{file}` — {desc}" for file, desc in self.index]
        (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def launch(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:
        return p.chromium.launch()


def main():
    from focusfarm import fix_console_encoding
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Скриншоты «Фокус-фермы»")
    parser.add_argument("--speed", type=float, default=15)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    reset_demo_db()
    proc, url = start_server(args.port, args.speed, log_path=ROOT / "data" / "screenshots_server.log")
    try:
        with sync_playwright() as p:
            browser = launch(p)
            shooter = Shooter(browser, url)
            Autopilot(url, pause=1, on_step=shooter.on_step).run()
            shooter.write_index()
            browser.close()
        print(f"\nСкриншоты: {OUT}")
    except DemoError as exc:
        print(f"Ошибка: {exc}")
        sys.exit(1)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
