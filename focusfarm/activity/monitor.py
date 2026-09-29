"""Монитор активности: какое окно активно и сколько секунд не было ввода.

Выбирает реализацию по ОС. Если ничего не работает — FallbackMonitor,
и в интерфейсе показываем предупреждение.
"""
import logging
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ActivitySample:
    idle_seconds: float
    process_name: str
    window_title: str = ""   # только в памяти, в базу не пишем!


class ActivityMonitor:
    """Базовый интерфейс."""
    available = True
    name = "base"

    def sample(self) -> ActivitySample:
        raise NotImplementedError


def create_monitor() -> ActivityMonitor:
    """Возвращает лучший доступный монитор для текущей ОС."""
    from focusfarm.activity.fallback import FallbackMonitor
    try:
        if sys.platform == "win32":
            from focusfarm.activity.windows import WindowsMonitor
            monitor = WindowsMonitor()
        elif sys.platform == "darwin":
            from focusfarm.activity.macos import MacMonitor
            monitor = MacMonitor()
        else:
            return FallbackMonitor()
        monitor.sample()  # пробный вызов: если упадёт — используем запасной
        return monitor
    except Exception as exc:  # любая ошибка → запасной вариант
        log.warning("Монитор активности недоступен: %s", exc)
        return FallbackMonitor()


class SafeMonitor(ActivityMonitor):
    """Обёртка: ошибка при чтении окна не роняет программу."""

    def __init__(self, inner: ActivityMonitor):
        self.inner = inner
        self.name = inner.name
        self.available = inner.available
        self.last_error = None

    def sample(self) -> ActivitySample:
        try:
            s = self.inner.sample()
            self.last_error = None
            return s
        except Exception as exc:
            if self.last_error is None:
                log.warning("Ошибка монитора активности: %s", exc)
            self.last_error = str(exc)
            return ActivitySample(idle_seconds=0, process_name="unknown")
