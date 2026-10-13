"""Звуки-«возвращалки»: эскалация при долгом отвлечении."""
import io
import wave

from focusfarm import nudge_sounds
from focusfarm.clock import FakeClock
from focusfarm.device.output import MockDeviceOutput
from focusfarm.events import EventBus
from focusfarm.reactions import Reactions

CFG = {"enabled": True, "min_gap_s": 5,
       "nudge": {"enabled": True, "after_s": [60, 180, 360, 600], "repeat_s": 120, "volume": 0.5}}


def setup(cfg=None, ok=True):
    clock, bus, played, events = FakeClock(), EventBus(), [], []
    bus.subscribe("nudge", events.append)

    def player(level, volume):
        played.append((level, volume))
        return ok

    r = Reactions(MockDeviceOutput(), clock, bus, cfg or CFG, nudge_player=player)
    return clock, bus, r, played, events


def change(bus, state, prev="FOCUS"):
    bus.publish("state_changed", {"state": state, "prev": prev})


def run(clock, r, seconds, speed=1.0):
    for _ in range(int(seconds)):
        clock.advance(1)
        r.tick(speed)


def test_levels_grow_with_distraction_time():
    clock, bus, r, played, _ = setup()
    change(bus, "DISTRACTED")
    run(clock, r, 59)
    assert played == []
    run(clock, r, 1)
    assert [lvl for lvl, _ in played] == [1]
    run(clock, r, 120)
    run(clock, r, 180)
    run(clock, r, 240)
    assert [lvl for lvl, _ in played] == [1, 2, 3, 4]


def test_volume_is_passed_to_player():
    clock, bus, r, played, _ = setup()
    change(bus, "DISTRACTED")
    run(clock, r, 60)
    assert played == [(1, 0.5)]


def test_returning_to_focus_stops_and_resets():
    clock, bus, r, played, _ = setup()
    change(bus, "DISTRACTED")
    run(clock, r, 100)
    change(bus, "FOCUS", prev="DISTRACTED")
    run(clock, r, 500)
    assert [lvl for lvl, _ in played] == [1]
    change(bus, "DISTRACTED")          # новый эпизод начинается с уровня 1
    run(clock, r, 60)
    assert [lvl for lvl, _ in played] == [1, 1]


def test_pause_and_break_cancel_nudges():
    clock, bus, r, played, _ = setup()
    change(bus, "DISTRACTED")
    run(clock, r, 30)
    change(bus, "PAUSED", prev="DISTRACTED")
    run(clock, r, 600)
    assert played == []


def test_top_level_repeats_but_not_more_often_than_repeat_s():
    clock, bus, r, played, _ = setup()
    change(bus, "DISTRACTED")
    run(clock, r, 600)
    assert [lvl for lvl, _ in played] == [1, 2, 3, 4]
    run(clock, r, 119)
    assert len(played) == 4
    run(clock, r, 1)
    assert [lvl for lvl, _ in played] == [1, 2, 3, 4, 4]


def test_maybe_distracted_does_not_trigger_nudges():
    clock, bus, r, played, _ = setup()
    change(bus, "MAYBE_DISTRACTED")
    run(clock, r, 700)
    assert played == []


def test_disabled_nudges_are_silent():
    cfg = {**CFG, "nudge": {**CFG["nudge"], "enabled": False}}
    clock, bus, r, played, _ = setup(cfg)
    change(bus, "DISTRACTED")
    run(clock, r, 700)
    assert played == []
    clock, bus, r, played, _ = setup({**CFG, "enabled": False})   # общий «звук выключен»
    change(bus, "DISTRACTED")
    run(clock, r, 700)
    assert played == []


def test_demo_speed_scales_thresholds():
    clock, bus, r, played, _ = setup()
    change(bus, "DISTRACTED")
    run(clock, r, 2, speed=30)         # 2 с × 30 = 60 игровых секунд
    assert [lvl for lvl, _ in played] == [1]


def test_event_tells_whether_system_sound_played():
    clock, bus, r, _, events = setup(ok=False)
    change(bus, "DISTRACTED")
    run(clock, r, 60)
    assert events == [{"level": 1, "system": False}]   # браузер сыграет запасной тон


def test_broken_player_does_not_crash():
    clock, bus, r, _, events = setup()

    def boom(level, volume):
        raise OSError("нет звуковой карты")

    r.nudge_player = boom
    change(bus, "DISTRACTED")
    run(clock, r, 60)
    assert "нет звуковой карты" in r.device_error
    assert events[0]["system"] is False


def test_set_sound_cfg_merges_nudge_section():
    _, _, r, _, _ = setup()
    r.set_sound_cfg({"enabled": True, "nudge": {"volume": 0.9}})
    assert r.nudge_cfg["volume"] == 0.9
    assert r.nudge_cfg["after_s"] == [60, 180, 360, 600]   # остальное не потерялось


def test_render_wav_levels_are_valid_and_distinct():
    sizes = []
    for level in range(1, nudge_sounds.LEVELS + 1):
        data = nudge_sounds.render_wav(level, 0.6)
        with wave.open(io.BytesIO(data)) as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2
            sizes.append(w.getnframes())
        peak = max(abs(int.from_bytes(data[i:i + 2], "little", signed=True)) for i in range(44, len(data), 2))
        assert 0 < peak < 32767
    assert len(set(sizes)) == len(sizes)    # у каждого уровня свой рисунок


def test_render_wav_clamps_bad_volume_and_level():
    assert nudge_sounds.render_wav(99, 5.0)       # не падает
    assert nudge_sounds.render_wav(-3, -1.0)


def test_preview_endpoint():
    from fastapi.testclient import TestClient

    from focusfarm.api.server import create_app
    from focusfarm.config import load_settings
    from focusfarm.session.manager import SessionManager
    from focusfarm.storage.db import Database

    played = []
    manager = SessionManager(load_settings(), Database(":memory:"), clock=FakeClock(),
                             nudge_player=lambda level, volume: played.append((level, volume)) or True)
    client = TestClient(create_app(manager, run_loop=False))
    r = client.post("/api/sound/preview", json={"level": 3, "volume": 0.4})
    assert r.status_code == 200 and r.json() == {"played": True, "level": 3}
    assert played == [(3, 0.4)]
