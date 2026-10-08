"""Тесты игровой логики: все правила раздела 9.2 ТЗ."""
import datetime as dt
import random

import pytest

from focusfarm.game.crops import load_crops, stage_for
from focusfarm.game.engine import GameEngine, GameError, quality_for
from focusfarm.session.state_machine import (
    DISTRACTED, FOCUS, MAYBE_DISTRACTED, NOTEBOOK, PAUSED, PHONE_OUT,
)

TODAY = dt.date(2026, 9, 30)


@pytest.fixture
def game():
    return GameEngine(rng=random.Random(1))


def ticks(game, state, seconds, today=TODAY):
    events = []
    for _ in range(int(seconds)):
        events += game.tick(state, 1, today)
    return events


# ---------- растения ----------

def test_crop_table():
    crops = load_crops()
    assert crops["guppy"].focus_min == 10 and crops["guppy"].price == 0
    assert crops["arowana"].coins == 80 and crops["arowana"].price == 300


def test_stages():
    assert [stage_for(p) for p in (0, 0.2, 0.5, 0.8, 1.0)] == \
        ["seed", "sprout", "young", "adult", "ready"]


def test_start_grid_3x3_and_only_radish_unlocked(game):
    assert game.size == 3 and len(game.plots) == 9
    assert game.unlocks == {"guppy"}


def test_default_crop_closest_to_length(game):
    game.unlocks |= {"goldfish", "koi"}
    assert game.default_crop(25) == "goldfish"
    assert game.default_crop(35) == "koi"
    assert game.default_crop(5) == "guppy"


def test_begin_session_plants_on_empty_plot(game):
    pos = game.begin_session(length_min=25)
    assert pos == (0, 0)
    assert game.plot(0, 0).crop_id == "guppy"


def test_cannot_plant_locked_crop(game):
    with pytest.raises(GameError):
        game.begin_session((0, 0), "arowana")


# ---------- рост ----------

def test_grows_only_in_focus_and_notebook(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, FOCUS, 10)
    ticks(game, NOTEBOOK, 10)
    for state in (MAYBE_DISTRACTED, DISTRACTED, PHONE_OUT, PAUSED):
        ticks(game, state, 10)
    assert game.plot(0, 0).progress_s == 20


def test_ripens_and_emits_event(game):
    game.begin_session((0, 0), "guppy")
    events = ticks(game, FOCUS, 600)
    assert game.is_ripe(0, 0)
    assert events == [{"type": "crop_ready", "x": 0, "y": 0, "crop": "guppy"}]


def test_progress_kept_between_sessions(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, FOCUS, 100)
    game.end_session()
    assert game.default_plot() == (0, 0)   # продолжаем недоросшее
    game.begin_session()
    ticks(game, FOCUS, 50)
    assert game.plot(0, 0).progress_s == 150


# ---------- сорняки ----------

def test_weed_every_60s_of_continuous_distraction(game):
    game.begin_session((0, 0), "guppy")
    assert ticks(game, DISTRACTED, 59) == []
    events = ticks(game, PHONE_OUT, 1)
    assert events == [{"type": "weed", "x": 0, "y": 0}]


def test_interrupted_distraction_restarts_weed_timer(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, DISTRACTED, 50)
    ticks(game, MAYBE_DISTRACTED, 1)
    assert ticks(game, DISTRACTED, 50) == []


def test_weeds_only_on_plots_with_plants_max_3(game):
    for pos in [(0, 0), (1, 1), (2, 2), (0, 2)]:
        game.plots[pos].crop_id = "guppy"
    game.active_plot = (0, 0)
    ticks(game, DISTRACTED, 600)
    assert game.weeds_total() == 3
    for pos, p in game.plots.items():
        if p.weeds:
            assert p.crop_id is not None


def test_weeding_requires_5_min_focus(game):
    game.begin_session((0, 0), "guppy")
    game.plots[(1, 0)].crop_id = "guppy"
    game.plots[(1, 0)].weeds = 1
    ticks(game, FOCUS, 299)
    with pytest.raises(GameError):
        game.weed(1, 0)
    ticks(game, FOCUS, 1)
    game.weed(1, 0)
    assert game.plot(1, 0).weeds == 0


def test_weed_on_neighbour_reduces_harvest_by_20_percent(game):
    game.begin_session((1, 1), "guppy")
    game.plots[(1, 1)].quality_hits = 1        # ★★ ×1.0 → 5 монет
    game.plots[(1, 1)].progress_s = 600
    game.plots[(2, 1)].crop_id = "guppy"
    game.plots[(2, 1)].weeds = 1
    assert game.harvest_value(1, 1)["coins"] == 4   # floor(5 × 0.8)


