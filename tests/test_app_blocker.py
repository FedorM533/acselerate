"""Блокировка приложений: мягкий и жёсткий режимы, защита от лишних закрытий.
Настоящие процессы не трогаем: вместо psutil — FakeProcesses."""
import pytest

from focusfarm.blocker.apps import AppBlocker, NullBlocker
from tests.conftest import Env

BLOCK = ["steam.exe", "telegram.exe"]


class FakeProcesses:
    def __init__(self, running=None, own=(1,)):
        self.procs = dict(running or {})     # pid → имя
        self.own = set(own)
        self.terminated = []
        self.fail = set()

    def running(self):
        return list(self.procs.items())

    def protected_pids(self):
        return self.own

    def terminate(self, pid):
        if pid in self.fail:
            return False
        self.terminated.append(pid)
        self.procs.pop(pid, None)
        return True


def make(running=None, **kw):
    procs = FakeProcesses(running, **kw)
    return AppBlocker(procs, warn_s=10), procs


def types(events):
    return [e["type"] for e in events]


def test_hard_mode_warns_then_closes_after_deadline():
    blocker, procs = make({100: "steam.exe"})
    events = blocker.update(0, True, True, BLOCK)
    assert types(events) == ["block_warning"] and events[0]["seconds"] == 10
    assert blocker.update(5, True, True, BLOCK) == [] and procs.terminated == []
    events = blocker.update(10, True, True, BLOCK)
    assert types(events) == ["app_closed"] and procs.terminated == [100]


def test_soft_mode_only_warns_once_and_never_closes():
    blocker, procs = make({100: "steam.exe"})
    assert types(blocker.update(0, True, False, BLOCK)) == ["block_warning"]
    for t in range(2, 120, 2):
        assert blocker.update(t, True, False, BLOCK) == []
    assert procs.terminated == []


def test_app_closed_by_user_before_deadline_is_not_killed():
    blocker, procs = make({100: "steam.exe"})
    blocker.update(0, True, True, BLOCK)
    procs.procs.clear()
    assert blocker.update(4, True, True, BLOCK) == []
    assert blocker.update(20, True, True, BLOCK) == [] and procs.terminated == []


def test_inactive_session_or_pause_resets_everything():
    blocker, procs = make({100: "steam.exe"})
    blocker.update(0, True, True, BLOCK)
    assert blocker.update(5, False, True, BLOCK) == []        # пауза / нет сессии
    assert blocker.view(5)["warnings"] == []
    # После возобновления отсчёт 10 секунд начинается заново.
    blocker.update(6, True, True, BLOCK)
    assert blocker.update(12, True, True, BLOCK) == [] and procs.terminated == []
    assert types(blocker.update(16, True, True, BLOCK)) == ["app_closed"]


def test_protected_and_own_processes_are_never_touched():
    blocker, procs = make({1: "steam.exe", 2: "explorer.exe", 3: "python.exe"}, own=(1,))
    names = BLOCK + ["explorer.exe", "python.exe"]
    assert blocker.update(0, True, True, names) == []
    assert blocker.update(60, True, True, names) == []
    assert procs.terminated == []


def test_names_are_case_insensitive_and_grouped():
    blocker, procs = make({100: "telegram.exe", 101: "telegram.exe"})
    events = blocker.update(0, True, True, ["Telegram.EXE"])
    assert types(events) == ["block_warning"]                 # одно предупреждение на имя
    events = blocker.update(10, True, True, ["Telegram.EXE"])
    assert types(events) == ["app_closed"] and sorted(procs.terminated) == [100, 101]


def test_failed_close_is_reported_once():
    blocker, procs = make({100: "steam.exe"})
    procs.fail.add(100)
    blocker.update(0, True, True, BLOCK)
    assert types(blocker.update(10, True, True, BLOCK)) == ["block_failed"]
    assert blocker.update(12, True, True, BLOCK) == []        # не мучаем каждую секунду


def test_empty_blocklist_does_nothing():
    blocker, procs = make({100: "steam.exe"})
    assert blocker.update(0, True, True, []) == []


def test_view_shows_seconds_left():
    blocker, _ = make({100: "steam.exe"})
    blocker.update(0, True, True, BLOCK)
    assert blocker.view(4)["warnings"] == [{"process": "steam.exe", "seconds_left": 6}]


# ---------- через менеджер сессии ----------

def blocker_env(tmp_path, strictness="hard", targets="pc", running=None):
    env = Env(tmp_path, overrides={"protection": {"strictness": strictness, "targets": targets}})
    env.procs = FakeProcesses(running or {200: "steam.exe"})
    env.manager.blocker = AppBlocker(env.procs, warn_s=10)
    # Правила в тестах свои: steam.exe — отвлечение.
    env.manager.classifier.set_rules({"default": "neutral", "rules": [
        {"category": "distraction", "process": ["steam.exe"]}]})
    return env


def test_default_manager_blocker_is_null(env):
    assert isinstance(env.manager.blocker, NullBlocker)


def test_session_hard_mode_closes_blacklisted_app(tmp_path):
    env = blocker_env(tmp_path)
    env.post("/api/session/start", {})
    env.tick(15)
    assert env.procs.terminated == [200]


def test_no_session_means_no_blocking(tmp_path):
    env = blocker_env(tmp_path)
    env.tick(30)
    assert env.procs.terminated == []


def test_pause_stops_blocking(tmp_path):
    env = blocker_env(tmp_path)
    env.post("/api/session/start", {})
    env.post("/api/session/pause")
    env.tick(30)
    assert env.procs.terminated == []


@pytest.mark.parametrize("targets,closed", [("pc", True), ("both", True), ("phone", False)])
def test_targets_decide_whether_pc_is_protected(tmp_path, targets, closed):
    env = blocker_env(tmp_path, targets=targets)
    env.post("/api/session/start", {})
    env.tick(15)
    assert bool(env.procs.terminated) is closed


def test_soft_mode_in_session_never_closes(tmp_path):
    env = blocker_env(tmp_path, strictness="soft")
    env.post("/api/session/start", {})
    env.tick(60)
    assert env.procs.terminated == []


def test_events_reach_the_interface_and_snapshot(tmp_path):
    env = blocker_env(tmp_path)
    env.post("/api/session/start", {})
    env.manager.take_events()
    env.tick(3)
    kinds = [e["type"] for e in env.manager.take_events()]
    assert "block_warning" in kinds
    assert env.state()["protection"]["warnings"][0]["process"] == "steam.exe"


def test_blocker_error_does_not_break_the_session(tmp_path):
    env = blocker_env(tmp_path)

    class Broken:
        def update(self, *args):
            raise RuntimeError("сломался")

        def view(self, now):
            return {"warnings": []}

    env.manager.blocker = Broken()
    env.post("/api/session/start", {})
    env.tick(5)
    assert env.state()["state"] != "IDLE"
