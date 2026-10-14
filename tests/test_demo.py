"""Фаза 8: сценарий демо из docs/DEMO.md при ускорении ×30 и работа без интернета.

Каждый env.tick() — одна НАСТОЯЩАЯ секунда, то есть 30 «игровых».
"""
import socket

import pytest

from focusfarm.session.state_machine import DISTRACTED, FOCUS, IDLE, PHONE_OUT


@pytest.fixture
def demo(make_env):
    return make_env(mode="demo", overrides={"demo_speed": 30}, docked=False)


def test_demo_scenario_x30(demo):
    env = demo
    s = env.state()
    assert s["mode"] == "demo" and s["speed"] == 30 and s["dev_tools"]

    # 1. Кладём телефон — сессия, зелёный свет, звук «сессия началась».
    env.post("/api/dev/phone", {"docked": True})
    env.tick()
    assert env.state()["state"] == FOCUS
    assert env.manager.device.led == "GREEN"
    assert env.state()["session"]["planned_s"] == 120 * 60   # демо-сессия: 4 настоящие минуты

    # 2. Работаем 12 секунд = 6 игровых минут.
    env.post("/api/dev/category", {"category": "work"})
    env.tick(12)
    assert env.state()["session"]["totals"]["FOCUS"] >= 300

    # 3. «Открыли YouTube»: жёлтый, через секунду красный.
    env.post("/api/dev/category", {"category": "distraction"})
    env.tick(1)
    assert env.manager.device.led in ("YELLOW", "RED")
    env.tick(3)
    assert env.state()["state"] == DISTRACTED and env.manager.device.led == "RED"

    # 4. Вернулись к работе.
    # Гистерезис: первый «хороший» тик запускает отсчёт recover_s, второй — возвращает.
    env.post("/api/dev/category", {"category": "work"})
    env.tick(2)
    assert env.state()["state"] == FOCUS

    # 5. (по желанию) Взяли телефон — мигает красным, вернули — снова фокус.
    env.post("/api/dev/phone", {"docked": False})
    env.tick(2)
    assert env.state()["state"] == PHONE_OUT and env.manager.device.led == "BLINK_RED"
    env.post("/api/dev/phone", {"docked": True})
    env.tick(2)
    assert env.state()["state"] == FOCUS

    # 6. Ещё немного работы.
    env.tick(8)

    # 7. Завершили — статистика показывает фокус и отвлечения.
    env.post("/api/session/end")
    assert env.state()["state"] == IDLE
    stats = env.client.get("/api/stats").json()
    assert stats["focus_s"] >= 600
    assert stats["distraction_reasons"] == {"window": 1, "phone": 1}


def test_env_variable_enables_demo(monkeypatch, tmp_path):
    from focusfarm.config import load_settings, speed_of
    monkeypatch.setenv("FOCUSFARM_DEMO_SPEED", "30")
    settings = load_settings()
    assert settings["mode"] == "demo" and speed_of(settings) == 30


def test_works_without_internet(demo, monkeypatch):
    """Любая попытка выйти в сеть (кроме 127.0.0.1) — ошибка теста."""
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(f"Программа полезла в интернет: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    env = demo
    env.post("/api/dev/phone", {"docked": True})
    env.tick(25)
    for url in ("/", "/app.js", "/style.css", "/api/state", "/api/stats?range=week",
                "/api/settings", "/api/rules", "/api/ports"):
        assert env.client.get(url).status_code == 200, url
