"""Общие заготовки для тестов: менеджер с FakeClock, базой в памяти
и управляемым «монитором активности»."""
import datetime as dt
import random

import pytest
from fastapi.testclient import TestClient

from focusfarm.activity.monitor import ActivityMonitor, ActivitySample
from focusfarm.api.server import create_app
from focusfarm.clock import FakeClock
from focusfarm.config import load_settings
from focusfarm.sensors.phone import MockPhoneSensor
from focusfarm.session.manager import SessionManager
from focusfarm.storage.db import Database


class FakeMonitor(ActivityMonitor):
    name = "fake"

    def __init__(self):
        self.process = "code.exe"
        self.title = "main.py - Visual Studio Code"
        self.idle = 0.0

    def use(self, process: str, title: str = ""):
        self.process, self.title = process, title

    def sample(self):
        return ActivitySample(self.idle, self.process, self.title)


class Env:
    """Всё, что нужно тесту: клиент API, часы, монитор, менеджер."""

    def __init__(self, tmp_path, mode="dev", overrides=None, docked=True):
        self.clock = FakeClock(dt.datetime(2026, 9, 30, 10, 0).timestamp())
        self.db = Database(":memory:")
        settings = load_settings(overrides={"mode": mode, **(overrides or {})})
        self.monitor = FakeMonitor()
        self.manager = SessionManager(settings, self.db, clock=self.clock,
                                      monitor=self.monitor, rng=random.Random(1),
                                      phone=MockPhoneSensor(docked=docked))
        self.app = create_app(self.manager, run_loop=False, rules_path=tmp_path / "rules.yaml")
        self.client = TestClient(self.app)

    def tick(self, seconds=1):
        for _ in range(int(seconds)):
            self.clock.advance(1)
            self.manager.tick()

    def state(self):
        return self.client.get("/api/state").json()

    def post(self, url, json=None, ok=True):
        r = self.client.post(url, json=json)
        if ok:
            assert r.status_code == 200, r.text
        return r


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("FOCUSFARM_DEMO_SPEED", raising=False)
    return Env(tmp_path)


@pytest.fixture
def make_env(tmp_path, monkeypatch):
    monkeypatch.delenv("FOCUSFARM_DEMO_SPEED", raising=False)
    return lambda **kw: Env(tmp_path, **kw)
