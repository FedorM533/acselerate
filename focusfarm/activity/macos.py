"""Монитор активности для macOS («по возможности»).

Активное приложение — через NSWorkspace (нужен pyobjc, необязательно).
Простой — из `ioreg -c IOHIDSystem` (HIDIdleTime в наносекундах).
Заголовков окон на macOS без особых разрешений нет — классифицируем по приложению.
"""
import re
import subprocess

from focusfarm.activity.monitor import ActivityMonitor, ActivitySample

IDLE_PATTERN = re.compile(r'"HIDIdleTime" = (\d+)')


def idle_seconds() -> float:
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True,
                         text=True, timeout=2).stdout
    match = IDLE_PATTERN.search(out)
    return int(match.group(1)) / 1e9 if match else 0.0


def active_app() -> str:
    try:
        from AppKit import NSWorkspace  # из pyobjc, может быть не установлен
    except ImportError:
        return "unknown"
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return (app.localizedName() or "unknown").lower() if app else "unknown"


class MacMonitor(ActivityMonitor):
    name = "macos"

    def sample(self) -> ActivitySample:
        return ActivitySample(idle_seconds(), active_app(), "")
