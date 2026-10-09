"""Генератор SVG-спрайтов пруда (оригинальная графика, единый стиль).

Запуск: python -m focusfarm.tools.make_sprites
Меняй фигуры здесь и перезапускай — файлы в focusfarm/web/sprites/ перезапишутся.

Правила стиля:
- рыбки нарисованы сбоку и плывут вправо, центр тела около (50, 52);
- у всех фигур одинаковый контур: тёмно-синий, толщина 2.5, скруглённые углы;
- палитра яркая, но мягкая, без чистого чёрного.
Пять стадий: seed (икринка), sprout (малёк), young (подросток),
adult (взрослая), ready (готова к выпуску — с сиянием).
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "sprites"

INK = "#1F3550"
O = f'stroke="{INK}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"'


def ow(width):
    """Тот же контур, но другой толщины."""
    return f'stroke="{INK}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"'


FISH = ("guppy", "goldfish", "koi", "angelfish", "arowana")

# Цвета: тело, плавники, пятна/полоски.
LOOK = {
    "guppy":     {"body": "#6BC4E8", "fin": "#F58A4B", "mark": "#F7C52B"},
    "goldfish":  {"body": "#F7A23B", "fin": "#F2762E", "mark": "#FFD27A"},
    "koi":       {"body": "#FFF4E6", "fin": "#F4F0E8", "mark": "#E8502E"},
    "angelfish": {"body": "#E4EDF5", "fin": "#C9D8E8", "mark": "#3F5F8A"},
    "arowana":   {"body": "#C9D2D8", "fin": "#9EB0BA", "mark": "#F2C14E"},
}
# Длина тела (rx) и толщина (ry) — у видов разные пропорции.
SHAPE = {
    "guppy": (21, 11), "goldfish": (22, 16), "koi": (26, 12),
    "angelfish": (17, 19), "arowana": (30, 11),
}
# Во сколько раз рисуем рыбку на каждой стадии (икринка рисуется отдельно).
STAGE_SCALE = {"sprout": 0.46, "young": 0.68, "adult": 0.85, "ready": 0.92}
FISH_VIEW = "0 8 100 88"   # рамка плотнее к рыбке, чтобы она не терялась в клетке


def svg(body: str, view: str = "0 0 100 100") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">{body}</svg>\n'


def fish_body(kind: str) -> str:
    """Рыбка в масштабе 1, центр (50, 52)."""
    c = LOOK[kind]
    rx, ry = SHAPE[kind]
    cx, cy = 50, 52
    head_x = cx + rx
    tail_x = cx - rx

    # Хвост.
    if kind == "guppy":
        tail = f'<path d="M{tail_x + 4} {cy} L{tail_x - 20} {cy - 17} Q{tail_x - 12} {cy} {tail_x - 20} {cy + 17} Z" fill="{c["fin"]}" {O}/>'
    elif kind == "goldfish":
        tail = (f'<path d="M{tail_x + 4} {cy} Q{tail_x - 22} {cy - 24} {tail_x - 20} {cy - 4} '
                f'Q{tail_x - 12} {cy} {tail_x - 20} {cy + 6} Q{tail_x - 22} {cy + 24} {tail_x + 4} {cy} Z" fill="{c["fin"]}" {O}/>')
    elif kind == "angelfish":
        tail = f'<path d="M{tail_x + 4} {cy} L{tail_x - 12} {cy - 12} L{tail_x - 8} {cy} L{tail_x - 12} {cy + 12} Z" fill="{c["fin"]}" {O}/>'
    else:
        tail = f'<path d="M{tail_x + 4} {cy} L{tail_x - 14} {cy - 13} L{tail_x - 8} {cy} L{tail_x - 14} {cy + 13} Z" fill="{c["fin"]}" {O}/>'

    # Плавники сверху и снизу.
    if kind == "angelfish":
        dorsal = f'<path d="M{cx - 8} {cy - ry + 4} L{cx + 4} {cy - ry - 24} L{cx + 12} {cy - ry + 3} Z" fill="{c["fin"]}" {O}/>'
        belly_fin = f'<path d="M{cx - 6} {cy + ry - 4} L{cx + 2} {cy + ry + 24} L{cx + 10} {cy + ry - 3} Z" fill="{c["fin"]}" {O}/>'
    else:
        dorsal = f'<path d="M{cx - 8} {cy - ry + 3} Q{cx} {cy - ry - 14} {cx + 12} {cy - ry + 4} Z" fill="{c["fin"]}" {O}/>'
        belly_fin = f'<path d="M{cx - 2} {cy + ry - 3} Q{cx + 4} {cy + ry + 9} {cx + 12} {cy + ry - 3} Z" fill="{c["fin"]}" {O}/>'

    body = f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{c["body"]}" {O}/>'
    shine = f'<ellipse cx="{cx + 2}" cy="{cy - ry * 0.45}" rx="{rx * 0.55}" ry="{ry * 0.22}" fill="#fff" opacity=".45"/>'

    # Узор вида.
    if kind == "guppy":
        marks = (f'<circle cx="{cx - 4}" cy="{cy + 1}" r="4" fill="{c["mark"]}" opacity=".9"/>'
                 f'<circle cx="{cx - 12}" cy="{cy - 3}" r="2.5" fill="{c["mark"]}" opacity=".9"/>')
    elif kind == "goldfish":
        marks = (f'<path d="M{cx - 6} {cy - ry + 2} Q{cx - 2} {cy} {cx - 6} {cy + ry - 2}" '
                 f'stroke="{c["mark"]}" stroke-width="3" fill="none" stroke-linecap="round" opacity=".8"/>')
    elif kind == "koi":
        marks = (f'<ellipse cx="{cx - 8}" cy="{cy - 4}" rx="9" ry="6" fill="{c["mark"]}"/>'
                 f'<ellipse cx="{cx + 10}" cy="{cy + 3}" rx="6" ry="5" fill="#2B3A4F"/>'
                 f'<ellipse cx="{cx + 2}" cy="{cy + 6}" rx="4" ry="3" fill="{c["mark"]}"/>')
    elif kind == "angelfish":
        marks = "".join(f'<path d="M{x} {cy - ry + 2} Q{x + 3} {cy} {x} {cy + ry - 2}" stroke="{c["mark"]}" '
                        f'stroke-width="3.5" fill="none" stroke-linecap="round"/>' for x in (cx - 6, cx + 6))
    else:
        marks = "".join(f'<path d="M{x} {cy - 5} q3 5 0 10" stroke="{c["mark"]}" stroke-width="2.4" '
                        f'fill="none" stroke-linecap="round"/>' for x in range(cx - 20, cx + 14, 8))

    eye = (f'<circle cx="{head_x - 8}" cy="{cy - 3}" r="4.2" fill="#fff" {ow(1.8)}/>'
           f'<circle cx="{head_x - 7}" cy="{cy - 3}" r="2" fill="{INK}"/>')
    mouth = f'<path d="M{head_x - 1} {cy + 3} q-3 2 -6 0" stroke="{INK}" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
    extra = ""
    if kind == "koi":   # усики
        extra = f'<path d="M{head_x - 2} {cy + 4} q5 4 7 8" stroke="{INK}" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
    return tail + dorsal + belly_fin + body + marks + shine + eye + mouth + extra


def scaled(inner: str, k: float, cx=50, cy=52) -> str:
    return f'<g transform="translate({cx} {cy}) scale({k}) translate({-cx} {-cy})">{inner}</g>'


def egg(kind: str) -> str:
    """Икринка: пара жемчужинок цвета будущей рыбки."""
    color = LOOK[kind]["body"]
    pearls = ""
    for x, y, r in ((44, 60, 8), (58, 63, 7), (51, 50, 6.5)):
        pearls += (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" opacity=".8" {O}/>'
                   f'<circle cx="{x}" cy="{y}" r="{r * 0.35}" fill="{INK}" opacity=".55"/>'
                   f'<circle cx="{x - r * 0.35}" cy="{y - r * 0.4}" r="{r * 0.22}" fill="#fff"/>')
    return svg(pearls)


def sparkle(x, y, r):
    return (f'<path d="M{x} {y - r} L{x + r * .3} {y - r * .3} L{x + r} {y} L{x + r * .3} {y + r * .3} '
            f'L{x} {y + r} L{x - r * .3} {y + r * .3} L{x - r} {y} L{x - r * .3} {y - r * .3} Z" '
            f'fill="#FFE27A" stroke="{INK}" stroke-width="1.2" stroke-linejoin="round"/>')


sprites = {}
for kind in FISH:
    sprites[f"{kind}_seed"] = egg(kind)
    for stage in ("sprout", "young", "adult"):
        sprites[f"{kind}_{stage}"] = svg(scaled(fish_body(kind), STAGE_SCALE[stage]), FISH_VIEW)
    glow = '<circle cx="50" cy="52" r="42" fill="#FFF3B0" opacity=".45"/>'
    sprites[f"{kind}_ready"] = svg(glow + scaled(fish_body(kind), STAGE_SCALE["ready"])
                                   + sparkle(14, 18, 8) + sparkle(88, 26, 6), FISH_VIEW)

# Общие стадии (для совместимости и магазина) — как у гуппи.
sprites["seed"] = egg("guppy")
sprites["sprout"] = sprites["guppy_sprout"]
sprites["young"] = sprites["guppy_young"]

# ---------------- место в пруду: песчаное пятно ----------------
sprites["spot"] = svg(
    '<ellipse cx="70" cy="22" rx="62" ry="15" fill="#E8D5A3" opacity=".55"/>'
    '<ellipse cx="70" cy="22" rx="46" ry="10" fill="#F2E3B8" opacity=".5"/>'
    '<circle cx="40" cy="24" r="2" fill="#B89F6A" opacity=".7"/><circle cx="98" cy="20" r="1.8" fill="#B89F6A" opacity=".7"/>'
    '<circle cx="76" cy="27" r="1.4" fill="#B89F6A" opacity=".7"/>',
    "0 0 140 40")

# ---------------- ил: мутное облачко, забавное, не страшное ----------------
sprites["silt"] = svg(
    f'<path d="M20 70 a14 14 0 0 1 4 -27 a20 20 0 0 1 38 -8 a18 18 0 0 1 22 18 a12 12 0 0 1 -6 17 Z" fill="#9C8F5A" opacity=".85" {O}/>'
    '<path d="M30 60 q10 6 22 0 M52 50 q8 4 16 0" stroke="#7B7040" stroke-width="3" fill="none" stroke-linecap="round"/>'
    f'<circle cx="42" cy="52" r="5" fill="#fff" {ow(2)}/><circle cx="60" cy="52" r="5" fill="#fff" {ow(2)}/>'
    f'<circle cx="43" cy="53" r="2.2" fill="{INK}"/><circle cx="61" cy="53" r="2.2" fill="{INK}"/>'
    f'<path d="M46 63 q5 4 10 0" stroke="{INK}" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
)

# ---------------- мелочи интерфейса ----------------
sprites["bubble"] = svg(
    f'<circle cx="50" cy="50" r="34" fill="#DDF3FF" opacity=".75" {O}/>'
    '<ellipse cx="38" cy="38" rx="9" ry="6" fill="#fff" transform="rotate(-35 38 38)"/>'
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


def pond_icon(n):
    """Значок «пруд n×n» для магазина: вода и n×n песчаных пятен-мест."""
    cell = 76 / n
    spots = "".join(
        f'<circle cx="{12 + i * cell + cell / 2}" cy="{12 + j * cell + cell / 2}" r="{cell / 2 - 3}" fill="#E8D5A3" opacity=".85" {ow(1.6)}/>'
        for i in range(n) for j in range(n))
    return svg(f'<rect x="6" y="6" width="88" height="88" rx="22" fill="#6BC4E8" {O}/>' + spots)


sprites["grid4"] = pond_icon(4)
sprites["grid5"] = pond_icon(5)

# ---------------- декор: водоросли, камни, замок ----------------
sprites["plants"] = svg("".join(
    f'<path d="M{x} 94 C{x - 10} 74 {x + 10} 58 {x} {top}" stroke="{INK}" stroke-width="{w + 2.5}" fill="none" stroke-linecap="round"/>'
    f'<path d="M{x} 94 C{x - 10} 74 {x + 10} 58 {x} {top}" stroke="{col}" stroke-width="{w}" fill="none" stroke-linecap="round"/>'
    for x, top, w, col in ((32, 24, 7, "#3F9A45"), (50, 12, 8, "#5BB85C"), (68, 30, 7, "#3F9A45"))))
sprites["rocks"] = svg(
    f'<path d="M6 94 Q10 62 36 58 Q56 56 62 94 Z" fill="#8E9AA6" {O}/>'
    f'<path d="M44 94 Q50 70 72 68 Q92 68 96 94 Z" fill="#A9B4BE" {O}/>'
    '<path d="M18 74 q6 -6 12 -2 M62 82 q6 -5 14 -1" stroke="#6C7884" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
)
sprites["castle"] = svg(
    f'<rect x="20" y="52" width="60" height="42" fill="#D8C7A2" {O}/>'
    f'<rect x="12" y="34" width="22" height="60" fill="#CDBA91" {O}/><rect x="66" y="34" width="22" height="60" fill="#CDBA91" {O}/>'
    f'<path d="M10 34 L23 12 L36 34 Z M64 34 L77 12 L90 34 Z" fill="#E8795B" {O}/>'
    f'<path d="M40 94 V74 a10 10 0 0 1 20 0 V94 Z" fill="#3B5C7A" {O}/>'
    '<rect x="18" y="52" width="8" height="8" rx="2" fill="#3B5C7A"/><rect x="74" y="52" width="8" height="8" rx="2" fill="#3B5C7A"/>'
)

# ---------------- здания: домик, мостик, маяк (только красота) ----------------
sprites["house"] = svg(
    f'<rect x="18" y="44" width="64" height="48" rx="4" fill="#E8B87A" {O}/>'
    f'<path d="M10 46 L50 14 L90 46 Z" fill="#D9604A" {O}/>'
    f'<rect x="42" y="62" width="18" height="30" rx="9" fill="#3B5C7A" {O}/>'
    f'<circle cx="28" cy="62" r="7" fill="#DDF3FF" {ow(2)}/><circle cx="72" cy="62" r="7" fill="#DDF3FF" {ow(2)}/>'
    f'<rect x="64" y="22" width="9" height="16" fill="#B0695A" {O}/>'
)
sprites["bridge"] = svg(
    f'<path d="M4 70 Q50 6 96 70" fill="none" stroke="{INK}" stroke-width="16" stroke-linecap="round"/>'
    '<path d="M4 70 Q50 6 96 70" fill="none" stroke="#C98B57" stroke-width="11" stroke-linecap="round"/>'
    + "".join(f'<path d="M{x} {y} v-12" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>'
              for x, y in ((22, 50), (36, 36), (50, 31), (64, 36), (78, 50))),
    "0 0 100 80")
sprites["lighthouse"] = svg(
    f'<path d="M36 92 L42 28 H58 L64 92 Z" fill="#F4EFE6" {O}/>'
    '<path d="M38 74 L62 74 L61 62 L39 62 Z M41 50 L59 50 L58 40 L42 40 Z" fill="#D9604A"/>'
    f'<rect x="38" y="20" width="24" height="10" rx="3" fill="#3B5C7A" {O}/>'
    f'<path d="M40 20 L50 6 L60 20 Z" fill="#D9604A" {O}/>'
    '<circle cx="50" cy="25" r="4" fill="#FFE27A"/>'
)

# ---------------- логотип: рыбка в пузыре ----------------
sprites["logo"] = svg(
    f'<circle cx="50" cy="50" r="42" fill="#DDF3FF" {ow(3)}/>'
    + scaled(fish_body("goldfish"), 0.8)
    + '<circle cx="76" cy="26" r="5" fill="#fff" opacity=".8"/><circle cx="84" cy="38" r="3" fill="#fff" opacity=".8"/>'
)

if __name__ == "__main__":
    from focusfarm import fix_console_encoding
    fix_console_encoding()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in sprites.items():
        (OUT / f"{name}.svg").write_text(content, encoding="utf-8")
    print(f"Готово: {len(sprites)} спрайтов в {OUT}")
