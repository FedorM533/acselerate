"""Монитор активности для Windows.

Активное окно — через pywin32, имя процесса — через psutil,
время простоя — GetLastInputInfo через ctypes (без хуков клавиатуры:
мы узнаём только КОГДА был последний ввод, но не ЧТО нажимали).
"""
import ctypes
from ctypes import wintypes

import psutil
import win32gui
import win32process

from focusfarm.activity.monitor import ActivityMonitor, ActivitySample


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    now_ms = ctypes.windll.kernel32.GetTickCount()
    # Счётчик 32-битный и раз в ~49 дней переполняется — берём разницу по модулю.
    return ((now_ms - info.dwTime) & 0xFFFFFFFF) / 1000.0


class WindowsMonitor(ActivityMonitor):
    name = "windows"

    def sample(self) -> ActivitySample:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) if hwnd else ""
        process = "unknown"
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(pid).name().lower()
            except (psutil.Error, ValueError):
                pass
        return ActivitySample(idle_seconds(), process, title)
