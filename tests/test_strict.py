"""Строгий режим: пароль, запрет паузы и выхода, флаг и сторож, пропавшее расширение."""
import json

import pytest

from focusfarm import watchdog
from focusfarm.session.manager import EXTENSION_TIMEOUT_S
from focusfarm.strict import (
    GRACE_S, LOCKOUT_S, MAX_FAILS, StrictGuard, hash_password, pending_resume, verify_password,
)
from tests.conftest import Env


def hard_env(tmp_path, strictness="hard"):
    return Env(tmp_path, overrides={"protection": {"strictness": strictness, "targets": "pc"}})


# ---------- пароль ----------

def test_password_hash_is_salted_and_verifiable():
    a, b = hash_password("секрет"), hash_password("секрет")
    assert a != b and "секрет" not in a
    assert verify_password("секрет", a) and not verify_password("другой", a)
    assert not verify_password("секрет", "мусор")


def test_set_change_and_clear_password(tmp_path):
    env = hard_env(tmp_path)
    r = env.client.put("/api/strict/password", json={"new": "abc"})
    assert r.status_code == 400                                   # слишком короткий
    assert env.client.put("/api/strict/password", json={"new": "секрет"}).status_code == 200
    assert env.client.get("/api/strict").json()["password_set"] is True
    # менять можно, только зная старый
    assert env.client.put("/api/strict/password", json={"new": "новый1"}).status_code == 400
    assert env.client.put("/api/strict/password", json={"new": "новый1", "old": "секрет"}).status_code == 200
    assert env.client.request("DELETE", "/api/strict/password", json={"password": "секрет"}).status_code == 400
    assert env.client.request("DELETE", "/api/strict/password", json={"password": "новый1"}).status_code == 200
    assert env.client.get("/api/strict").json()["password_set"] is False


def test_password_is_not_stored_in_plain_text(tmp_path):
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    assert "секрет" not in env.db.get_secret("strict_password")


# ---------- запрет досрочного выхода ----------

def test_hard_session_without_password_cannot_be_paused_or_ended(tmp_path):
    env = hard_env(tmp_path)
    env.post("/api/session/start", {})
    assert env.client.post("/api/session/pause").status_code == 400
    assert env.client.post("/api/session/end").status_code == 400
    assert env.state()["session"] is not None and not env.state()["session"]["paused"]


def test_hard_session_with_password(tmp_path):
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    env.post("/api/session/start", {})
    assert env.client.post("/api/session/pause", json={"password": "не то"}).status_code == 400
    assert env.client.post("/api/session/pause", json={"password": "секрет"}).status_code == 200
    assert env.state()["session"]["paused"] is True
    assert env.client.post("/api/session/end", json={"password": "секрет"}).status_code == 200
    assert env.state()["session"] is None


def test_soft_session_is_not_locked(tmp_path):
    env = hard_env(tmp_path, strictness="soft")
    env.post("/api/session/start", {})
    env.post("/api/session/pause")
    env.post("/api/session/resume")
    env.post("/api/session/end")


def test_session_ends_by_timer(tmp_path):
    env = hard_env(tmp_path)
    env.post("/api/session/start", {"length_min": 1})
    env.tick(65)
    assert env.state()["session"] is None


def test_wrong_passwords_lock_out_even_the_right_one(tmp_path):
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    env.post("/api/session/start", {})
    for _ in range(MAX_FAILS):
        assert env.client.post("/api/session/end", json={"password": "нет"}).status_code == 400
    assert env.client.post("/api/session/end", json={"password": "секрет"}).status_code == 400
    env.clock.advance(LOCKOUT_S + 1)
    assert env.client.post("/api/session/end", json={"password": "секрет"}).status_code == 200


def test_cannot_weaken_protection_without_password(tmp_path):
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    env.post("/api/session/start", {})
    soft = {"protection": {"strictness": "soft"}}
    assert env.client.put("/api/settings", json=soft).status_code == 400
    assert env.manager.settings["protection"]["strictness"] == "hard"
    assert env.client.put("/api/settings", json={**soft, "password": "секрет"}).status_code == 200
    assert env.manager.settings["protection"]["strictness"] == "soft"


def test_other_settings_stay_free_during_hard_session(tmp_path):
    env = hard_env(tmp_path)
    env.post("/api/session/start", {})
    assert env.client.put("/api/settings", json={"ui": {"pond_fish_max": 5}}).status_code == 200


def test_password_cannot_be_changed_during_hard_session(tmp_path):
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    env.post("/api/session/start", {})
    assert env.client.put("/api/strict/password", json={"new": "хитрый", "old": "секрет"}).status_code == 400


def test_dock_button_cannot_pause_hard_session(tmp_path):
    env = hard_env(tmp_path)
    env.post("/api/session/start", {})
    env.manager._on_button("PAUSE")
    assert env.state()["session"]["paused"] is False


# ---------- расширение ----------

def test_lost_extension_is_reported_once(tmp_path):
    env = hard_env(tmp_path)
    env.post("/api/session/start", {})
    env.client.get("/api/protection/sites")                       # расширение отозвалось
    env.tick(5)
    assert env.state()["protection"]["strict"]["extension_lost"] is False
    seen = []
    env.manager.bus.subscribe("extension_lost", seen.append)
    env.tick(EXTENSION_TIMEOUT_S + 5)
    assert env.state()["protection"]["strict"]["extension_lost"] is True
    assert len(seen) == 1
    env.tick(10)
    assert len(seen) == 1                                         # не повторяем


