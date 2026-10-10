"""Блокировка приложений: мягкий и жёсткий режимы, защита от лишних закрытий.
Настоящие процессы не трогаем: вместо psutil — FakeProcesses."""
import pytest

from focusfarm.blocker.apps import CLOSE_GRACE_S, SOFT_REPEAT_S, AppBlocker, NullBlocker
from tests.conftest import Env

BLOCK = ["steam.exe", "telegram.exe"]


class FakeProcesses:
    def __init__(self, running=None, own=(1,)):
        self.procs = dict(running or {})     # pid → имя
        self.own = set(own)
        self.terminated = []
        self.fail = set()
        self.windows = None      # pid → имя программ с окнами; None — все запущенные

    def running(self):
        return list(self.procs.items())

    def protected_pids(self):
        return self.own

    def window_apps(self):
        return list(self.windows.items()) if self.windows is not None else list(self.procs.items())

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


def test_soft_mode_warns_again_and_again_but_never_closes():
    blocker, procs = make({100: "steam.exe"})
    assert types(blocker.update(0, True, False, BLOCK)) == ["block_warning"]
    for t in range(2, SOFT_REPEAT_S, 2):
        assert blocker.update(t, True, False, BLOCK) == []         # между напоминаниями тихо
    for k in (1, 2, 3):                                            # человек убрал, а программа открыта: снова
        assert types(blocker.update(k * SOFT_REPEAT_S, True, False, BLOCK)) == ["block_warning"]
    assert procs.terminated == []


def test_soft_warning_stops_when_app_is_closed():
    blocker, procs = make({100: "steam.exe"})
    blocker.update(0, True, False, BLOCK)
    procs.procs.clear()
    assert blocker.update(SOFT_REPEAT_S, True, False, BLOCK) == []


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

class PoliteProcesses(FakeProcesses):
    """Умеет вежливую просьбу закрыться: программа слушается или упрямится."""

    def __init__(self, *a, obey=True, **kw):
        super().__init__(*a, **kw)
        self.asked = []
        self.obey = obey

    def request_close(self, pid):
        self.asked.append(pid)
        if self.obey:
            self.procs.pop(pid, None)
        return True


def test_polite_close_comes_first_and_spares_obedient_app():
    procs = PoliteProcesses({100: "steam.exe"})
    blocker = AppBlocker(procs, warn_s=10)
    blocker.update(0, True, True, BLOCK)
    blocker.update(10, True, True, BLOCK)                       # срок вышел: просим вежливо
    assert procs.asked == [100] and procs.terminated == []
    events = blocker.update(12, True, True, BLOCK)              # программа закрылась сама
    assert [e["type"] for e in events] == ["app_closed"] and procs.terminated == []


def test_stubborn_app_is_terminated_after_grace():
    procs = PoliteProcesses({100: "steam.exe"}, obey=False)
    blocker = AppBlocker(procs, warn_s=10)
    blocker.update(0, True, True, BLOCK)
    blocker.update(10, True, True, BLOCK)
    blocker.update(14, True, True, BLOCK)
    assert procs.terminated == []                               # ещё ждём
    events = blocker.update(10 + CLOSE_GRACE_S + 1, True, True, BLOCK)
    assert procs.terminated == [100] and [e["type"] for e in events] == ["app_closed"]


def test_warn_seconds_come_from_settings(tmp_path):
    env = Env(tmp_path, overrides={"protection": {"strictness": "hard", "warn_s": 25}})
    env.manager.blocker = AppBlocker(FakeProcesses(), warn_s=10)
    env.post("/api/session/start", {})
    env.tick(2)
    assert env.manager.blocker.warn_s == 25


@pytest.mark.parametrize("bad", [0, 2, 121, "10", True, 1.5])
def test_warn_s_is_validated(tmp_path, bad):
    env = Env(tmp_path)
    assert env.client.put("/api/settings", json={"protection": {"warn_s": bad}}).status_code == 400


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
    env.manager.set_password("секрет")    # в жёстком режиме пауза только с паролем
    env.post("/api/session/start", {})
    env.post("/api/session/pause", {"password": "секрет"})
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


# ---------- белый список ----------

ALLOW = ["code.exe", "chrome.exe"]


def test_whitelist_closes_only_windowed_apps_not_in_list():
    blocker, procs = make({100: "code.exe", 101: "game.exe", 102: "svc.exe"})
    procs.windows = {100: "code.exe", 101: "game.exe"}      # у svc.exe нет окна
    events = blocker.update(0, True, True, [], ALLOW)
    assert [e["process"] for e in events] == ["game.exe"]
    blocker.update(10, True, True, [], ALLOW)
    assert procs.terminated == [101]


def test_whitelist_never_touches_protected_or_own_processes():
    blocker, procs = make({1: "myapp.exe", 200: "explorer.exe", 201: "taskmgr.exe"}, own=(1,))
    assert blocker.update(0, True, True, [], ALLOW) == []
    blocker.update(20, True, True, [], ALLOW)
    assert procs.terminated == []


def test_empty_whitelist_blocks_nothing():
    blocker, procs = make({100: "game.exe"})
    assert blocker.update(0, True, True, [], []) == []
    blocker.update(30, True, True, [], [])
    assert procs.terminated == []


def test_whitelist_soft_mode_warns_repeatedly_without_closing():
    blocker, procs = make({100: "game.exe"})
    assert types(blocker.update(0, True, False, [], ALLOW)) == ["block_warning"]
    assert types(blocker.update(SOFT_REPEAT_S, True, False, [], ALLOW)) == ["block_warning"]
    assert procs.terminated == []


def test_whitelist_is_case_insensitive_and_inactive_session_blocks_nothing():
    blocker, procs = make({100: "code.exe"})
    assert blocker.update(0, True, True, [], ["CODE.EXE"]) == []
    blocker, procs = make({101: "game.exe"})
    assert blocker.update(0, False, True, [], ALLOW) == []
