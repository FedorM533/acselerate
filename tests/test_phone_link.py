"""Связь с телефоном по Wi-Fi: сопряжение, токены, WebSocket, защита.
Настоящую сеть не трогаем: приложение для телефона проверяем через TestClient."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from focusfarm.api.server import create_app
from focusfarm.config import ConfigError, load_settings
from focusfarm.phone import lan
from focusfarm.phone.hub import MAX_DEVICES, PAIR_MAX_FAILS, PAIR_TTL_S, PairingError, hash_token
from tests.conftest import Env


class FakeLan:
    error = ""

    def sync(self, settings): ...
    def stop(self): ...
    def address(self): return ("192.168.1.5", 8766)


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(lan, "SEND_POLL_S", 0.02)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path, overrides={"protection": {"targets": "both"}})


@pytest.fixture
def phone_client(env):
    """Приложение для телефона без проверки адреса клиента (TestClient не из частной сети)."""
    return TestClient(lan.build_phone_app(env.manager, allow_client=lambda host: True))


def pair(env, name="Pixel"):
    secret, _ = env.manager.phones.open_pairing()
    return env.manager.phones.complete_pairing(secret, name)


def read_until(ws, kind, limit=50):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("type") == kind:
            return msg
    raise AssertionError(f"не дождались сообщения {kind}")


# ---------- сопряжение ----------

def test_pairing_gives_token_and_stores_only_its_hash(env):
    device_id, token = pair(env)
    assert len(token) >= 32
    row = env.db.conn.execute("SELECT token_hash, name FROM phone_devices WHERE id = ?", (device_id,)).fetchone()
    assert row["token_hash"] == hash_token(token) and token != row["token_hash"]
    assert row["name"] == "Pixel"
    assert env.manager.phones.authenticate(token)["id"] == device_id


def test_secret_is_single_use(env):
    secret, _ = env.manager.phones.open_pairing()
    env.manager.phones.complete_pairing(secret, "A")
    with pytest.raises(PairingError):
        env.manager.phones.complete_pairing(secret, "B")


def test_secret_expires(env):
    secret, _ = env.manager.phones.open_pairing()
    env.clock.advance(PAIR_TTL_S + 1)
    with pytest.raises(PairingError):
        env.manager.phones.complete_pairing(secret, "A")


def test_wrong_secrets_burn_the_code(env):
    secret, _ = env.manager.phones.open_pairing()
    for _ in range(PAIR_MAX_FAILS):
        with pytest.raises(PairingError):
            env.manager.phones.complete_pairing("не тот", "A")
    with pytest.raises(PairingError):          # даже верный секрет уже не подходит
        env.manager.phones.complete_pairing(secret, "A")


def test_new_pairing_cancels_the_previous_secret(env):
    old, _ = env.manager.phones.open_pairing()
    env.manager.phones.open_pairing()
    with pytest.raises(PairingError):
        env.manager.phones.complete_pairing(old, "A")


def test_device_limit(env):
    for i in range(MAX_DEVICES):
        pair(env, f"P{i}")
    secret, _ = env.manager.phones.open_pairing()
    with pytest.raises(PairingError):
        env.manager.phones.complete_pairing(secret, "лишний")


def test_unknown_or_malformed_tokens_are_rejected(env):
    pair(env)
    for bad in ("", "x" * 40, None, 123, "a" * 500):
        assert env.manager.phones.authenticate(bad) is None


def test_pair_endpoint(env, phone_client):
    secret, _ = env.manager.phones.open_pairing()
    r = phone_client.post("/pair", json={"secret": secret, "name": "  Мой   телефон "})
    assert r.status_code == 200 and r.json()["token"]
    assert env.manager.phones.devices()[0]["name"] == "Мой телефон"
    assert phone_client.post("/pair", json={"secret": secret}).status_code == 403    # секрет уже использован


# ---------- WebSocket ----------

def test_connect_receives_state_and_marks_phone_online(env, phone_client):
    _, token = pair(env)
    with phone_client.websocket_connect("/phone") as ws:
        ws.send_json({"type": "hello", "token": token})
        assert read_until(ws, "hello_ok")["name"] == "Pixel"
        state = read_until(ws, "state")
        assert state["active"] is False and state["list_mode"] == "blacklist"
        assert env.manager.phones.online_count() == 1
        assert env.state()["protection"]["phones_online"] == 1
    assert env.manager.phones.online_count() == 0


def test_state_follows_the_session(env, phone_client):
    _, token = pair(env)
    with phone_client.websocket_connect("/phone") as ws:
        ws.send_json({"type": "hello", "token": token})
        read_until(ws, "state")
        env.post("/api/session/start", {"length_min": 25})
        for _ in range(100):
            state = read_until(ws, "state")
            if state["active"]:
                break
        assert state["active"] is True and state["session_id"] and state["remaining_s"] > 0


def test_phone_is_not_protected_when_target_is_pc(tmp_path):
    env = Env(tmp_path, overrides={"protection": {"targets": "pc"}})
    env.post("/api/session/start", {})
    assert env.manager.phone_state()["active"] is False
    assert env.manager.pc_protection_active() is True


def test_bad_token_is_refused(env, phone_client):
    pair(env)
    with phone_client.websocket_connect("/phone") as ws:
        ws.send_json({"type": "hello", "token": "x" * 43})
        assert ws.receive_json() == {"type": "error", "reason": "bad_token"}
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_first_message_must_be_hello(env, phone_client):
    _, token = pair(env)
    with phone_client.websocket_connect("/phone") as ws:
        ws.send_json({"type": "report", "events": [], "token": token})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4400


def test_silent_client_is_dropped(env, phone_client, monkeypatch):
    monkeypatch.setattr(lan, "HELLO_TIMEOUT_S", 0.2)
    with phone_client.websocket_connect("/phone") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4408


def test_report_is_accepted_and_filtered(env, phone_client):
    device_id, token = pair(env)
    events = [{"kind": "blocked", "app": "com.game", "ts": 5},
              {"kind": "hacked", "app": "x"}, "мусор",
              {"kind": "service_off", "ts": True}]
    with phone_client.websocket_connect("/phone") as ws:
        ws.send_json({"type": "hello", "token": token})
        read_until(ws, "hello_ok")
        ws.send_json({"type": "report", "events": events})
        assert read_until(ws, "report_ok")["accepted"] == 2
    recent = env.manager.phones.recent
    assert [e["kind"] for e in recent] == ["blocked", "service_off"]
    assert recent[0]["device"] == device_id and recent[0]["ts"] == 5
    assert recent[1]["ts"] == env.clock.now()          # bool вместо времени не принимаем


def test_revoked_device_is_disconnected(env, phone_client):
    device_id, token = pair(env)
    with phone_client.websocket_connect("/phone") as ws:
        ws.send_json({"type": "hello", "token": token})
        read_until(ws, "hello_ok")
        env.manager.phones.revoke(device_id)
        read_until(ws, "revoked")
    assert env.manager.phones.authenticate(token) is None


def test_clients_outside_private_network_are_refused(env):
    client = TestClient(lan.build_phone_app(env.manager))     # настоящая проверка адреса
    assert client.post("/pair", json={"secret": "x"}).status_code == 403


@pytest.mark.parametrize("host,ok", [
    ("192.168.0.10", True), ("10.1.2.3", True), ("172.16.5.5", True), ("127.0.0.1", True),
    ("8.8.8.8", False), ("93.184.216.34", False), ("", False), (None, False), ("не ip", False),
])
def test_private_client_check(host, ok):
    assert lan.is_private_client(host) is ok


def test_phone_app_exposes_nothing_but_pair_and_phone(phone_client):
    for path in ("/api/state", "/api/settings", "/", "/docs", "/openapi.json"):
        assert phone_client.get(path).status_code == 404


# ---------- интерфейс на ПК ----------

def test_wifi_status_and_pair_need_lan(env):
    status = env.client.get("/api/wifi/status").json()
    assert status["enabled"] is False and status["running"] is False and status["devices"] == []
    assert env.client.post("/api/wifi/pair").status_code == 409


def test_pair_returns_qr_when_lan_is_running(env, tmp_path):
    client = TestClient(create_app(env.manager, run_loop=False, rules_path=tmp_path / "rules.yaml",
                                   lan=FakeLan()))
    r = client.post("/api/wifi/pair")
    assert r.status_code == 200
    data = r.json()
    assert data["payload"].startswith("focusfarm://pair?h=192.168.1.5&p=8766&s=")
    assert "<svg" in data["qr_svg"] and data["expires_in"] == PAIR_TTL_S
    assert env.manager.phones.pairing_open()
    assert client.delete("/api/wifi/pair").status_code == 200
    assert not env.manager.phones.pairing_open()


def test_device_can_be_removed_from_pc(env):
    device_id, _ = pair(env)
    assert env.client.get("/api/wifi/status").json()["devices"][0]["id"] == device_id
    assert env.client.delete(f"/api/wifi/devices/{device_id}").status_code == 200
    assert env.client.delete(f"/api/wifi/devices/{device_id}").status_code == 404


# ---------- настройки ----------

def test_lan_is_off_by_default():
    assert load_settings()["network"] == {"lan_enabled": False, "port": 8766}


@pytest.mark.parametrize("patch", [
    {"lan_enabled": "yes"}, {"port": 80}, {"port": "8766"}, {"port": True}, {"port": 8765},
])
def test_bad_network_settings_are_rejected(patch):
    with pytest.raises(ConfigError):
        load_settings(overrides={"network": patch})


def test_network_is_editable_through_api(env):
    r = env.client.put("/api/settings", json={"network": {"lan_enabled": True, "port": 9000}})
    assert r.status_code == 200 and r.json()["network"] == {"lan_enabled": True, "port": 9000}
    assert env.client.put("/api/settings", json={"network": {"port": 22}}).status_code == 400
