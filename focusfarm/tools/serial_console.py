"""Ручная проверка протокола подставки.

    python -m focusfarm.tools.serial_console --list          # какие порты есть
    python -m focusfarm.tools.serial_console --port COM3     # подключиться

После подключения всё, что присылает подставка, печатается на экран,
а введённые строки (например, LED GREEN, SOUND 3, PING) отправляются ей.
Пустая строка или Ctrl+C — выход.
"""
import argparse
import threading
import time

from focusfarm import fix_console_encoding
from focusfarm.device.serial_link import BAUDRATE

HELP = "Команды: LED GREEN|YELLOW|RED|BLUE|OFF|BLINK_RED, SOUND 1..4, PING, STATUS. Пустая строка — выход."


def list_ports():
    from serial.tools import list_ports as lp
    ports = list(lp.comports())
    if not ports:
        print("Порты не найдены. Подключи ESP32 по USB и проверь драйвер (CP210x / CH340).")
    for p in ports:
        print(f"{p.device:10} {p.description}")


def reader(ser, stop: threading.Event):
    while not stop.is_set():
        try:
            line = ser.readline().decode("ascii", errors="replace").strip()
        except Exception as exc:
            print(f"\n[ошибка чтения: {exc}]")
            stop.set()
            return
        if line:
            print(f"\n{time.strftime('%H:%M:%S')} ← {line}\n> ", end="", flush=True)


def console(port: str):
    import serial
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=0.5)
    except serial.SerialException as exc:
        print(f"Не удалось открыть {port}: {exc}")
        return
    print(f"Подключено к {port} ({BAUDRATE} бод). {HELP}")
    stop = threading.Event()
    threading.Thread(target=reader, args=(ser, stop), daemon=True).start()
    try:
        while not stop.is_set():
            line = input("> ").strip()
            if not line:
                break
            ser.write((line + "\n").encode("ascii", errors="replace"))
            print(f"{time.strftime('%H:%M:%S')} → {line}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        ser.close()
        print("\nОтключено.")


def main():
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Консоль подставки Фокус-док")
    parser.add_argument("--list", action="store_true", help="показать доступные порты")
    parser.add_argument("--port", help="порт, например COM3 или /dev/ttyUSB0")
    args = parser.parse_args()
    if args.list or not args.port:
        list_ports()
        if not args.port:
            print("\nЧтобы подключиться: python -m focusfarm.tools.serial_console --port COM3")
        return
    console(args.port)


if __name__ == "__main__":
    main()
