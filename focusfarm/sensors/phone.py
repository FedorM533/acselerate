"""Датчик «телефон в подставке».

PhoneSensor — интерфейс. MockPhoneSensor — программная заглушка, которой
управляют из интерфейса (POST /api/dev/phone). SerialPhoneSensor — настоящая
подставка на ESP32 (см. focusfarm/device/serial_link.py).
"""


class PhoneSensor:
    source = "base"

    def __init__(self):
        self._listeners = []

    def is_docked(self) -> bool:
        raise NotImplementedError

    def on_dock_changed(self, handler):
        """handler(docked: bool) вызывается при каждом изменении."""
        self._listeners.append(handler)

    def _notify(self, docked: bool):
        for handler in self._listeners:
            handler(docked)


class MockPhoneSensor(PhoneSensor):
    source = "mock"

    def __init__(self, docked: bool = False):
        super().__init__()
        self._docked = docked

    def is_docked(self) -> bool:
        return self._docked

    def set_docked(self, docked: bool):
        if docked != self._docked:
            self._docked = docked
            self._notify(docked)
