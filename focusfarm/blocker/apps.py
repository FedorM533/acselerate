"""Блокировка приложений на ПК.

Пока идёт сессия (и не пауза), ищем запущенные программы из чёрного списка:
- мягко (soft): говорим, что программа отвлекает, и повторяем каждые SOFT_REPEAT_S секунд,
  пока она открыта; ничего не закрываем;
- жёстко (hard): предупреждаем и через WARN_S секунд закрываем программу: сначала вежливо
  (окнам посылается WM_CLOSE, программа может спросить «сохранить?»), и только если она
  не закрылась за CLOSE_GRACE_S секунд, завершаем процесс.

Время берём из настоящих часов (не ускоряем в демо): 10 секунд на сохранение
работы должны быть настоящими. Системные программы и сама «Фокус-пруд» (вместе
с родительскими процессами) не закрываем никогда.
"""
import logging
import os
import shutil
import subprocess
import sys

import psutil

log = logging.getLogger(__name__)

WARN_S = 10          # сколько секунд до закрытия в жёстком режиме
SOFT_REPEAT_S = 30     # в мягком режиме напоминаем снова, пока программа открыта
CLOSE_GRACE_S = 8     # сколько ждём после вежливой просьбы закрыться
SCAN_EVERY_S = 2     # как часто просматриваем список процессов

# Эти программы не закрываем, даже если их внесли в чёрный список.
PROTECTED = frozenset({
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
    "taskmgr.exe", "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "python.exe", "pythonw.exe", "py.exe", "node.exe",
    # Linux: оболочка рабочего стола, терминалы и сам Python.
    "systemd", "gnome-shell", "xwayland", "xorg", "kwin_wayland", "kwin_x11", "plasmashell",
    "gnome-terminal-server", "kgx", "ptyxis", "konsole", "xterm", "xfce4-terminal", "tilix",
    "bash", "sh", "zsh", "fish", "python", "python3", "node",
})


