"""Монитор активности для Linux.

Время простоя (когда был последний ввод, но не ЧТО нажимали):
- GNOME (и X11, и Wayland) — Mutter IdleMonitor по D-Bus через `gdbus`;
- другие X11-окружения — `xprintidle`, если установлен.

Активное окно:
- X11 — `xprop`: _NET_ACTIVE_WINDOW → _NET_WM_PID и _NET_WM_NAME;
- GNOME на Wayland — обычной программе окно не видно, поэтому спрашиваем наше
  маленькое расширение GNOME Shell (`linux/gnome-extension/`). Установка:
  `python -m focusfarm.tools.gnome_ext`, потом выйти из сеанса и войти снова.

Только стандартные программы рабочего стола, без новых зависимостей Python.
Те же помощники использует блокировщик программ (`blocker/apps.py`).
"""
import ast
import json
import os
import re
import shutil
import subprocess

import psutil

from focusfarm.activity.monitor import ActivityMonitor, ActivitySample

TIMEOUT_S = 2
EXT_DEST = "org.carpo.FocusWindow"
EXT_PATH = "/org/carpo/FocusWindow"

INSTALL_HINT = ("Чтобы программа видела активное окно в GNOME на Wayland, выполните "
                "«python -m focusfarm.tools.gnome_ext», затем выйдите из сеанса и войдите снова.")
NO_WINDOWS_HINT = ("В этом окружении рабочего стола активное окно не определяется — "
                   "включайте режим «пишу в тетради» или работайте в сеансе X11.")


def _run(cmd: list[str]) -> str:
    """Запускает программу и возвращает её вывод. Ошибка → исключение (его ловит SafeMonitor)."""
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    if done.returncode != 0:
        raise OSError(f"{cmd[0]}: {done.stderr.strip() or 'код ' + str(done.returncode)}")
    return done.stdout


def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name().lower()
    except (psutil.Error, ValueError):
        return "unknown"


# ---------- разбор вывода программ (отдельно, чтобы проверять в тестах) ----------

def parse_gdbus_string(text: str) -> str:
    """`('{"pid": 1}',)` → `{"pid": 1}`. Расширение отдаёт только ASCII, так что формат простой."""
    return ast.literal_eval(text.strip())[0]


def parse_gdbus_uint(text: str) -> int:
    """`(uint64 15151,)` → 15151."""
    match = re.search(r"(\d+)\s*,?\s*\)", text)
    if not match:
        raise ValueError(f"не понял ответ: {text!r}")
    return int(match.group(1))


def parse_xprop_active(text: str) -> str | None:
    """`_NET_ACTIVE_WINDOW: window id # 0x400003` → '0x400003' (0x0 — нет окна)."""
    match = re.search(r"#\s*(0x[0-9a-fA-F]+)", text)
    if not match or int(match.group(1), 16) == 0:
        return None
    return match.group(1)


def parse_xprop_window(text: str) -> tuple[int | None, str]:
    """Вывод `xprop -id … _NET_WM_PID _NET_WM_NAME` → (pid, заголовок)."""
    pid_match = re.search(r"_NET_WM_PID\D*?=\s*(\d+)", text)
    title_match = re.search(r'_NET_WM_NAME[^=]*=\s*"((?:[^"\\]|\\.)*)"', text)
    title = ""
    if title_match:
        title = re.sub(r"\\(.)", r"\1", title_match.group(1))
    return (int(pid_match.group(1)) if pid_match else None), title


def parse_xprop_client_list(text: str) -> list[str]:
    """`_NET_CLIENT_LIST: window id # 0x1, 0x2` → ['0x1', '0x2']."""
    return re.findall(r"0x[0-9a-fA-F]+", text.partition("#")[2])


# ---------- источники ----------

def gnome_idle_seconds() -> float:
    out = _run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
                "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"])
    return parse_gdbus_uint(out) / 1000.0


def xprintidle_seconds() -> float:
    return int(_run(["xprintidle"]).strip()) / 1000.0


def extension_call(method: str, *args: str) -> str:
    """Вызов метода нашего расширения GNOME Shell. Нет расширения → исключение."""
    out = _run(["gdbus", "call", "--session", "--dest", EXT_DEST, "--object-path", EXT_PATH,
                "--method", f"{EXT_DEST}.{method}", *args])
    return out


def extension_active() -> tuple[int | None, str]:
    data = json.loads(parse_gdbus_string(extension_call("Active")))
    return data.get("pid"), data.get("title", "")


def extension_windows() -> list[tuple[int, str]]:
    data = json.loads(parse_gdbus_string(extension_call("Windows")))
    return [(w["pid"], w.get("title", "")) for w in data if w.get("pid")]


def extension_close(pid: int) -> bool:
    return "true" in extension_call("Close", str(pid))


def x11_active() -> tuple[int | None, str]:
    window = parse_xprop_active(_run(["xprop", "-root", "_NET_ACTIVE_WINDOW"]))
    if window is None:
        return None, ""
    return parse_xprop_window(_run(["xprop", "-id", window, "_NET_WM_PID", "_NET_WM_NAME"]))


def x11_windows() -> list[tuple[int, str]]:
    result = []
    for window in parse_xprop_client_list(_run(["xprop", "-root", "_NET_CLIENT_LIST"])):
        try:
            pid, title = parse_xprop_window(_run(["xprop", "-id", window, "_NET_WM_PID", "_NET_WM_NAME"]))
        except (OSError, subprocess.SubprocessError):
            continue    # окно успело закрыться
        if pid:
            result.append((pid, title))
    return result


def window_backend() -> str | None:
    """Как узнавать окна: 'gnome' (расширение), 'x11' (xprop) или None."""
    if is_wayland():
        if shutil.which("gdbus"):
            try:
                extension_call("Active")
                return "gnome"
            except (OSError, subprocess.SubprocessError):
                pass
        return None
    if os.environ.get("DISPLAY") and shutil.which("xprop"):
        return "x11"
    return None


def list_windows(backend: str | None) -> list[tuple[int, str]]:
    """Все обычные окна (pid, заголовок) — для белого списка."""
    if backend == "gnome":
        return extension_windows()
    if backend == "x11":
        return x11_windows()
    return []


class LinuxMonitor(ActivityMonitor):
    name = "linux"

    def __init__(self):
        self.hint = None
        self.idle = None
        if shutil.which("gdbus"):
            try:
                gnome_idle_seconds()
                self.idle = gnome_idle_seconds
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        if self.idle is None and shutil.which("xprintidle") and not is_wayland():
            self.idle = xprintidle_seconds
        self.backend = window_backend()
        if self.backend is None:
            gnome = "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
            self.hint = INSTALL_HINT if (is_wayland() and gnome) else NO_WINDOWS_HINT
        # Без окна классифицировать нечего — это «недоступно», как и запасной монитор.
        self.available = self.backend is not None
        self.name = f"linux-{self.backend or 'no-windows'}"

    def sample(self) -> ActivitySample:
        idle = self.idle() if self.idle else 0.0
        pid, title = None, ""
        if self.backend == "gnome":
            pid, title = extension_active()
        elif self.backend == "x11":
            pid, title = x11_active()
        return ActivitySample(idle, process_name(pid) if pid else "unknown", title)
