"""Запуск: python -m focusfarm → сервер на 127.0.0.1 и открытие браузера.

Флаги:
  --demo [N]     демо-режим, время ускорено в N раз (по умолчанию 30)
  --dev          режим разработчика (панель с виртуальным телефоном)
  --port N       порт (по умолчанию из settings.yaml)
  --no-browser   не открывать браузер
  --db PATH      другой файл базы (например, чистая ферма для демо)
  --fresh        начать с чистой фермы (стирает файл из --db; основную базу не трогает)
"""
import argparse
from pathlib import Path
import logging
import threading
import webbrowser

import uvicorn

from focusfarm import fix_console_encoding
from focusfarm.api.server import build_manager, create_app
from focusfarm.storage.db import DEFAULT_PATH

HOST = "127.0.0.1"  # только локально, наружу не слушаем


def main():
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Фокус-ферма")
    parser.add_argument("--demo", nargs="?", const=30, type=float, metavar="N",
                        help="демо-режим с ускорением ×N (по умолчанию 30)")
    parser.add_argument("--dev", action="store_true", help="режим разработчика")
    parser.add_argument("--port", type=int, help="порт сервера")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    parser.add_argument("--db", help="путь к файлу базы (по умолчанию data/focusfarm.db)")
    parser.add_argument("--fresh", action="store_true", help="чистая ферма (только вместе с --db)")
    args = parser.parse_args()
    if args.fresh:
        if not args.db or Path(args.db).resolve() == DEFAULT_PATH.resolve():
            parser.error("--fresh работает только с отдельной базой: --db data/demo.db")
        Path(args.db).unlink(missing_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Флаги командной строки действуют только на этот запуск и в базу не пишутся.
    cli = {}
    if args.demo:
        cli = {"mode": "demo", "demo_speed": args.demo}
    elif args.dev:
        cli = {"mode": "dev"}
    manager = build_manager(args.db or DEFAULT_PATH, cli_overrides=cli)

    port = args.port or manager.settings.get("server", {}).get("port", 8765)
    url = f"http://{HOST}:{port}/"
    mode = manager.settings.get("mode")
    print(f"Фокус-ферма запускается: {url}  (режим: {mode}, скорость ×{manager.speed:g})")
    print("Остановить: Ctrl+C")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(manager), host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
