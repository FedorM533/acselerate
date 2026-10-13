"""Установка расширения GNOME Shell, которое сообщает «Фокус-пруду» активное окно.

    python -m focusfarm.tools.gnome_ext            установить и включить
    python -m focusfarm.tools.gnome_ext --remove   удалить

Нужно только в GNOME на Wayland: там обычная программа не видит чужих окон.
Расширение ставится в папку пользователя (без sudo). GNOME на Wayland подхватывает
новые расширения только после повторного входа в систему.
"""
import argparse
import ast
import shutil
import subprocess
import sys
from pathlib import Path

from focusfarm import fix_console_encoding

UUID = "carpo-focus@carpo.local"
SOURCE = Path(__file__).resolve().parents[2] / "linux" / "gnome-extension" / UUID


def target_dir() -> Path:
    return Path.home() / ".local" / "share" / "gnome-shell" / "extensions" / UUID


def _gsettings_get(key: str) -> str:
    return subprocess.run(["gsettings", "get", "org.gnome.shell", key],
                          capture_output=True, text=True, timeout=10).stdout.strip()


def add_to_enabled(current: str, uuid: str = UUID) -> list[str] | None:
    """Список enabled-extensions с нашим расширением; None — уже включено."""
    items = [] if current.startswith("@as") else list(ast.literal_eval(current or "[]"))
    if uuid in items:
        return None
    return items + [uuid]


def enable():
    """Включаем через gsettings: `gnome-extensions enable` не знает про расширение до перезахода."""
    new = add_to_enabled(_gsettings_get("enabled-extensions"))
    if new is not None:
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(new)],
                       check=True, timeout=10)
    # Если пользователь выключил все расширения разом, наше тоже не заработает.
    if _gsettings_get("disable-user-extensions") == "true":
        subprocess.run(["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"],
                       check=True, timeout=10)


def install() -> Path:
    if not (SOURCE / "metadata.json").is_file():
        raise FileNotFoundError(f"Не нашёл расширение в {SOURCE}")
    target = target_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, target, dirs_exist_ok=True)
    enable()
    return target


def remove():
    subprocess.run(["gnome-extensions", "disable", UUID], capture_output=True, timeout=10)
    shutil.rmtree(target_dir(), ignore_errors=True)


def main():
    fix_console_encoding()
    parser = argparse.ArgumentParser(description="Расширение GNOME для монитора активности")
    parser.add_argument("--remove", action="store_true", help="удалить расширение")
    args = parser.parse_args()
    if not shutil.which("gsettings"):
        print("Это не GNOME (нет gsettings): расширение здесь не нужно и не установится.")
        return 1
    if args.remove:
        remove()
        print("Расширение удалено. Выйдите из сеанса и войдите снова.")
        return 0
    try:
        path = install()
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Не получилось установить расширение: {exc}")
        return 1
    print(f"Расширение установлено: {path}")
    print("Выйдите из сеанса и войдите снова — после этого программа увидит активное окно.")
    print("Проверка: python -m focusfarm.activity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