class PsutilProcesses:
    """Настоящий список процессов и их закрытие."""

    def running(self) -> list[tuple[int, str]]:
        result = []
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info.get("name")
            if name:
                result.append((proc.info["pid"], name.lower()))
        return result

    def protected_pids(self) -> set[int]:
        """Наш процесс и все его родители (например, консоль, из которой запустили)."""
        pids = {os.getpid()}
        try:
            pids.update(p.pid for p in psutil.Process().parents())
        except psutil.Error:
            pass
        return pids

    def window_apps(self) -> list[tuple[int, str]]:
        """Программы с видимым окном (для белого списка)."""
        if sys.platform.startswith("linux"):
            return self._linux_window_apps()
        return self._windows_window_apps()

    def request_close(self, pid: int) -> bool:
        """Вежливо просит окна процесса закрыться (как кнопка «×»). True — хотя бы одному окну отправили."""
        if sys.platform.startswith("linux"):
            return self._linux_request_close(pid)
        return self._windows_request_close(pid)

    # ---------- Windows ----------

    def _windows_window_apps(self) -> list[tuple[int, str]]:
        """Системные из папки Windows и окна без заголовка пропускаем: закрывать
        их нельзя, а пользователь их не видит."""
        try:
            import win32con
            import win32gui
            import win32process
        except ImportError:    # не Windows: белый список на этой системе не работает
            return []
        pids = set()

        def visit(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return
            if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
                return
            pids.add(win32process.GetWindowThreadProcessId(hwnd)[1])

        try:
            win32gui.EnumWindows(visit, None)
        except Exception:      # окна могут исчезать прямо во время обхода
            log.warning("Не удалось перечислить окна", exc_info=True)
        windows = os.environ.get("SystemRoot", r"C:\Windows").lower()
        result = []
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                if not proc.exe().lower().startswith(windows):
                    result.append((pid, proc.name().lower()))
            except psutil.Error:
                continue
        return result

    def _windows_request_close(self, pid: int) -> bool:
        try:
            import win32con
            import win32gui
            import win32process
        except ImportError:
            return False
        hwnds = []

        def visit(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
                hwnds.append(hwnd)

        try:
            win32gui.EnumWindows(visit, None)
            for hwnd in hwnds:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            log.warning("Не удалось послать WM_CLOSE процессу %s", pid, exc_info=True)
            return False
        return bool(hwnds)

    # ---------- Linux ----------
    # Окна узнаём так же, как монитор активности: X11 — xprop, GNOME на Wayland —
    # наше расширение GNOME Shell. Без них белый список на Linux не работает.

    def _linux_backend(self) -> str | None:
        from focusfarm.activity import linux
        if getattr(self, "_backend", None) is None:
            self._backend = linux.window_backend()   # расширение могли включить уже после старта
        return self._backend

    def _linux_window_apps(self) -> list[tuple[int, str]]:
        from focusfarm.activity import linux
        try:
            windows = linux.list_windows(self._linux_backend())
        except (OSError, subprocess.SubprocessError, ValueError):
            log.warning("Не удалось перечислить окна", exc_info=True)
            return []
        result = {}
        for pid, _title in windows:
            name = linux.process_name(pid)
            if name != "unknown":
                result[pid] = name
        return list(result.items())

    def _linux_request_close(self, pid: int) -> bool:
        from focusfarm.activity import linux
        backend = self._linux_backend()
        try:
            if backend == "gnome":
                return linux.extension_close(pid)
            if backend == "x11" and shutil.which("wmctrl"):
                sent = False
                for window in linux.parse_xprop_client_list(
                        linux._run(["xprop", "-root", "_NET_CLIENT_LIST"])):
                    owner, _ = linux.parse_xprop_window(
                        linux._run(["xprop", "-id", window, "_NET_WM_PID", "_NET_WM_NAME"]))
                    if owner == pid:
                        linux._run(["wmctrl", "-i", "-c", window])
                        sent = True
                return sent
        except (OSError, subprocess.SubprocessError, ValueError):
            log.warning("Не удалось вежливо закрыть процесс %s", pid, exc_info=True)
        return False   # не смогли попросить — после предупреждения завершим процесс (SIGTERM)

    def terminate(self, pid: int) -> bool:
        try:
            psutil.Process(pid).terminate()
            return True
        except psutil.NoSuchProcess:
            return True    # уже закрылась сама
        except psutil.Error as exc:
            log.warning("Не удалось закрыть процесс %s: %s", pid, exc)
            return False


class NullBlocker:
    """Ничего не блокирует: значение по умолчанию (тесты, демо без блокировки)."""

    def update(self, now, active, hard, blocklist, allowlist=None) -> list[dict]:
        return []

    def window_apps(self) -> list[tuple[int, str]]:
        return []

    def view(self, now) -> dict:
        return {"warnings": []}


class AppBlocker:
    def __init__(self, processes=None, warn_s: float = WARN_S):
        self.processes = processes or PsutilProcesses()
        self.warn_s = warn_s
        self._tracked: dict[int, tuple[str, float | None]] = {}   # pid → (имя, срок закрытия)
        self._failed: set[int] = set()    # закрыть не вышло — не пытаемся каждую секунду
        self._last_scan: float | None = None
        self._closing: dict[int, tuple[str, float]] = {}   # pid → (имя, когда завершать силой)
        self._warned: dict[int, float] = {}                # pid → когда предупреждали в последний раз (мягко)

    def reset(self):
        self._warned.clear()
        self._closing.clear()
        self._tracked.clear()
        self._failed.clear()
        self._last_scan = None

    def window_apps(self) -> list[tuple[int, str]]:
        """Программы с окнами — подсказка для составления белого списка."""
        protected = self.processes.protected_pids()
        return [(pid, name) for pid, name in self.processes.window_apps()
                if pid not in protected and name not in PROTECTED]

    def update(self, now: float, active: bool, hard: bool, blocklist, allowlist=None) -> list[dict]:
        """Один шаг. Возвращает события: block_warning, app_closed, block_failed.

        allowlist=None — чёрный список (blocklist). Иначе белый: закрываем все
        программы с окном, которых нет в allowlist. Пустой белый список ничего не
        блокирует, иначе при включении режима закрылось бы вообще всё."""
        if allowlist is None:
            names = {name.lower() for name in blocklist} - PROTECTED
        else:
            names = {name.lower() for name in allowlist}
        if not active or not names:
            self.reset()
            return []
        events = []
        if self._last_scan is None or now - self._last_scan >= SCAN_EVERY_S:
            self._last_scan = now
            events += self._scan(now, hard, names, whitelist=allowlist is not None)
        if hard:
            events += self._close_expired(now)
        return events

    def _scan(self, now, hard, names, whitelist=False) -> list[dict]:
        protected = self.processes.protected_pids()
        if whitelist:
            found = {pid: name for pid, name in self.processes.window_apps()
                     if name not in names and name not in PROTECTED and pid not in protected}
        else:
            found = {pid: name for pid, name in self.processes.running()
                     if name in names and pid not in protected}
        gone = []
        for pid in list(self._tracked):          # программу уже закрыли (сама, по просьбе или без нас)
            if pid not in found:
                del self._tracked[pid]
                self._warned.pop(pid, None)
                if pid in self._closing:
                    gone.append(self._closing.pop(pid)[0])
        self._failed &= set(found)
        new_names = []
        for pid, name in found.items():
            if pid not in self._tracked:
                self._tracked[pid] = (name, now + self.warn_s if hard else None)
                self._warned[pid] = now
                if name not in new_names:
                    new_names.append(name)
            elif not hard and now - self._warned.get(pid, now) >= SOFT_REPEAT_S:
                self._warned[pid] = now          # мягко: человек убрал предупреждение, а программа открыта
                if name not in new_names:
                    new_names.append(name)
        return ([{"type": "block_warning", "process": name, "hard": hard,
                  "seconds": self.warn_s if hard else 0} for name in new_names]
                + [{"type": "app_closed", "process": n} for n in dict.fromkeys(gone)])

    def _close_expired(self, now) -> list[dict]:
        closed, failed = [], []
        for pid, (name, deadline) in list(self._tracked.items()):
            if deadline is None or now < deadline or pid in self._failed:
                continue
            if pid in self._closing:
                if now < self._closing[pid][1]:
                    continue                      # ещё даём программе закрыться самой
                del self._closing[pid]
            elif getattr(self.processes, "request_close", None) and self.processes.request_close(pid):
                self._closing[pid] = (name, now + CLOSE_GRACE_S)
                continue
            if self.processes.terminate(pid):
                del self._tracked[pid]
                if name not in closed:
                    closed.append(name)
            else:
                self._failed.add(pid)
                if name not in failed:
                    failed.append(name)
        return ([{"type": "app_closed", "process": n} for n in closed]
                + [{"type": "block_failed", "process": n} for n in failed])

    def view(self, now: float) -> dict:
        """Что сейчас под предупреждением — для интерфейса."""
        warnings = {}
        for name, deadline in self._tracked.values():
            left = max(0.0, deadline - now) if deadline is not None else None
            if name not in warnings or (left is not None and left < (warnings[name] or 1e9)):
                warnings[name] = left
        return {"warnings": [{"process": n, "seconds_left": left} for n, left in warnings.items()]}
