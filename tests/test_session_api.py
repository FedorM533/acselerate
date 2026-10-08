"""Фаза 4: сессия, хранение, реакции, REST и WebSocket."""
from focusfarm.sensors.phone import MockPhoneSensor
from focusfarm.session.state_machine import DISTRACTED, FOCUS, IDLE, PHONE_OUT


def test_full_cycle_through_api(make_env):
    """Положить телефон → фокус → отвлечение → сорняк → возврат → урожай."""
    env = make_env(docked=False)
    device = env.manager.device
    assert env.state()["state"] == IDLE

    # 1. Кладём (виртуальный) телефон — сессия стартует сама.
    env.post("/api/dev/phone", {"docked": True})
    env.tick()
    s = env.state()
    assert s["state"] == FOCUS and s["session"] is not None
    assert device.led == "GREEN" and "SOUND 4" in device.log

    # 2. Работаем 5 минут — редис растёт.
    env.tick(300)
    plot = next(p for p in env.state()["farm"]["plots"] if p["active"])
    assert plot["crop"] == "guppy" and plot["stage"] == "young"

    # 3. Открыли YouTube → «кажется, отвлёкся» → «отвлёкся».
    env.monitor.use("chrome.exe", "Котики - YouTube")
    env.tick(2)
    assert env.state()["state"] == "MAYBE_DISTRACTED" and device.led == "YELLOW"
    env.tick(30)
    assert env.state()["state"] == DISTRACTED and device.led == "RED"
    assert "SOUND 2" in device.log

    # 4. Минута отвлечения → сорняк.
    env.tick(60)
    farm = env.state()["farm"]
    weeds = [p for p in farm["plots"] if p["weeds"]]
    assert len(weeds) == 1

    # 5. Вернулись к работе → через recover_s снова FOCUS.
    env.monitor.use("code.exe", "main.py")
    env.tick(6)
    assert env.state()["state"] == FOCUS

    # 6. После 5 минут фокуса можно прополоть.
    env.post("/api/farm/weed", {"x": weeds[0]["x"], "y": weeds[0]["y"]})
    assert not any(p["weeds"] for p in env.state()["farm"]["plots"])

    # 7. Дорастили — урожай.
    env.tick(300)
    plot = next(p for p in env.state()["farm"]["plots"] if p["active"])
    assert plot["ripe"] and "SOUND 3" in device.log
    result = env.post("/api/farm/harvest", {"x": plot["x"], "y": plot["y"]}).json()
    assert result["coins"] == 5 and result["stars"] == 2   # 1 эпизод отвлечения → ★★
    assert env.state()["farm"]["coins"] == 5

    # 8. Завершаем, смотрим статистику.
    env.post("/api/session/end")
    assert env.state()["state"] == IDLE and device.led == "OFF"
    stats = env.client.get("/api/stats?range=day").json()
    assert stats["sessions"] == 1
    assert stats["distractions"] == 1
    assert stats["focus_s"] >= 600
    assert stats["top_processes"][0]["name"] == "chrome.exe"
    states = [seg["state"] for seg in stats["timeline"]["segments"]]
    assert states == ["FOCUS", "MAYBE_DISTRACTED", "DISTRACTED", "FOCUS"]


def test_window_titles_never_saved(env):
    env.monitor.use("chrome.exe", "Секретный заголовок - YouTube")
    env.post("/api/session/start", {})
    env.tick(40)
    env.post("/api/session/end")
    dump = "\n".join(env.db.conn.iterdump())
    assert "Секретный" not in dump and "YouTube" not in dump
    assert "chrome.exe" in dump


def test_manual_start_with_plot_and_crop(env):
    env.manager.game.coins = 30
    env.post("/api/shop/buy", {"item": "crop:goldfish"})
    s = env.post("/api/session/start", {"plot": [2, 1], "crop": "goldfish", "length_min": 25}).json()
    assert s["session"]["plot"] == [2, 1]
    assert s["session"]["planned_s"] == 1500


def test_start_twice_is_error(env):
    env.post("/api/session/start", {})
    r = env.post("/api/session/start", {}, ok=False)
    assert r.status_code == 400 and "уже идёт" in r.json()["detail"]


def test_pause_and_resume(env):
    env.post("/api/session/start", {})
    env.post("/api/session/pause")
    env.tick(10)
    s = env.state()
    assert s["state"] == "PAUSED" and s["device"]["led"] == "BLUE"
    assert s["session"]["elapsed_s"] == 0          # пауза не съедает время сессии
    env.post("/api/session/resume")
    assert env.state()["state"] == FOCUS


def test_notebook_mode(env):
    env.post("/api/session/start", {})
    env.monitor.idle = 1000
    env.post("/api/session/notebook", {"on": True})
    env.tick(5)
    assert env.state()["state"] == "NOTEBOOK"


def test_phone_out_blinks_and_sound_once(make_env):
    env = make_env(docked=False)
    env.post("/api/dev/phone", {"docked": True})
    env.tick()
    env.post("/api/dev/phone", {"docked": False})
    env.tick(40)
    assert env.state()["state"] == PHONE_OUT
    assert env.manager.device.led == "BLINK_RED"
    assert env.manager.device.log.count("SOUND 1") == 1


