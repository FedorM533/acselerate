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
