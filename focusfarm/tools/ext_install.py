"""Помощник установки расширения браузера.

Chrome и Edge (с 137-й версии) не дают программам ставить расширения втихую: ни флага
`--load-extension`, ни установки из папки без участия человека. Поэтому мы делаем всё остальное:
кладём расширение в постоянную папку, открываем нужную страницу браузера и кладём путь в буфер обмена.
Человеку остаётся включить «Режим разработчика» и нажать «Загрузить распакованное».

Firefox принимает расширение файлом .xpi. Без подписи Mozilla его ставят Firefox ESR,
Developer Edition и Nightly (после xpinstall.signatures.required = false), обычный Firefox —
только «временно», до перезапуска браузера. Поэтому для Firefox собираем ещё и .xpi.

На Linux браузеры ищем по имени программы в PATH, на Windows — в Program Files.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from focusfarm.paths import EXTENSION_DIR as SOURCE  # noqa: E402  (в собранном приложении лежит рядом с exe)


def _roots() -> list[str]:
    return [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]


# ключ → (название, путь к программе внутри Program Files или LocalAppData, страница расширений)
BROWSERS = {
    "chrome": ("Google Chrome", r"Google\Chrome\Application\chrome.exe", "chrome://extensions"),
    "edge": ("Microsoft Edge", r"Microsoft\Edge\Application\msedge.exe", "edge://extensions"),
    "yandex": ("Яндекс Браузер", r"Yandex\YandexBrowser\Application\browser.exe", "browser://extensions"),
    "chromium": ("Chromium", r"Chromium\Application\chrome.exe", "chrome://extensions"),
    "firefox": ("Firefox", r"Mozilla Firefox\firefox.exe", "about:addons"),
}

# Имена программ на Linux (первое найденное в PATH).
LINUX_COMMANDS = {
    "chrome": ("google-chrome", "google-chrome-stable"),
    "edge": ("microsoft-edge", "microsoft-edge-stable"),
    "yandex": ("yandex-browser", "yandex-browser-stable"),
    "chromium": ("chromium", "chromium-browser"),
    "firefox": ("firefox", "firefox-esr"),
}

XPI_NAME = "carpo-focus.xpi"

CHROMIUM_STEPS = [
    "В открывшемся окне включите переключатель «Режим разработчика» (справа вверху).",
    "Нажмите «Загрузить распакованное».",
    "В окне выбора папки укажите путь ниже и нажмите «Выбор папки».",
]


def firefox_steps(xpi: Path, folder: Path) -> list[str]:
    return [
        "В новой вкладке откройте about:config, найдите xpinstall.signatures.required и сделайте false "
        "(так можно в Firefox ESR, Developer Edition и Nightly).",
        f"На открывшейся странице about:addons нажмите ⚙ → «Установить дополнение из файла…» и выберите {xpi}.",
        "Обычный Firefox без подписи Mozilla не пустит: там откройте about:debugging → «Этот Firefox» → "
        f"«Загрузить временное дополнение…» → {folder / 'manifest.json'} (до перезапуска браузера).",
    ]


def installed_browsers() -> dict[str, str]:
    """{ключ: полный путь к программе} только для тех браузеров, что найдены на компьютере."""
    found = {}
    if sys.platform.startswith("linux"):
        for key, commands in LINUX_COMMANDS.items():
            path = next(filter(None, map(shutil.which, commands)), None)
            if path:
                found[key] = path
        return found
    for key, (_, relative, _) in BROWSERS.items():
        for root in _roots():
            path = Path(root) / relative if root else None
            if path and path.is_file():
                found[key] = str(path)
                break
    return found


def target_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "Carpo" / "extension"


def prepare_folder(source: Path = SOURCE, target: Path | None = None) -> Path:
    """Копия расширения в постоянное место: не пропадёт, если папку с программой переложат."""
    target = target or target_dir()
    if not (source / "manifest.json").is_file():
        raise FileNotFoundError("Не нашёл папку extension рядом с программой")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def build_xpi(folder: Path) -> Path:
    """Архив .xpi для Firefox: те же файлы, что в папке, manifest.json — в корне архива."""
    xpi = folder.parent / XPI_NAME
    with zipfile.ZipFile(xpi, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    return xpi


def copy_to_clipboard(text: str) -> bool:
    if sys.platform.startswith("linux"):
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=text, text=True, check=True, timeout=10)
                    return True
                except (OSError, subprocess.SubprocessError):
                    continue
        return False
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
    if browser == "firefox":
        xpi = build_xpi(folder)
        path, steps = xpi, firefox_steps(xpi, folder)
    else:
        path, steps = folder, CHROMIUM_STEPS
    return {
        "folder": str(path),
        "copied": copy_to_clipboard(str(path)),
        "opened": open_extensions_page(browser),
        "browser": BROWSERS[browser][0],
        "steps": steps,
    }
