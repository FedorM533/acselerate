"""Настройки режимов защиты: строгость и где защищать."""
import pytest

from focusfarm.config import ConfigError, load_settings


def test_defaults_are_soft_and_pc_only():
    protection = load_settings()["protection"]
    assert protection == {"strictness": "soft", "targets": "pc", "list_mode": "blacklist",
                          "allow_apps": [], "allow_sites": [], "warn_s": 10}


@pytest.mark.parametrize("patch", [
    {"list_mode": "greylist"}, {"allow_apps": "code.exe"}, {"allow_sites": [1, 2]},
])
def test_bad_list_settings_are_rejected(patch):
    with pytest.raises(ConfigError):
        load_settings(overrides={"protection": patch})


def test_whitelist_is_editable_through_api(env):
    patch = {"list_mode": "whitelist", "allow_apps": ["code.exe"], "allow_sites": ["wikipedia.org"]}
    r = env.client.put("/api/settings", json={"protection": patch})
    assert r.status_code == 200
    saved = env.client.get("/api/settings").json()["protection"]
    assert saved["list_mode"] == "whitelist" and saved["allow_apps"] == ["code.exe"]


@pytest.mark.parametrize("strictness", ["soft", "hard"])
@pytest.mark.parametrize("targets", ["pc", "phone", "both"])
def test_valid_combinations_are_accepted(strictness, targets):
    s = load_settings(overrides={"protection": {"strictness": strictness, "targets": targets}})
    assert s["protection"]["strictness"] == strictness and s["protection"]["targets"] == targets


@pytest.mark.parametrize("patch", [
    {"strictness": "extreme"}, {"strictness": None}, {"targets": "tv"}, {"targets": ""},
])
def test_bad_values_are_rejected(patch):
    with pytest.raises(ConfigError):
        load_settings(overrides={"protection": patch})


def test_protection_is_editable_through_api(env):
    r = env.client.put("/api/settings", json={"protection": {"strictness": "hard", "targets": "both"}})
    assert r.status_code == 200
    assert r.json()["protection"]["strictness"] == "hard" and r.json()["protection"]["targets"] == "both"
    # Выбор переживает чтение настроек заново.
    assert env.client.get("/api/settings").json()["protection"]["targets"] == "both"


def test_api_rejects_bad_protection_without_saving(env):
    assert env.client.put("/api/settings", json={"protection": {"strictness": "extreme"}}).status_code == 400
    assert env.client.put("/api/settings", json={"protection": "hard"}).status_code == 400
    assert env.client.get("/api/settings").json()["protection"]["strictness"] == "soft"
