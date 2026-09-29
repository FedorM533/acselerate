import pytest

from focusfarm import config
from focusfarm.clock import FakeClock, RealClock


def test_fake_clock_advances():
    clock = FakeClock(100)
    clock.advance(5.5)
    assert clock.now() == 105.5


def test_real_clock_moves_forward():
    clock = RealClock()
    assert clock.now() > 1_600_000_000


def test_default_settings_are_valid():
    s = config.load_settings()
    assert s["thresholds"]["phone_grace_s"] == 30
    assert s["game"]["crops"]["radish"]["focus_min"] == 10


def test_overrides_are_merged():
    s = config.load_settings(overrides={"thresholds": {"recover_s": 9}})
    assert s["thresholds"]["recover_s"] == 9
    assert s["thresholds"]["phone_grace_s"] == 30


def test_bad_threshold_rejected():
    with pytest.raises(config.ConfigError):
        config.load_settings(overrides={"thresholds": {"recover_s": -1}})


def test_env_demo_speed(monkeypatch):
    monkeypatch.setenv("FOCUSFARM_DEMO_SPEED", "30")
    s = config.load_settings()
    assert s["mode"] == "demo"
    assert config.speed_of(s) == 30


def test_speed_is_one_in_normal_mode(monkeypatch):
    monkeypatch.delenv("FOCUSFARM_DEMO_SPEED", raising=False)
    assert config.speed_of({"mode": "normal", "demo_speed": 30}) == 1
