"""Фаза 7: подставка по serial. Настоящий порт заменён заглушкой FakeSerial."""
import queue
import random
import time

import pytest

from focusfarm.clock import FakeClock
from focusfarm.config import load_settings
from focusfarm.device import serial_link
from focusfarm.device.dock import Dock
from focusfarm.session.manager import SessionManager
from focusfarm.storage.db import Database


class FakeSerial:
    """Притворяется ESP32: то, что «прислало устройство», кладём в incoming."""

    def __init__(self):
        self.incoming = queue.Queue()
        self.written = []
        self.broken = False
        self.closed = False

    def readline(self):
        if self.broken:
            raise OSError("кабель выдернули")
        try:
            return (self.incoming.get(timeout=0.02) + "\n").encode()
        except queue.Empty:
            return b""

    def write(self, data: bytes):
        if self.broken:
            raise OSError("кабель выдернули")
        self.written.append(data.decode().strip())

    def close(self):
        self.closed = True


class Opener:
    """Выдаёт новые FakeSerial; если available=False — порт «не найден»."""

    def __init__(self, available=True):
        self.available = available
        self.opened = []

    def __call__(self, port):
        if not self.available:
            raise OSError(f"порт {port} не найден")
        self.opened.append(FakeSerial())
        return self.opened[-1]


def wait_for(condition, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    raise AssertionError("не дождались")


@pytest.fixture(autouse=True)
def fast_reconnect(monkeypatch):
    monkeypatch.setattr(serial_link, "RECONNECT_S", 0.05)


@pytest.fixture
def opener():
    return Opener()


@pytest.fixture
def dock(opener):
    d = Dock("COM7", opener=opener)
    yield d
    d.stop()


def test_no_port_means_virtual_dock():
    d = Dock("")
    assert d.source == "mock" and d.status_text() is None and d.is_connected()
    d.set_docked(True)
    assert d.is_docked()


def test_connect_hello_and_dock(dock, opener):
    wait_for(lambda: dock.serial_ok)
    port = opener.opened[0]
    assert "STATUS" in port.written                 # спросили состояние при подключении
    port.incoming.put("HELLO fw=0.1")
    port.incoming.put("DOCK 1")
    wait_for(dock.is_docked)
    assert dock.source == "serial"
    assert "прошивка 0.1" in dock.status_text()


def test_led_and_sound_commands(dock, opener):
    wait_for(lambda: dock.serial_ok)
    dock.set_led("GREEN")
    dock.play_sound(4)
    written = opener.opened[0].written
    assert "LED GREEN" in written and "SOUND 4" in written
    assert dock.led == "GREEN"            # виртуальная подставка тоже знает цвет


def test_buttons(dock, opener):
    pressed = []
    dock.on_button(pressed.append)
    wait_for(lambda: dock.serial_ok)
    opener.opened[0].incoming.put("BTN PAUSE")
    opener.opened[0].incoming.put("BTN NOTEBOOK")
    wait_for(lambda: len(pressed) == 2)
    assert pressed == ["PAUSE", "NOTEBOOK"]


def test_garbage_lines_are_ignored(dock, opener):
    wait_for(lambda: dock.serial_ok)
    for junk in ("", "DOCK", "DOCK 5", "ЧТО-ТО", "BTN"):
        opener.opened[0].incoming.put(junk)
    opener.opened[0].incoming.put("DOCK 1")
    wait_for(dock.is_docked)


def test_port_missing_falls_back_to_mock():
    d = Dock("COM99", mock_docked=True, opener=Opener(available=False))
    try:
        time.sleep(0.1)
        assert not d.serial_ok and d.source == "mock"
        assert d.is_docked()                       # работает виртуальный датчик
        assert "не подключена" in d.status_text()
        d.set_led("RED")                           # ничего не падает
    finally:
        d.stop()


def test_reconnect_after_cable_pulled(dock, opener):
    wait_for(lambda: dock.serial_ok)
    dock.set_led("YELLOW")
    opener.opened[0].broken = True
    wait_for(lambda: len(opener.opened) >= 2 and dock.serial_ok)
    # После переподключения подставка сразу получает текущий цвет.
    wait_for(lambda: "LED YELLOW" in opener.opened[-1].written)


def test_change_port_in_settings(dock, opener):
    wait_for(lambda: dock.serial_ok)
    dock.set_port("")
    assert dock.link is None and dock.source == "mock"
    assert opener.opened[0].closed


def test_session_driven_by_real_dock(opener):
    """Телефон кладут в настоящую подставку → сессия стартует, LED зелёный;
    кнопка на подставке ставит паузу."""
    clock = FakeClock()
    settings = load_settings(overrides={"mode": "normal", "device": {"serial_port": "COM7"}})
    dock = Dock("COM7", opener=opener)
    manager = SessionManager(settings, Database(":memory:"), clock=clock, phone=dock,
                             device=dock, rng=random.Random(1))
    try:
        wait_for(lambda: dock.serial_ok)
        port = opener.opened[0]
        port.incoming.put("DOCK 1")
        wait_for(dock.is_docked)
        clock.advance(1)
        manager.tick()
        assert manager.state == "FOCUS"
        assert "LED GREEN" in port.written and "SOUND 4" in port.written
        port.incoming.put("BTN PAUSE")
        wait_for(lambda: manager.state == "PAUSED")
        assert "LED BLUE" in port.written
    finally:
        manager.close()


def test_port_from_settings_api(tmp_path, monkeypatch):
    """Выбор COM-порта в «Настройках» переключает настоящую подставку;
    несуществующий порт не роняет программу."""
    from fastapi.testclient import TestClient

    from focusfarm.api.server import build_manager, create_app
    from focusfarm.device import dock as dock_module

    monkeypatch.delenv("FOCUSFARM_DEMO_SPEED", raising=False)
    monkeypatch.setattr(dock_module, "open_serial", Opener(available=False))
    manager = build_manager(":memory:", cli_overrides={"mode": "normal"})
    client = TestClient(create_app(manager, run_loop=False, rules_path=tmp_path / "rules.yaml"))
    try:
        assert client.put("/api/settings", json={"device": {"serial_port": "COM42"}}).status_code == 200
        assert manager.phone.port == "COM42"
        time.sleep(0.1)
        device = client.get("/api/state").json()["device"]
        assert device["connected"] is False and "не подключена" in device["status"]
        client.put("/api/settings", json={"device": {"serial_port": ""}})
        assert manager.phone.link is None
    finally:
        manager.close()
