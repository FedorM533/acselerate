"""Блокировка приложений на ПК.

Пока идёт сессия (и не пауза), ищем запущенные программы из чёрного списка:
- мягко (soft): один раз говорим, что программа отвлекает; ничего не закрываем;
- жёстко (hard): предупреждаем и через WARN_S секунд закрываем программу.

Время берём из настоящих часов (не ускоряем в демо): 10 секунд на сохранение
работы должны быть настоящими. Системные программы и сама «Фокус-пруд» (вместе
с родительскими процессами) не закрываем никогда.
"""
import logging
import os

import psutil

log = logging.getLogger(__name__)

WARN_S = 10          # сколько секунд до закрытия в жёстком режиме
SCAN_EVERY_S = 2     # как часто просматриваем список процессов

# Эти программы не закрываем, даже если их внесли в чёрный список.
PROTECTED = frozenset({
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
    "taskmgr.exe", "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "python.exe", "pythonw.exe", "py.exe", "node.exe",
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

    def update(self, now, active, hard, blocklist) -> list[dict]:
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

    def reset(self):
        self._tracked.clear()
        self._failed.clear()
        self._last_scan = None

    def update(self, now: float, active: bool, hard: bool, blocklist) -> list[dict]:
        """Один шаг. Возвращает события: block_warning, app_closed, block_failed."""
        blocklist = {name.lower() for name in blocklist} - PROTECTED
        if not active or not blocklist:
            self.reset()
            return []
        events = []
        if self._last_scan is None or now - self._last_scan >= SCAN_EVERY_S:
            self._last_scan = now
            events += self._scan(now, hard, blocklist)
        if hard:
            events += self._close_expired(now)
        return events

    def _scan(self, now, hard, blocklist) -> list[dict]:
        protected = self.processes.protected_pids()
        found = {pid: name for pid, name in self.processes.running()
                 if name in blocklist and pid not in protected}
        for pid in list(self._tracked):          # программу уже закрыли без нас
            if pid not in found:
                del self._tracked[pid]
        self._failed &= set(found)
        new_names = []
        for pid, name in found.items():
            if pid not in self._tracked:
                self._tracked[pid] = (name, now + self.warn_s if hard else None)
                if name not in new_names:
                    new_names.append(name)
        return [{"type": "block_warning", "process": name, "hard": hard,
                 "seconds": self.warn_s if hard else 0} for name in new_names]

    def _close_expired(self, now) -> list[dict]:
        closed, failed = [], []
        for pid, (name, deadline) in list(self._tracked.items()):
            if deadline is None or now < deadline or pid in self._failed:
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
