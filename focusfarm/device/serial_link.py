"""Связь с подставкой ESP32 по USB-serial (протокол — firmware/PROTOCOL.md).

SerialLink держит соединение в фоновом потоке:
- если порт не открылся или связь пропала — пробует снова каждые RECONNECT_S секунд;
- раз в PING_S секунд шлёт PING; если устройство молчит дольше TIMEOUT_S —
  считаем, что связь потеряна, и переподключаемся.
Любые ошибки порта логируются и не роняют программу.

SerialPhoneSensor и SerialDeviceOutput — тонкие обёртки над SerialLink,
реализующие интерфейсы PhoneSensor и DeviceOutput.
"""
import logging
import threading
import time

from focusfarm.device.output import LED_COLORS, DeviceOutput
from focusfarm.sensors.phone import PhoneSensor

log = logging.getLogger(__name__)

BAUDRATE = 115200
RECONNECT_S = 3
PING_S = 5
TIMEOUT_S = 12


def open_serial(port: str):
    """Открывает настоящий порт. В тестах вместо неё подставляется заглушка."""
    import serial
    return serial.Serial(port, BAUDRATE, timeout=0.5)


class SerialLink:
    def __init__(self, port: str, opener=open_serial):
        self.port = port
        self.opener = opener
        self.connected = False
        self.fw_version = None
        self.last_error = None
        self._serial = None
        self._listeners = []          # handler(line: str)
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self._thread = None
        self._last_rx = 0.0
        self._last_ping = 0.0

    # ---------- управление ----------

    def on_line(self, handler):
        self._listeners.append(handler)

    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"serial-{self.port}", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._close()
        if self._thread:
            self._thread.join(timeout=2)

    def send(self, line: str) -> bool:
        """Отправляет команду. Возвращает False, если связи нет."""
        if not self.connected:
            return False
        try:
            with self._write_lock:
                self._serial.write((line + "\n").encode("ascii"))
            return True
        except Exception as exc:
            self._lost(exc)
            return False

    # ---------- фоновый поток ----------

    def _run(self):
        while not self._stop.is_set():
            if not self.connected:
                self._try_open()
                if not self.connected:
                    self._stop.wait(RECONNECT_S)
                    continue
            self._read_once()
            self._keep_alive()

    def _try_open(self):
        try:
            self._serial = self.opener(self.port)
            self.connected = True
            self.last_error = None
            self._last_rx = self._last_ping = time.monotonic()
            log.info("Подставка: порт %s открыт", self.port)
            self.send("STATUS")      # попросить текущее состояние датчика
            self._dispatch("CONNECTED")
        except Exception as exc:
            if self.last_error != str(exc):
                log.warning("Подставка: не удалось открыть %s: %s", self.port, exc)
            self.last_error = str(exc)
            self.connected = False

    def _read_once(self):
        try:
            raw = self._serial.readline()
        except Exception as exc:
            self._lost(exc)
            return
        if not raw:
            return
        line = raw.decode("ascii", errors="replace").strip()
        if not line:
            return
        self._last_rx = time.monotonic()
        if line.startswith("HELLO"):
            self.fw_version = line.partition("fw=")[2] or "?"
        self._dispatch(line)

    def _keep_alive(self):
        now = time.monotonic()
        if now - self._last_rx > TIMEOUT_S:
            self._lost(TimeoutError("устройство не отвечает"))
        elif now - self._last_ping > PING_S:
            self._last_ping = now
            self.send("PING")

    def _dispatch(self, line: str):
        for handler in list(self._listeners):
            try:
                handler(line)
            except Exception:
                log.exception("Ошибка обработки строки от подставки: %r", line)

    def _lost(self, exc):
        if self.connected:
            log.warning("Подставка: связь потеряна (%s)", exc)
        self.last_error = str(exc)
        self._close()
        self._dispatch("DISCONNECTED")

    def _close(self):
        self.connected = False
        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass
        self._serial = None


class SerialPhoneSensor(PhoneSensor):
    """Датчик телефона по строкам DOCK 1 / DOCK 0. Кнопки — BTN PAUSE / BTN NOTEBOOK."""
    source = "serial"

    def __init__(self, link: SerialLink):
        super().__init__()
        self.link = link
        self._docked = False
        self._button_handlers = []
        link.on_line(self._on_line)

    def on_button(self, handler):
        """handler(name) — name: "PAUSE" или "NOTEBOOK"."""
        self._button_handlers.append(handler)

    def is_docked(self) -> bool:
        return self._docked

    def _on_line(self, line: str):
        parts = line.split()
        if len(parts) == 2 and parts[0] == "DOCK" and parts[1] in ("0", "1"):
            docked = parts[1] == "1"
            if docked != self._docked:
                self._docked = docked
                self._notify(docked)
        elif len(parts) == 2 and parts[0] == "BTN":
            for handler in self._button_handlers:
                handler(parts[1])


class SerialDeviceOutput(DeviceOutput):
    """Свет и звук по строкам LED <цвет> / SOUND <n>."""
    source = "serial"

    def __init__(self, link: SerialLink):
        self.link = link

    def set_led(self, color: str):
        if color not in LED_COLORS:
            raise ValueError(f"Неизвестный цвет: {color}")
        self.link.send(f"LED {color}")

    def play_sound(self, n: int):
        self.link.send(f"SOUND {int(n)}")

    def is_connected(self) -> bool:
        return self.link.connected
