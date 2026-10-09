"""Коллекция рыбок: хранение, имена, миграция базы, настройки пруда."""
import sqlite3

import pytest

from focusfarm.config import ConfigError, load_settings
from focusfarm.storage.db import MIGRATIONS, Database


def ripe_guppy(env):
    env.post("/api/session/start", {})
    env.tick(601)   # гуппи растёт 10 минут


def test_migration_from_v1_keeps_old_data(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0])
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version VALUES (1)")
    conn.execute("INSERT INTO wallet VALUES (1, 77)")
    conn.commit()
    conn.close()
    db = Database(path)
    assert db.schema_version() == len(MIGRATIONS) >= 2
    assert db.load_farm()["coins"] == 77
    assert db.list_fish() == []


def test_harvest_saves_named_fish(env):
    ripe_guppy(env)
    r = env.post("/api/farm/harvest", {"x": 0, "y": 0, "name": "  Бублик  "}).json()
    assert r["coins"] > 0
    fish = env.client.get("/api/collection").json()["fish"]
    assert len(fish) == 1
    assert fish[0]["name"] == "Бублик" and fish[0]["fish_id"] == "guppy" and fish[0]["stars"] == 3


def test_harvest_without_name_is_allowed(env):
    ripe_guppy(env)
    env.post("/api/farm/harvest", {"x": 0, "y": 0})
    assert env.client.get("/api/collection").json()["fish"][0]["name"] == ""


@pytest.mark.parametrize("raw,clean", [
    ("x" * 50, "x" * 20),
    ("a\u0000b\nc", "abc"),
    ("  много   пробелов  ", "много пробелов"),
    ("<b>hi</b>", "<b>hi</b>"),   # хранится как текст; интерфейс экранирует
])
def test_name_is_sanitized(env, raw, clean):
    ripe_guppy(env)
    env.post("/api/farm/harvest", {"x": 0, "y": 0, "name": raw})
    assert env.client.get("/api/collection").json()["fish"][0]["name"] == clean


def test_species_summary(env):
    ripe_guppy(env)
    env.post("/api/farm/harvest", {"x": 0, "y": 0})
    species = {s["id"]: s for s in env.client.get("/api/collection").json()["species"]}
    assert species["guppy"]["count"] == 1 and species["guppy"]["best_stars"] == 3
    assert species["arowana"]["count"] == 0 and not species["arowana"]["unlocked"]


def test_practice_session_is_flagged_and_gives_no_fish(make_env):
    env = make_env(docked=False)
    env.post("/api/session/start", {"without_phone": True})
    env.tick(30)
    assert env.manager.db.last_session()["practice"] == 1
    assert env.client.get("/api/collection").json()["fish"] == []


@pytest.mark.parametrize("value", [0, 12, 60])
def test_pond_fish_max_accepts_range(value):
    assert load_settings(overrides={"ui": {"pond_fish_max": value}})["ui"]["pond_fish_max"] == value


@pytest.mark.parametrize("value", [-1, 61, "много", 2.5, None])
def test_pond_fish_max_rejects_bad_values(value):
    with pytest.raises(ConfigError):
        load_settings(overrides={"ui": {"pond_fish_max": value}})


@pytest.mark.parametrize("body", [{"ui": 5}, {"ui": None}, {"rewards": "on"}])
def test_bad_section_types_give_400_not_500(env, body):
    assert env.client.put("/api/settings", json=body).status_code == 400


def test_ui_settings_editable_through_api(env):
    r = env.client.put("/api/settings", json={"ui": {"pond_fish_max": 5}})
    assert r.status_code == 200 and r.json()["ui"]["pond_fish_max"] == 5
    assert env.client.put("/api/settings", json={"ui": {"pond_fish_max": 999}}).status_code == 400
