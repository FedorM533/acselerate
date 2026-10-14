#!/usr/bin/env python3
"""
Carpo Pond v2 — генератор реалистичных растровых ассетов.

Карпы: процедурная текстура (перекрывающаяся чешуя, мягкие края пятен, перламутр/металлик),
объём по карте высот (диффуз + блик), полупрозрачные плавники с лучами.
Вода: глубина по шуму, размытое дно, каустика двумя отдельными слоями (для анимации).
Декор: берётся из векторных ассетов v1 и «оживляется» — зерно, объём, свет.

Запуск из корня комплекта:   pip install cairosvg numpy scipy pillow
                              python3 v2/tools/generate_assets_v2.py
Время работы: ~2–4 минуты.
"""
import io
import json
import math
import os
import random

import cairosvg
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V1_SVG = os.path.join(KIT, "assets", "svg")
OUT = os.path.join(KIT, "v2", "assets")
RNG = np.random.default_rng(7)
MANIFEST = []


# ------------------------------------------------------------------ утилиты
def hexc(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255.0


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def fbm(h, w, octaves=5, base=8, seed=0, persistence=0.5):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp = tot = 0.0
    amp = 1.0
    for o in range(octaves):
        gy, gx = max(2, int(h / base * 2 ** o / 4)), max(2, int(w / base * 2 ** o / 4))
        g = rng.random((gy + 3, gx + 3)).astype(np.float32)
        z = ndi.zoom(g, ((h + 1) / gy, (w + 1) / gx), order=3)[:h, :w]
        out += amp * z
        tot += amp
        amp *= persistence
    out /= tot
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


def mask_from_paths(paths, w, h, scale):
    body = "".join(f'<path d="{p}" fill="#fff"/>' for p in paths)
    s = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
         f'<rect width="{w}" height="{h}" fill="#000"/>{body}</svg>')
    png = cairosvg.svg2png(bytestring=s.encode(), scale=scale)
    return np.asarray(Image.open(io.BytesIO(png)).convert("L"), dtype=np.float32) / 255.0


def blob(cx, cy, rx, ry, n=9, jitter=0.15, seed=0):
    rnd = random.Random(seed)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        k = 1 + rnd.uniform(-jitter, jitter)
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    out = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(out) + "Z"


def lighting(mask, blur=14, k=90.0, power=14):
    dist = ndi.distance_transform_edt(mask > 0.5).astype(np.float32)
    hmap = np.sqrt(np.clip(dist / (dist.max() + 1e-6), 0, 1))
    hmap = ndi.gaussian_filter(hmap, blur)
    hmap = hmap / (hmap.max() + 1e-6) * mask
    gy, gx = np.gradient(hmap)
    nx, ny, nz = -gx * k, -gy * k, np.ones_like(hmap)
    nl = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    nx, ny, nz = nx / nl, ny / nl, nz / nl
    L = np.array([-0.45, -0.55, 0.7]); L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    Hh = L + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    spec = np.clip(nx * Hh[0] + ny * Hh[1] + nz * Hh[2], 0, 1) ** power
    return lam, spec, hmap


def save(img, name, kind, sizes, extra=None):
    """sizes: dict folder -> (w, h)."""
    item = {"id": name, "kind": kind, "files": {}}
    for folder, (w, h) in sizes.items():
        d = os.path.join(OUT, folder)
        os.makedirs(d, exist_ok=True)
        im = img if img.size == (w, h) else img.resize((w, h), Image.LANCZOS)
        if im.mode == "RGB":
            p = os.path.join(d, name + ".jpg")
            im.save(p, quality=90)
        else:
            p = os.path.join(d, name + ".png")
            im.save(p, optimize=True)
        im.save(os.path.join(d, name + ".webp"), quality=86, method=6)
        item["files"][folder] = os.path.relpath(p, OUT)
        item["files"][folder + "_webp"] = os.path.relpath(os.path.join(d, name + ".webp"), OUT)
    item["size"] = list(img.size)
    if extra:
        item.update(extra)
    MANIFEST.append(item)


# ------------------------------------------------------------------ КАРПЫ
S = 4
KW, KH = 120 * S, 280 * S
BODY = ("M60,9 C75,9 85,20 87,44 C89,72 86,108 79,142 C75,162 67,190 63,210 "
        "L57,210 C53,190 45,162 41,142 C34,108 31,72 33,44 C35,20 45,9 60,9Z")