def test_never_seen_extension_is_not_an_alarm(tmp_path):
    env = hard_env(tmp_path)
    env.post("/api/session/start", {})
    env.tick(EXTENSION_TIMEOUT_S + 5)
    assert env.state()["protection"]["strict"]["extension_lost"] is False


# ---------- что нельзя править в строгой сессии ----------

def test_strict_session_blocks_bypass_endpoints(tmp_path):
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    env.post("/api/session/start", {})
    bad = [
        ("PUT", "/api/settings", {"mode": "demo", "demo_speed": 1000}),
        ("PUT", "/api/settings", {"session": {"auto_end_after_phone_out_min": 0}}),
        ("PUT", "/api/settings", {"device": {"phone_source": "mock"}}),
        ("PUT", "/api/rules", {"default": "neutral", "rules": []}),
        ("DELETE", "/api/phone/pair", None),
        ("DELETE", "/api/wifi/devices/нет-такого", None),
    ]
    for method, url, body in bad:
        r = env.client.request(method, url, json=body)
        assert r.status_code == 400, (url, r.text)
    assert env.state()["session"] is not None


def test_rules_are_editable_without_session(tmp_path):
    env = hard_env(tmp_path)
    r = env.client.put("/api/rules", json={"default": "neutral", "rules": []})
    assert r.status_code == 200


def test_parallel_password_guessing_respects_limit(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    env = hard_env(tmp_path)
    env.manager.set_password("секрет")
    env.post("/api/session/start", {})

    def guess(i):
        return env.client.post("/api/session/end", json={"password": f"нет{i}"}).status_code

    with ThreadPoolExecutor(20) as pool:
        list(pool.map(guess, range(20)))
    # 5 неверных попыток исчерпали лимит: даже верный пароль сейчас не принимается
    assert env.client.post("/api/session/end", json={"password": "секрет"}).status_code == 400


# ---------- флаг и сторож ----------

def test_pending_resume_gives_remaining_minutes(tmp_path):
    lock = tmp_path / "x.strict"
    lock.write_text(json.dumps({"until": 1000 + 600 + GRACE_S}), encoding="utf-8")
    assert pending_resume(lock, 1000.0) == pytest.approx(10.0)
    assert pending_resume(lock, 1000 + 600 - 10) is None             # осталось меньше полуминуты
    assert pending_resume(tmp_path / "нет.strict", 0) is None
    lock.write_text("мусор", encoding="utf-8")
    assert pending_resume(lock, 0) is None


def test_guard_writes_flag_while_locked_and_removes_it(tmp_path):
    spawned = []
    guard = StrictGuard(tmp_path / "x.strict", ["--port", "9"], 9,
                        spawn=lambda *a: spawned.append(a) or 4242, pid_alive=lambda pid: pid == 4242)
    guard.update(True, 5000.0)
    assert json.loads((tmp_path / "x.strict").read_text())["until"] == 5000.0
    guard.update(True, 5000.0)
    assert len(spawned) == 1                                      # сторож жив — второго не запускаем
    guard.update(False)
    assert not (tmp_path / "x.strict").exists()


def test_guard_respawns_dead_watchdog(tmp_path):
    spawned = []
    guard = StrictGuard(tmp_path / "x.strict", [], 9, spawn=lambda *a: spawned.append(a) or 7,
                        pid_alive=lambda pid: False, retry_s=0)
    guard.update(True, 5000.0)
    guard.update(True, 5000.0)
    assert len(spawned) == 2


def test_manager_feeds_the_guard(tmp_path):
    env = hard_env(tmp_path)
    calls = []

    class Spy:
        def update(self, active, until=0.0):
            calls.append(active)

    env.manager.strict_guard = Spy()
    env.tick(2)
    env.post("/api/session/start", {"length_min": 1})
    env.tick(2)
    env.tick(70)
    assert calls[0] is False and True in calls and calls[-1] is False


def test_watchdog_restarts_when_program_is_gone(tmp_path):
    lock = tmp_path / "x.strict"
    lock.write_text(json.dumps({"until": 1000}))
    started = []
    n = watchdog.run(lock, 9, ["--port", "9"], alive=lambda port: False, start=started.append,
                     now=lambda: 10.0, sleep=lambda s: None, max_loops=28)
    # перезапуски на проверках 2, 14 и 26: после каждого пауза на запуск (30 с = 10 проверок)
    assert n == len(started) == 3 and started[0] == ["--port", "9"]


def test_watchdog_waits_two_checks_before_restart(tmp_path):
    lock = tmp_path / "x.strict"
    lock.write_text(json.dumps({"until": 1000}))
    started = []
    watchdog.run(lock, 9, [], alive=lambda port: False, start=started.append,
                 now=lambda: 10.0, sleep=lambda s: None, max_loops=1)
    assert started == []


def test_watchdog_does_nothing_when_program_is_alive(tmp_path):
    lock = tmp_path / "x.strict"
    lock.write_text(json.dumps({"until": 1000}))
    started = []
    watchdog.run(lock, 9, [], alive=lambda port: True, start=started.append,
                 now=lambda: 10.0, sleep=lambda s: None, max_loops=5)
    assert started == []


@pytest.mark.parametrize("content", [None, "мусор", json.dumps({"until": 5})])
def test_watchdog_leaves_when_no_valid_flag(tmp_path, content):
    lock = tmp_path / "x.strict"
    if content is not None:
        lock.write_text(content, encoding="utf-8")
    started = []
    n = watchdog.run(lock, 9, [], alive=lambda port: False, start=started.append,
                     now=lambda: 10.0, sleep=lambda s: None, max_loops=50)
    assert n == 0 and started == []                               # вышел сам, ничего не запуская
