"""Датчик «телефон подключён к компьютеру кабелем» (USB).

Как это работает:
1. Раз в `POLL_S` секунд (в фоновом потоке) спрашиваем у системы список
   USB-устройств. На Windows — PowerShell `Get-PnpDevice`, на macOS —
   `system_profiler`. На других системах список пуст.
2. «Мой телефон» запоминается при привязке (см. `UsbPhoneSensor.pair_*`):
   сравниваем список до и после подключения кабеля, новое устройство — телефон.
3. Телефон считается «в подставке», пока его устройство есть в списке.

Узнаём телефон по паре (VID, серийный номер), а PID игнорируем: при смене
режима USB («зарядка» / «передача файлов») телефон меняет PID.

Ограничение: USB знает только, что кабель подключён, а не что телефон лежит
без дела. Чтобы им нельзя было пользоваться, включите на телефоне режим
«Фокусирование» с белым списком приложений.
"""
import logging
import re
import subprocess
import sys
import threading

from focusfarm.sensors.phone import PhoneSensor

log = logging.getLogger(__name__)

POLL_S = 2

# USB\VID_18D1&PID_4EE1\ABC123 — устройство верхнего уровня.
# Составные интерфейсы (…&MI_00…) пропускаем: у них нет своего серийного номера.
_WIN_ID = re.compile(r"^USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})\\(.+)$", re.IGNORECASE)

_PS_COMMAND = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
    "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
    "Where-Object { $_.InstanceId -like 'USB\\VID_*' } | "
    "ForEach-Object { $_.InstanceId + '|' + $_.FriendlyName }"
)


def parse_windows(text: str) -> list[dict]:
    """Разбирает вывод PowerShell: строки «InstanceId|Имя» → список устройств."""
    devices = {}
    for line in text.splitlines():
        instance_id, _, name = line.strip().partition("|")
        match = _WIN_ID.match(instance_id)
        if not match:
            continue
        vid, pid, serial = match.group(1).upper(), match.group(2).upper(), match.group(3)
        key = f"{vid}:{serial}"
        devices.setdefault(key, {"id": key, "vid": vid, "pid": pid, "serial": serial,
                                 "name": name.strip() or f"USB-устройство {vid}:{pid}"})
    return list(devices.values())


def parse_macos(text: str) -> list[dict]:
    """Разбирает вывод `system_profiler SPUSBDataType`."""
    devices, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line.endswith(":") and not line.startswith(("Product ID", "Vendor ID", "Serial Number")):
            current = {"name": line[:-1], "vid": "", "pid": "", "serial": ""}
            devices.append(current)
        elif current is not None:
            if line.startswith("Product ID:"):
                current["pid"] = line.split(":", 1)[1].strip().removeprefix("0x").upper()
            elif line.startswith("Vendor ID:"):
                current["vid"] = line.split(":", 1)[1].split()[0].removeprefix("0x").upper()
            elif line.startswith("Serial Number:"):
                current["serial"] = line.split(":", 1)[1].strip()
    result = []
    for d in devices:
        if d["vid"] and d["serial"]:
            result.append({**d, "id": f"{d['vid']}:{d['serial']}"})
    return result


class UsbLister:
    """Спрашивает у системы список USB-устройств. В тестах заменяется заглушкой."""

    def list_devices(self) -> list[dict]:
        if sys.platform == "win32":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_COMMAND],
                capture_output=True, text=True, encoding="utf-8", timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return parse_windows(out)
        if sys.platform == "darwin":
            out = subprocess.run(["system_profiler", "SPUSBDataType"],
                                 capture_output=True, text=True, timeout=15).stdout
            return parse_macos(out)
        return []


class UsbPhoneSensor(PhoneSensor):
    source = "usb"

    def __init__(self, lister=None, paired_id: str = "", paired_name: str = "", poll_s: float = POLL_S):
        super().__init__()
        self.lister = lister or UsbLister()
        self.paired_id = paired_id
        self.paired_name = paired_name
        self.poll_s = poll_s
        self.devices: list[dict] = []
        self.error = None
        self._docked = False
        self._baseline: set[str] | None = None
        self._stop = threading.Event()
        self._thread = None

    # ---------- опрос ----------

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="usb-phone", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            if self.paired_id:   # пока телефон не привязан, систему зря не опрашиваем
                self.poll()
            self._stop.wait(self.poll_s)

    def poll(self):
        """Один опрос. Ошибки не роняют программу — только сообщение в интерфейсе."""
        try:
            self.devices = self.lister.list_devices()
            self.error = None
        except Exception as exc:
            log.warning("Не удалось получить список USB-устройств: %s", exc)
            self.error = f"Не удалось прочитать USB: {exc}"
            self.devices = []
        docked = bool(self.paired_id) and any(d["id"] == self.paired_id for d in self.devices)
        if docked != self._docked:
            self._docked = docked
            self._notify(docked)

    def is_docked(self) -> bool:
        return self._docked

    # ---------- привязка ----------

    @property
    def paired(self) -> bool:
        return bool(self.paired_id)

    def set_paired(self, device_id: str, name: str = ""):
        if (device_id, name) != (self.paired_id, self.paired_name):
            self.paired_id, self.paired_name = device_id, name
            self._docked = False   # дальше состояние обновит ближайший опрос

    def pair_begin(self):
        """Шаг 1: запоминаем, что подключено сейчас (телефон ещё не подключён)."""
        self.poll()
        self._baseline = {d["id"] for d in self.devices}

    def pair_finish(self) -> list[dict]:
        """Шаг 2: телефон подключили. Возвращает новые устройства-кандидаты."""
        if self._baseline is None:
            return []
        self.poll()
        return [d for d in self.devices if d["id"] not in self._baseline]

    def view(self) -> dict:
        return {"paired": self.paired, "name": self.paired_name, "docked": self._docked,
                "error": self.error}
