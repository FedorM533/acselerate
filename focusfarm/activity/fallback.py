"""Запасной монитор: ничего не знает об окнах, работает только датчик телефона."""
from focusfarm.activity.monitor import ActivityMonitor, ActivitySample


class FallbackMonitor(ActivityMonitor):
    available = False
    name = "fallback"

    def sample(self) -> ActivitySample:
        return ActivitySample(idle_seconds=0, process_name="unknown")
