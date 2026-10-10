"""Блокировка сайтов: что отдаём расширению браузера и когда."""
import pytest

from focusfarm.activity.classifier import Classifier, normalize_domain, validate_rules
from focusfarm.config import ConfigError
from focusfarm.session.manager import EXTENSION_TIMEOUT_S
from tests.conftest import Env

RULES = {"default": "neutral", "rules": [
    {"category": "work", "domains": ["moodle.org"]},
    {"category": "distraction", "domains": ["YouTube.com", "https://www.vk.com/feed", "youtube.com"]},
]}


def site_env(tmp_path, strictness="hard", targets="pc"):
    env = Env(tmp_path, overrides={"protection": {"strictness": strictness, "targets": targets}})
    env.manager.classifier.set_rules(RULES)
    return env


def sites(env):
    r = env.client.get("/api/protection/sites")
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize("raw,expected", [
    ("YouTube.com", "youtube.com"),
    ("https://www.vk.com/feed?x=1", "vk.com"),
    ("http://localhost:8080/path", "localhost"),
    ("  .twitch.tv. ", "twitch.tv"),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_rules_accept_domains_normalize_and_dedupe():
    rules = validate_rules(RULES)
    assert rules["rules"][1]["domains"] == ["youtube.com", "vk.com"]


def test_rule_with_only_empty_domains_is_rejected():
    with pytest.raises(ConfigError):
        validate_rules({"rules": [{"category": "distraction", "domains": ["", "  "]}]})
    with pytest.raises(ConfigError):
        validate_rules({"rules": [{"category": "distraction", "domains": "youtube.com"}]})


def test_domains_do_not_change_window_classification():
    clf = Classifier(RULES)
    assert clf.classify("chrome.exe", "YouTube - Google Chrome") == "neutral"


def test_default_rules_file_has_sites():
    from focusfarm.activity.classifier import load_rules
    domains = [d for r in load_rules()["rules"] for d in r.get("domains", [])]
    assert "youtube.com" in domains


def test_no_session_means_not_active(tmp_path):
    data = sites(site_env(tmp_path))
    assert data["active"] is False
    assert data["domains"] == ["youtube.com", "vk.com"]       # только отвлечения, не «работа»


def test_active_during_session_with_mode_and_time(tmp_path):
    env = site_env(tmp_path)
    env.post("/api/session/start", {"length_min": 25})
    data = sites(env)
    assert data["active"] is True and data["hard"] is True
    assert data["remaining_s"] == pytest.approx(25 * 60)


def test_soft_mode_is_reported(tmp_path):
    env = site_env(tmp_path, strictness="soft")
    env.post("/api/session/start", {})
    assert sites(env)["hard"] is False


def test_pause_turns_site_blocking_off(tmp_path):
    env = site_env(tmp_path)
    env.post("/api/session/start", {})
    env.post("/api/session/pause")
    assert sites(env)["active"] is False
    env.post("/api/session/resume")
    assert sites(env)["active"] is True


@pytest.mark.parametrize("targets,active", [("pc", True), ("both", True), ("phone", False)])
def test_targets_decide_site_blocking(tmp_path, targets, active):
    env = site_env(tmp_path, targets=targets)
    env.post("/api/session/start", {})
    assert sites(env)["active"] is active


def test_extension_connection_status(tmp_path):
    env = site_env(tmp_path)
    assert env.state()["protection"]["extension_connected"] is False
    sites(env)                                                 # расширение «позвонило»
    assert env.state()["protection"]["extension_connected"] is True
    env.clock.advance(EXTENSION_TIMEOUT_S + 1)                 # и замолчало
    assert env.state()["protection"]["extension_connected"] is False