PECT_R = "M83,54 C102,54 120,72 118,104 C108,96 95,86 79,78Z"
PECT_L = "M37,54 C18,54 0,72 2,104 C12,96 25,86 41,78Z"
PELV_R = "M75,124 C89,127 96,142 93,156 C87,149 80,142 72,138Z"
PELV_L = "M45,124 C31,127 24,142 27,156 C33,149 40,142 48,138Z"
TAIL = ("M57,204 C50,225 36,250 22,276 C38,272 52,262 60,252 "
        "C68,262 82,272 98,276 C84,250 70,225 63,204Z")
DORSAL = "M58.5,80 C57,100 57,130 59,154 L61,154 C63,130 63,100 61.5,80Z"


def scale_field(h, w, r, mask, seed=5):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dy = r * 0.95
    best = np.full((h, w), 1e9, np.float32)
    ring = np.zeros((h, w), np.float32)
    shade = np.zeros((h, w), np.float32)
    cid = np.zeros((h, w), np.float32)
    rows, cols = int(h / dy) + 3, int(w / r) + 3
    rnd = rng.random((rows, cols)).astype(np.float32)
    for ri in range(-1, rows - 1):
        cy = ri * dy
        off = (r / 2) if ri % 2 else 0
        for ci in range(-1, cols - 1):
            cx = ci * r + off
            y0, y1 = int(max(0, cy - r)), int(min(h, cy + r + 1))
            x0, x1 = int(max(0, cx - r)), int(min(w, cx + r + 1))
            if y0 >= y1 or x0 >= x1:
                continue
            sy, sx = yy[y0:y1, x0:x1], xx[y0:y1, x0:x1]
            d = np.sqrt((sx - cx) ** 2 + (sy - cy) ** 2) / r
            b = best[y0:y1, x0:x1]
            inside = (d < 1.0) & (cy < b)
            b[inside] = cy
            ring[y0:y1, x0:x1][inside] = smoothstep(0.72, 0.98, d[inside])
            shade[y0:y1, x0:x1][inside] = np.clip((sy[inside] - cy) / r, -1, 1)
            cid[y0:y1, x0:x1][inside] = rnd[ri + 1, ci + 1]
    return ring * mask, shade * mask, cid * mask


# общие маски и поля считаются один раз
_body = mask_from_paths([BODY], 120, 280, S)
_tail = mask_from_paths([TAIL], 120, 280, S)
_dorsal = mask_from_paths([DORSAL], 120, 280, S)
_fins = [(mask_from_paths([PECT_R], 120, 280, S), 82, 62, 14),
         (mask_from_paths([PECT_L], 120, 280, S), 38, 62, 14),
         (mask_from_paths([PELV_R, PELV_L], 120, 280, S), 60, 130, 18),
         (_tail, 60, 206, 22)]
_noise = fbm(KH, KW, 5, base=6, seed=3)
_fine = fbm(KH, KW, 3, base=1.5, seed=4)
_ring, _sshade, _cid = scale_field(KH, KW, 4.2 * S, _body)
_lam, _spec, _hmap = lighting(_body)
_YY, _XX = np.mgrid[0:KH, 0:KW].astype(np.float32)


def soft_patch(paths, blur=1.6, warp_amt=0.4, fine_amt=0.12, lo=0.44, hi=0.56):
    pm = mask_from_paths(paths, 120, 280, S)
    pm = ndi.gaussian_filter(pm, blur * S)
    warp = (_noise - 0.5) * warp_amt + (_fine - 0.5) * fine_amt
    return smoothstep(lo, hi, pm + warp) * _body


