"""Телефон по USB-кабелю: разбор списка устройств, привязка, строгий старт сессии."""
import pytest

from focusfarm.device.dock import Dock
from focusfarm.sensors.usb_phone import UsbPhoneSensor, parse_macos, parse_windows

PHONE = {"id": "18D1:ABC123", "vid": "18D1", "pid": "4EE1", "serial": "ABC123", "name": "Pixel"}
MOUSE = {"id": "046D:XYZ", "vid": "046D", "pid": "C077", "serial": "XYZ", "name": "Mouse"}


class FakeLister:
    def __init__(self, *devices):
        self.devices = list(devices)
        self.fail = False

    def list_devices(self):
        if self.fail:
            raise OSError("нет доступа")
        return list(self.devices)


def test_parse_windows_keeps_top_level_devices_only():
    text = r"""USB\VID_18D1&PID_4EE1\ABC123|Pixel 7
USB\VID_18D1&PID_4EE1&MI_00\7&1A2B&0&0000|Pixel интерфейс
USB\ROOT_HUB30\4&1&0|Hub
мусорная строка
"""
    devices = parse_windows(text)
    assert [d["id"] for d in devices] == ["18D1:ABC123"]
    assert devices[0]["name"] == "Pixel 7" and devices[0]["pid"] == "4EE1"


def test_parse_macos():
    text = """
USB:
    Pixel 7:
      Product ID: 0x4ee1
      Vendor ID: 0x18d1  (Google Inc.)
      Serial Number: ABC123
"""
    assert [d["id"] for d in parse_macos(text)] == ["18D1:ABC123"]


def test_docked_follows_paired_device():
    lister = FakeLister(MOUSE)
    usb = UsbPhoneSensor(lister, paired_id=PHONE["id"])
    events = []
    usb.on_dock_changed(events.append)
    usb.poll()
    assert not usb.is_docked()
    lister.devices.append(PHONE)
    usb.poll()
    assert usb.is_docked() and events == [True]
    lister.devices.remove(PHONE)
    usb.poll()
    assert not usb.is_docked() and events == [True, False]


def test_unpaired_never_docked():
    usb = UsbPhoneSensor(FakeLister(PHONE, MOUSE))
    usb.poll()
    assert not usb.is_docked()


def test_pairing_finds_the_new_device():
    lister = FakeLister(MOUSE)
    usb = UsbPhoneSensor(lister)
    usb.pair_begin()
    lister.devices.append(PHONE)
    assert usb.pair_finish() == [PHONE]


def test_pair_finish_without_begin_is_empty():
    assert UsbPhoneSensor(FakeLister(PHONE)).pair_finish() == []


def test_lister_error_does_not_crash():
    lister = FakeLister(PHONE)
    usb = UsbPhoneSensor(lister, paired_id=PHONE["id"])
    usb.poll()
    lister.fail = True
    usb.poll()
    assert not usb.is_docked() and "USB" in usb.error


def test_dock_accepts_any_source():
    lister = FakeLister(PHONE)
    usb = UsbPhoneSensor(lister, paired_id=PHONE["id"])
    dock = Dock(usb=usb)
    assert not dock.is_docked() and dock.source == "mock"
    usb.poll()
    assert dock.is_docked() and dock.source == "usb"
    dock.set_phone_source("serial")   # USB отключён настройкой
    assert not dock.is_docked()
    dock.shutdown()


# ---------- строгий старт и тренировка без телефона ----------

def test_session_does_not_start_without_phone(make_env):
    env = make_env(docked=False)
    r = env.post("/api/session/start", {}, ok=False)
    assert r.status_code == 400 and "телефон" in r.json()["detail"].lower()
    assert env.state()["session"] is None


def test_practice_session_without_phone_gives_no_growth(make_env):
    env = make_env(docked=False)
    env.post("/api/session/start", {"without_phone": True})
    env.tick(300)
    s = env.state()
    assert s["state"] == "FOCUS" and s["session"]["no_phone"]
    assert all(p["crop"] is None for p in s["farm"]["plots"])
    assert s["session"]["totals"]["FOCUS"] >= 299   # время идёт в статистику


def test_normal_mode_phone_is_not_assumed_docked(make_env):
    env = make_env(mode="normal", docked=False)
    env.tick(5)
    assert env.state()["session"] is None
    assert env.state()["phone"]["docked"] is False


def test_pairing_api_roundtrip(tmp_path):
    import datetime as dt
    import random

    from fastapi.testclient import TestClient

    from focusfarm.api.server import create_app
    from focusfarm.clock import FakeClock
    from focusfarm.config import load_settings
    from focusfarm.session.manager import SessionManager
    from focusfarm.storage.db import Database
    from conftest import FakeMonitor

    lister = FakeLister(MOUSE)
    dock = Dock(usb=UsbPhoneSensor(lister))
    manager = SessionManager(load_settings(overrides={"mode": "dev"}), Database(":memory:"),
                             clock=FakeClock(dt.datetime(2026, 9, 30, 10, 0).timestamp()),
                             monitor=FakeMonitor(), rng=random.Random(1), phone=dock, device=dock)
    client = TestClient(create_app(manager, run_loop=False, rules_path=tmp_path / "rules.yaml"))

    assert client.post("/api/phone/pair/begin").json() == {"ok": True}
    lister.devices.append(PHONE)
    r = client.post("/api/phone/pair/finish").json()
    assert r["paired"] and r["usb"]["name"] == "Pixel" and r["usb"]["docked"]
    assert client.get("/api/state").json()["phone"]["docked"] is True
    assert client.get("/api/settings").json()["device"]["usb_phone"]["id"] == PHONE["id"]

    assert client.delete("/api/phone/pair").json()["paired"] is False
    dock.shutdown()
