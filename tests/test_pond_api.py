"""Пруд поверх сессий: открытия, причина прерывания, итог сессии."""
from focusfarm.session.state_machine import IDLE


def run_session(env, minutes, end="manual", reason=None, note=None):
    env.post("/api/session/start", {"length_min": minutes})
    env.tick(minutes * 60 if end == "time_up" else minutes * 60 - 1)
    if end != "time_up":
        body = {"reason_code": reason, "reason_note": note} if reason else {}
        env.post("/api/session/end", body)
    assert env.state()["state"] == IDLE
    return env.client.get("/api/pond/result").json()


def test_config_has_everything_for_client(env):
    cfg = env.client.get("/api/pond/config").json()
    assert {"progression", "visual", "strings", "reasons", "palette"} <= set(cfg)
    assert len(cfg["progression"]["unlocks"]) == 16
    assert "_rules" not in cfg["strings"]


def test_new_pond_is_empty(env):
    s = env.client.get("/api/pond").json()
    assert s["unlocked"] == [] and s["unseen"] == [] and s["journal"] == {"focus_min": 0, "days": 0}


def test_completed_45_gives_54_and_first_unlocks(env):
    r = run_session(env, 45, end="time_up")
    assert r["status"] == "completed" and r["base"] == 45 and r["bonus"] == 9
    s = env.client.get("/api/pond").json()
    assert [u["id"] for u in s["unlocked"]] == ["first_pad", "reeds"]
    assert s["unlocked"][0]["date"] == "2026-09-30" and s["unseen"] == ["first_pad", "reeds"]
    assert "drops" not in s and "drops" not in s["journal"]      # капли не показываем


def test_interrupt_with_reason_gives_bonus_and_golden(env):
    r = run_session(env, 25, reason="urgent")
    assert r["status"] == "interrupted_with_reason" and r["base"] == 24 and r["bonus"] == 3 and r["golden"] == 3


def test_interrupt_without_reason_only_base(env):
    r = run_session(env, 25)
    assert r["status"] == "interrupted_no_reason" and r["bonus"] == 0 and r["golden"] == 0


def test_unknown_reason_is_ignored(env):
    r = run_session(env, 25, reason="hacker")
    assert r["status"] == "interrupted_no_reason"


def test_other_note_is_cut_and_stored_locally(env):
    run_session(env, 25, reason="other", note="x" * 200)
    row = env.db.last_session()
    assert row["reason_code"] == "other" and len(row["reason_note"]) == 80
    run_session(env, 25, reason="urgent", note="не должна сохраниться")
    assert env.db.last_session()["reason_note"] is None


def test_too_short_session(env):
    env.post("/api/session/start", {})
    env.tick(60)
    env.post("/api/session/end", {"reason_code": "urgent"})
    r = env.client.get("/api/pond/result").json()
    assert r["status"] == "too_short" and r["base"] == 0 and r["golden"] == 0


def test_practice_session_does_not_feed_the_pond(make_env):
    env = make_env(docked=False)
    env.post("/api/session/start", {"without_phone": True, "length_min": 30})
    env.tick(30 * 60)
    s = env.client.get("/api/pond").json()
    assert s["journal"]["focus_min"] == 0 and s["unlocked"] == []


def test_seen_and_never_shrinks(env):
    run_session(env, 45, end="time_up")
    env.client.get("/api/pond")
    env.post("/api/pond/seen", {"ids": ["first_pad"]})
    assert env.client.get("/api/pond").json()["unseen"] == ["reeds"]
    env.db.conn.execute("DELETE FROM sessions")      # журнал пропал — открытое остаётся
    assert len(env.client.get("/api/pond").json()["unlocked"]) == 2


def test_pomodoro_and_events_carry_session_id(env):
    env.post("/api/session/start", {})
    env.post("/api/session/end")
    events = env.manager.take_events()
    assert any(e.get("type") == "session_ended" and e.get("session_id") for e in events)