def koi_colors(variant):
    """Возвращает col(H,W,3), scale_strength(H,W), rim_color|None, metallic, fin_col, fin_alpha, fin_marks"""
    t = (_YY / KH)[..., None]
    zeros = np.zeros((KH, KW), np.float32)
    fin_marks = None
    rim_color = None
    if variant in ("kohaku", "sanke", "tancho"):
        base = hexc("#F4EFE6")
        col = np.broadcast_to(base, (KH, KW, 3)).copy()
        pearl = (fbm(KH, KW, 3, base=30, seed=9) - 0.5)[..., None]
        if variant == "tancho":
            yy, xx = _YY / S, _XX / S
            d = np.sqrt((xx - 60) ** 2 + (yy - 48) ** 2)
            patch = smoothstep(13.5, 12.0, d + (_fine - 0.5) * 1.6) * _body
        else:
            seed = 0 if variant == "kohaku" else 10
            patch = soft_patch([blob(60, 45, 20, 17, seed=1 + seed, jitter=0.14),
                                blob(66, 104, 26, 32, seed=2 + seed, jitter=0.2),
                                blob(54, 163, 15, 19, seed=3 + seed, jitter=0.2)])
        red = hexc("#C42A1C") * (1 - (0.55 * _noise + 0.45 * _fine)[..., None]) + \
            hexc("#E2502E") * (0.55 * _noise + 0.45 * _fine)[..., None]
        col = col * (1 - patch[..., None]) + red * patch[..., None]
        col = col + pearl * np.array([0.05, 0.02, 0.08], np.float32) * (1 - patch[..., None])
        nose = smoothstep(60 * S, 14 * S, _YY)[..., None]
        col = col * (1 - 0.15 * nose) + hexc("#F2C2B4") * 0.15 * nose * (1 - patch[..., None])
        sumi = zeros
        if variant == "sanke":
            sumi = soft_patch([blob(44, 92, 6, 5, seed=21), blob(79, 138, 5, 7, seed=22),
                               blob(49, 182, 4, 5, seed=23), blob(70, 70, 4, 3.5, seed=24),
                               blob(62, 120, 3.5, 4, seed=25)], blur=0.9, warp_amt=0.25, lo=0.40, hi=0.55)
            col = col * (1 - sumi[..., None]) + hexc("#17181C") * sumi[..., None]
            fin_marks = "sumi"
        strength = 0.05 + 0.13 * patch + 0.05 * sumi
        return col, strength, rim_color, 0.25, hexc("#FFFFFF"), 0.88, fin_marks
    if variant == "ogon":
        col = hexc("#F7D57A") * (1 - t) + hexc("#D98A1E") * t
        col = col * (0.9 + 0.2 * _noise[..., None])
        return col, 0.16 + zeros, None, 0.9, hexc("#F7CF73"), 0.8, None
    if variant == "platinum":
        col = hexc("#EEF2F4") * (1 - t) + hexc("#9FAAB2") * t
        sheen = (0.5 + 0.5 * np.sin(_XX / S * 0.25 + _noise * 6))[..., None]
        col = col * (0.86 + 0.2 * sheen) + np.array([0.0, 0.01, 0.03], np.float32)
        return col, 0.22 + zeros, None, 1.3, hexc("#E6ECEF"), 0.8, None
    if variant == "asagi":
        xx = _XX / S
        side = smoothstep(0.55, 0.95, np.abs(xx - 60) / 27 + (_noise - 0.5) * 0.25)
        side *= smoothstep(30, 60, _YY / S) * (1 - smoothstep(170, 205, _YY / S))
        back = hexc("#5F84A3") * (1 - t) + hexc("#476C8C") * t
        col = back * (1 - side[..., None]) + hexc("#E2773A") * side[..., None]
        head = soft_patch([blob(60, 24, 17, 15, seed=31, jitter=0.08)], blur=5, warp_amt=0.15) * 0.75
        col = col * (1 - head[..., None]) + hexc("#B9CCD8") * head[..., None]
        strength = 0.55 * (1 - side) * (1 - head)
        return col, strength, hexc("#DDEAF3"), 0.35, hexc("#F3A574"), 0.82, None
    raise ValueError(variant)


