# -*- mode: python ; coding: utf-8 -*-
# Сборка Carpo.exe: scripts/build_windows.ps1 (или: pyinstaller carpo.spec --noconfirm).
from PyInstaller.utils.hooks import collect_submodules

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("focusfarm")
    + collect_submodules("websockets")
    + ["win32gui", "win32process", "win32api", "win32con", "serial.tools.list_ports"]
)

a = Analysis(
    ["carpo_app.py"],
    pathex=["."],
    datas=[
        ("config", "config"),
        ("focusfarm/web", "focusfarm/web"),
        ("extension", "extension"),
    ],
    hiddenimports=hidden,
    excludes=["pytest", "tkinter", "matplotlib", "numpy", "pandas"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Carpo",
    console=True,                     # окно с логом: закрыл окно — программа остановилась
    icon="focusfarm/web/brand/favicon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Carpo")