def test_auto_end_after_phone_out(make_env):
    env = make_env(docked=False)
    env.post("/api/dev/phone", {"docked": True})
    env.tick()
    env.post("/api/dev/phone", {"docked": False})
    env.tick(10 * 60 + 1)
    s = env.state()
    assert s["state"] == IDLE and "телефон" in s["message"]


def test_auto_end_when_time_is_up(env):
    env.post("/api/session/start", {"length_min": 1})
    env.tick(61)
    s = env.state()
    assert s["state"] == IDLE and "Отдохни" in s["message"]


def test_demo_speed_accelerates_growth(make_env):
    env = make_env(mode="demo", overrides={"demo_speed": 30})
    env.post("/api/session/start", {})
    env.tick(20)                       # 20 с × 30 = 600 с = редис готов
    plot = next(p for p in env.state()["farm"]["plots"] if p["active"])
    assert plot["ripe"]
    assert env.state()["speed"] == 30


def test_dev_endpoints_forbidden_in_normal_mode(make_env):
    env = make_env(mode="normal")
    assert env.post("/api/dev/phone", {"docked": True}, ok=False).status_code == 403
    assert env.post("/api/dev/category", {"category": "work"}, ok=False).status_code == 403


def test_forced_category(env):
    env.post("/api/session/start", {})
    env.post("/api/dev/category", {"category": "distraction"})
    env.tick(31)
    assert env.state()["state"] == DISTRACTED
    env.post("/api/dev/category", {"category": None})
    env.tick(6)
    assert env.state()["state"] == FOCUS


def test_farm_survives_restart(tmp_path, env):
    db_path = tmp_path / "farm.db"
    from focusfarm.api.server import build_manager
    m1 = build_manager(db_path, cli_overrides={"mode": "dev"}, clock=env.clock, monitor=env.monitor,
                       phone=MockPhoneSensor(docked=True))
    m1.start_session()
    for _ in range(100):
        env.clock.advance(1)
        m1.tick()
    m1.db.conn.close()
    m2 = build_manager(db_path, cli_overrides={"mode": "dev"}, clock=env.clock, monitor=env.monitor,
                       phone=MockPhoneSensor(docked=True))
    assert m2.game.plot(0, 0).progress_s == 100
    assert m2.db.last_session()["end_reason"] == "crash"


def test_schema_version():
    from focusfarm.storage.db import MIGRATIONS, Database
    db = Database(":memory:")
    assert db.schema_version() == len(MIGRATIONS)
    db.migrate()   # повторный запуск ничего не ломает
    assert db.schema_version() == len(MIGRATIONS)


def test_settings_put_and_validation(env):
    r = env.client.put("/api/settings", json={"thresholds": {"recover_s": 10}})
    assert r.status_code == 200 and r.json()["thresholds"]["recover_s"] == 10
    assert env.manager.settings["thresholds"]["recover_s"] == 10
    r = env.client.put("/api/settings", json={"thresholds": {"recover_s": -5}})
    assert r.status_code == 400
    r = env.client.put("/api/settings", json={"server": {"port": 1}})
    assert r.status_code == 400


def test_sound_can_be_disabled(env):
    env.client.put("/api/settings", json={"sound": {"enabled": False}})
    env.post("/api/session/start", {})
    assert not any(c.startswith("SOUND") for c in env.manager.device.log)


def test_rules_put(env, tmp_path):
    rules = env.client.get("/api/rules").json()
    rules["rules"].insert(0, {"category": "distraction", "process": ["game.exe"]})
    r = env.client.put("/api/rules", json=rules)
    assert r.status_code == 200
    assert (tmp_path / "rules.yaml").exists()
    assert env.manager.classifier.classify("GAME.exe") == "distraction"
    bad = env.client.put("/api/rules", json={"rules": [{"category": "fun", "process": ["x"]}]})
    assert bad.status_code == 400


def test_ports_endpoint(env):
    assert isinstance(env.client.get("/api/ports").json(), list)


def test_websocket_sends_state(env):
    with env.client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert data["state"] == IDLE and "farm" in data and data["events"] == []


def test_events_table_filled(env):
    env.post("/api/session/start", {})
    env.monitor.use("telegram.exe")
    env.tick(40)
    rows = env.db.conn.execute("SELECT state, category, process_name FROM events").fetchall()
    assert [tuple(r) for r in rows][-1] == ("DISTRACTED", "distraction", "telegram.exe")


def test_week_stats_and_days(env):
    env.post("/api/session/start", {})
    env.tick(120)
    env.post("/api/session/end")
    week = env.client.get("/api/stats?range=week").json()
    assert len(week["days"]) == 7
    assert week["days"][-1]["focus_min"] == 2
    assert env.client.get("/api/stats?range=year").status_code == 400


def test_forced_category_not_blamed_on_real_process(env):
    env.monitor.use("cmd.exe")
    env.post("/api/session/start", {})
    env.post("/api/dev/category", {"category": "distraction"})
    env.tick(40)
    top = env.client.get("/api/stats").json()["top_processes"]
    assert top[0]["name"] == "(панель разработчика)"