def make_koi(variant):
    col, strength, rim_color, metallic, fin_col, fin_alpha, fin_marks = koi_colors(variant)
    sh = (strength * _ring)[..., None]
    if rim_color is None:
        col = col * (1 - sh * 0.9)
    else:  # у асаги край чешуи светлый — «сетка»
        col = col * (1 - sh) + rim_color * sh * 0.85
    glint = (0.5 + 0.5 * np.sin(_cid * 40.0)) * (1 - _ring) * smoothstep(-0.2, 0.6, -_sshade)
    col = col + (metallic * 0.22 * glint)[..., None]
    col = col * (0.72 + 0.38 * _lam)[..., None] + (_spec * (0.10 + 0.22 * metallic))[..., None]
    rim = smoothstep(0.35, 0.0, _hmap)[..., None]
    col = col * (1 - 0.22 * rim) * (0.97 + 0.06 * _fine[..., None])
    col = col * (1 - 0.12 * _dorsal[..., None]) + 0.06 * _dorsal[..., None]

    rgb = np.zeros((KH, KW, 3), np.float32)
    alpha = np.zeros((KH, KW), np.float32)
    for m, ox, oy, nr in _fins:
        ang = np.arctan2(_YY - oy * S, _XX - ox * S)
        rays = smoothstep(0.75, 1.0, 0.5 + 0.5 * np.cos(ang * nr * 2))
        dist = np.sqrt((_YY - oy * S) ** 2 + (_XX - ox * S) ** 2) / (40 * S)
        a = m * fin_alpha * np.clip(1.0 - 0.5 * dist, 0.32, 1.0) * (0.85 + 0.3 * _fine)
        a = np.clip(a + m * 0.22 * rays * np.clip(1.1 - 0.5 * dist, 0, 1), 0, 1)
        c = fin_col[None, None] * (0.92 + 0.12 * rays[..., None])
        if fin_marks == "sumi" and oy == 62:      # чёрные полосы на грудных плавниках санке
            stripe = smoothstep(0.6, 0.95, 0.5 + 0.5 * np.cos(ang * 5)) * smoothstep(0.15, 0.4, dist)
            c = c * (1 - 0.85 * stripe[..., None])
        rgb = c * a[..., None] + rgb * (1 - a[..., None])
        alpha = a + alpha * (1 - a)
    rgb = col * _body[..., None] + rgb * (1 - _body[..., None])
    alpha = _body + alpha * (1 - _body)
    for ex in (46.5, 73.5):
        d = np.sqrt((_XX - ex * S) ** 2 + (_YY - 31 * S) ** 2) / S
        eye = smoothstep(2.9, 2.3, d)
        rgb = rgb * (1 - eye[..., None]) + hexc("#16120F") * eye[..., None]
        hl = smoothstep(1.0, 0.4, np.sqrt((_XX - (ex - 0.8) * S) ** 2 + (_YY - 30.1 * S) ** 2) / S)
        rgb = rgb * (1 - hl[..., None]) + hl[..., None]
    rgba = np.dstack([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)])
    return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")


def make_koi_shadow():
    a = np.clip(_body + 0.6 * sum(m for m, *_ in _fins), 0, 1)
    a = ndi.gaussian_filter(a, 9 * S / 4) * 0.55
    rgba = np.dstack([np.zeros_like(a), np.full_like(a, 0.05), np.full_like(a, 0.08), a])
    return Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ ВОДА
