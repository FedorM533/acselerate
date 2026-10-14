#!/usr/bin/env python3
"""Собирает самодостаточное превью preview/pond-preview.html (открывается двойным кликом, без сервера)."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
svg_dir = os.path.join(ROOT, "assets", "svg")
assets = {f[:-4]: open(os.path.join(svg_dir, f), encoding="utf-8").read().strip()
          for f in sorted(os.listdir(svg_dir)) if f.endswith(".svg") and not f.startswith("app_icon")}


def load(p):
    return json.load(open(os.path.join(ROOT, "config", p), encoding="utf-8"))


data = ("const ASSETS = " + json.dumps(assets, ensure_ascii=False) + ";\n"
        "const CFG = " + json.dumps(load("progression.json"), ensure_ascii=False) + ";\n"
        "const PAL = " + json.dumps(load("palette.json"), ensure_ascii=False) + ";\n"
        "const REASONS = " + json.dumps(load("interrupt_reasons.json"), ensure_ascii=False) + ";\n"
        "const STR = " + json.dumps(load("strings_ru.json"), ensure_ascii=False) + ";\n")
engine = open(os.path.join(ROOT, "reference", "progressEngine.js"), encoding="utf-8").read()
engine = re.sub(r"^export ", "", engine, flags=re.M)

tpl = open(os.path.join(ROOT, "tools", "preview_template.html"), encoding="utf-8").read()
out = tpl.replace("/*__DATA__*/", data).replace("/*__ENGINE__*/", engine)
os.makedirs(os.path.join(ROOT, "preview"), exist_ok=True)
path = os.path.join(ROOT, "preview", "pond-preview.html")
open(path, "w", encoding="utf-8").write(out)
print(f"OK: {path} ({len(out) // 1024} KB)")
