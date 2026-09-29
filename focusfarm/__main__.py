"""Запуск: python -m focusfarm → сервер на 127.0.0.1 и открытие браузера."""
import argparse
import threading
import webbrowser

import uvicorn

from focusfarm import fix_console_encoding
from focusfarm.api.server import create_app

HOST = "127.0.0.1"  # только локально, наружу не слушаем
PORT = 8765


def main():
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Фокус-ферма")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    args = parser.parse_args()

    url = f"http://{HOST}:{PORT}/"
    print(f"Фокус-ферма запускается: {url}")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
