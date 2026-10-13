"""Где лежат файлы программы: ресурсы (только чтение) и данные пользователя (запись).

Из исходников (python -m focusfarm) всё лежит в папке репозитория, как раньше.
Из собранного приложения (Carpo.exe, PyInstaller) ресурсы лежат рядом с программой, а база,
правила и журнал — в профиле пользователя: туда можно писать, и они переживают обновление.
"""
import os
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# Папка с ресурсами: config/, extension/, focusfarm/web/.
if FROZEN:
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BUNDLE_DIR = Path(__file__).resolve().parent.parent


def _user_dir() -> Path:
    if not FROZEN:
        return BUNDLE_DIR
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Carpo"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "carpo"


USER_DIR = _user_dir()
DATA_DIR = USER_DIR / "data"
LOG_DIR = USER_DIR / "logs"
CONFIG_DIR = BUNDLE_DIR / "config"                      # настройки по умолчанию (только чтение)
WEB_DIR = BUNDLE_DIR / "focusfarm" / "web"
EXTENSION_DIR = BUNDLE_DIR / "extension"
# Правила программ и сайтов человек меняет в интерфейсе, поэтому в собранном виде они живут в профиле.
RULES_PATH = (USER_DIR / "config" / "rules.yaml") if FROZEN else (CONFIG_DIR / "rules.yaml")


def seed_user_files():
    """Первый запуск собранного приложения: кладём в профиль правила по умолчанию."""
    if not FROZEN:
        return
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not RULES_PATH.exists():
        shutil.copyfile(CONFIG_DIR / "rules.yaml", RULES_PATH)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def self_command() -> list[str]:
    """Как запустить эту же программу ещё раз (для сторожа)."""
    return [sys.executable] if FROZEN else [sys.executable, "-m", "focusfarm"]


def watchdog_command() -> list[str]:
    """Как запустить сторожа."""
    return [sys.executable, "--watchdog"] if FROZEN else [sys.executable, "-m", "focusfarm.watchdog"]
