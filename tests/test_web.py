"""Интерфейс: файлы на месте, ничего не грузится из интернета, старой игры в нём нет."""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "focusfarm" / "web"


def test_static_files_served(env):
    for path in ("/", "/app.js", "/style.css", "/tokens.css", "/brand/favicon.ico"):
        assert env.client.get(path).status_code == 200, path


def test_no_external_resources():
    """Всё работает без интернета: никаких CDN, шрифтов и счётчиков."""
    for file in [*WEB.glob("*.html"), *WEB.glob("*.js"), *WEB.glob("*.css")]:
        text = file.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!127\.0\.0\.1)", text), file.name


def test_font_is_local_with_license():
    for name in ("jost-latin-300-normal.woff2", "jost-cyrillic-300-normal.woff2", "manrope-latin-600-normal.woff2", "manrope-cyrillic-600-normal.woff2"):
        assert (WEB / "fonts" / name).exists(), name
    for name in ("LICENSE-Jost.txt", "LICENSE-Manrope.txt"):
        assert "Open Font License" in (WEB / "fonts" / name).read_text(encoding="utf-8"), name


def test_pond_files_served_and_assets_exist(env):
    import json
    for path in ("/pond.js", "/pond.css", "/pond/img/koi_kohaku.webp", "/pond/img/water_day.webp", "/pond/img/caustics_a.webp"):
        assert env.client.get(path).status_code == 200, path
    cfg = env.client.get("/api/pond/config").json()
    names = {"koi_shadow", "water_day", "water_dusk", "water_night", "caustics_a", "caustics_b"}
    prog = cfg["progression"]
    for group in (prog["base"]["placements"], prog["base"]["koi"]):
        names |= {x["asset"] for x in group}
    for u in prog["unlocks"]:
        for key in ("placements", "replace", "koi"):
            names |= {x["asset"] for x in u.get(key, []) if "asset" in x}
        if "ambient" in u:
            names.add(u["ambient"]["asset"])
    for name in names:
        assert (WEB / "pond" / "img" / f"{name}.webp").exists(), name


def test_pond_ui_has_required_controls(env):
    page = env.client.get("/").text
    for marker in ('id="pond-canvas"', 'id="pond-hide"', 'id="pond-jbtn"', 'id="pond-reasons"', 'id="pond-start"'):
        assert marker in page, marker


def test_old_game_is_gone(env):
    """Пруд переписывается заново: старых экранов и API игры быть не должно."""
    page = env.client.get("/").text
    for marker in ('id="tab-farm"', 'id="tab-shop"', 'id="tab-quests"', 'id="tab-collection"', "game-only"):
        assert marker not in page, marker
    for url in ("/api/collection", "/api/rewards"):
        assert env.client.get(url).status_code == 404, url
    assert env.client.post("/api/shop/buy", json={"item": "x"}).status_code in (404, 405)
    assert "farm" not in env.state() and "rewards" not in env.state()
