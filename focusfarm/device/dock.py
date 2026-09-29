"""Подставка целиком: настоящая (ESP32) с запасной виртуальной.

Dock одновременно реализует PhoneSensor и DeviceOutput, поэтому менеджер
сессии не знает, какая подставка сейчас работает.

- Порт не задан → только виртуальная подставка (mock).
- Порт задан и связь есть → датчик и свет/звук идут через ESP32.
- Связь пропала → «подставка не подключена», автоматически работаем через
  mock, а в фоне переподключаемся. После переподключения повторяем цвет LED.
"""
from focusfarm.device.output import DeviceOutput, MockDeviceOutput
from focusfarm.device.serial_link import SerialDeviceOutput, SerialLink, SerialPhoneSensor, open_serial
from focusfarm.sensors.phone import MockPhoneSensor, PhoneSensor


class Dock(PhoneSensor, DeviceOutput):
    def __init__(self, port: str = "", mock_docked: bool = False, opener=None):
        PhoneSensor.__init__(self)
        self.opener = opener or open_serial   # в тестах подменяется заглушкой
        self.mock_phone = MockPhoneSensor(docked=mock_docked)
        self.mock_device = MockDeviceOutput()   # всегда хранит «что сейчас горит» для интерфейса
        self.port = ""
        self.link = None
        self.serial_phone = None
        self.serial_device = None
        self._button_handlers = []
        self.set_port(port)

    # ---------- порт ----------

    def set_port(self, port: str):
        port = (port or "").strip()
        if port == self.port:
            return
        self.stop()
        self.port = port
        if not port:
            return
        self.link = SerialLink(port, opener=self.opener)
        self.serial_phone = SerialPhoneSensor(self.link)
        self.serial_device = SerialDeviceOutput(self.link)
        self.serial_phone.on_button(self._on_button)
        self.link.on_line(self._on_link_event)
        self.link.start()

    def stop(self):
        if self.link:
            self.link.stop()
        self.link = self.serial_phone = self.serial_device = None

    @property
    def serial_ok(self) -> bool:
        return bool(self.link and self.link.connected)

    def _on_link_event(self, line: str):
        if line == "CONNECTED":
            # Повторяем текущий цвет, чтобы подставка сразу показала состояние.
            self.serial_device.set_led(self.mock_device.led)

    # ---------- PhoneSensor ----------

    @property
    def source(self) -> str:
        return "serial" if self.serial_ok else "mock"

    def is_docked(self) -> bool:
        if self.serial_ok:
            return self.serial_phone.is_docked()
        return self.mock_phone.is_docked()

    def set_docked(self, docked: bool):
        """Виртуальный телефон (панель разработчика)."""
        self.mock_phone.set_docked(docked)

    def on_button(self, handler):
        self._button_handlers.append(handler)

    def _on_button(self, name: str):
        for handler in self._button_handlers:
            handler(name)

    # ---------- DeviceOutput ----------

    @property
    def led(self):
        return self.mock_device.led

    @property
    def last_sound(self):
        return self.mock_device.last_sound

    @property
    def log(self):
        return self.mock_device.log

    def set_led(self, color: str):
        self.mock_device.set_led(color)
        if self.serial_ok:
            self.serial_device.set_led(color)

    def play_sound(self, n: int):
        self.mock_device.play_sound(n)
        if self.serial_ok:
            self.serial_device.play_sound(n)

    def is_connected(self) -> bool:
        return self.serial_ok if self.port else True

    def status_text(self) -> str | None:
        if not self.port:
            return None   # интерфейс напишет «Виртуальная подставка»
        if self.serial_ok:
            fw = f", прошивка {self.link.fw_version}" if self.link.fw_version else ""
            return f"Подставка подключена ({self.port}{fw})"
        return f"Подставка не подключена ({self.port}) — работает виртуальная"
