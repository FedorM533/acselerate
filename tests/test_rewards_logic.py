"""Чистая логика заданий и ачивок (без базы и времени)."""
import datetime as dt

import pytest

from focusfarm.game.rewards import (
    ACHIEVEMENTS, DAILY_COIN_CAP, QUESTS, cap_reward, daily_quests, new_achievements, quest_progress,
)

DAY = dt.date(2026, 9, 30)


def test_daily_quests_are_deterministic_and_have_a_focus_quest():
    first = [q["id"] for q in daily_quests(DAY)]
    assert first == [q["id"] for q in daily_quests(DAY)]
    assert len(first) == 3 and len(set(first)) == 3
    assert any(QUESTS[i]["kind"] == "focus_min" for i in first)


def test_quests_vary_between_days():
    sets = {tuple(q["id"] for q in daily_quests(DAY + dt.timedelta(days=d))) for d in range(14)}
    assert len(sets) > 1


@pytest.mark.parametrize("kind", ["focus_min", "releases", "sessions", "clean_min"])
def test_quest_progress_reads_matching_stat(kind):
    quest = next(q for q in QUESTS.values() if q["kind"] == kind)
    stats = {"focus_min": 0, "releases": 0, "sessions": 0, "clean_min": 0}
    assert quest_progress(quest, stats) == 0
    stats[kind] = quest["target"] + 5
    assert quest_progress(quest, stats) == quest["target"]   # прогресс не больше цели


def test_coin_cap_per_day():
    assert cap_reward(already=0, reward=10) == 10
    assert cap_reward(already=DAILY_COIN_CAP - 3, reward=10) == 3
    assert cap_reward(already=DAILY_COIN_CAP, reward=10) == 0


def test_achievements_trigger_once_and_only_when_reached():
    totals = {"fish_total": 0, "species_owned": 0, "best_stars": 0, "streak": 0,
              "focus_total_h": 0, "clean_best_min": 0, "buildings_owned": 0}
    assert new_achievements(totals, set()) == []
    totals["fish_total"] = 1
    got = [a["id"] for a in new_achievements(totals, set())]
    assert got == ["first_fish"]
    assert new_achievements(totals, {"first_fish"}) == []


def test_every_achievement_is_reachable_and_rewards_are_small():
    huge = {"fish_total": 999, "species_owned": 5, "best_stars": 3, "streak": 30,
            "focus_total_h": 999, "clean_best_min": 999, "buildings_owned": 3}
    ids = {a["id"] for a in new_achievements(huge, set())}
    assert ids == {a["id"] for a in ACHIEVEMENTS}
    assert all(a.get("coins", 0) <= 60 for a in ACHIEVEMENTS)
