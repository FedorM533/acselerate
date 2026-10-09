"""Задания и ачивки в игре + главное правило: НЕ ОТВЛЕКАТЬ во время работы."""
from focusfarm.game.rewards import QUESTS


def only(env, *ids):
    """Подменяем задания дня, чтобы тест не зависел от даты."""
    env.manager.rewards.quest_picker = lambda day: [QUESTS[i] for i in ids]


def reward_events(env):
    return [e for e in env.manager.take_events() if e["type"] == "reward"]


# ---------- тишина во время работы ----------

def test_nothing_is_announced_or_paid_during_focus(env):
    only(env, "focus20")
    env.post("/api/session/start", {})
    log_before = list(env.manager.device.log)
    env.tick(21 * 60)   # задание «20 минут» выполнено, но мы в фокусе
    assert reward_events(env) == []
    assert env.state()["farm"]["coins"] == 0
    assert env.state()["rewards"]["unseen"] == 0
    assert env.manager.device.log == log_before   # ни звука, ни света на подставке


def test_nothing_is_announced_in_notebook_mode(env):
    only(env, "focus20")
    env.post("/api/session/start", {})
    env.post("/api/session/notebook", {"on": True})
    env.tick(21 * 60)
    assert reward_events(env) == [] and env.state()["farm"]["coins"] == 0


def test_reward_arrives_after_session(env):
    only(env, "focus20")
    env.post("/api/session/start", {})
    env.tick(21 * 60)
    env.post("/api/session/end")
    env.tick(1)
    events = reward_events(env)
    assert [e["id"] for e in events] == ["focus20"]
    assert env.state()["farm"]["coins"] == QUESTS["focus20"]["reward"]
    assert env.state()["rewards"]["unseen"] == 1


def test_reward_arrives_on_pause(env):
    only(env, "focus20")
    env.post("/api/session/start", {})
    env.tick(21 * 60)
    env.post("/api/session/pause")
    env.tick(6)
    assert [e["id"] for e in reward_events(env)] == ["focus20"]


def test_reward_is_paid_only_once(env):
    only(env, "focus20")
    env.post("/api/session/start", {})
    env.tick(21 * 60)
    env.post("/api/session/end")
    env.tick(30)
    coins = env.state()["farm"]["coins"]
    env.manager.take_events()
    env.tick(60)
    assert env.state()["farm"]["coins"] == coins
    assert reward_events(env) == []


def test_rewards_can_be_switched_off(make_env):
    env = make_env(overrides={"rewards": {"enabled": False}})
    only(env, "focus20")
    env.post("/api/session/start", {})
    env.tick(21 * 60)
    env.post("/api/session/end")
    env.tick(10)
    assert reward_events(env) == [] and env.state()["farm"]["coins"] == 0
    assert env.state()["rewards"]["enabled"] is False


# ---------- что считается ----------

def test_practice_session_does_not_count(make_env):
    env = make_env(docked=False)
    only(env, "focus20")
    env.post("/api/session/start", {"without_phone": True})
    env.tick(21 * 60)
    assert env.manager.rewards.day_stats()["focus_min"] == 0


def test_distraction_breaks_clean_session_quest(env):
    only(env, "clean15")
    env.post("/api/session/start", {"length_min": 60})
    env.tick(5 * 60)
    env.monitor.use("chrome.exe", "Котики - YouTube")
    env.tick(60)
    env.monitor.use("code.exe", "main.py")
    env.tick(20 * 60)
    env.post("/api/session/end")
    env.tick(1)
    assert env.manager.rewards.day_stats()["clean_min"] == 0
    assert reward_events(env) == []


def test_daily_cap_limits_quest_coins(env):
    only(env, "focus20", "focus45", "clean15")
    env.manager.rewards.cap = 12
    env.post("/api/session/start", {"length_min": 60})
    env.tick(50 * 60)
    env.post("/api/session/end")
    env.tick(1)
    paid = sum(e["coins"] for e in reward_events(env) if e["kind"] == "quest")
    assert paid == 12


# ---------- ачивки ----------

def test_first_fish_achievement_after_release(env):
    env.post("/api/session/start", {})
    env.tick(601)
    env.post("/api/farm/harvest", {"x": 0, "y": 0, "name": "Рыжик"})
    env.post("/api/session/end")
    env.tick(1)
    ids = [e["id"] for e in reward_events(env)]
    assert "first_fish" in ids
    view = env.client.get("/api/rewards").json()
    assert next(a for a in view["achievements"] if a["id"] == "first_fish")["unlocked"]


def test_mark_seen_clears_badge(env):
    only(env, "focus20")
    env.post("/api/session/start", {})
    env.tick(21 * 60)
    env.post("/api/session/end")
    env.tick(1)
    assert env.state()["rewards"]["unseen"] >= 1
    env.post("/api/rewards/seen")
    assert env.state()["rewards"]["unseen"] == 0


def test_rewards_view_shape(env):
    view = env.client.get("/api/rewards").json()
    assert len(view["quests"]) == 3
    assert {"id", "title", "target", "progress", "done", "reward"} <= set(view["quests"][0])
    assert {"id", "title", "desc", "unlocked"} <= set(view["achievements"][0])


def test_building_reward_unlocks_building(env):
    env.manager.game.unlocks.discard("building:house")
    env.manager.rewards.grant_for_test("fish_5")
    assert "building:house" in env.manager.game.unlocks
