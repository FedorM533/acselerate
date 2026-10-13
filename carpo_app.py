"""Точка входа собранного приложения (Carpo.exe).

Один exe умеет две роли: сама программа и сторож строгого режима (флаг --watchdog).
Из исходников по-прежнему запускают `python -m focusfarm`.
"""
import multiprocessing
import os
import sys


def _ensure_streams():
    """Без консоли (процесс запущен сторожем) stdout/stderr отсутствуют: print() и логи падали бы."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _ensure_streams()
    if "--watchdog" in sys.argv:
        sys.argv.remove("--watchdog")
        from focusfarm.watchdog import main as watchdog_main
        watchdog_main()
    else:
        from focusfarm.__main__ import main
        main()
