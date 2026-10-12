"""Помощник установки расширения браузера.

Chrome и Edge (с 137-й версии) не дают программам ставить расширения втихую: ни флага
`--load-extension`, ни установки из папки без участия человека. Поэтому мы делаем всё остальное:
кладём расширение в постоянную папку, открываем нужную страницу браузера и кладём путь в буфер обмена.
Человеку остаётся включить «Режим разработчика» и нажать «Загрузить распакованное».
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent.parent / "extension"


def _roots() -> list[str]:
    return [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]


# ключ → (название, путь к программе внутри Program Files или LocalAppData, страница расширений)
BROWSERS = {
    "chrome": ("Google Chrome", r"Google\Chrome\Application\chrome.exe", "chrome://extensions"),
    "edge": ("Microsoft Edge", r"Microsoft\Edge\Application\msedge.exe", "edge://extensions"),
    "yandex": ("Яндекс Браузер", r"Yandex\YandexBrowser\Application\browser.exe", "browser://extensions"),
}


def installed_browsers() -> dict[str, str]:
    """{ключ: полный путь к программе} только для тех браузеров, что найдены на компьютере."""
    found = {}
    for key, (_, relative, _) in BROWSERS.items():
        for root in _roots():
            path = Path(root) / relative if root else None
            if path and path.is_file():
                found[key] = str(path)
                break
    return found


def target_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Carpo" / "extension"


def prepare_folder(source: Path = SOURCE, target: Path | None = None) -> Path:
    """Копия расширения в постоянное место: не пропадёт, если папку с программой переложат."""
    target = target or target_dir()
    if not (source / "manifest.json").is_file():
        raise FileNotFoundError("Не нашёл папку extension рядом с программой")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def copy_to_clipboard(text: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:CARPO_CLIP"],
                       env={**os.environ, "CARPO_CLIP": text}, check=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def open_extensions_page(browser: str) -> bool:
    """Открывает страницу расширений выбранного браузера."""
    exe = installed_browsers().get(browser)
    if exe is None:
        return False
    subprocess.Popen([exe, BROWSERS[browser][2]])
    return True


def install(browser: str) -> dict:
    """Всё, что можно сделать за человека. Вернёт путь к папке и что получилось."""
    folder = prepare_folder()
    return {
        "folder": str(folder),
        "copied": copy_to_clipboard(str(folder)),
        "opened": open_extensions_page(browser),
        "browser": BROWSERS[browser][0],
    }
