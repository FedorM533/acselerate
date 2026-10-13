"""Сторож: если во время строгой сессии программу закрыли, запускает её снова.

Запуск (делает сама программа): python -m focusfarm.watchdog --lock FILE --port N -- ARGS...
Сторож ничего не блокирует сам, он только перезапускает «Фокус-пруд». Программа, в свою очередь,
следит, что сторож жив (см. StrictGuard). Администратора это не остановит, см. focusfarm/strict.py.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from focusfarm import paths

CHECK_EVERY_S = 3
DEAD_CHECKS = 2          # столько проверок подряд программа молчит — перезапуск
START_GRACE_S = 30       # после запуска даём программе время подняться, чтобы не плодить копии


def lock_valid(lock_path: Path, now: float) -> bool:
    """Флаг есть и срок строгой сессии ещё не вышел."""
    try:
        until = float(json.loads(Path(lock_path).read_text(encoding="utf-8")).get("until", 0))
    except (OSError, ValueError, AttributeError):
        return False
    return now < until


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def launch(args: list[str]):
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen([*paths.self_command(), "--no-browser", *args], creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)


def run(lock_path: Path, port: int, args: list[str], *, alive=port_open, start=launch,
        now=time.time, sleep=time.sleep, max_loops: int | None = None) -> int:
    """Главный цикл. Возвращает, сколько раз перезапускал программу (для тестов).
    Выходит, когда строгой сессии нет, а программа закрыта."""
    restarts = 0
    silent = 0
    loops = 0
    while max_loops is None or loops < max_loops:
        loops += 1
        up = alive(port)
        locked = lock_valid(lock_path, now())
        if up:
            silent = 0
        elif not locked:
            break                      # сессия кончилась, программу закрыли: сторожу делать нечего
        else:
            silent += 1
            if silent >= DEAD_CHECKS:
                start(args)
                restarts += 1
                silent = -(START_GRACE_S // CHECK_EVERY_S)
        sleep(CHECK_EVERY_S)
    return restarts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("args", nargs="*")
    ns = parser.parse_args()
    run(Path(ns.lock), ns.port, [a for a in ns.args if a != "--"])


if __name__ == "__main__":
    main()
