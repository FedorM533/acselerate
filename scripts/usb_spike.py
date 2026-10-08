"""Проверка USB: что компьютер видит, когда ты подключаешь телефон кабелем.

Запусти, когда телефон под рукой:
    python scripts/usb_spike.py

Скрипт покажет список USB-устройств ДО и ПОСЛЕ подключения и напечатает новые.
Если новых устройств нет — кабель только для зарядки (без линий данных) или телефон
заблокирован/в режиме «только зарядка» и не отдаёт данные. Попробуй другой кабель.
Результат пришли команде: по нему настраивается привязка телефона.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focusfarm import fix_console_encoding  # noqa: E402
from focusfarm.sensors.usb_phone import UsbLister  # noqa: E402


def show(title, devices):
    print(f"\n{title} ({len(devices)}):")
    for d in devices:
        print(f"  {d['id']:<28} PID {d['pid']:<5} {d['name']}")


def main():
    fix_console_encoding()
    lister = UsbLister()
    input("1. ОТКЛЮЧИ телефон от компьютера и нажми Enter… ")
    before = lister.list_devices()
    show("До подключения", before)
    input("\n2. ПОДКЛЮЧИ телефон кабелем (на телефоне выбери «Передача файлов»), подожди 3 секунды и нажми Enter… ")
    after = lister.list_devices()
    show("После подключения", after)
    known = {d["id"] for d in before}
    new = [d for d in after if d["id"] not in known]
    show("НОВЫЕ устройства", new)
    if not new:
        print("\nНовых устройств нет: проверь кабель (нужен с данными) и режим USB на телефоне.")
    elif len(new) == 1:
        print("\nОтлично: найдено одно новое устройство — это и есть телефон.")
    else:
        print("\nНовых устройств несколько — при привязке придётся выбрать телефон из списка.")


if __name__ == "__main__":
    main()
