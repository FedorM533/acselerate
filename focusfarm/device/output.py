"""Выход на подставку: свет и звук.

DeviceOutput — интерфейс. MockDeviceOutput — «виртуальная подставка»:
пишет команды в лог и запоминает их, чтобы интерфейс нарисовал цветной круг.
"""
import logging

log = logging.getLogger(__name__)

LED_COLORS = ("GREEN", "YELLOW", "RED", "BLUE", "OFF", "BLINK_RED")

SOUND_NAMES = {
    1: "мягкий сигнал",
    2: "сигнал «отвлёкся»",
    3: "урожай собран",
    4: "сессия началась",
}


class DeviceOutput:
    source = "base"

    def set_led(self, color: str):
        raise NotImplementedError

    def play_sound(self, n: int):
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError


class MockDeviceOutput(DeviceOutput):
    source = "mock"

    def __init__(self):
        self.led = "OFF"
        self.last_sound = None
        self.log = []   # история команд (для тестов и отладки)

    def set_led(self, color: str):
        if color not in LED_COLORS:
            raise ValueError(f"Неизвестный цвет: {color}")
        if color != self.led:
            self.led = color
            self.log.append(f"LED {color}")
            log.info("[виртуальная подставка] LED %s", color)

    def play_sound(self, n: int):
        self.last_sound = n
        self.log.append(f"SOUND {n}")
        log.info("[виртуальная подставка] SOUND %s (%s)", n, SOUND_NAMES.get(n, "?"))

    def is_connected(self) -> bool:
        return True
