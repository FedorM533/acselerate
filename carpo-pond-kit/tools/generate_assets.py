#!/usr/bin/env python3
"""
Генератор SVG-ассетов Carpo Pond.

Все ассеты — оригинальные векторные рисунки, вид на пруд СВЕРХУ.
Запуск:  python3 tools/generate_assets.py
Результат: assets/svg/*.svg (+ PNG, если установлен cairosvg: pip install cairosvg)

Цвета берутся из словаря PALETTE ниже — поменяй их здесь и перезапусти,
чтобы перекрасить весь набор.
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_DIR = os.path.join(ROOT, "assets", "svg")
PNG_DIR = os.path.join(ROOT, "assets", "png")

PALETTE = {
    "koi_white": "#F6F1E7",
    "koi_red": "#D53D29",
    "koi_black": "#1D1E24",
    "koi_gold_a": "#F4C653",
    "koi_gold_b": "#DE942A",
    "koi_silver_a": "#F1F3F2",
    "koi_silver_b": "#C9D2D6",
    "koi_asagi_back": "#7C9AB0",
    "koi_asagi_orange": "#E2773A",
    "pad_center": "#4F9C80",
    "pad_edge": "#2B6A5B",
    "pad_rim": "#1E5045",
    "pad_vein": "#9AD6BA",
    "stone_light": "#B3B5AE",
    "stone_mid": "#7A7E78",
    "stone_dark": "#4E524D",
    "moss_a": "#6F8C3C",
    "moss_b": "#A3B85E",
    "leaf_dark": "#3C7537",
    "leaf_light": "#93C05F",
    "wood_dark": "#5A3D29",
    "wood_light": "#94714F",
    "lotus_pink_base": "#FBE4EA",
    "lotus_pink_tip": "#E5759B",
    "lotus_white_base": "#FFFFFF",
    "lotus_white_tip": "#EEDCE3",
    "lotus_core": "#F2C94C",
    "sakura_petal": "#FBE6EC",
    "sakura_petal_edge": "#F2BCCB",
    "sakura_center": "#DD7E9B",
    "glow_warm": "#FFE6A3",
    "glow_firefly": "#E9FF9E",
}
P = PALETTE


# ---------------------------------------------------------------- helpers
def svg(w, h, body, defs=""):
    d = f"<defs>{defs}</defs>" if defs else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">{d}{body}</svg>\n')


def f2(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def catmull_closed(pts):
    n = len(pts)
    out = [f"M{f2(pts[0][0])},{f2(pts[0][1])}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{f2(c1[0])},{f2(c1[1])} {f2(c2[0])},{f2(c2[1])} {f2(p2[0])},{f2(p2[1])}")
    return " ".join(out) + "Z"


def blob(cx, cy, rx, ry, n=9, jitter=0.15, seed=0, rot=0.0):
    rnd = random.Random(seed)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        k = 1 + rnd.uniform(-jitter, jitter)
        x, y = rx * k * math.cos(a), ry * k * math.sin(a)
        c, s = math.cos(rot), math.sin(rot)
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    return catmull_closed(pts)


def write(name, content):
    os.makedirs(SVG_DIR, exist_ok=True)
    with open(os.path.join(SVG_DIR, name + ".svg"), "w", encoding="utf-8") as fh:
        fh.write(content)
    ASSETS.append(name)


ASSETS = []

# ---------------------------------------------------------------- KOI
# viewBox 120 x 280, голова вверху (смотрит в -Y). Пивот хвоста: (60, 208).
KOI_W, KOI_H = 120, 280
BODY = ("M60,10 C76,10 86,30 87,62 C88,100 80,140 70,175 C66,190 64,200 63,210 "
        "L57,210 C56,200 54,190 50,175 C40,140 32,100 33,62 C34,30 44,10 60,10Z")
PECT = "M82,56 C98,58 114,74 113,100 C105,93 93,83 79,76Z"
PECT_RAYS = [(97, 62), (105, 70), (110, 82), (112, 94)]
PELV = "M74,122 C86,126 92,138 90,150 C85,144 79,138 71,135Z"
TAIL = ("M57,206 C52,225 40,248 28,272 C42,268 54,260 60,252 "
        "C66,260 78,268 92,272 C80,248 68,225 63,206Z")
TAIL_RAYS = [(32, 268), (44, 262), (54, 257), (66, 257), (76, 262), (88, 268)]


def scales_path():
    parts = []
    row = 0
    y = 44
    while y < 205:
        off = 3.5 if row % 2 else 0
        x = 30 + off
        while x < 92:
            parts.append(f"M{f2(x-3.5)},{f2(y)} Q{f2(x)},{f2(y+4)} {f2(x+3.5)},{f2(y)}")
            x += 7
        y += 7
        row += 1
    return " ".join(parts)


SCALES = scales_path()


def fin_group(fill, opacity, ray_color, sumi=False):
    rays = " ".join(f"M82,64 L{x},{y}" for x, y in PECT_RAYS)
    sumi_el = ""
    if sumi:
        sumi_el = (f'<path d="M83,60 C95,64 104,74 108,86" stroke="{P["koi_black"]}" '
                   f'stroke-width="2.2" fill="none" stroke-linecap="round" opacity="0.75"/>')
    one = (f'<path d="{PECT}" fill="{fill}" opacity="{opacity}"/>'
           f'<path d="{rays}" stroke="{ray_color}" stroke-width="0.7" opacity="0.6" fill="none"/>'
           f'{sumi_el}'
           f'<path d="{PELV}" fill="{fill}" opacity="{opacity}"/>')
    return f'<g id="fins">{one}<g transform="translate(120,0) scale(-1,1)">{one}</g></g>'


def tail_group(fill, opacity, ray_color):
    rays = " ".join(f"M60,210 L{x},{y}" for x, y in TAIL_RAYS)
    return (f'<g id="tail"><path d="{TAIL}" fill="{fill}" opacity="{opacity}"/>'
            f'<path d="{rays}" stroke="{ray_color}" stroke-width="0.7" opacity="0.55" fill="none"/></g>')


def koi_svg(variant, part="full"):
    """part: full | body | tail"""
    v = KOI_VARIANTS[variant]
    defs = (
        f'<clipPath id="bodyclip"><path d="{BODY}"/></clipPath>'
        '<linearGradient id="shade" x1="33" y1="0" x2="87" y2="0" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#000" stop-opacity="0.24"/>'
        '<stop offset="0.24" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#fff" stop-opacity="0.20"/>'
        '<stop offset="0.76" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0.24"/></linearGradient>'
        + v.get("defs", "")
    )
    tail = tail_group(v["fin"], v["fin_op"], v["ray"])
    if part == "tail":
        return svg(KOI_W, KOI_H, tail, defs)
    fins = fin_group(v["fin"], v["fin_op"], v["ray"], sumi=v.get("sumi_fins", False))
    body = (
        f'<g id="body"><g clip-path="url(#bodyclip)">'
        f'<path d="{BODY}" fill="{v["base"]}"/>'
        f'{v.get("patches", "")}'
        f'<path d="{SCALES}" stroke="{v["scale"]}" stroke-opacity="{v["scale_op"]}" stroke-width="0.6" fill="none"/>'
        f'<rect x="20" y="0" width="80" height="220" fill="url(#shade)"/>'
        f'<ellipse cx="60" cy="112" rx="2.6" ry="40" fill="#fff" opacity="0.16"/>'
        f'</g>'
        f'<circle cx="46" cy="30" r="2.5" fill="#15171A"/><circle cx="45.3" cy="29.2" r="0.8" fill="#fff"/>'
        f'<circle cx="74" cy="30" r="2.5" fill="#15171A"/><circle cx="73.3" cy="29.2" r="0.8" fill="#fff"/>'
        f'<path d="M53,15 Q49,10 45,9 M67,15 Q71,10 75,9" stroke="{v["fin"]}" stroke-width="1.1" '
        f'fill="none" stroke-linecap="round" opacity="0.9"/>'
        f'</g>'
    )
    content = fins + (tail if part == "full" else "") + body
    return svg(KOI_W, KOI_H, content, defs)


def kohaku_patches(seed=0, color=None):
    c = color or P["koi_red"]
    return (f'<path d="{blob(60, 45, 20, 17, seed=1 + seed, jitter=0.14)}" fill="{c}"/>'
            f'<path d="{blob(66, 104, 26, 32, seed=2 + seed, jitter=0.2)}" fill="{c}"/>'
            f'<path d="{blob(54, 163, 15, 19, seed=3 + seed, jitter=0.2)}" fill="{c}"/>')


KOI_VARIANTS = {
    "kohaku": dict(base=P["koi_white"], patches=kohaku_patches(), fin=P["koi_white"],
                   fin_op=0.62, ray="#ffffff", scale="#000", scale_op=0.07),
    "tancho": dict(base=P["koi_white"],
                   patches=f'<circle cx="60" cy="47" r="13" fill="{P["koi_red"]}"/>',
                   fin=P["koi_white"], fin_op=0.62, ray="#ffffff", scale="#000", scale_op=0.06),
    "sanke": dict(base=P["koi_white"],
                  patches=kohaku_patches(seed=10) +
                  f'<path d="{blob(44, 92, 6, 5, seed=21)}" fill="{P["koi_black"]}"/>'
                  f'<path d="{blob(79, 138, 5, 7, seed=22)}" fill="{P["koi_black"]}"/>'
                  f'<path d="{blob(49, 182, 4, 5, seed=23)}" fill="{P["koi_black"]}"/>'
                  f'<path d="{blob(70, 70, 4, 3.5, seed=24)}" fill="{P["koi_black"]}"/>',
                  fin=P["koi_white"], fin_op=0.62, ray="#ffffff", scale="#000", scale_op=0.07,
                  sumi_fins=True),
    "ogon": dict(base="url(#gold)",
                 defs=('<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">'
                       f'<stop offset="0" stop-color="{P["koi_gold_a"]}"/>'
                       f'<stop offset="1" stop-color="{P["koi_gold_b"]}"/></linearGradient>'),
                 patches='<ellipse cx="60" cy="90" rx="9" ry="70" fill="#fff" opacity="0.22"/>',
                 fin=P["koi_gold_a"], fin_op=0.6, ray="#FFF4C8", scale="#8A5A10", scale_op=0.22),
    "platinum": dict(base="url(#silver)",
                     defs=('<linearGradient id="silver" x1="0" y1="0" x2="0" y2="1">'
                           f'<stop offset="0" stop-color="{P["koi_silver_a"]}"/>'
                           f'<stop offset="1" stop-color="{P["koi_silver_b"]}"/></linearGradient>'),
                     patches='<ellipse cx="60" cy="90" rx="9" ry="70" fill="#fff" opacity="0.35"/>',
                     fin=P["koi_silver_a"], fin_op=0.6, ray="#ffffff", scale="#5D6B72", scale_op=0.18),
    "asagi": dict(base=P["koi_asagi_back"],
                  defs=('<linearGradient id="hi" x1="33" y1="0" x2="87" y2="0" gradientUnits="userSpaceOnUse">'
                        f'<stop offset="0" stop-color="{P["koi_asagi_orange"]}"/>'
                        f'<stop offset="0.2" stop-color="{P["koi_asagi_orange"]}" stop-opacity="0.85"/>'
                        f'<stop offset="0.34" stop-color="{P["koi_asagi_orange"]}" stop-opacity="0"/>'
                        f'<stop offset="0.66" stop-color="{P["koi_asagi_orange"]}" stop-opacity="0"/>'
                        f'<stop offset="0.8" stop-color="{P["koi_asagi_orange"]}" stop-opacity="0.85"/>'
                        f'<stop offset="1" stop-color="{P["koi_asagi_orange"]}"/></linearGradient>'),
                  patches=('<rect x="20" y="40" width="80" height="170" fill="url(#hi)"/>'
                           f'<path d="{blob(60, 32, 21, 20, seed=31, jitter=0.08)}" fill="#DCE6EA"/>'),
                  fin="#F0A06E", fin_op=0.6, ray="#FFE2CC", scale="#2F4A60", scale_op=0.55),
}

for name in KOI_VARIANTS:
    write(f"koi_{name}", koi_svg(name))
    write(f"koi_{name}_body", koi_svg(name, "body"))
    write(f"koi_{name}_tail", koi_svg(name, "tail"))

# мягкая тень под карпом (рисуется под рыбой со смещением ~(+6,+10) px)
write("koi_shadow", svg(KOI_W, KOI_H,
      '<ellipse cx="60" cy="130" rx="36" ry="120" fill="url(#sh)"/>',
      '<radialGradient id="sh"><stop offset="0" stop-color="#001018" stop-opacity="0.45"/>'
      '<stop offset="0.6" stop-color="#001018" stop-opacity="0.2"/>'
      '<stop offset="1" stop-color="#001018" stop-opacity="0"/></radialGradient>'))


# ---------------------------------------------------------------- LILY PADS
def lily_pad(center, edge, rim, vein, notch_deg=-60, curl=False, flecks=True, seed=0):
    cx = cy = 100
    r = 90
    a1 = math.radians(notch_deg + 7)
    a2 = math.radians(notch_deg - 7)
    p1 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    p2 = (cx + r * math.cos(a2), cy + r * math.sin(a2))
    shape = f"M{cx},{cy} L{f2(p1[0])},{f2(p1[1])} A{r},{r} 0 1,1 {f2(p2[0])},{f2(p2[1])}Z"
    defs = (f'<radialGradient id="pad" cx="0.5" cy="0.5" r="0.5">'
            f'<stop offset="0" stop-color="{center}"/><stop offset="0.75" stop-color="{edge}"/>'
            f'<stop offset="1" stop-color="{rim}"/></radialGradient>'
            f'<clipPath id="padclip"><path d="{shape}"/></clipPath>')
    veins = []
    for d in range(0, 360, 18):
        if abs(((d - notch_deg + 180) % 360) - 180) < 14:
            continue
        a = math.radians(d)
        veins.append(f"M{cx},{cy} L{f2(cx + 86 * math.cos(a))},{f2(cy + 86 * math.sin(a))}")
    rnd = random.Random(seed)
    fl = ""
    if flecks:
        for _ in range(14):
            a = rnd.uniform(0, 2 * math.pi)
            rr = rnd.uniform(20, 80)
            fl += (f'<circle cx="{f2(cx + rr * math.cos(a))}" cy="{f2(cy + rr * math.sin(a))}" '
                   f'r="{f2(rnd.uniform(0.8, 2.2))}" fill="#D9C46A" opacity="0.35"/>')
    curl_el = ""
    if curl:
        curl_el = ('<path d="M30,150 C55,185 120,195 165,160 C125,178 70,175 30,150Z" '
                   'fill="#A35A4E" opacity="0.85"/>'
                   '<path d="M30,150 C70,175 125,178 165,160" stroke="#E0A090" stroke-width="1.5" '
                   'fill="none" opacity="0.6"/>')
    body = (f'<path d="{shape}" fill="url(#pad)" stroke="{rim}" stroke-width="2"/>'
            f'<g clip-path="url(#padclip)">'
            f'<path d="{" ".join(veins)}" stroke="{vein}" stroke-width="1.3" opacity="0.33" fill="none"/>'
            f'{fl}'
            f'<ellipse cx="78" cy="70" rx="40" ry="26" fill="#fff" opacity="0.07"/>'
            f'{curl_el}</g>'
            f'<circle cx="{cx}" cy="{cy}" r="3.2" fill="{vein}" opacity="0.8"/>')
    return svg(200, 200, body, defs)


write("lily_pad_a", lily_pad(P["pad_center"], P["pad_edge"], P["pad_rim"], P["pad_vein"], seed=1))
write("lily_pad_b", lily_pad("#86AE5A", "#5C8A3E", "#465F2C", "#D4E8A4", notch_deg=40, seed=2))
write("lily_pad_curled", lily_pad("#5AA585", "#2F7060", P["pad_rim"], P["pad_vein"],
                                  notch_deg=-120, curl=True, seed=3))


# ---------------------------------------------------------------- LOTUS
def petal_ring(n, length, width, rot0, grad_id, cx=100, cy=100):
    w = width
    d = f"M0,0 C{-w},{-length*0.3} {-w*1.05},{-length*0.75} 0,{-length} C{w*1.05},{-length*0.75} {w},{-length*0.3} 0,0Z"
    out = []
    for i in range(n):
        a = rot0 + i * 360 / n
        out.append(f'<path d="{d}" fill="url(#{grad_id})" stroke="#000" stroke-opacity="0.06" '
                   f'stroke-width="0.8" transform="translate({cx},{cy}) rotate({f2(a)})"/>')
    return "".join(out)


def lotus(base, tip, bud=False):
    defs = ""
    for gid, b, t in (("pa", base, tip), ("pb", base, tip), ("pc", base, b_mix(base, tip))):
        defs += (f'<linearGradient id="{gid}" x1="0" y1="1" x2="0" y2="0">'
                 f'<stop offset="0" stop-color="{b}"/><stop offset="1" stop-color="{t}"/></linearGradient>')
    if bud:
        body = (petal_ring(5, 34, 12, 10, "pa", 50, 50) + petal_ring(3, 22, 9, 50, "pc", 50, 50) +
                '<circle cx="50" cy="50" r="3" fill="#C9637F" opacity="0.7"/>')
        return svg(100, 100, body, defs)
    seeds = "".join(
        f'<circle cx="{f2(100 + 6.5 * math.cos(i * 1.2566))}" cy="{f2(100 + 6.5 * math.sin(i * 1.2566))}" '
        f'r="1.6" fill="#B98A22"/>' for i in range(5))
    stamens = "".join(
        f'<circle cx="{f2(100 + 18 * math.cos(i * 0.3927))}" cy="{f2(100 + 18 * math.sin(i * 0.3927))}" '
        f'r="2" fill="#F7D774"/>' for i in range(16))
    body = (petal_ring(8, 86, 26, 0, "pa") + petal_ring(8, 64, 20, 22.5, "pb") +
            petal_ring(6, 40, 14, 10, "pc") + stamens +
            f'<circle cx="100" cy="100" r="13" fill="{P["lotus_core"]}"/>' + seeds)
    return svg(200, 200, body, defs)


def b_mix(a, b, t=0.45):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


write("lotus_pink", lotus(P["lotus_pink_base"], P["lotus_pink_tip"]))
write("lotus_white", lotus(P["lotus_white_base"], P["lotus_white_tip"]))
write("lotus_bud", lotus(P["lotus_pink_base"], "#D9618A", bud=True))


# ---------------------------------------------------------------- STONES
def stone(seed, rx, ry, rot, mossy=False):
    shape = blob(100, 100, rx, ry, n=8, jitter=0.12, seed=seed, rot=rot)
    rnd = random.Random(seed * 7)
    defs = ('<radialGradient id="st" cx="0.38" cy="0.32" r="0.75">'
            f'<stop offset="0" stop-color="{P["stone_light"]}"/>'
            f'<stop offset="0.6" stop-color="{P["stone_mid"]}"/>'
            f'<stop offset="1" stop-color="{P["stone_dark"]}"/></radialGradient>'
            f'<clipPath id="stclip"><path d="{shape}"/></clipPath>'
            '<radialGradient id="stsh"><stop offset="0" stop-color="#001018" stop-opacity="0.45"/>'
            '<stop offset="1" stop-color="#001018" stop-opacity="0"/></radialGradient>')
    speck = "".join(
        f'<circle cx="{f2(rnd.uniform(40, 160))}" cy="{f2(rnd.uniform(40, 160))}" r="{f2(rnd.uniform(0.6, 1.8))}" '
        f'fill="{rnd.choice(["#3F433F", "#D6D7D1"])}" opacity="0.5"/>' for _ in range(40))
    crack = (f'<path d="M{f2(rnd.uniform(60, 90))},{f2(rnd.uniform(70, 90))} '
             f'q{f2(rnd.uniform(10, 25))},{f2(rnd.uniform(5, 15))} {f2(rnd.uniform(25, 45))},{f2(rnd.uniform(15, 35))}" '
             f'stroke="#3F433F" stroke-width="1.2" fill="none" opacity="0.45"/>')
    moss = ""
    if mossy:
        moss = (f'<path d="{blob(80, 72, rx * 0.55, ry * 0.42, n=10, jitter=0.3, seed=seed + 50)}" fill="{P["moss_a"]}" opacity="0.95"/>'
                f'<path d="{blob(118, 60, rx * 0.3, ry * 0.25, n=8, jitter=0.3, seed=seed + 51)}" fill="{P["moss_a"]}" opacity="0.9"/>'
                f'<path d="{blob(78, 68, rx * 0.35, ry * 0.25, n=9, jitter=0.3, seed=seed + 52)}" fill="{P["moss_b"]}" opacity="0.85"/>')
        moss += "".join(
            f'<circle cx="{f2(rnd.uniform(55, 130))}" cy="{f2(rnd.uniform(45, 95))}" r="{f2(rnd.uniform(1, 2.4))}" '
            f'fill="{P["moss_b"]}" opacity="0.8"/>' for _ in range(18))
    body = (f'<ellipse cx="108" cy="110" rx="{rx + 6}" ry="{ry + 6}" fill="url(#stsh)"/>'
            f'<path d="{shape}" fill="url(#st)"/>'
            f'<g clip-path="url(#stclip)">{speck}{crack}{moss}</g>')
    return svg(200, 200, body, defs)


for nm, args in {"a": (11, 70, 52, 0.3), "b": (12, 58, 58, 1.1), "c": (13, 74, 40, -0.4)}.items():
    write(f"stone_{nm}", stone(*args))
    write(f"stone_{nm}_mossy", stone(*args, mossy=True))


# ---------------------------------------------------------------- PLANTS
def reeds(seed=5):
    rnd = random.Random(seed)
    defs = ('<linearGradient id="bl" x1="0" y1="1" x2="0" y2="0">'
            f'<stop offset="0" stop-color="{P["leaf_dark"]}"/><stop offset="1" stop-color="{P["leaf_light"]}"/></linearGradient>')
    blades = []
    for i in range(26):
        a = i * 360 / 26 + rnd.uniform(-6, 6)
        L = rnd.uniform(55, 95)
        w = rnd.uniform(3, 5.5)
        bend = rnd.uniform(-14, 14)
        d = f"M{-w},0 Q{bend - w * 0.4},{-L * 0.6} {bend * 1.4},{-L} Q{bend + w * 0.4},{-L * 0.6} {w},0Z"
        blades.append(f'<path d="{d}" fill="url(#bl)" transform="translate(100,100) rotate({f2(a)})"/>')
    body = '<circle cx="100" cy="100" r="16" fill="#2E5A2B"/>' + "".join(blades)
    return svg(200, 200, body, defs)


def fern(seed=8):
    rnd = random.Random(seed)
    fronds = []
    for i in range(6):
        a = i * 60 + rnd.uniform(-10, 10)
        L = rnd.uniform(78, 92)
        leaflets = []
        for k in range(1, 12):
            t = k / 12
            y = -L * t
            s = (1 - t) * 11 + 2
            leaflets.append(f'<ellipse cx="{f2(-s * 0.9)}" cy="{f2(y)}" rx="{f2(s)}" ry="{f2(s * 0.38)}" '
                            f'transform="rotate(-28 {f2(-s * 0.9)} {f2(y)})" fill="{P["leaf_light"] if k % 3 else "#7DAE52"}"/>')
            leaflets.append(f'<ellipse cx="{f2(s * 0.9)}" cy="{f2(y - 2)}" rx="{f2(s)}" ry="{f2(s * 0.38)}" '
                            f'transform="rotate(28 {f2(s * 0.9)} {f2(y - 2)})" fill="#6FA44C"/>')
        fronds.append(f'<g transform="translate(100,100) rotate({f2(a)})">'
                      f'{"".join(leaflets)}<path d="M0,0 Q4,{-L / 2} 0,{-L}" stroke="{P["leaf_dark"]}" stroke-width="1.6" fill="none"/></g>')
    return svg(200, 200, "".join(fronds))


write("reeds", reeds())
write("fern", fern())

# коряга
write("driftwood", svg(300, 120,
      '<path d="M18,78 C70,60 130,70 190,56 C220,49 255,40 286,30" stroke="url(#wd)" stroke-width="20" '
      'stroke-linecap="round" fill="none"/>'
      '<path d="M150,64 C170,80 196,92 228,98" stroke="url(#wd)" stroke-width="11" stroke-linecap="round" fill="none"/>'
      '<path d="M96,68 C104,50 108,36 118,22" stroke="url(#wd)" stroke-width="8" stroke-linecap="round" fill="none"/>'
      '<path d="M24,72 C80,55 140,64 200,50 C235,42 260,35 282,27" stroke="#C9A982" stroke-width="3" '
      'opacity="0.45" fill="none" stroke-linecap="round"/>'
      '<ellipse cx="120" cy="64" rx="5" ry="3.5" fill="#3E2A1C"/><ellipse cx="210" cy="51" rx="4" ry="3" fill="#3E2A1C"/>'
      f'<path d="{blob(70, 64, 16, 7, seed=91, jitter=0.3)}" fill="{P["moss_a"]}" opacity="0.8"/>',
      '<linearGradient id="wd" x1="0" y1="0" x2="0" y2="1">'
      f'<stop offset="0" stop-color="{P["wood_light"]}"/><stop offset="1" stop-color="{P["wood_dark"]}"/></linearGradient>'))

# каменный фонарь (вид сверху: шестигранная крыша)
hexpts = [(100 + 70 * math.cos(math.radians(60 * i + 30)), 100 + 70 * math.sin(math.radians(60 * i + 30))) for i in range(6)]
hexd = "M" + " L".join(f"{f2(x)},{f2(y)}" for x, y in hexpts) + "Z"
ridges = "".join(f'<path d="M100,100 L{f2(x)},{f2(y)}" stroke="#5A5E58" stroke-width="2" opacity="0.6"/>' for x, y in hexpts)
write("stone_lantern", svg(200, 200,
      '<ellipse cx="108" cy="110" rx="78" ry="78" fill="url(#lsh)"/>'
      f'<path d="{hexd}" fill="url(#roof)" stroke="#4E524D" stroke-width="3" stroke-linejoin="round"/>'
      + ridges +
      f'<path d="{blob(70, 80, 18, 12, seed=71, jitter=0.3)}" fill="{P["moss_a"]}" opacity="0.85"/>'
      '<circle cx="100" cy="100" r="16" fill="url(#roof)" stroke="#4E524D" stroke-width="2"/>'
      '<circle cx="100" cy="97" r="7" fill="#C2C4BD"/>',
      '<radialGradient id="roof" cx="0.4" cy="0.35" r="0.8">'
      f'<stop offset="0" stop-color="{P["stone_light"]}"/><stop offset="1" stop-color="{P["stone_mid"]}"/></radialGradient>'
      '<radialGradient id="lsh"><stop offset="0" stop-color="#001018" stop-opacity="0.5"/>'
      '<stop offset="1" stop-color="#001018" stop-opacity="0"/></radialGradient>'))

write("lantern_glow", svg(400, 400, '<circle cx="200" cy="200" r="200" fill="url(#g)"/>',
      f'<radialGradient id="g"><stop offset="0" stop-color="{P["glow_warm"]}" stop-opacity="0.75"/>'
      f'<stop offset="0.35" stop-color="{P["glow_warm"]}" stop-opacity="0.28"/>'
      f'<stop offset="1" stop-color="{P["glow_warm"]}" stop-opacity="0"/></radialGradient>'))


# ---------------------------------------------------------------- SAKURA
def sakura_flower(cx, cy, r, rot):
    petal = (f"M0,0 C{-r * 0.55},{-r * 0.25} {-r * 0.6},{-r * 0.85} {-r * 0.18},{-r} "
             f"L0,{-r * 0.84} L{r * 0.18},{-r} C{r * 0.6},{-r * 0.85} {r * 0.55},{-r * 0.25} 0,0Z")
    out = "".join(f'<path d="{petal}" fill="url(#sp)" transform="translate({f2(cx)},{f2(cy)}) rotate({f2(rot + i * 72)})"/>'
                  for i in range(5))
    return out + f'<circle cx="{f2(cx)}" cy="{f2(cy)}" r="{f2(r * 0.22)}" fill="{P["sakura_center"]}"/>'


def sakura_branch(seed=4):
    rnd = random.Random(seed)
    branch = ('<path d="M400,400 C330,350 280,300 230,250 C190,210 140,190 80,170" stroke="#4A3328" '
              'stroke-width="14" fill="none" stroke-linecap="round"/>'
              '<path d="M300,320 C300,260 320,210 350,170" stroke="#4A3328" stroke-width="8" fill="none" stroke-linecap="round"/>'
              '<path d="M200,225 C190,180 160,140 120,110" stroke="#4A3328" stroke-width="6" fill="none" stroke-linecap="round"/>'
              '<path d="M150,190 C120,210 90,230 50,240" stroke="#4A3328" stroke-width="5" fill="none" stroke-linecap="round"/>')
    centers = [(350, 170), (120, 110), (50, 240), (80, 170), (230, 250), (300, 300), (260, 270), (180, 200), (330, 220)]
    flowers = ""
    for (x, y) in centers:
        for _ in range(4):
            flowers += sakura_flower(x + rnd.uniform(-26, 26), y + rnd.uniform(-26, 26),
                                     rnd.uniform(11, 16), rnd.uniform(0, 72))
    defs = (f'<radialGradient id="sp" cx="0.5" cy="1" r="1"><stop offset="0" stop-color="{P["sakura_petal"]}"/>'
            f'<stop offset="1" stop-color="{P["sakura_petal_edge"]}"/></radialGradient>')
    return svg(400, 400, branch + flowers, defs)


write("sakura_branch", sakura_branch())
write("sakura_petal", svg(40, 40,
      '<path d="M20,36 C8,30 6,14 14,5 L20,10 L26,5 C34,14 32,30 20,36Z" fill="url(#sp)"/>',
      f'<linearGradient id="sp" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{P["sakura_petal"]}"/>'
      f'<stop offset="1" stop-color="{P["sakura_petal_edge"]}"/></linearGradient>'))

# ---------------------------------------------------------------- FX
write("ripple", svg(200, 200,
      '<circle cx="100" cy="100" r="92" stroke="#fff" stroke-width="2.5" fill="none" opacity="0.55"/>'
      '<circle cx="100" cy="100" r="74" stroke="#fff" stroke-width="1.5" fill="none" opacity="0.28"/>'))
for nm, col in (("light_particle", P["glow_warm"]), ("firefly", P["glow_firefly"])):
    write(nm, svg(64, 64,
          '<circle cx="32" cy="32" r="32" fill="url(#g)"/><circle cx="32" cy="32" r="3.2" fill="#fff"/>',
          f'<radialGradient id="g"><stop offset="0" stop-color="{col}" stop-opacity="1"/>'
          f'<stop offset="0.3" stop-color="{col}" stop-opacity="0.45"/>'
          f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>'))


# ---------------------------------------------------------------- WATER (1000 x 1600, портрет)
WATER = {
    "day":   ("#3B8E8B", "#1F5F66", "#0D3540", None),
    "dusk":  ("#4C6F78", "#2B4757", "#152434", "#F2A65A"),
    "night": ("#1F3D4E", "#10243A", "#050D19", "#BFD7FF"),
}
for tod, (c0, c1, c2, tint) in WATER.items():
    rnd = random.Random(42)
    # мягкие «глубокие места» — эллипсы с радиальным градиентом, без фильтров
    deep = "".join(f'<ellipse cx="{f2(rnd.uniform(150, 850))}" cy="{f2(rnd.uniform(200, 1400))}" '
                   f'rx="{f2(rnd.uniform(160, 300))}" ry="{f2(rnd.uniform(180, 340))}" fill="url(#deep)"/>' for i in range(7))
    tint_el = ""
    if tint:
        tint_el = '<rect width="1000" height="1600" fill="url(#tint)"/>'
    defs = (f'<radialGradient id="w" cx="0.5" cy="0.45" r="0.75"><stop offset="0" stop-color="{c0}"/>'
            f'<stop offset="0.6" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></radialGradient>'
            f'<radialGradient id="deep"><stop offset="0" stop-color="{c2}" stop-opacity="0.45"/>'
            f'<stop offset="1" stop-color="{c2}" stop-opacity="0"/></radialGradient>')
    if tint:
        op = 0.22 if tod == "dusk" else 0.12
        defs += (f'<radialGradient id="tint" cx="{0.2 if tod == "dusk" else 0.75}" cy="0.08" r="0.7">'
                 f'<stop offset="0" stop-color="{tint}" stop-opacity="{op}"/>'
                 f'<stop offset="1" stop-color="{tint}" stop-opacity="0"/></radialGradient>')
    write(f"water_{tod}", svg(1000, 1600, f'<rect width="1000" height="1600" fill="url(#w)"/>{deep}{tint_el}', defs))


def caustics(seed=3):
    rnd = random.Random(seed)
    step = 110
    cols, rows = 11, 17
    pts = [[(c * step + rnd.uniform(-40, 40) - 50, r * step + rnd.uniform(-40, 40) - 50) for c in range(cols)] for r in range(rows)]
    paths = []
    for r in range(rows):
        for c in range(cols):
            x, y = pts[r][c]
            for (dr, dc) in ((0, 1), (1, 0)):
                rr, cc = r + dr, c + dc
                if rr < rows and cc < cols:
                    x2, y2 = pts[rr][cc]
                    ax, ay = x + (x2 - x) / 3 + rnd.uniform(-28, 28), y + (y2 - y) / 3 + rnd.uniform(-28, 28)
                    bx, by = x + 2 * (x2 - x) / 3 + rnd.uniform(-28, 28), y + 2 * (y2 - y) / 3 + rnd.uniform(-28, 28)
                    paths.append(f"M{f2(x)},{f2(y)} C{f2(ax)},{f2(ay)} {f2(bx)},{f2(by)} {f2(x2)},{f2(y2)}")
    return svg(1000, 1600, f'<path d="{" ".join(paths)}" stroke="#E8FFFA" stroke-width="2.2" '
               f'stroke-linecap="round" fill="none" opacity="0.075"/>')


write("caustics", caustics())

# ---------------------------------------------------------------- APP ICON
def koi_inner(variant):
    s = koi_svg(variant)
    inner = s.split(">", 1)[1].rsplit("</svg>", 1)[0]
    return inner


icon_koi = koi_inner("kohaku")
write("app_icon", svg(1024, 1024,
      '<rect width="1024" height="1024" rx="230" fill="url(#bg)"/>'
      '<circle cx="512" cy="512" r="330" stroke="#fff" stroke-width="6" fill="none" opacity="0.14"/>'
      '<circle cx="512" cy="512" r="410" stroke="#fff" stroke-width="4" fill="none" opacity="0.08"/>'
      f'<g transform="translate(512,500) rotate(32) scale(2.55) translate(-60,-140)">{icon_koi}</g>',
      '<radialGradient id="bg" cx="0.5" cy="0.45" r="0.7"><stop offset="0" stop-color="#2F8382"/>'
      '<stop offset="1" stop-color="#0D3540"/></radialGradient>'))
write("app_icon_foreground", svg(1024, 1024,
      f'<g transform="translate(512,500) rotate(32) scale(2.0) translate(-60,-140)">{icon_koi}</g>'))
write("app_icon_background", svg(1024, 1024, '<rect width="1024" height="1024" fill="url(#bg)"/>',
      '<radialGradient id="bg" cx="0.5" cy="0.45" r="0.7"><stop offset="0" stop-color="#2F8382"/>'
      '<stop offset="1" stop-color="#0D3540"/></radialGradient>'))


# ---------------------------------------------------------------- PNG export
def export_png():
    try:
        import cairosvg
    except ImportError:
        print("cairosvg не установлен — PNG пропущены (pip install cairosvg)")
        return
    for name in ASSETS:
        src = os.path.join(SVG_DIR, name + ".svg")
        big = name.startswith(("water_", "caustics", "app_icon"))
        scales = ((2 if name.startswith(("water_", "caustics")) else 1),) if big else (1, 2, 3)
        for sc in scales:
            sub = os.path.join(PNG_DIR, f"{sc}x") if not big else os.path.join(PNG_DIR, "full")
            os.makedirs(sub, exist_ok=True)
            cairosvg.svg2png(url=src, write_to=os.path.join(sub, name + ".png"), scale=sc)


def write_manifest():
    import json
    import re
    kinds = {
        "koi_": "koi", "lily_pad": "surface", "lotus": "surface", "stone_lantern": "shore",
        "stone_": "shore", "reeds": "shore", "fern": "shore", "driftwood": "shore",
        "sakura_branch": "overhang", "sakura_petal": "ambient", "lantern_glow": "glow",
        "ripple": "fx", "light_particle": "fx", "firefly": "ambient", "water_": "water",
        "caustics": "caustics", "app_icon": "icon",
    }
    items = []
    for name in ASSETS:
        txt = open(os.path.join(SVG_DIR, name + ".svg"), encoding="utf-8").read()
        w, h = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', txt).groups())
        kind = next(v for k, v in kinds.items() if name.startswith(k))
        it = {"id": name, "svg": f"svg/{name}.svg", "viewBox": [w, h], "kind": kind}
        if not name.startswith(("water_", "caustics", "app_icon")):
            it["png"] = {s: f"png/{s}/{name}.png" for s in ("1x", "2x", "3x")}
        else:
            it["png"] = {"full": f"png/full/{name}.png"}
        if kind == "koi" and name != "koi_shadow":
            it["headDirection"] = "up (-Y); при движении поворачивать на atan2(vy, vx) + 90°"
            it["tailPivot"] = [60, 208]
            if not name.endswith(("_body", "_tail")):
                it["parts"] = {"body": f"{name}_body", "tail": f"{name}_tail"}
                it["svgTailGroupId"] = "tail"
        if name == "koi_shadow":
            it["usage"] = "рисовать под каждым карпом, смещение (+6, +10) в пикселях холста, тот же поворот"
        items.append(it)
    json.dump({"_comment": "Все ассеты — вид сверху. Размеры viewBox — исходные единицы SVG. PNG 1x = размер viewBox; water_* и caustics в png/full экспортированы в 2x (2000x3200), иконки — 1024x1024.",
               "assets": items},
              open(os.path.join(ROOT, "assets", "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    write_manifest()
    export_png()
    print(f"OK: {len(ASSETS)} SVG -> {SVG_DIR}")
