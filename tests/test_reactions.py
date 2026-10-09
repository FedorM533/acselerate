"""Реакции подставки и ограничение частоты звуков."""
from focusfarm.clock import FakeClock
from focusfarm.device.output import MockDeviceOutput
from focusfarm.events import EventBus
from focusfarm.reactions import Reactions


def setup():
    clock, bus, device = FakeClock(), EventBus(), MockDeviceOutput()
    Reactions(device, clock, bus, {"enabled": True, "distracted_repeat_s": 180, "min_gap_s": 5})
    return clock, bus, device


def change(bus, state, prev="FOCUS"):
    bus.publish("state_changed", {"state": state, "prev": prev})


def test_led_colors_for_states():
    clock, bus, device = setup()
    expected = {"FOCUS": "GREEN", "NOTEBOOK": "GREEN", "MAYBE_DISTRACTED": "YELLOW",
                "DISTRACTED": "RED", "PHONE_OUT": "BLINK_RED", "PAUSED": "BLUE", "IDLE": "OFF"}
    for state, color in expected.items():
        change(bus, state)
        assert device.led == color


def test_distracted_sound_not_more_than_every_3_min():
    clock, bus, device = setup()
    change(bus, "DISTRACTED")
    clock.advance(60)
    change(bus, "FOCUS")
    change(bus, "DISTRACTED")
    assert device.log.count("SOUND 2") == 1
    clock.advance(121)
    change(bus, "DISTRACTED")
    assert device.log.count("SOUND 2") == 2


def test_min_gap_between_any_sounds():
    clock, bus, device = setup()
    bus.publish("session_started", {})
    bus.publish("harvested", {})
    assert device.log.count("SOUND 3") == 0
    clock.advance(5)
    bus.publish("harvested", {})
    assert device.log.count("SOUND 3") == 1


def test_crop_ready_is_silent_during_work():
    """Игра не отвлекает: рыбка выросла посреди работы — подставка молчит."""
    clock, bus, device = setup()
    bus.publish("crop_ready", {})
    assert device.log.count("SOUND 3") == 0


def test_phone_out_sound_once_per_episode():
    clock, bus, device = setup()
    change(bus, "PHONE_OUT", prev="FOCUS")
    clock.advance(10)
    change(bus, "PHONE_OUT", prev="PHONE_OUT")
    assert device.log.count("SOUND 1") == 1


def test_device_error_does_not_crash():
    class Broken(MockDeviceOutput):
        def set_led(self, color):
            raise OSError("порт закрыт")

    clock, bus = FakeClock(), EventBus()
    r = Reactions(Broken(), clock, bus)
    bus.publish("state_changed", {"state": "FOCUS", "prev": "IDLE"})
    assert "порт закрыт" in r.device_error


def test_bus_handler_error_is_isolated():
    bus = EventBus()
    got = []
    bus.subscribe("x", lambda d: 1 / 0)
    bus.subscribe("x", lambda d: got.append(d))
    bus.publish("x", {"a": 1})
    assert got == [{"a": 1}]
