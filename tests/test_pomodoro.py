"""Pomodoro: перерывы в длинных сессиях, блокировка на время отдыха, отдельная статистика отдыха."""
import pytest

from tests.conftest import Env

# Короткие отрезки, чтобы тест шёл быстро: работа 5 мин, перерыв 1 мин, после 2 рабочих отрезков — 5 мин.
POMODORO = {"enabled": True, "min_session_min": 10, "work_min": 5, "short_break_min": 1,
            "cycles": 2, "long_break_min": 5}


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path, overrides={"pomodoro": POMODORO, "protection": {"targets": "both", "strictness": "hard"}})


def start(env, minutes):
    env.post("/api/session/start", {"length_min": minutes})


def run_until(env, state, limit=4000):
    for _ in range(limit):
        if env.state()["state"] == state:
            return
        env.tick()
    raise AssertionError(f"состояние {state} не наступило, сейчас {env.state()['state']}")


def test_short_session_has_no_breaks(env):
    start(env, 5)
    assert env.state()["session"]["pomodoro"] is None
    env.tick(310)
    assert env.state()["state"] != "BREAK"


def test_break_starts_after_work_block_and_turns_protection_off(env):
    start(env, 20)
    assert env.state()["session"]["pomodoro"]["phase"] == "work"
    assert env.manager.pc_protection_active() and env.manager.phone_protection_active()
    run_until(env, "BREAK")
    snap = env.state()
    assert snap["state_label"] == "Перерыв" and snap["session"]["pomodoro"]["phase"] == "break"
    assert not env.manager.pc_protection_active() and not env.manager.phone_protection_active()
    assert env.client.get("/api/protection/sites").json()["active"] is False
    phone = env.manager.phone_state()
    assert phone["active"] is False and phone["break_left_s"] > 0
    assert 290 <= snap["session"]["elapsed_s"] <= 310        # работа остановилась на 5 минутах


def test_break_time_is_not_work_time_and_protection_returns_after_it(env):
    start(env, 20)
    run_until(env, "BREAK")
    before = env.state()["session"]["elapsed_s"]
    env.tick(30)
    assert env.state()["session"]["elapsed_s"] == before        # время перерыва в длину сессии не входит
    run_until(env, "FOCUS")
    assert env.manager.pc_protection_active() and env.manager.phone_protection_active()
    session = env.state()["session"]
    assert 55 <= session["totals"]["BREAK"] <= 65 and session["pomodoro"]["phase"] == "work"


def test_every_second_break_is_long(env):
    start(env, 20)
    run_until(env, "BREAK")
    first = env.state()["session"]["pomodoro"]
    assert first["break_long"] is False and first["phase_left_s"] <= 60
    run_until(env, "FOCUS")
    run_until(env, "BREAK")
    second = env.state()["session"]["pomodoro"]
    assert second["break_long"] is True and 250 <= second["phase_left_s"] <= 300


def test_no_break_when_session_is_about_to_end(env):
    start(env, 10)
    run_until(env, "BREAK")                  # после 5 минут остаётся ещё 5: перерыв нужен
    run_until(env, "FOCUS")
    env.tick(310)
    assert env.state()["state"] == "IDLE"    # второй отрезок был последним: перерыва перед концом нет


def test_pause_is_not_possible_during_break_but_break_can_be_skipped(env):
    start(env, 20)
    run_until(env, "BREAK")
    r = env.client.post("/api/session/pause", json={})
    assert r.status_code == 400 and "перерыв" in r.json()["detail"].lower()
    r = env.client.post("/api/session/break/skip")
    assert r.status_code == 200 and r.json()["state"] == "FOCUS"
    assert env.client.post("/api/session/break/skip").status_code == 400     # перерыва уже нет


def test_rest_is_a_separate_statistic(env):
    start(env, 20)
    run_until(env, "BREAK")
    run_until(env, "FOCUS")
    stats = env.client.get("/api/stats").json()
    assert stats["rest"]["count"] == 1 and 55 <= stats["rest"]["seconds"] <= 65
    assert "BREAK" not in stats["by_state_s"]
    assert 290 <= stats["focus_s"] <= 330                    # отдых в фокус не засчитан


def test_guard_deadline_accounts_for_future_breaks(env):
    start(env, 20)
    left = env.manager._wall_left_s()
    assert left > 20 * 60 + 3 * 60 - 1                       # 20 мин работы + перерывы (1 + 5 + 1 мин до конца)


def test_settings_validation_rejects_nonsense(env):
    r = env.client.put("/api/settings", json={"pomodoro": {"work_min": 1}, "password": "x"})
    assert r.status_code == 400