def worley_edges(h, w, cell, seed, warp=None):
    rng = np.random.default_rng(seed)
    gy, gx = h // cell + 3, w // cell + 3
    pts = rng.random((gy, gx, 2)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if warp is not None:
        xx = xx + warp[0]; yy = yy + warp[1]
    cy, cx = np.floor(yy / cell).astype(int), np.floor(xx / cell).astype(int)
    f1 = np.full((h, w), 1e9, np.float32); f2 = np.full((h, w), 1e9, np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = np.clip(cy + dy + 1, 0, gy - 1), np.clip(cx + dx + 1, 0, gx - 1)
            px = (nx - 1 + pts[ny, nx, 0]) * cell
            py = (ny - 1 + pts[ny, nx, 1]) * cell
            d = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
            f2 = np.where(d < f1, f1, np.minimum(f2, d))
            f1 = np.minimum(f1, d)
    return (f2 - f1) / cell


WS = 1.5                      # вода рендерится 1500x2400 (холст 1000x1600 * 1.5)
WW, WH = int(1000 * WS), int(1600 * WS)


def water_depth():
    depth = fbm(WH, WW, 5, base=160 * WS, seed=11)
    yy, xx = np.mgrid[0:WH, 0:WW].astype(np.float32)
    vign = np.sqrt(((xx - WW * 0.5) / (WW * 0.62)) ** 2 + ((yy - WH * 0.45) / (WH * 0.6)) ** 2)
    return np.clip(0.75 * depth + 0.5 * vign - 0.22, 0, 1), yy, xx


WATER_TOD = {
    "day":   dict(shallow="#2F8A86", mid="#17575F", deep="#0A2E38", sky="#E8FBFF", sky_k=0.07, sky_pos=(0.15, 0.05)),
    "dusk":  dict(shallow="#4E7A80", mid="#2C4B5C", deep="#122233", sky="#FFC27A", sky_k=0.10, sky_pos=(0.2, 0.0)),
    "night": dict(shallow="#1F4558", mid="#10283C", deep="#040B16", sky="#BFD7FF", sky_k=0.06, sky_pos=(0.78, 0.06)),
}


def make_water_base(tod, d, yy, xx):
    p = WATER_TOD[tod]
    sh, mi, de = hexc(p["shallow"]), hexc(p["mid"]), hexc(p["deep"])
    d3 = d[..., None]
    col = np.where(d3 < 0.5, sh * (1 - d3 * 2) + mi * (d3 * 2), mi * (2 - d3 * 2) + de * (d3 * 2 - 1))
    silt = fbm(WH, WW, 6, base=22 * WS, seed=12)
    peb = worley_edges(WH, WW, int(34 * WS), 13)
    bottom = ndi.gaussian_filter(0.6 * silt + 0.4 * smoothstep(0.0, 0.25, peb), 2.5 * WS)
    col = col * (0.88 + 0.22 * (bottom * (1 - d))[..., None])
    sx, sy = p["sky_pos"]
    sky = smoothstep(1.0, 0.0, np.sqrt(((xx - WW * sx) / (WW * 0.9)) ** 2 + ((yy - WH * sy) / (WH * 0.55)) ** 2))
    col = col + (sky * p["sky_k"])[..., None] * hexc(p["sky"])
    col = col * (0.97 + 0.06 * fbm(WH, WW, 4, base=40 * WS, seed=41)[..., None])
    col = col + (RNG.random((WH, WW)).astype(np.float32)[..., None] - 0.5) * 0.012
    return Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8), "RGB")


def make_caustics(d, seed, cell, width, warp_seed):
    """Белые линии с альфой. Два слоя с разным масштабом двигаются навстречу — получается живое мерцание."""
    wx = (fbm(WH, WW, 3, base=120 * WS, seed=warp_seed) - 0.5) * 70 * WS
    wy = (fbm(WH, WW, 3, base=120 * WS, seed=warp_seed + 1) - 0.5) * 70 * WS
    wx2 = (fbm(WH, WW, 4, base=60 * WS, seed=warp_seed + 2) - 0.5) * 120 * WS
    wy2 = (fbm(WH, WW, 4, base=60 * WS, seed=warp_seed + 3) - 0.5) * 120 * WS
    c = np.exp(-(worley_edges(WH, WW, int(cell * WS), seed, (wx + wx2, wy + wy2)) / width) ** 2)
    c = ndi.gaussian_filter(c, 1.5 * WS)
    patchy = smoothstep(0.3, 0.8, fbm(WH, WW, 3, base=220 * WS, seed=seed + 7))
    c = c * (0.3 + 0.7 * patchy) * (1 - 0.7 * d)
    bloom = ndi.gaussian_filter(c, 8 * WS)
    a = np.clip(c * 0.55 + bloom * 0.35, 0, 1)
    rgba = np.dstack([np.full_like(a, 0.85), np.full_like(a, 1.0), np.full_like(a, 0.95), a])
    return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ ДЕКОР из v1
def texturize(name, scale=3, grain=0.14, relief=0.55, blur=6, gloss=0.12, seed=1):
    png = cairosvg.svg2png(url=os.path.join(V1_SVG, name + ".svg"), scale=scale)
    im = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"), dtype=np.float32) / 255.0
    rgb, a = im[..., :3], im[..., 3]
    h, w = a.shape
    solid = (a > 0.6).astype(np.float32)
    lam, spec, hmap = lighting(solid, blur=blur, k=60.0, power=10)
    g = fbm(h, w, 5, base=3, seed=seed)
    g2 = fbm(h, w, 3, base=0.8, seed=seed + 1)
    rgb = rgb * (1 - relief + relief * (0.55 + 0.6 * lam))[..., None]
    rgb = rgb * (1 - grain + grain * 2 * (0.6 * g + 0.4 * g2))[..., None]
    rgb = rgb + (spec * gloss * solid)[..., None]
    out = np.dstack([np.clip(rgb, 0, 1), a])
    return Image.fromarray((out * 255).astype(np.uint8), "RGBA")


