"""Фокус-пруд — программная часть проекта «Фокус-док»."""
import sys

__version__ = "0.1.0"


def fix_console_encoding():
    """На Windows консоль/перенаправленный вывод может быть не в UTF-8 —
    тогда print() с русским текстом падает. Переключаем на UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
