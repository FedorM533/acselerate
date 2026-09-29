"""Интерфейс: файлы на месте, спрайты для всех растений, ничего не грузится из интернета."""
import re
from pathlib import Path

from focusfarm.game.crops import DEFAULT_CROPS

WEB = Path(__file__).resolve().parent.parent / "focusfarm" / "web"


def test_static_files_served(env):
    for path in ("/", "/app.js", "/style.css", "/sprites/plot.svg", "/sprites/weed.svg"):
        assert env.client.get(path).status_code == 200, path


def test_sprites_for_every_crop_and_stage(env):
    for crop in DEFAULT_CROPS:
        for stage in ("adult", "ready"):
            assert env.client.get(f"/sprites/{crop}_{stage}.svg").status_code == 200
    for name in ("seed", "sprout", "young", "drop", "coin", "scarecrow", "fence", "bench"):
        assert env.client.get(f"/sprites/{name}.svg").status_code == 200


def test_no_external_resources():
    """Всё работает без интернета: никаких CDN, шрифтов и счётчиков."""
    for file in [*WEB.glob("*.html"), *WEB.glob("*.js"), *WEB.glob("*.css")]:
        text = file.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!127\.0\.0\.1)", text), file.name


def test_all_crop_stages_have_sprites_and_valid_svg():
    """5 культур × 5 стадий — отдельные SVG; все спрайты — корректный XML."""
    import xml.dom.minidom

    sprites = WEB / "sprites"
    for crop in DEFAULT_CROPS:
        for stage in ("seed", "sprout", "young", "adult", "ready"):
            assert (sprites / f"{crop}_{stage}.svg").exists(), f"{crop}_{stage}"
    for file in sprites.glob("*.svg"):
        xml.dom.minidom.parse(str(file))


def test_font_is_local_with_license():
    assert (WEB / "fonts" / "Nunito.ttf").exists()
    assert "Open Font License" in (WEB / "fonts" / "OFL.txt").read_text(encoding="utf-8")