DECOR = {
    # имя: (тип, зерно, рельеф, размытие высоты, глянец)
    "stone_a": ("shore", 0.22, 0.65, 10, 0.10), "stone_b": ("shore", 0.22, 0.65, 10, 0.10),
    "stone_c": ("shore", 0.22, 0.65, 10, 0.10), "stone_a_mossy": ("shore", 0.22, 0.65, 10, 0.08),
    "stone_b_mossy": ("shore", 0.22, 0.65, 10, 0.08), "stone_c_mossy": ("shore", 0.22, 0.65, 10, 0.08),
    "lily_pad_a": ("surface", 0.10, 0.35, 14, 0.22), "lily_pad_b": ("surface", 0.12, 0.35, 14, 0.18),
    "lily_pad_curled": ("surface", 0.10, 0.35, 14, 0.22),
    "lotus_pink": ("surface", 0.06, 0.45, 4, 0.10), "lotus_white": ("surface", 0.05, 0.45, 4, 0.10),
    "lotus_bud": ("surface", 0.06, 0.45, 4, 0.10),
    "reeds": ("shore", 0.10, 0.30, 2, 0.05), "fern": ("shore", 0.10, 0.30, 2, 0.05),
    "driftwood": ("shore", 0.30, 0.60, 4, 0.06), "stone_lantern": ("shore", 0.22, 0.55, 8, 0.08),
    "sakura_branch": ("overhang", 0.06, 0.35, 2, 0.06), "sakura_petal": ("ambient", 0.04, 0.3, 2, 0.08),
}
PLAIN = {"lantern_glow": "glow", "firefly": "ambient", "light_particle": "fx", "ripple": "fx"}


def main():
    os.makedirs(OUT, exist_ok=True)
    koi_sizes = {"3x": (360, 840), "2x": (240, 560)}
    for v in ("kohaku", "ogon", "tancho", "sanke", "asagi", "platinum"):
        img = make_koi(v)
        save(img, f"koi_{v}", "koi", koi_sizes,
             {"headDirection": "up (-Y)", "designSize": [120, 280],
              "deform": "рисовать полосами с боковым смещением — см. visual_v2.json → koi.undulation"})
        print("koi", v)
    save(make_koi_shadow(), "koi_shadow", "koiShadow", koi_sizes,
         {"usage": "рисовать под каждым карпом на «дне»: смещение и масштаб — visual_v2.json → koi.shadow"})

    d, yy, xx = water_depth()
    for tod in WATER_TOD:
        save(make_water_base(tod, d, yy, xx), f"water_{tod}", "water", {"full": (WW, WH)},
             {"note": "фон без каустики, вид сверху, холст 1000x1600 * 1.5"})
        print("water", tod)
    save(make_caustics(d, 31, 70, 0.045, 21), "caustics_a", "caustics", {"full": (WW, WH)},
         {"blend": "screen / lighter", "note": "крупный слой, дрейфует медленно"})
    save(make_caustics(d, 32, 46, 0.05, 61), "caustics_b", "caustics", {"full": (WW, WH)},
         {"blend": "screen / lighter", "note": "мелкий слой, дрейфует навстречу слою A"})
    print("caustics")

    for name, (kind, grain, relief, blur, gloss) in DECOR.items():
        img = texturize(name, 3, grain, relief, blur, gloss, seed=len(name))
        w, h = img.size
        save(img, name, kind, {"3x": (w, h), "2x": (w * 2 // 3, h * 2 // 3)})
    for name, kind in PLAIN.items():
        png = cairosvg.svg2png(url=os.path.join(V1_SVG, name + ".svg"), scale=3)
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        w, h = img.size
        save(img, name, kind, {"3x": (w, h), "2x": (w * 2 // 3, h * 2 // 3)})
    print("decor")

    json.dump({"_comment": "Ассеты v2 (растр). 3x = 3 пикселя на единицу дизайна v1; вода — 1.5x холста 1000x1600. "
                           "Для каждого файла есть .webp (меньше размер, та же картинка).",
               "assets": MANIFEST},
              open(os.path.join(OUT, "manifest_v2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("OK", len(MANIFEST), "assets ->", OUT)


if __name__ == "__main__":
    main()
