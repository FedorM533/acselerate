"""Упаковка в Carpo.exe: пути, сторож, отчёт для разработчика."""
import io
import sys
import zipfile

from fastapi.testclient import TestClient

from focusfarm import paths
from focusfarm.api.server import create_app
from focusfarm.clock import FakeClock
from focusfarm.config import load_settings
from focusfarm.session.manager import SessionManager
from focusfarm.storage.db import Database


def test_source_run_uses_repo_folders():
    assert not paths.FROZEN
    assert paths.CONFIG_DIR.joinpath("settings.yaml").is_file()
    assert paths.WEB_DIR.joinpath("index.html").is_file()
    assert paths.EXTENSION_DIR.joinpath("manifest.json").is_file()
    assert paths.RULES_PATH == paths.CONFIG_DIR / "rules.yaml"


def test_commands_from_sources():
    assert paths.self_command() == [sys.executable, "-m", "focusfarm"]
    assert paths.watchdog_command() == [sys.executable, "-m", "focusfarm.watchdog"]


def test_commands_from_exe(monkeypatch):
    monkeypatch.setattr(paths, "FROZEN", True)
    assert paths.self_command() == [sys.executable]
    assert paths.watchdog_command() == [sys.executable, "--watchdog"]


def test_first_run_of_exe_creates_profile_files(monkeypatch, tmp_path):
    user = tmp_path / "Carpo"
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "RULES_PATH", user / "config" / "rules.yaml")
    monkeypatch.setattr(paths, "DATA_DIR", user / "data")
    monkeypatch.setattr(paths, "LOG_DIR", user / "logs")
    paths.seed_user_files()
    assert (user / "config" / "rules.yaml").read_text(encoding="utf-8") \
        == (paths.CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8")
    assert (user / "data").is_dir() and (user / "logs").is_dir()
    (user / "config" / "rules.yaml").write_text("свои: правила", encoding="utf-8")
    paths.seed_user_files()    # второй запуск не затирает правила пользователя
    assert (user / "config" / "rules.yaml").read_text(encoding="utf-8") == "свои: правила"


def test_seed_does_nothing_from_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "RULES_PATH", tmp_path / "x" / "rules.yaml")
    paths.seed_user_files()
    assert not (tmp_path / "x").exists()


def make_client(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path)
    (tmp_path / "carpo.log").write_text("строка журнала", encoding="utf-8")
    manager = SessionManager(load_settings(), Database(":memory:"), clock=FakeClock())
    return TestClient(create_app(manager, run_loop=False))


def test_about_has_version_and_feedback_url(monkeypatch, tmp_path):
    r = make_client(monkeypatch, tmp_path).get("/api/about")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] and body["packaged"] is False and "feedback_url" in body


def test_diagnostics_zip_has_info_and_log(monkeypatch, tmp_path):
    r = make_client(monkeypatch, tmp_path).get("/api/diagnostics")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert "Carpo" in z.read("info.txt").decode("utf-8")
        assert z.read("logs/carpo.log").decode("utf-8") == "строка журнала"
