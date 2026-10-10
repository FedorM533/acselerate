"""Строгий режим: пароль для досрочного выхода и файл-флаг для сторожа.

Честное ограничение: человек с правами администратора может завершить любой процесс
или удалить программу. Строгий режим защищает от «рука сама потянулась», а не от взлома.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

ITERATIONS = 200_000
MIN_PASSWORD_LEN = 4
MAX_FAILS = 5            # столько неверных паролей подряд — и пауза на LOCKOUT_S
LOCKOUT_S = 60


GRACE_S = 120            # запас в флаге: сторож не выключается раньше конца сессии


def pending_resume(lock_path: Path, now: float) -> float | None:
    """Если программу закрыли посреди строгой сессии, сколько минут от неё осталось (иначе None)."""
    try:
        until = float(json.loads(Path(lock_path).read_text(encoding="utf-8")).get("until", 0))
    except (OSError, ValueError, AttributeError):
        return None
    minutes = (until - GRACE_S - now) / 60
    return minutes if minutes >= 0.5 else None


def hash_password(password: str) -> str:
    """Хеш пароля с солью (PBKDF2-SHA256). Сам пароль нигде не хранится."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, digest = stored.split("$")
        if scheme != "pbkdf2":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(calc, bytes.fromhex(digest))
    except (ValueError, AttributeError):
        return False


class StrictGuard:
    """Файл-флаг «идёт строгая сессия» + запуск сторожа.

    В файле лежит срок действия (настоящее время, unix): так забытый флаг после сбоя
    или перезагрузки не заставит сторожа бесконечно перезапускать программу.
    """

    def __init__(self, lock_path: Path, relaunch_args: list[str], port: int, spawn=None, pid_alive=None,
                 retry_s: float = 30.0, monotonic=time.monotonic):
        self.lock_path = Path(lock_path)
        self.pid_path = self.lock_path.with_suffix(".watchdog.pid")
        self.relaunch_args = relaunch_args
        self.port = port
        self._spawn = spawn or self._spawn_watchdog
        self._pid_alive = pid_alive or _pid_alive
        self._active = False
        self._until = 0.0
        self._retry_s = retry_s
        self._monotonic = monotonic
        self._last_spawn: float | None = None

    def update(self, active: bool, until: float = 0.0):
        """Вызывать каждый тик: пишет/стирает флаг и следит, что сторож жив."""
        if active:
            if not self._active or abs(until - self._until) > 30:   # старт или срок заметно сдвинулся
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                self.lock_path.write_text(json.dumps({"until": until}), encoding="utf-8")
                self._until = until
            self._ensure_watchdog()
        elif self._active:
            self.lock_path.unlink(missing_ok=True)
        self._active = active

    def _ensure_watchdog(self):
        try:
            pid = int(self.pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = 0
        if pid and self._pid_alive(pid):
            return
        now = self._monotonic()
        if self._last_spawn is not None and now - self._last_spawn < self._retry_s:
            return                  # сторож только что запускался: не плодим процессы, если он падает
        self._last_spawn = now
        try:
            new_pid = self._spawn(self.lock_path, self.port, self.relaunch_args)
            if new_pid:
                self.pid_path.write_text(str(new_pid), encoding="utf-8")
        except Exception:   # без сторожа защита работает, просто слабее
            log.exception("Не удалось запустить сторожа")

    @staticmethod
    def _spawn_watchdog(lock_path, port, relaunch_args) -> int:
        cmd = [sys.executable, "-m", "focusfarm.watchdog", "--lock", str(lock_path), "--port", str(port),
               "--", *relaunch_args]
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        proc = subprocess.Popen(cmd, creationflags=flags, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return proc.pid


def _pid_alive(pid: int) -> bool:
    """Жив ли именно сторож: номер процесса после перезагрузки мог достаться чужой программе."""
    try:
        import psutil
        return "focusfarm.watchdog" in " ".join(psutil.Process(pid).cmdline())
    except Exception:
        return False
