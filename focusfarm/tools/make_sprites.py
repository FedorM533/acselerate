"""Генератор SVG-спрайтов фермы (оригинальная графика, единый стиль).

Запуск: python -m focusfarm.tools.make_sprites
Меняй фигуры здесь и перезапускай — файлы в focusfarm/web/sprites/ перезапишутся.

Правила стиля:
- вид сбоку, растение «стоит» на линии земли y = 92 (грядку рисует bed.svg);
- у всех фигур одинаковый контур: тёмно-коричневый, толщина 2.5, скруглённые углы;
- палитра тёплая, без чистого чёрного.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "sprites"

INK = "#3B2A1E"
O = f'stroke="{INK}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"'


def ow(width):
    """Тот же контур, но другой толщины."""
    return f'stroke="{INK}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"'


LEAF = "#6CC060"
LEAF_DARK = "#3F9A45"
STEM = "#4F9A3E"
GROUND = 92

CROPS = ("radish", "carrot", "potato", "sunflower", "pumpkin")


def svg(body: str, view: str = "0 0 100 100") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">{body}</svg>\n'


def leaf(cx, cy, rx, ry, rot, color=LEAF):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{color}" {O} transform="rotate({rot} {cx} {cy})"/>'


def stem(x1, y1, x2, y2, width=4, bend=0):
    mx, my = (x1 + x2) / 2 + bend, (y1 + y2) / 2
    return f'<path d="M{x1} {y1} Q{mx} {my} {x2} {y2}" stroke="{INK}" stroke-width="{width + 2.5}" fill="none" stroke-linecap="round"/>' \
           f'<path d="M{x1} {y1} Q{mx} {my} {x2} {y2}" stroke="{STEM}" stroke-width="{width}" fill="none" stroke-linecap="round"/>'


def crumb():
    """Маленький холмик земли у основания растения."""
    return f'<path d="M30 {GROUND} Q50 {GROUND - 12} 70 {GROUND} Z" fill="#7A5134" {O}/>'


# ---------------- стадии, общие для всех культур ----------------

SEED_COLORS = {"radish": "#E8698A", "carrot": "#F29A45", "potato": "#D8B274",
               "sunflower": "#5A4636", "pumpkin": "#F4E3B5"}
SPROUT_TINT = {"radish": LEAF, "carrot": "#7CC75A", "potato": LEAF_DARK,
               "sunflower": "#7CC75A", "pumpkin": "#58B056"}


def seed(crop):
    color = SEED_COLORS[crop]
    stripes = ""
    if crop == "sunflower":
        stripes = '<path d="M46 78 L54 83" stroke="#EDE4D8" stroke-width="1.6"/>'
    return svg(crumb() + f'<ellipse cx="50" cy="80" rx="9" ry="6.5" fill="{color}" {O} transform="rotate(-20 50 80)"/>' + stripes
               + f'<path d="M52 74 q3 -8 10 -9" stroke="{INK}" stroke-width="5.5" fill="none" stroke-linecap="round"/>'
               + f'<path d="M52 74 q3 -8 10 -9" stroke="{LEAF}" stroke-width="3" fill="none" stroke-linecap="round"/>')


def sprout(crop):
    tint = SPROUT_TINT[crop]
    return svg(crumb() + stem(50, GROUND - 2, 50, 70, 4)
               + leaf(41, 69, 10, 5, -25, tint) + leaf(59, 69, 10, 5, 25, tint))


def young(crop):
    if crop == "radish":
        body = stem(50, 90, 50, 64, 4) + leaf(38, 62, 8, 17, -35) + leaf(62, 62, 8, 17, 35) + leaf(50, 56, 8, 18, 0, LEAF_DARK)
    elif crop == "carrot":
        body = "".join(stem(50, 90, 50 + dx, 52 + abs(dx), 3, dx / 2) for dx in (-12, 0, 12)) \
            + "".join(f'<circle cx="{50 + dx}" cy="{52 + abs(dx)}" r="5" fill="{LEAF}" {O}/>' for dx in (-12, 0, 12))
    elif crop == "potato":
        body = stem(50, 90, 50, 62, 5) + leaf(36, 70, 12, 7, -20, LEAF_DARK) + leaf(64, 70, 12, 7, 20, LEAF_DARK) + leaf(50, 58, 9, 8, 0)
    elif crop == "sunflower":
        body = stem(50, 90, 50, 46, 5) + leaf(39, 72, 11, 5.5, -30, LEAF_DARK) + leaf(61, 64, 11, 5.5, 30) + leaf(40, 52, 8, 4.5, -35) \
            + f'<circle cx="50" cy="44" r="5" fill="#8CC06A" {O}/>'
    else:  # pumpkin
        body = f'<path d="M50 90 Q40 80 30 84" stroke="{STEM}" stroke-width="4" fill="none"/>' + stem(50, 90, 52, 70, 4) \
            + leaf(38, 70, 13, 10, -15, LEAF_DARK) + leaf(62, 66, 13, 10, 15) + f'<path d="M30 84 q-6 -4 -3 -9" stroke="{STEM}" stroke-width="2" fill="none"/>'
    return svg(crumb() + body)


# ---------------- взрослое и готовое ----------------

def radish(ready):
    tops = leaf(40, 46, 8, 20, -25) + leaf(60, 46, 8, 20, 25) + leaf(50, 40, 8, 22, 0, LEAF_DARK)
    if not ready:
        return tops + f'<ellipse cx="50" cy="80" rx="10" ry="9" fill="#D8456B" {O}/>'
    return tops + '<path d="M50 94 L50 99" stroke="#E8C6CF" stroke-width="2.5" stroke-linecap="round"/>' \
        + f'<ellipse cx="50" cy="78" rx="16" ry="15" fill="#E04A72" {O}/>' \
        + '<ellipse cx="44" cy="72" rx="4.5" ry="3.5" fill="#F7A3B8"/>'


def carrot(ready):
    tops = "".join(stem(50, 68, 50 + dx * 1.5, 26 + abs(dx), 3.5, dx) for dx in (-12, -5, 0, 5, 12))
    if not ready:
        return tops + f'<path d="M41 68 L59 68 L50 92 Z" fill="#EE8A2A" {O}/>'
    return tops + f'<path d="M37 64 L63 64 L50 99 Z" fill="#F28C28" {O}/>' \
        + f'<path d="M44 74 H52 M46 82 H53" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'


def potato(ready):
    bush = stem(50, 90, 50, 58, 5) + leaf(33, 64, 15, 9, -15, LEAF_DARK) + leaf(67, 64, 15, 9, 15, LEAF_DARK) \
        + leaf(40, 48, 12, 8, -30) + leaf(60, 48, 12, 8, 30) + leaf(50, 40, 10, 8, 0)
    flowers = f'<circle cx="46" cy="35" r="4" fill="#F4F0FF" {O}/><circle cx="56" cy="33" r="4" fill="#E8E0FF" {O}/>'
    if not ready:
        return bush + f'<circle cx="50" cy="34" r="4" fill="#F4F0FF" {O}/>'
    return bush + flowers \
        + f'<ellipse cx="28" cy="88" rx="10" ry="7" fill="#D1A86B" {O}/>' \
        + f'<ellipse cx="72" cy="89" rx="11" ry="7.5" fill="#C99B5C" {O}/>' \
        + f'<circle cx="26" cy="87" r="1.2" fill="{INK}"/><circle cx="74" cy="88" r="1.2" fill="{INK}"/>'


def sunflower(ready):
    body = stem(50, 92, 50, 34, 5) + leaf(37, 68, 13, 6, -30, LEAF_DARK) + leaf(63, 58, 13, 6, 30)
    if not ready:
        return body + f'<circle cx="50" cy="30" r="10" fill="#7DB85A" {O}/>' \
            + "".join(leaf(50, 21, 3.5, 7, a, "#9ACB74") for a in (-40, 0, 40))
    petals = "".join(f'<ellipse cx="50" cy="11" rx="5.5" ry="10" fill="#F7C52B" {O} transform="rotate({a} 50 26)"/>'
                     for a in range(0, 360, 30))
    return body + petals + f'<circle cx="50" cy="26" r="10.5" fill="#7A4A1E" {O}/>' \
        + '<circle cx="47" cy="23" r="1.6" fill="#B07B4F"/><circle cx="53" cy="28" r="1.6" fill="#B07B4F"/><circle cx="52" cy="22" r="1.4" fill="#B07B4F"/>'


def pumpkin(ready):
    vine = f'<path d="M12 90 Q30 76 50 84 T88 86" stroke="{STEM}" stroke-width="4" fill="none" stroke-linecap="round"/>' \
        + leaf(22, 74, 12, 9, -10, LEAF_DARK) + leaf(78, 72, 12, 9, 10, LEAF_DARK)
    if not ready:
        return vine + f'<ellipse cx="50" cy="80" rx="12" ry="10" fill="#9FC955" {O}/>' \
            + f'<path d="M50 71 V89" stroke="{INK}" stroke-width="1.8"/>'
    return vine \
        + f'<ellipse cx="37" cy="76" rx="14" ry="16" fill="#E8791F" {O}/>' \
        + f'<ellipse cx="63" cy="76" rx="14" ry="16" fill="#E8791F" {O}/>' \
        + f'<ellipse cx="50" cy="76" rx="14" ry="17" fill="#F58A2A" {O}/>' \
        + f'<path d="M50 60 Q46 52 53 47" stroke="{INK}" stroke-width="6.5" fill="none" stroke-linecap="round"/>' \
        + '<path d="M50 60 Q46 52 53 47" stroke="#5B7A2A" stroke-width="4" fill="none" stroke-linecap="round"/>' \
        + '<ellipse cx="44" cy="69" rx="3" ry="6" fill="#FFB36B"/>'


DRAW = {"radish": radish, "carrot": carrot, "potato": potato, "sunflower": sunflower, "pumpkin": pumpkin}

sprites = {}
for crop in CROPS:
    sprites[f"{crop}_seed"] = seed(crop)
    sprites[f"{crop}_sprout"] = sprout(crop)
    sprites[f"{crop}_young"] = young(crop)
    sprites[f"{crop}_adult"] = svg(DRAW[crop](False))
    sprites[f"{crop}_ready"] = svg(DRAW[crop](True))

# Общие стадии (для совместимости и магазина) — как у редиса.
sprites["seed"] = seed("radish")
sprites["sprout"] = sprout("radish")
sprites["young"] = young("radish")

# ---------------- грядка (вид сбоку) ----------------
BED = (
    f'<path d="M6 20 Q10 6 30 5 H110 Q130 6 134 20 L128 36 H12 Z" fill="#8B5E3C" {O}/>'
    '<path d="M18 14 Q24 10 34 11 M56 10 H76 M98 11 Q110 10 120 14" stroke="#B07B4F" stroke-width="3" stroke-linecap="round" fill="none"/>'
    '<circle cx="40" cy="24" r="2" fill="#6E4A2E"/><circle cx="92" cy="27" r="2" fill="#6E4A2E"/><circle cx="68" cy="22" r="1.6" fill="#B07B4F"/>'
)
sprites["bed"] = svg(BED, "0 0 140 40")
sprites["plot"] = svg(BED, "0 0 140 40")

# ---------------- сорняк: забавный, не страшный ----------------
sprites["weed"] = svg(
    f'<path d="M50 92 L30 50 L44 66 L48 38 L54 64 L66 44 L62 70 L78 58 L64 92 Z" fill="#8FA33A" {O}/>'
    f'<circle cx="48" cy="30" r="7" fill="#B77FD6" {O}/><circle cx="48" cy="30" r="2.5" fill="#F5C542"/>'
    f'<circle cx="46" cy="76" r="6" fill="#fff" {O}/><circle cx="60" cy="75" r="5" fill="#fff" {O}/>'
    f'<circle cx="47" cy="77" r="2.5" fill="{INK}"/><circle cx="61" cy="76" r="2.2" fill="{INK}"/>'
    f'<path d="M48 86 q5 4 10 0" stroke="{INK}" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
)

# ---------------- небо ----------------
sprites["sun"] = svg(
    "".join(f'<path d="M50 50 L50 6" stroke="#F5C542" stroke-width="7" stroke-linecap="round" transform="rotate({a} 50 50)"/>'
            for a in range(0, 360, 30))
    + f'<circle cx="50" cy="50" r="27" fill="#FFD95A" {O}/>'
    + f'<circle cx="41" cy="46" r="3" fill="{INK}"/><circle cx="59" cy="46" r="3" fill="{INK}"/>'
    + f'<path d="M40 57 q10 9 20 0" stroke="{INK}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    + '<circle cx="35" cy="54" r="4" fill="#F7A3B8" opacity=".7"/><circle cx="65" cy="54" r="4" fill="#F7A3B8" opacity=".7"/>'
)
sprites["cloud"] = svg(
    f'<path d="M22 70 a16 16 0 0 1 6 -31 a24 24 0 0 1 44 -6 a18 18 0 0 1 12 37 Z" fill="#FFFFFF" {O}/>',
    "0 0 100 80")
sprites["cloud_grey"] = svg(
    f'<path d="M22 70 a16 16 0 0 1 6 -31 a24 24 0 0 1 44 -6 a18 18 0 0 1 12 37 Z" fill="#D5DCE3" {O}/>'
    '<path d="M30 60 q12 5 26 0" stroke="#B9C3CC" stroke-width="3" fill="none" stroke-linecap="round"/>',
    "0 0 100 80")

# ---------------- мелочи интерфейса ----------------
sprites["drop"] = svg(
    f'<path d="M50 14 Q70 44 70 58 A20 20 0 0 1 30 58 Q30 44 50 14 Z" fill="#7CC4F4" {O}/>'
    '<ellipse cx="42" cy="56" rx="4" ry="7" fill="#D5EEFF"/>'
)
sprites["coin"] = svg(
    f'<circle cx="50" cy="50" r="40" fill="#F5C542" {ow(5)}/>'
    '<circle cx="50" cy="50" r="27" fill="none" stroke="#E0A91E" stroke-width="4"/>'
    '<path d="M50 32 C50 44 44 52 36 54 C46 54 50 60 50 70 C50 60 56 54 64 54 C56 52 50 44 50 32 Z" fill="#FFF1B8"/>'
)
sprites["lock"] = svg(
    f'<path d="M34 46 V34 a16 16 0 0 1 32 0 V46" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
    f'<rect x="24" y="44" width="52" height="42" rx="10" fill="#F5C542" {ow(4)}/>'
    f'<circle cx="50" cy="62" r="5" fill="{INK}"/><path d="M50 64 V74" stroke="{INK}" stroke-width="4" stroke-linecap="round"/>'
)


def grid_icon(n):
    cell = 76 / n
    rects = "".join(
        f'<rect x="{12 + i * cell + 2}" y="{12 + j * cell + 2}" width="{cell - 4}" height="{cell - 4}" rx="4" fill="#8B5E3C" {ow(2)}/>'
        for i in range(n) for j in range(n))
    return svg(f'<rect x="6" y="6" width="88" height="88" rx="14" fill="#9FD27A" {O}/>' + rects)


sprites["grid4"] = grid_icon(4)
sprites["grid5"] = grid_icon(5)

# ---------------- декор ----------------
sprites["scarecrow"] = svg(
    f'<path d="M50 30 V96" stroke="#8A5A2B" stroke-width="6"/>'
    f'<path d="M16 46 H84" stroke="#8A5A2B" stroke-width="5" stroke-linecap="round"/>'
    f'<path d="M34 42 H66 L62 76 H38 Z" fill="#D0643C" {O}/>'
    '<path d="M38 52 H62 M40 64 H60" stroke="#A84E2A" stroke-width="3"/>'
    f'<circle cx="50" cy="26" r="12" fill="#F0D49A" {O}/>'
    f'<path d="M32 18 H68 L60 6 H40 Z" fill="#6B4A2A" {O}/>'
    f'<circle cx="45" cy="26" r="2" fill="{INK}"/><circle cx="55" cy="26" r="2" fill="{INK}"/>'
    f'<path d="M45 32 Q50 35 55 32" stroke="{INK}" stroke-width="2" fill="none"/>'
    '<path d="M16 46 l-6 6 M16 46 l-6 -4 M84 46 l6 6 M84 46 l6 -4" stroke="#E6C35C" stroke-width="3" stroke-linecap="round"/>'
)
sprites["fence"] = svg(
    f'<rect x="2" y="46" width="96" height="8" fill="#C9985E" {O}/><rect x="2" y="72" width="96" height="8" fill="#C9985E" {O}/>'
    + "".join(f'<path d="M{x} 94 V34 L{x + 7} 26 L{x + 14} 34 V94 Z" fill="#E0B27A" {O}/>' for x in (6, 30, 54, 78))
)
sprites["bench"] = svg(
    '<path d="M18 74 V94 M82 74 V94 M18 30 V64 M82 30 V64" stroke="#5A4A3E" stroke-width="5" stroke-linecap="round"/>'
    f'<rect x="10" y="36" width="80" height="11" rx="3" fill="#B5784A" {O}/>'
    f'<rect x="10" y="50" width="80" height="11" rx="3" fill="#A86C40" {O}/>'
    f'<rect x="8" y="64" width="84" height="11" rx="3" fill="#C98B57" {O}/>'
)

# ---------------- логотип: росток в подставке ----------------
sprites["logo"] = svg(
    f'<path d="M22 70 H78 L72 92 H28 Z" fill="#B07B4F" {ow(3)}/>'
    f'<rect x="30" y="64" width="40" height="8" rx="4" fill="#5BB85C" {ow(3)}/>'
    '<path d="M50 66 C50 52 50 44 50 36" stroke="#2F7D32" stroke-width="5" fill="none" stroke-linecap="round"/>'
    f'<path d="M50 44 C40 44 30 36 30 24 C42 24 50 32 50 44 Z" fill="#5BB85C" {ow(3)}/>'
    f'<path d="M50 38 C60 38 72 30 72 16 C58 16 50 26 50 38 Z" fill="#7ACB6B" {ow(3)}/>'
)

if __name__ == "__main__":
    from focusfarm import fix_console_encoding
    fix_console_encoding()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in sprites.items():
        (OUT / f"{name}.svg").write_text(content, encoding="utf-8")
    print(f"Готово: {len(sprites)} спрайтов в {OUT}")
