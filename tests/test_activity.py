"""Тесты классификатора и монитора активности."""
import sys

import pytest

from focusfarm.activity.classifier import Classifier, load_rules, save_rules, validate_rules
from focusfarm.activity.fallback import FallbackMonitor
from focusfarm.activity.monitor import ActivityMonitor, SafeMonitor, create_monitor
from focusfarm.config import ConfigError


@pytest.fixture
def clf():
    return Classifier(load_rules())


def test_work_by_process(clf):
    assert clf.classify("Code.exe", "main.py - Visual Studio Code") == "work"


def test_work_by_title(clf):
    assert clf.classify("chrome.exe", "Курс Python — Stepik") == "work"


def test_distraction_by_title_case_insensitive(clf):
    assert clf.classify("chrome.exe", "Котики - YouTube") == "distraction"
    assert clf.classify("firefox.exe", "Новости | ВКонтакте") == "distraction"


def test_distraction_by_process(clf):
    assert clf.classify("Telegram.exe", "") == "distraction"


def test_default_is_neutral(clf):
    assert clf.classify("explorer.exe", "Загрузки") == "neutral"
    assert clf.classify("unknown", "") == "neutral"


def test_first_match_wins():
    clf = Classifier({"default": "neutral", "rules": [
        {"category": "work", "title_contains": ["youtube"]},
        {"category": "distraction", "title_contains": ["youtube"]},
    ]})
    assert clf.classify("chrome.exe", "Лекция по матану - YouTube") == "work"


def test_process_rule_is_exact_not_substring(clf):
    # «mycode.exe» не должен совпасть с «code.exe»
    assert clf.classify("mycode.exe", "") == "neutral"


def test_invalid_category_rejected():
    with pytest.raises(ConfigError):
        validate_rules({"rules": [{"category": "fun", "process": ["a.exe"]}]})


def test_rule_without_lists_rejected():
    with pytest.raises(ConfigError):
        validate_rules({"rules": [{"category": "work"}]})


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "rules.yaml"
    save_rules({"default": "work", "rules": [{"category": "distraction", "process": ["Game.EXE"]}]}, path)
    data = load_rules(path)
    assert data["default"] == "work"
    assert data["rules"][0]["process"] == ["game.exe"]


def test_fallback_monitor():
    s = FallbackMonitor().sample()
    assert s.process_name == "unknown" and s.idle_seconds == 0
    assert FallbackMonitor.available is False


def test_safe_monitor_swallows_errors():
    class Broken(ActivityMonitor):
        def sample(self):
            raise OSError("нет доступа")

    safe = SafeMonitor(Broken())
    assert safe.sample().process_name == "unknown"
    assert "нет доступа" in safe.last_error


@pytest.mark.skipif(sys.platform != "win32", reason="только Windows")
def test_windows_monitor_works():
    monitor = create_monitor()
    assert monitor.name == "windows"
    s = monitor.sample()
    assert s.idle_seconds >= 0 and isinstance(s.process_name, str)
