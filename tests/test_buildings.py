"""Здания в пруду: домик, мостик, маяк — только красота, покупаются за монеты."""
import datetime as dt
import random

import pytest

from focusfarm.game.engine import GameEngine, GameError


@pytest.fixture
def game():
    return GameEngine(rng=random.Random(1))


def test_shop_lists_buildings(game):
    items = {i["item"]: i for i in game.shop_items()}
    for key in ("building:house", "building:bridge", "building:lighthouse"):
        assert items[key]["kind"] == "building" and not items[key]["owned"]


def test_buy_building(game):
    game.coins = 100
    game.buy("building:house")
    assert "building:house" in game.unlocks and game.coins < 100
    with pytest.raises(GameError):
        game.buy("building:house")


def test_cannot_buy_without_money(game):
    game.coins = 1
    with pytest.raises(GameError):
        game.buy("building:lighthouse")


def test_buildings_have_no_effect_on_growth(game):
    game.coins = 1000
    for b in ("house", "bridge", "lighthouse"):
        game.buy(f"building:{b}")
    game.begin_session((0, 0), "guppy")
    for _ in range(100):
        game.tick("FOCUS", 1, dt.date(2026, 9, 30))
    assert game.plot(0, 0).progress_s == pytest.approx(100)


def test_buildings_in_snapshot_and_save(env):
    env.manager.game.coins = 500
    env.post("/api/shop/buy", {"item": "building:bridge"})
    assert env.state()["farm"]["buildings"] == ["bridge"]
    restored = GameEngine()
    restored.load_dict(env.manager.game.to_dict())
    assert "building:bridge" in restored.unlocks
