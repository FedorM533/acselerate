"""Сопряжение телефонов и учёт подключений.

Как это работает:
1. На ПК нажимаем «Подключить телефон» → open_pairing() создаёт одноразовый секрет
   (живёт PAIR_TTL_S секунд) и показывает его в QR-коде.
2. Телефон сканирует QR и отправляет секрет → complete_pairing() выдаёт токен.
   Токен знает только телефон; в базе лежит его SHA-256.
3. Дальше телефон подключается по WebSocket и первым сообщением шлёт токен.

Время идёт через Clock, чтобы тесты могли его двигать.
"""
import hashlib
import hmac
import logging
import secrets
import uuid

log = logging.getLogger(__name__)

PAIR_TTL_S = 120          # сколько живёт QR-код
PAIR_MAX_FAILS = 5        # столько неверных секретов — и код сгорает
MAX_DEVICES = 5
MAX_NAME_LEN = 40
MAX_REPORT_EVENTS = 100   # событий в одном отчёте телефона
RECENT_LIMIT = 50         # сколько последних событий телефона держим в памяти
REPORT_KINDS = ("blocked", "opened", "service_off", "service_on")


class PairingError(Exception):
    """Сопряжение не удалось (текст безопасен для показа телефону)."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_name(value) -> str:
    text = " ".join(str(value or "").split())[:MAX_NAME_LEN]
    return text or "Телефон"


class PhoneHub:
    def __init__(self, db, clock, bus=None):
        self.db = db
        self.clock = clock
        self.bus = bus
        self._secret_hash: str | None = None
        self._secret_until = 0.0
        self._fails = 0
        self._online: dict[str, str] = {}       # device_id → имя (сейчас на связи)
        self._conns: dict[str, int] = {}        # device_id → сколько соединений открыто
        self.recent: list[dict] = []            # последние события телефона, только в памяти

    # ---------- сопряжение ----------

    def open_pairing(self) -> tuple[str, float]:
        """Новый одноразовый секрет. Прежний, если был, перестаёт действовать."""
        secret = secrets.token_urlsafe(12)
        self._secret_hash = hash_token(secret)
        self._secret_until = self.clock.now() + PAIR_TTL_S
        self._fails = 0
        return secret, PAIR_TTL_S

    def close_pairing(self):
        self._secret_hash = None

    def pairing_open(self) -> bool:
        return self._secret_hash is not None and self.clock.now() < self._secret_until

    def complete_pairing(self, secret, name) -> tuple[str, str]:
        """Возвращает (device_id, token). Секрет одноразовый."""
        if not self.pairing_open():
            self._secret_hash = None
            raise PairingError("Код сопряжения не открыт или устарел. Нажмите «Подключить телефон» на ПК.")
        if not isinstance(secret, str) or not hmac.compare_digest(hash_token(secret), self._secret_hash):
            self._fails += 1
            if self._fails >= PAIR_MAX_FAILS:
                self._secret_hash = None
                log.warning("Слишком много неверных кодов сопряжения — код закрыт")
            raise PairingError("Неверный код сопряжения.")
        if len(self.db.list_phone_devices()) >= MAX_DEVICES:
            raise PairingError(f"Уже подключено {MAX_DEVICES} телефонов. Удалите ненужный на ПК.")
        self._secret_hash = None                      # секрет использован
        token = secrets.token_urlsafe(32)
        device_id = uuid.uuid4().hex[:12]
        self.db.add_phone_device(device_id, clean_name(name), hash_token(token), self.clock.now())
        log.info("Телефон сопряжён: %s", device_id)
        return device_id, token

    # ---------- проверка токена и подключения ----------

    def authenticate(self, token) -> dict | None:
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            return None
        device = self.db.find_phone_device(hash_token(token))
        if device:
            self.db.touch_phone_device(device["id"], self.clock.now())
        return device

    def still_valid(self, device_id: str) -> bool:
        """Не отозвали ли устройство, пока оно было на связи."""
        return any(d["id"] == device_id for d in self.db.list_phone_devices())

    def set_online(self, device_id: str, name: str, online: bool):
        """Соединений может быть два (старое ещё не закрылось, новое уже открыто): считаем их."""
        count = self._conns.get(device_id, 0) + (1 if online else -1)
        if count > 0:
            self._conns[device_id] = count
            self._online[device_id] = name
        else:
            self._conns.pop(device_id, None)
            self._online.pop(device_id, None)

    def online_count(self) -> int:
        return len(self._online)

    def devices(self) -> list[dict]:
        rows = self.db.list_phone_devices()
        return [{**row, "online": row["id"] in self._online} for row in rows]

    def revoke(self, device_id: str) -> bool:
        self._conns.pop(device_id, None)
        self._online.pop(device_id, None)
        return self.db.delete_phone_device(device_id)

    # ---------- отчёты телефона ----------

    def accept_report(self, device_id: str, events) -> int:
        """Принимает события, накопленные телефоном (в том числе пока не было связи).
        Хранит только вид события и название приложения, и только в памяти."""
        if not isinstance(events, list):
            return 0
        accepted = 0
        for item in events[:MAX_REPORT_EVENTS]:
            if not isinstance(item, dict) or item.get("kind") not in REPORT_KINDS:
                continue
            ts = item.get("ts")
            event = {
                "device": device_id,
                "kind": item["kind"],
                "app": str(item.get("app", ""))[:120],
                "ts": float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else self.clock.now(),
            }
            self.recent.append(event)
            accepted += 1
            if self.bus:
                self.bus.publish("phone_report", event)
        del self.recent[:-RECENT_LIMIT]
        return accepted
