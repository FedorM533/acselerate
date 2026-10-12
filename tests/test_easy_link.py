"""Простая связь с телефоном: код из 6 цифр, автопоиск ПК в сети, установка расширения."""
import json
import socket

import pytest
from fastapi.testclient import TestClient

from focusfarm.api.server import create_app
from focusfarm.phone import lan
from focusfarm.tools import ext_install
from tests.conftest import Env


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_pairing_code_is_six_digits_and_works(env):
    code, _ = env.manager.phones.open_pairing()
    assert len(code) == 6 and code.isdigit()
    device_id, token = env.manager.phones.complete_pairing(code, "Pixel")
    assert device_id and token


def test_pair_endpoint_switches_on_wifi_by_itself(env, tmp_path):
    """Человеку не нужно искать переключатель в настройках: кнопка «Подключить телефон» включает связь."""
    started = []

    class FakeLan:
        error = ""

        def sync(self, settings): started.append(settings["network"]["lan_enabled"])
        def stop(self): ...
        def address(self): return ("192.168.1.5", 8766) if started and started[-1] else None
        def wait_started(self, timeout=0): return self.address()

    client = TestClient(create_app(env.manager, run_loop=False, rules_path=tmp_path / "rules.yaml", lan=FakeLan()))
    assert env.manager.settings["network"]["lan_enabled"] is False
    r = client.post("/api/wifi/pair")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["code"]) == 6 and body["payload"].endswith(body["code"])
    assert started == [True] and env.manager.settings["network"]["lan_enabled"] is True


def ask(port, payload=lan.DISCOVERY_QUERY, wait=0.6):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(wait)
    try:
        sock.sendto(payload, ("127.0.0.1", port))
        return json.loads(sock.recvfrom(512)[0])
    except socket.timeout:
        return None
    finally:
        sock.close()


@pytest.fixture
def discovery(env, monkeypatch):
    monkeypatch.setattr(lan, "DISCOVERY_PORT", 48799)
    d = lan.Discovery(env.manager, "192.168.1.5", 8766)
    d.start()
    yield d
    d.stop()


def test_discovery_is_silent_until_pairing_is_open(env, discovery):
    assert ask(48799) is None
    env.manager.phones.open_pairing()
    answer = ask(48799)
    assert answer["host"] == "192.168.1.5" and answer["port"] == 8766 and answer["name"]


def test_discovery_ignores_foreign_networks(env, monkeypatch):
    monkeypatch.setattr(lan, "DISCOVERY_PORT", 48798)
    d = lan.Discovery(env.manager, "192.168.1.5", 8766, allow_client=lambda host: False)
    d.start()
    try:
        env.manager.phones.open_pairing()
        assert ask(48798) is None
    finally:
        d.stop()


def test_discovery_ignores_garbage(env, discovery):
    env.manager.phones.open_pairing()
    assert ask(48799, b"hello") is None


def test_prepare_folder_copies_extension(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "manifest.json").write_text("{}")
    target = ext_install.prepare_folder(source, tmp_path / "out" / "ext")
    assert (target / "manifest.json").is_file()
    ext_install.prepare_folder(source, target)            # повторная установка поверх не падает


def test_prepare_folder_needs_manifest(tmp_path):
    with pytest.raises(FileNotFoundError):
        ext_install.prepare_folder(tmp_path, tmp_path / "out")


def test_extension_install_endpoint(env, monkeypatch):
    monkeypatch.setattr(ext_install, "install", lambda browser: {"folder": "C:/x", "copied": True,
                                                                 "opened": True, "browser": browser})
    assert env.client.post("/api/extension/install", json={"browser": "chrome"}).json()["opened"] is True
    assert env.client.post("/api/extension/install", json={"browser": "rm -rf"}).status_code == 400
