"""Генератор SVG-спрайтов фермы (оригинальная графика).

Запуск: python -m focusfarm.tools.make_sprites
Меняй фигуры здесь и перезапускай — файлы в focusfarm/web/sprites/ перезапишутся.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "sprites"

LEAF = "#5cae4a"
LEAF_DARK = "#3f8a36"
STEM = "#4f9a3e"


def svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">{body}</svg>\n'


def leaf(cx, cy, rx, ry, rot, color=LEAF):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{color}" transform="rotate({rot} {cx} {cy})"/>'


MOUND = '<ellipse cx="50" cy="84" rx="22" ry="6" fill="#6b4a2f"/>'

sprites = {}

sprites["plot"] = svg(
    '<rect x="4" y="4" width="92" height="92" rx="14" fill="#8a5a36"/>'
    '<rect x="8" y="8" width="84" height="84" rx="11" fill="#9c6a42"/>'
    '<path d="M14 30 H86 M14 50 H86 M14 70 H86" stroke="#7d5232" stroke-width="4" stroke-linecap="round"/>'
    '<circle cx="24" cy="40" r="2" fill="#7d5232"/><circle cx="70" cy="60" r="2" fill="#7d5232"/>'
    '<circle cx="52" cy="22" r="1.6" fill="#b88458"/><circle cx="36" cy="78" r="1.6" fill="#b88458"/>'
)

sprites["seed"] = svg(
    MOUND + '<ellipse cx="50" cy="78" rx="6" ry="4.5" fill="#d9b56b" stroke="#a4803e" stroke-width="1.5"/>'
)

sprites["sprout"] = svg(
    MOUND + f'<path d="M50 84 Q50 70 50 62" stroke="{STEM}" stroke-width="4" fill="none" stroke-linecap="round"/>'
    + leaf(42, 62, 9, 4.5, -25) + leaf(58, 62, 9, 4.5, 25)
)

sprites["young"] = svg(
    MOUND + f'<path d="M50 84 Q49 62 50 44" stroke="{STEM}" stroke-width="5" fill="none" stroke-linecap="round"/>'
    + leaf(38, 66, 13, 6, -20, LEAF_DARK) + leaf(62, 66, 13, 6, 20, LEAF_DARK)
    + leaf(41, 48, 11, 5, -35) + leaf(59, 48, 11, 5, 35)
)

# ---- Редис ----
radish_tops = (leaf(40, 44, 7, 18, -25) + leaf(60, 44, 7, 18, 25) + leaf(50, 38, 7, 20, 0, LEAF_DARK))
sprites["radish_adult"] = svg(
    MOUND + radish_tops + '<ellipse cx="50" cy="72" rx="9" ry="8" fill="#d8456b"/>'
)
sprites["radish_ready"] = svg(
    MOUND + radish_tops + '<ellipse cx="50" cy="72" rx="15" ry="13" fill="#e04a72"/>'
    '<path d="M50 85 L50 95" stroke="#e8c6cf" stroke-width="2.5" stroke-linecap="round"/>'
    '<ellipse cx="44" cy="67" rx="4" ry="3" fill="#f28aa5"/>'
)

# ---- Морковь ----
carrot_tops = "".join(
    f'<path d="M50 62 Q{50 + dx} {40} {50 + dx * 1.6} {22 + abs(dx) // 2}" stroke="{LEAF}" stroke-width="4" fill="none" stroke-linecap="round"/>'
    for dx in (-14, -6, 0, 6, 14)
)
sprites["carrot_adult"] = svg(
    MOUND + carrot_tops + '<path d="M42 64 L58 64 L50 84 Z" fill="#ee8a2a"/>'
)
sprites["carrot_ready"] = svg(
    MOUND + carrot_tops + '<path d="M38 60 L62 60 L50 96 Z" fill="#f28c28"/>'
    '<path d="M44 70 H52 M46 78 H53" stroke="#c96b15" stroke-width="2" stroke-linecap="round"/>'
)

# ---- Картофель ----
potato_bush = (
    f'<path d="M50 84 L50 56" stroke="{STEM}" stroke-width="5"/>'
    + leaf(34, 58, 14, 8, -15, LEAF_DARK) + leaf(66, 58, 14, 8, 15, LEAF_DARK)
    + leaf(40, 44, 12, 7, -30) + leaf(60, 44, 12, 7, 30) + leaf(50, 36, 9, 7, 0)
)
sprites["potato_adult"] = svg(MOUND + potato_bush + '<circle cx="50" cy="32" r="4" fill="#f4f0ff"/>')
sprites["potato_ready"] = svg(
    MOUND + potato_bush
    + '<circle cx="46" cy="33" r="4" fill="#f4f0ff"/><circle cx="56" cy="31" r="4" fill="#e8e0ff"/>'
    '<ellipse cx="30" cy="86" rx="9" ry="6.5" fill="#c9a064" stroke="#9a7440" stroke-width="1.5"/>'
    '<ellipse cx="70" cy="87" rx="10" ry="7" fill="#d1a86b" stroke="#9a7440" stroke-width="1.5"/>'
    '<circle cx="28" cy="85" r="1" fill="#8a6a3a"/><circle cx="72" cy="86" r="1" fill="#8a6a3a"/>'
)

# ---- Подсолнух ----
sun_stem = (
    f'<path d="M50 86 Q48 60 50 34" stroke="{STEM}" stroke-width="5" fill="none"/>'
    + leaf(38, 64, 12, 6, -30, LEAF_DARK) + leaf(62, 56, 12, 6, 30)
)
sprites["sunflower_adult"] = svg(
    MOUND + sun_stem + '<circle cx="50" cy="30" r="10" fill="#6fae4f"/>'
    + "".join(leaf(50, 20, 3, 7, a, "#8cc06a") for a in (-40, 0, 40))
)
petals = "".join(
    f'<ellipse cx="50" cy="12" rx="5" ry="10" fill="#f7c52b" transform="rotate({a} 50 26)"/>'
    for a in range(0, 360, 30)
)
sprites["sunflower_ready"] = svg(
    MOUND + sun_stem + petals + '<circle cx="50" cy="26" r="10" fill="#7a4a1e"/>'
    '<circle cx="47" cy="23" r="1.5" fill="#a0672e"/><circle cx="53" cy="28" r="1.5" fill="#a0672e"/>'
)

# ---- Тыква ----
vine = (
    '<path d="M16 84 Q34 70 50 78 T84 80" stroke="#4f9a3e" stroke-width="3.5" fill="none"/>'
    + leaf(24, 70, 11, 8, -10, LEAF_DARK) + leaf(76, 68, 11, 8, 10, LEAF_DARK)
)
sprites["pumpkin_adult"] = svg(
    MOUND + vine + '<ellipse cx="50" cy="74" rx="11" ry="9" fill="#8fbf4a"/>'
    '<path d="M50 65 V83" stroke="#6e9a33" stroke-width="2"/>'
)
sprites["pumpkin_ready"] = svg(
    MOUND + vine
    + '<ellipse cx="38" cy="70" rx="13" ry="15" fill="#e8791f"/>'
    '<ellipse cx="62" cy="70" rx="13" ry="15" fill="#e8791f"/>'
    '<ellipse cx="50" cy="70" rx="14" ry="16" fill="#f58a2a"/>'
    '<path d="M50 55 Q46 48 52 44" stroke="#5b7a2a" stroke-width="4" fill="none" stroke-linecap="round"/>'
    '<ellipse cx="44" cy="64" rx="3" ry="5" fill="#ffab5c"/>'
)

# ---- Сорняк ----
sprites["weed"] = svg(
    '<g transform="translate(58 22) scale(0.8)">'
    '<path d="M0 90 L-22 20 L-6 60 L0 0 L8 58 L26 18 L8 90 Z" fill="#6d7f2e" stroke="#4a5a1c" stroke-width="3"/>'
    '<circle cx="0" cy="0" r="8" fill="#a45ec7"/><circle cx="-22" cy="20" r="6" fill="#a45ec7"/>'
    '<circle cx="26" cy="18" r="6" fill="#a45ec7"/></g>'
)

# ---- Капля «хочет пить» ----
sprites["drop"] = svg(
    '<path d="M50 14 Q70 44 70 58 A20 20 0 0 1 30 58 Q30 44 50 14 Z" fill="#5ab4f0" stroke="#2f86c5" stroke-width="3"/>'
    '<ellipse cx="42" cy="56" rx="4" ry="7" fill="#bfe4ff"/>'
)

# ---- Монета ----
sprites["coin"] = svg(
    '<circle cx="50" cy="50" r="40" fill="#f2c230" stroke="#c9961a" stroke-width="6"/>'
    '<circle cx="50" cy="50" r="27" fill="none" stroke="#e0a91e" stroke-width="4"/>'
    '<path d="M40 38 L50 30 L60 38 L60 62 L40 62 Z" fill="#e0a91e"/>'
)

# ---- Декор ----
sprites["scarecrow"] = svg(
    '<path d="M50 30 V96" stroke="#8a5a2b" stroke-width="6"/>'
    '<path d="M18 46 H82" stroke="#8a5a2b" stroke-width="5"/>'
    '<path d="M34 42 H66 L62 74 H38 Z" fill="#d0643c"/>'
    '<path d="M38 50 H62 M40 62 H60" stroke="#b04e2a" stroke-width="3"/>'
    '<circle cx="50" cy="26" r="12" fill="#f0d49a"/>'
    '<path d="M32 18 H68 L60 8 H40 Z" fill="#6b4a2a"/><rect x="30" y="16" width="40" height="5" rx="2" fill="#6b4a2a"/>'
    '<circle cx="45" cy="26" r="2" fill="#333"/><circle cx="55" cy="26" r="2" fill="#333"/>'
    '<path d="M45 32 Q50 35 55 32" stroke="#333" stroke-width="2" fill="none"/>'
    '<path d="M18 46 l-6 6 M18 46 l-6 -4 M82 46 l6 6 M82 46 l6 -4" stroke="#e6c35c" stroke-width="3"/>'
)
sprites["fence"] = svg(
    "".join(f'<path d="M{x} 92 V34 L{x + 7} 26 L{x + 14} 34 V92 Z" fill="#c9985e" stroke="#936a39" stroke-width="2.5"/>'
            for x in (6, 30, 54, 78))
    + '<rect x="2" y="46" width="96" height="8" fill="#b5844c"/><rect x="2" y="72" width="96" height="8" fill="#b5844c"/>'
)
sprites["bench"] = svg(
    '<rect x="10" y="38" width="80" height="10" rx="3" fill="#b5784a"/>'
    '<rect x="10" y="52" width="80" height="10" rx="3" fill="#a86c40"/>'
    '<rect x="8" y="64" width="84" height="10" rx="3" fill="#c98b57"/>'
    '<path d="M18 74 V94 M82 74 V94 M18 30 V64 M82 30 V64" stroke="#5a5a5a" stroke-width="5" stroke-linecap="round"/>'
)

if __name__ == "__main__":
    from focusfarm import fix_console_encoding
    fix_console_encoding()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in sprites.items():
        (OUT / f"{name}.svg").write_text(content, encoding="utf-8")
    print(f"Готово: {len(sprites)} спрайтов в {OUT}")
