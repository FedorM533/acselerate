#!/usr/bin/env python3
"""Собирает самодостаточный v2/preview/pond-preview-v2.html (все картинки встроены как WebP)."""
import base64
import json
import os
import re

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V2 = os.path.join(KIT, "v2")
manifest = json.load(open(os.path.join(V2, "assets", "manifest_v2.json"), encoding="utf-8"))

img = {}
for a in manifest["assets"]:
    f = a["files"].get("2x_webp") or a["files"].get("full_webp")
    data = open(os.path.join(V2, "assets", f), "rb").read()
    img[a["id"]] = "data:image/webp;base64," + base64.b64encode(data).decode()


def load(*p):
    return json.load(open(os.path.join(*p), encoding="utf-8"))


strings = load(KIT, "config", "strings_ru.json")
strings.update({k: v for k, v in load(V2, "config", "strings_v2_ru.json").items() if not k.startswith("_")})
data = ("const IMG = " + json.dumps(img) + ";\n"
        "const CFG = " + json.dumps(load(KIT, "config", "progression.json"), ensure_ascii=False) + ";\n"
        "const PAL = " + json.dumps(load(KIT, "config", "palette.json"), ensure_ascii=False) + ";\n"
        "const VIS = " + json.dumps(load(V2, "config", "visual_v2.json"), ensure_ascii=False) + ";\n"
        "const REASONS = " + json.dumps(load(KIT, "config", "interrupt_reasons.json"), ensure_ascii=False) + ";\n"
        "const STR = " + json.dumps(strings, ensure_ascii=False) + ";\n")
engine = re.sub(r"^export ", "", open(os.path.join(KIT, "reference", "progressEngine.js"), encoding="utf-8").read(), flags=re.M)
tpl = open(os.path.join(V2, "tools", "preview_v2_template.html"), encoding="utf-8").read()
out = tpl.replace("/*__DATA__*/", data).replace("/*__ENGINE__*/", engine)
os.makedirs(os.path.join(V2, "preview"), exist_ok=True)
path = os.path.join(V2, "preview", "pond-preview-v2.html")
open(path, "w", encoding="utf-8").write(out)
print(f"OK: {path} ({len(out) // 1024} KB)")