def test_far_weed_does_not_reduce_harvest(game):
    game.plots[(0, 0)] = game.plots[(0, 0)].__class__("guppy", 600, 0, 1)
    game.plots[(2, 2)].crop_id = "guppy"
    game.plots[(2, 2)].weeds = 1
    assert game.harvest_value(0, 0)["coins"] == 5


# ---------- качество ----------

def test_quality_table():
    assert quality_for(0) == (3, 1.5)
    assert quality_for(1) == (2, 1.0)
    assert quality_for(2) == (2, 1.0)
    assert quality_for(3) == (1, 0.7)


def test_quality_counts_episodes_not_seconds(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, DISTRACTED, 10)
    ticks(game, PHONE_OUT, 10)      # продолжение того же эпизода
    ticks(game, FOCUS, 5)
    ticks(game, DISTRACTED, 5)      # новый эпизод
    assert game.plot(0, 0).quality_hits == 2


# ---------- урожай и монеты ----------

def test_harvest_perfect_quality(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, FOCUS, 600)
    result = game.harvest(0, 0)
    assert result["coins"] == 7 and result["stars"] == 3   # floor(5 × 1.5)
    assert game.coins == 7


def test_harvest_unripe_forbidden(game):
    game.begin_session((0, 0), "guppy")
    with pytest.raises(GameError):
        game.harvest(0, 0)


def test_harvest_active_plot_replants(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, FOCUS, 600)
    game.harvest(0, 0)
    assert game.plot(0, 0).crop_id == "guppy"
    assert game.plot(0, 0).progress_s == 0


def test_plants_never_die(game):
    game.begin_session((0, 0), "guppy")
    ticks(game, FOCUS, 100)
    ticks(game, PHONE_OUT, 10_000)
    assert game.plot(0, 0).crop_id == "guppy"
    assert game.plot(0, 0).progress_s == 100


# ---------- серия и дождь ----------

def test_day_counts_after_25_min(game):
    ticks(game, FOCUS, 25 * 60 - 1)
    assert not game.day_counts(TODAY)
    ticks(game, FOCUS, 1)
    assert game.day_counts(TODAY)


def test_streak_and_rain(game):
    for back in (1, 2):
        game.days[(TODAY - dt.timedelta(days=back)).isoformat()] = 1500
    assert game.streak(TODAY) == 2 and not game.is_raining(TODAY)
    game.days[TODAY.isoformat()] = 1500
    assert game.streak(TODAY) == 3 and game.is_raining(TODAY)


def test_streak_broken_by_gap(game):
    game.days[(TODAY - dt.timedelta(days=1)).isoformat()] = 1500
    game.days[(TODAY - dt.timedelta(days=3)).isoformat()] = 1500
    assert game.streak(TODAY) == 1


def test_rain_speeds_growth_10_percent(game):
    for back in (0, 1, 2):
        game.days[(TODAY - dt.timedelta(days=back)).isoformat()] = 1500
    game.begin_session((0, 0), "guppy")
    ticks(game, FOCUS, 100)
    assert game.plot(0, 0).progress_s == pytest.approx(110)


# ---------- магазин ----------

def test_buy_crop(game):
    game.coins = 30
    game.buy("crop:goldfish")
    assert "goldfish" in game.unlocks and game.coins == 0


def test_buy_without_money_fails(game):
    game.coins = 10
    with pytest.raises(GameError):
        game.buy("crop:goldfish")
    assert game.coins == 10


def test_expansions_in_order(game):
    game.coins = 1000
    with pytest.raises(GameError):
        game.buy("expand_5")
    game.buy("expand_4")
    assert game.size == 4 and len(game.plots) == 16
    game.buy("expand_5")
    assert game.size == 5 and len(game.plots) == 25
    assert game.coins == 300


def test_decor_has_no_game_effect(game):
    game.coins = 20
    game.buy("decor:plants")
    assert "decor:plants" in game.unlocks
    with pytest.raises(GameError):
        game.buy("decor:plants")


# ---------- сохранение ----------

def test_save_and_load_roundtrip(game):
    game.coins = 42
    game.begin_session((1, 2), "guppy")
    ticks(game, FOCUS, 30)
    restored = GameEngine()
    restored.load_dict(game.to_dict())
    assert restored.coins == 42
    assert restored.plot(1, 2).progress_s == 30
    assert restored.days == game.days
