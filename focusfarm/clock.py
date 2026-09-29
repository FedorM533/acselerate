"""Абстракция времени. Вся логика берёт время только отсюда —
тогда в тестах можно «перематывать» время без ожидания."""
import datetime as dt
import time


class Clock:
    """Базовый интерфейс часов."""

    def now(self) -> float:
        """Текущее время в секундах (как time.time())."""
        raise NotImplementedError

    def today(self) -> dt.date:
        """Сегодняшняя дата по локальному времени."""
        return dt.datetime.fromtimestamp(self.now()).date()


class RealClock(Clock):
    """Настоящие часы компьютера."""

    def now(self) -> float:
        return time.time()


class FakeClock(Clock):
    """Часы для тестов: время двигается только вручную."""

    def __init__(self, start: float = 1_700_000_000.0):
        self._now = float(start)

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def set(self, timestamp: float) -> None:
        self._now = float(timestamp)
