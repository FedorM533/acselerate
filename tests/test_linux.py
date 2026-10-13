"""Linux: разбор вывода xprop/gdbus, USB из sysfs, расширение GNOME, помощник расширения браузера.

Настоящие программы рабочего стола не запускаем — проверяем разбор их вывода.
"""
import json
import sys
import zipfile

import pytest

from focusfarm.activity import linux
from focusfarm.activity.classifier import Classifier, load_rules
from focusfarm.blocker.apps import AppBlocker
from focusfarm.sensors.usb_phone import list_linux
from focusfarm.tools import ext_install, gnome_ext


def test_parse_gdbus_idle():
    assert linux.parse_gdbus_uint("(uint64 15151,)\n") == 15151


def test_parse_gdbus_string_from_extension():
    # Расширение отдаёт кириллицу как \uXXXX, gdbus удваивает обратную косую черту.
    out = """('{"pid":42,"title":"\\\\u041a\\\\u043e\\\\u043d\\\\u0441\\\\u043f\\\\u0435\\\\u043a\\\\u0442"}',)\n"""
    data = json.loads(linux.parse_gdbus_string(out))
    assert data == {"pid": 42, "title": "Конспект"}


def test_parse_xprop_active_window():
    assert linux.parse_xprop_active("_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3a00007\n") == "0x3a00007"
    assert linux.parse_xprop_active("_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0\n") is None


def test_parse_xprop_window_pid_and_title():
    text = '_NET_WM_PID(CARDINAL) = 4242\n_NET_WM_NAME(UTF8_STRING) = "Лекция \\"1\\" — Firefox"\n'
    assert linux.parse_xprop_window(text) == (4242, 'Лекция "1" — Firefox')
    assert linux.parse_xprop_window("_NET_WM_PID:  not found.\n") == (None, "")


def test_parse_xprop_client_list():
    text = "_NET_CLIENT_LIST(WINDOW): window id # 0x1e00003, 0x2400004\n"
    assert linux.parse_xprop_client_list(text) == ["0x1e00003", "0x2400004"]


def test_linux_monitor_uses_extension(monkeypatch):
    monkeypatch.setattr(linux, "window_backend", lambda: "gnome")
    monkeypatch.setattr(linux.shutil, "which", lambda name: None)    # без gdbus: простой = 0
    monkeypatch.setattr(linux, "extension_active", lambda: (123, "YouTube — Firefox"))
    monkeypatch.setattr(linux, "process_name", lambda pid: "firefox")
    monitor = linux.LinuxMonitor()
    assert monitor.available and monitor.name == "linux-gnome" and monitor.hint is None
    sample = monitor.sample()
    assert (sample.process_name, sample.window_title, sample.idle_seconds) == ("firefox", "YouTube — Firefox", 0.0)


def test_linux_monitor_without_windows_gives_hint(monkeypatch):
    monkeypatch.setattr(linux, "window_backend", lambda: None)
    monkeypatch.setattr(linux.shutil, "which", lambda name: None)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monitor = linux.LinuxMonitor()
    assert not monitor.available
    assert "gnome_ext" in monitor.hint
    assert monitor.sample().process_name == "unknown"


def test_linux_process_names_in_rules():
    clf = Classifier(load_rules())
    assert clf.classify("code") == "work"
    assert clf.classify("telegram-desktop") == "distraction"
    assert clf.classify("code.exe") == "work"          # Windows-имена остались


def test_blocker_never_closes_linux_shell():
    class Procs:
        def running(self):
            return [(10, "gnome-shell"), (11, "bash"), (12, "discord")]

        def protected_pids(self):
            return set()

    events = AppBlocker(Procs()).update(0, True, False, ["gnome-shell", "bash", "discord"])
    assert [e["process"] for e in events] == ["discord"]


def _usb(root, name, **files):
    folder = root / name
    folder.mkdir()
    for key, value in files.items():
        (folder / key).write_text(value + "\n")


def test_list_linux_usb(tmp_path):
    _usb(tmp_path, "3-3.1", idVendor="04e8", idProduct="6860", serial="RF8X40F11VE",
         manufacturer="SAMSUNG", product="SAMSUNG_Android")
    _usb(tmp_path, "3-3.1:1.0", idVendor="04e8", serial="RF8X40F11VE")   # интерфейс, не устройство
    _usb(tmp_path, "usb1", idVendor="1d6b", idProduct="0002", serial="0000:00:12.2")  # корневой хаб
    _usb(tmp_path, "3-3.2", idVendor="c0f4", idProduct="0af5")           # клавиатура без серийника
    devices = list_linux(tmp_path)
    assert devices == [{"id": "04E8:RF8X40F11VE", "vid": "04E8", "pid": "6860",
                        "serial": "RF8X40F11VE", "name": "SAMSUNG Android"}]


def test_list_linux_without_sysfs(tmp_path):
    assert list_linux(tmp_path / "нет") == []


def test_gnome_ext_adds_uuid_once():
    assert gnome_ext.add_to_enabled("@as []") == [gnome_ext.UUID]
    assert gnome_ext.add_to_enabled("['a@b']") == ["a@b", gnome_ext.UUID]
    assert gnome_ext.add_to_enabled(f"['{gnome_ext.UUID}']") is None


def test_gnome_extension_files_exist():
    assert (gnome_ext.SOURCE / "extension.js").is_file()
    meta = json.loads((gnome_ext.SOURCE / "metadata.json").read_text(encoding="utf-8"))
    assert meta["uuid"] == gnome_ext.UUID


def test_build_xpi_has_manifest_at_root(tmp_path):
    folder = ext_install.prepare_folder(ext_install.SOURCE, tmp_path / "Carpo" / "extension")
    xpi = ext_install.build_xpi(folder)
    with zipfile.ZipFile(xpi) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["browser_specific_settings"]["gecko"]["id"]
    assert "scripts" in manifest["background"]          # Firefox
    assert "service_worker" in manifest["background"]   # Chrome


def test_linux_browsers_found_in_path(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ext_install.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in ("firefox-esr", "chromium") else None)
    assert ext_install.installed_browsers() == {"chromium": "/usr/bin/chromium", "firefox": "/usr/bin/firefox-esr"}


def test_firefox_install_gives_xpi_and_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(ext_install, "target_dir", lambda: tmp_path / "Carpo" / "extension")
    monkeypatch.setattr(ext_install, "open_extensions_page", lambda browser: True)
    monkeypatch.setattr(ext_install, "copy_to_clipboard", lambda text: False)
    result = ext_install.install("firefox")
    assert result["folder"].endswith(ext_install.XPI_NAME)
    assert any("about:addons" in step for step in result["steps"])
    assert ext_install.install("chrome")["steps"] == ext_install.CHROMIUM_STEPS


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="только Linux")
def test_create_monitor_on_linux():
    from focusfarm.activity.monitor import create_monitor
    monitor = create_monitor()
    assert monitor.name.startswith("linux") or monitor.name == "fallback"
