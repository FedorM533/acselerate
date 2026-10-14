"""Менеджер сессии: жизненный цикл сессии и тик раз в секунду.

Каждую секунду:
1. читаем монитор активности и датчик телефона;
2. машина состояний решает, в каком мы состоянии;
3. всё сохраняется в базу, события уходят в шину (а оттуда — в интерфейс
   и на подставку).

Демо-режим: «игровое» время идёт в `speed` раз быстрее настоящего. Им
измеряются пороги. Время простоя клавиатуры (idle_seconds) НЕ
ускоряем: иначе в демо «кажется, отвлёкся» включалось бы через 6 секунд
без движения мыши, и показывать было бы неудобно.
"""
import logging
import threading

from focusfarm.activity.classifier import CATEGORIES, Classifier, load_rules, normalize_domain
from focusfarm.activity.fallback import FallbackMonitor
from focusfarm.activity.monitor import SafeMonitor
from focusfarm.blocker.apps import NullBlocker
from focusfarm.clock import Clock, RealClock
from focusfarm.config import speed_of
from focusfarm.device.output import MockDeviceOutput
from focusfarm.events import EventBus
from focusfarm.errors import AppError
from focusfarm.phone.hub import PhoneHub
from focusfarm.reactions import Reactions
from focusfarm.sensors.phone import MockPhoneSensor
from focusfarm.strict import (
    GRACE_S, LOCKOUT_S, MAX_FAILS, MIN_PASSWORD_LEN, hash_password, verify_password,
)
from focusfarm.session.state_machine import (
    FOCUS, IDLE, PAUSED, Inputs, StateMachine,
)
from focusfarm.storage.db import Database

log = logging.getLogger(__name__)

STATE_LABELS = {
    "IDLE": "Сессия не идёт",
    "FOCUS": "Работаешь",
    "NOTEBOOK": "Пишешь в тетради",
    "MAYBE_DISTRACTED": "Кажется, отвлёкся",
    "DISTRACTED": "Отвлёкся",
    "PHONE_OUT": "Телефон вынут",
    "PAUSED": "Пауза",
    "BREAK": "Перерыв",
}
BREAK = "BREAK"          # перерыв Pomodoro: блокировка выключена

FORCED_PROCESS = "(панель разработчика)"
MAX_DT_S = 5  # если компьютер «уснул», не засчитываем пропущенное время разом
EXTENSION_TIMEOUT_S = 90  # сколько тишины от расширения браузера считаем «оно пропало»


class SessionManager:
    def __init__(self, settings: dict, db: Database, clock: Clock | None = None,
                 bus: EventBus | None = None, monitor=None, classifier=None,
                 phone=None, device=None, blocker=None, nudge_player=None):
        self.clock = clock or RealClock()
        # Без явного блокировщика ничего не закрываем (тесты, демо).
        self.blocker = blocker or NullBlocker()
        self.extension_seen = None   # когда расширение браузера последний раз спрашивало сайты
        self.strict_guard = None     # StrictGuard (флаг для сторожа); ставит __main__, в тестах его нет
        self._pw_fails = 0           # неверные пароли подряд
        self._pw_blocked_until = 0.0
        self._ext_alerted = False
        self.bus = bus or EventBus()
        self.db = db
        self.phones = PhoneHub(db, self.clock, self.bus)   # телефоны по Wi-Fi
        self.monitor = monitor if isinstance(monitor, SafeMonitor) else SafeMonitor(monitor or FallbackMonitor())
        self.classifier = classifier or Classifier(load_rules())
        # Без датчика телефон «не подключён»: сессия стартует только по сигналу
        # USB/подставки (в dev/demo телефон кладут вручную из панели).
        self.phone = phone or MockPhoneSensor(docked=False)
        self.device = device or MockDeviceOutput()
        self.lock = threading.RLock()

        self.reactions = Reactions(self.device, self.clock, self.bus, settings.get("sound"), nudge_player)
        db.close_unfinished_sessions()

        self.state = IDLE
        self.session = None          # данные текущей сессии (dict) или None
        self.sm = None               # машина состояний текущей сессии
        self.settings = {}
        self.speed = 1.0
        self.apply_settings(settings)
        self.paused = False
        self.notebook = False
        self.forced_category = None  # из панели разработчика
        self.game_now = 0.0          # «игровое» время в секундах
        self.last_tick = self.clock.now()
        self.prev_docked = self.phone.is_docked()
        self.activity = {"category": "neutral", "process": "unknown", "idle_s": 0.0}
        self.message = None          # сообщение для интерфейса (например, «отдохни»)
        self.pending_events = []     # события для WebSocket
        self.bus.subscribe("*", self._collect_event)
        self.reactions.set_led("OFF")
        if hasattr(self.phone, "on_button"):
            self.phone.on_button(self._on_button)

    # ---------- настройки ----------

    def apply_settings(self, settings: dict):
        with self.lock:
            self.settings = settings
            self.speed = speed_of(settings)
            if self.sm:
                self.sm.th.update(settings["thresholds"])
            self.reactions.set_sound_cfg(settings.get("sound"))
            device = settings.get("device", {})
            if hasattr(self.phone, "set_port"):   # настоящая подставка: порт из настроек
                self.phone.set_port(device.get("serial_port", ""))
            if hasattr(self.phone, "set_phone_source"):
                self.phone.set_phone_source(device.get("phone_source", "auto"))
            usb = getattr(self.phone, "usb", None)
            if usb is not None:   # телефон, привязанный по USB-кабелю
                paired = device.get("usb_phone") or {}
                usb.set_paired(paired.get("id", ""), paired.get("name", ""))

    def close(self):
        """Вызывается при остановке сервера: закрываем порт подставки."""
        closer = getattr(self.phone, "shutdown", None) or getattr(self.phone, "stop", None)
        if closer:
            closer()

    @property
    def dev_tools(self) -> bool:
        return self.settings.get("mode") in ("dev", "demo")

    def default_length_min(self) -> float:
        s = self.settings["session"]
        if self.settings.get("mode") == "demo":
            return s.get("demo_length_min", s["default_length_min"])
        return s["default_length_min"]

    # ---------- события ----------

    def _collect_event(self, topic: str, data: dict):
        self.pending_events.append({**data, "type": topic})
        del self.pending_events[:-50]   # храним только последние 50

    def take_events(self) -> list[dict]:
        with self.lock:
            events, self.pending_events = self.pending_events, []
            return events

    def _set_state(self, new_state: str):
        prev, self.state = self.state, new_state
        session_id = self.session["id"] if self.session else None
        self.db.add_event(session_id, self.clock.now(), new_state,
                          self.activity["category"], self.activity["process"])
        self.bus.publish("state_changed", {"state": new_state, "prev": prev,
                                           "label": STATE_LABELS[new_state]})

    # ---------- жизненный цикл сессии ----------

    def start_session(self, length_min: float | None = None, without_phone: bool = False):
        """without_phone — тренировка без телефона: время считается в статистике."""
        with self.lock:
            if self.session:
                raise AppError("Сессия уже идёт")
            if not without_phone and not self.phone.is_docked():
                raise AppError("Подключи телефон кабелем или поставь на подставку — "
                                "без него таймер не запускается.")
            length = float(length_min or self.default_length_min())
            if length <= 0:
                raise AppError("Длина сессии должна быть больше нуля")
            now = self.clock.now()
            self.session = {
                "id": self.db.start_session(now, length, practice=without_phone),
                "start": now,
                "planned_s": length * 60,
                "elapsed_s": 0.0,
                "totals": {},
                "no_phone": without_phone,
                "pomo": self._pomodoro_plan(length),
                "phase": "work",         # work | break
                "phase_s": 0.0,          # секунд в текущем отрезке (работа или перерыв)
                "cycle": 0,              # сколько рабочих отрезков закончилось перерывом
                "break_len_s": 0.0,
                "break_long": False,
            }
            self.sm = StateMachine(self.settings["thresholds"], start_state=FOCUS)
            self.paused = self.notebook = False
            self.message = "Тренировка без телефона: время идёт в статистику." if without_phone else None
            self.bus.publish("session_started", {"length_min": length})
            self._set_state(FOCUS)
            self._save()
            return self.snapshot()

    # ---------- Pomodoro ----------

    def _pomodoro_plan(self, length_min: float) -> dict | None:
        """Перерывы нужны только длинным сессиям. Длины считаем в «игровых» секундах, как и саму сессию."""
        cfg = self.settings.get("pomodoro", {})
        if not cfg.get("enabled", True) or length_min < cfg.get("min_session_min", 50):
            return None
        return {"work_s": cfg.get("work_min", 25) * 60, "short_s": cfg.get("short_break_min", 5) * 60,
                "long_s": cfg.get("long_break_min", 25) * 60, "cycles": int(cfg.get("cycles", 4))}

    def on_break(self) -> bool:
        return bool(self.session) and self.session.get("phase") == "break"

    def _wall_left_s(self) -> float:
        """Сколько секунд осталось до конца сессии вместе с будущими перерывами (для сторожа)."""
        s = self.session
        left = max(0.0, s["planned_s"] - s["elapsed_s"])
        pomo = s.get("pomo")
        if not pomo:
            return left
        on_break = s["phase"] == "break"
        extra = max(0.0, s["break_len_s"] - s["phase_s"]) if on_break else 0.0
        until_break = pomo["work_s"] - (0.0 if on_break else s["phase_s"])
        cycle, work = s["cycle"], left
        while work - until_break >= 60:        # так же решает _maybe_start_break
            work -= until_break
            cycle += 1
            extra += pomo["long_s"] if cycle % pomo["cycles"] == 0 else pomo["short_s"]
            until_break = pomo["work_s"]
        return left + extra

    def _maybe_start_break(self):
        """Отработали рабочий отрезок — начинаем перерыв (если до конца сессии ещё есть что работать)."""
        s = self.session
        pomo = s.get("pomo")
        if not pomo or s["phase"] != "work" or s["phase_s"] < pomo["work_s"]:
            return
        if s["planned_s"] - s["elapsed_s"] < 60:
            return
        s["cycle"] += 1
        long = s["cycle"] % pomo["cycles"] == 0
        s["phase"], s["phase_s"], s["break_long"] = "break", 0.0, long
        s["break_len_s"] = pomo["long_s"] if long else pomo["short_s"]
        self.paused = self.notebook = False
        self.message = None
        self._set_state(BREAK)
        minutes = round(s["break_len_s"] / 60)
        self.bus.publish("break_started", {
            "long": long, "minutes": minutes, "cycle": s["cycle"],
            "message": (f"Длинный перерыв {minutes} мин: отдохни как следует ☕" if long
                        else f"Перерыв {minutes} мин ☕ Блокировка выключена, потом включится сама."),
        })

    def _tick_break(self, dt: float):
        s = self.session
        s["totals"][BREAK] = s["totals"].get(BREAK, 0.0) + dt
        s["phase_s"] += dt
        self._save()
        if s["phase_s"] >= s["break_len_s"]:
            self._end_break(early=False)

    def _end_break(self, early: bool):
        s = self.session
        s["phase"], s["phase_s"] = "work", 0.0
        self.sm = StateMachine(self.settings["thresholds"], start_state=FOCUS)    # после отдыха начинаем «с чистого листа»
        self.paused = self.notebook = False
        self._set_state(FOCUS)
        self.bus.publish("break_ended", {
            "early": early, "message": "Перерыв закончился: блокировка снова включена. Продолжаем 🐟"})

    def skip_break(self):
        """Закончить перерыв раньше. Это возврат к работе, а не ослабление защиты: пароль не нужен."""
        with self.lock:
            if not self.on_break():
                raise AppError("Сейчас не перерыв")
            self._end_break(early=True)
            self._save()
            return self.snapshot()

    def end_session(self, reason: str = "manual", reason_code: str | None = None,
                    reason_note: str | None = None):
        with self.lock:
            if not self.session:
                raise AppError("Сессия не идёт")
            s = self.session
            self.db.update_session(s["id"], s["totals"], end=self.clock.now(), end_reason=reason)
            if reason_code:
                self.db.set_session_reason(s["id"], reason_code, reason_note)
            self._set_state(IDLE)
            self._save()
            focus_min = round((s["totals"].get("FOCUS", 0) + s["totals"].get("NOTEBOOK", 0)) / 60)
            break_min = self.settings["session"].get("break_min", 5)
            self.message = {
                "time_up": f"Время вышло! Ты в фокусе {focus_min} мин. Отдохни {break_min} минут ☕",
                "phone_out": "Сессия завершена: телефон долго был вне подставки.",
            }.get(reason, f"Сессия завершена. В фокусе: {focus_min} мин.")
            self.bus.publish("session_ended", {"reason": reason, "focus_min": focus_min, "session_id": s["id"],
                                               "message": self.message})
            self.session = None
            self.sm = None
            self.paused = self.notebook = False

    def _require_session(self):
        if not self.session:
            raise AppError("Сессия не идёт")

    def pause(self):
        with self.lock:
            self._require_session()
            if self.on_break():
                raise AppError("Сейчас перерыв: пауза не нужна, отдыхай ☕")
            self.paused = True
            self._update_state()

    def resume(self):
        with self.lock:
            self._require_session()
            self.paused = False
            self._update_state()

    def set_notebook(self, on: bool):
        with self.lock:
            self._require_session()
            if self.on_break():
                raise AppError("Сейчас перерыв")
            self.notebook = bool(on)
            self._update_state()

    def confirm_presence(self):
        """Ответ «Я здесь» на вопрос в режиме тетради."""
        with self.lock:
            self._require_session()
            self.sm.confirm_presence(self.game_now)

    def _update_state(self):
        """Пересчитать состояние сразу (по кнопке), не дожидаясь тика."""
        if self.on_break():
            return
        inp = Inputs(self._phone_ok(), self.activity["idle_s"], self.activity["category"],
                     self.notebook, self.paused)
        new_state = self.sm.update(inp, self.game_now)
        if new_state != self.state:
            self._set_state(new_state)

    def _phone_ok(self) -> bool:
        """В тренировке без телефона телефон не проверяем."""
        if self.session and self.session.get("no_phone"):
            return True
        return self.phone.is_docked()

    # ---------- тик ----------

    def tick(self):
        with self.lock:
            now = self.clock.now()
            dt_real = max(0.0, min(now - self.last_tick, MAX_DT_S))
            self.last_tick = now
            dt = dt_real * self.speed
            self.game_now += dt

            self._read_activity()
            self._run_blocker()
            self._watch_strict()
            docked = self.phone.is_docked()
            just_docked = docked and not self.prev_docked
            self.prev_docked = docked

            if self.session is None:
                if just_docked and self.settings["session"].get("auto_start_on_dock", True):
                    self.start_session()
                return

            if self.on_break():           # отдыхаем: ни рост, ни отвлечения, ни телефон не проверяем
                self._tick_break(dt)
                return

            self._update_state()
            self.reactions.tick(self.speed)   # звуки-«возвращалки» при долгом отвлечении

            s = self.session
            s["totals"][self.state] = s["totals"].get(self.state, 0.0) + dt
            if self.state != PAUSED:
                s["elapsed_s"] += dt
                s["phase_s"] += dt
            self._save()
            self._check_auto_end()
            if self.session:
                self._maybe_start_break()

    def _read_activity(self):
        sample = self.monitor.sample()
        category = self.classifier.classify(sample.process_name, sample.window_title)
        idle = sample.idle_seconds
        process = sample.process_name
        if self.forced_category:
            # «Разработчик сам решает»: настоящее окно не учитываем,
            # чтобы в статистике не винить ни в чём не повинную программу.
            category, idle, process = self.forced_category, 0.0, FORCED_PROCESS
        # Заголовок окна дальше не передаём и не сохраняем.
        self.activity = {"category": category, "process": process, "idle_s": idle}

    def _blocklist(self) -> list[str]:
        """Программы из правил с категорией «отвлечение» (заголовки вкладок — для расширения)."""
        names = []
        for rule in self.classifier.rules["rules"]:
            if rule["category"] == "distraction":
                names += rule.get("process", [])
        return names

    def site_blocklist(self) -> list[str]:
        """Сайты из правил с категорией «отвлечение» — для расширения браузера."""
        domains = []
        for rule in self.classifier.rules["rules"]:
            if rule["category"] == "distraction":
                domains += rule.get("domains", [])
        return list(dict.fromkeys(domains))

    def whitelist_mode(self) -> bool:
        return self.settings.get("protection", {}).get("list_mode", "blacklist") == "whitelist"

    def app_allowlist(self) -> list[str]:
        """Белый список программ: имена процессов в нижнем регистре."""
        words = self.settings.get("protection", {}).get("allow_apps", [])
        return list(dict.fromkeys(w.strip().lower() for w in words if w.strip()))

    def site_allowlist(self) -> list[str]:
        """Белый список сайтов: только домены, без https:// и пути."""
        words = self.settings.get("protection", {}).get("allow_sites", [])
        return list(dict.fromkeys(d for d in map(normalize_domain, words) if d))

    def phone_protection_active(self) -> bool:
        """Защита телефона: в сессии, не на паузе и если защищаем телефон."""
        targets = self.settings.get("protection", {}).get("targets", "pc")
        return (self.session is not None and not self.paused and not self.on_break()
                and targets in ("phone", "both"))

    def phone_state(self) -> dict:
        """Что сообщаем телефону по Wi-Fi (см. docs/PHONE_PROTOCOL.md)."""
        with self.lock:
            s = self.session
            protection = self.settings.get("protection", {})
            return {
                "active": self.phone_protection_active(),
                "hard": protection.get("strictness", "soft") == "hard",
                "list_mode": protection.get("list_mode", "blacklist"),
                "remaining_s": round(max(0.0, s["planned_s"] - s["elapsed_s"])) if s else 0,
                "session_id": s["id"] if s else None,
                # Перерыв Pomodoro: телефон не блокирует, но показывает, сколько отдыхать.
                "break_left_s": round(max(0.0, s["break_len_s"] - s["phase_s"])) if self.on_break() else 0,
            }

    # ---------- строгий режим ----------

    def strict_locked(self) -> bool:
        """Идёт сессия с жёсткой защитой: досрочно выйти можно только с паролем."""
        return self.session is not None and self.settings.get("protection", {}).get("strictness") == "hard"

    def password_set(self) -> bool:
        return self.db.get_secret("strict_password") is not None

    def forbid_in_strict(self, what: str):
        """Правки, которыми можно обойти защиту (правила, привязки, телефоны), закрыты до конца
        строгой сессии. Выйти из неё можно с паролем: после этого правки снова доступны."""
        if self.strict_locked():
            raise AppError(f"Строгий режим: {what} нельзя менять во время сессии. "
                            "Дождитесь конца или завершите сессию с паролем.")

    def require_unlock(self, password: str | None):
        """Проверка перед паузой, досрочным концом или сменой защиты в строгой сессии."""
        with self.lock:      # проверка и счётчик ошибок одним куском: параллельный перебор не обходит лимит
            self._require_unlock(password)

    def _require_unlock(self, password: str | None):
        if not self.strict_locked():
            return
        stored = self.db.get_secret("strict_password")
        if stored is None:
            raise AppError("Строгий режим: до конца таймера выйти нельзя. "
                            "Задай пароль в настройках, чтобы иметь запасной выход.")
        now = self.clock.now()
        if now < self._pw_blocked_until:
            raise AppError(f"Слишком много неверных паролей. Подожди {round(self._pw_blocked_until - now)} с.")
        if not password or not verify_password(password, stored):
            self._pw_fails += 1
            if self._pw_fails >= MAX_FAILS:
                self._pw_fails = 0
                self._pw_blocked_until = now + LOCKOUT_S
            raise AppError("Строгий режим: нужен верный пароль")
        self._pw_fails = 0

    def set_password(self, new: str, old: str | None = None):
        new_hash = hash_password(new) if len(new or "") >= MIN_PASSWORD_LEN else None   # считаем вне блокировки
        with self.lock:
            if self.strict_locked():
                raise AppError("Во время строгой сессии пароль менять нельзя")
            stored = self.db.get_secret("strict_password")
            if stored is not None and not (old and verify_password(old, stored)):
                raise AppError("Старый пароль неверный")
            if new_hash is None:
                raise AppError(f"Пароль не короче {MIN_PASSWORD_LEN} символов")
            self.db.set_secret("strict_password", new_hash)

    def clear_password(self, old: str | None):
        with self.lock:
            if self.strict_locked():
                raise AppError("Во время строгой сессии пароль убирать нельзя")
            stored = self.db.get_secret("strict_password")
            if stored is not None and not (old and verify_password(old, stored)):
                raise AppError("Пароль неверный")
            self.db.set_secret("strict_password", None)

    def extension_lost(self) -> bool:
        """В строгой сессии расширение, которое раньше отвечало, замолчало (его отключили)."""
        targets = self.settings.get("protection", {}).get("targets", "pc")
        return (self.strict_locked() and targets in ("pc", "both") and self.extension_seen is not None
                and not self.extension_connected())

    def strict_view(self) -> dict:
        return {"locked": self.strict_locked(), "password_set": self.password_set(),
                "extension_lost": self.extension_lost()}

    def _watch_strict(self):
        """Каждый тик: флаг для сторожа и сообщение, если отключили расширение."""
        locked = self.strict_locked()
        if self.strict_guard:
            try:
                s = self.session
                left = self._wall_left_s() / max(self.speed, 1.0) if s else 0.0
                self.strict_guard.update(locked, self.clock.now() + left + GRACE_S)
            except Exception:
                log.exception("Не удалось обновить флаг сторожа")
        lost = self.extension_lost()
        if lost and not self._ext_alerted:
            self.bus.publish("extension_lost", {"message": "Расширение браузера отключено: сайты не блокируются."})
        self._ext_alerted = lost

    def pc_protection_active(self) -> bool:
        """Защита компьютера (программы и сайты): только в сессии, не на паузе
        и если в настройках защищаем компьютер."""
        targets = self.settings.get("protection", {}).get("targets", "pc")
        return (self.session is not None and not self.paused and not self.on_break()
                and targets in ("pc", "both"))

    def sites_view(self) -> dict:
        """Ответ для расширения. Заодно запоминаем, что оно на связи.

        Тик держит замок, пока опрашивает окна и процессы, и может занять секунду. Расширению ждать
        нельзя (оно решит «программы нет»), поэтому при занятом замке отдаём последний ответ."""
        self.extension_seen = self.clock.now()
        cache = getattr(self, "_sites_cache", None)
        if not self.lock.acquire(timeout=0.5 if cache else -1):
            return cache
        try:
            view = self._build_sites_view()
        finally:
            self.lock.release()
        self._sites_cache = view
        return view

    def _build_sites_view(self) -> dict:
        s = self.session
        whitelist = self.whitelist_mode()
        allow = self.site_allowlist()
        return {
            # Пустой белый список ничего не блокирует (см. AppBlocker.update).
            "active": self.pc_protection_active() and not (whitelist and not allow),
            "hard": self.settings.get("protection", {}).get("strictness", "soft") == "hard",
            "mode": "whitelist" if whitelist else "blacklist",
            "domains": self.site_blocklist(),
            "allow": allow,
            "remaining_s": max(0.0, s["planned_s"] - s["elapsed_s"]) if s else 0.0,
        }

    def extension_connected(self) -> bool:
        """Расширение опрашивает сервер раз в полминуты; 90 с тишины — значит, его нет или выключили."""
        return self.extension_seen is not None and self.clock.now() - self.extension_seen < EXTENSION_TIMEOUT_S

    def _run_blocker(self):
        """Блокировка программ: см. pc_protection_active()."""
        protection = self.settings.get("protection", {})
        active = self.pc_protection_active()
        if hasattr(self.blocker, "warn_s"):
            self.blocker.warn_s = protection.get("warn_s", self.blocker.warn_s)
        try:
            events = self.blocker.update(self.clock.now(), active,
                                         protection.get("strictness", "soft") == "hard",
                                         self._blocklist(),
                                         self.app_allowlist() if self.whitelist_mode() else None)
        except Exception:   # ошибка блокировщика не должна ронять сессию
            log.exception("Ошибка блокировки приложений")
            return
        for event in events:
            self.bus.publish(event["type"], event)

    def _check_auto_end(self):
        s = self.session
        limit_s = self.settings["session"]["auto_end_after_phone_out_min"] * 60
        phone_out_since = self.sm.phone_out_since
        if phone_out_since is not None and self.game_now - phone_out_since >= limit_s:
            self.end_session("phone_out")
        elif s["elapsed_s"] >= s["planned_s"]:
            self.end_session("time_up")

    def _save(self):
        if self.session:
            self.db.update_session(self.session["id"], self.session["totals"])

    # ---------- кнопка на подставке ----------

    def _on_button(self, name: str):
        """Короткое нажатие — пауза/продолжить (или старт), долгое — режим тетради."""
        try:
            with self.lock:
                if name == "PAUSE":
                    if self.strict_locked() and not self.paused:
                        raise AppError("Строгий режим: паузу можно только с паролем в приложении")
                    if not self.session:
                        self.start_session()
                    elif self.paused:
                        self.resume()
                    else:
                        self.pause()
                elif name == "NOTEBOOK" and self.session:
                    self.set_notebook(not self.notebook)
        except AppError as exc:
            log.info("Кнопка %s: %s", name, exc)

    # ---------- панель разработчика ----------

    def set_phone_docked(self, docked: bool):
        with self.lock:
            if not hasattr(self.phone, "set_docked"):
                raise AppError("Датчик телефона не виртуальный")
            self.phone.set_docked(bool(docked))

    def set_forced_category(self, category: str | None):
        with self.lock:
            if category not in (None, *CATEGORIES):
                raise AppError(f"Категория должна быть одной из {CATEGORIES}")
            self.forced_category = category

    def usb_view(self) -> dict | None:
        usb = getattr(self.phone, "usb", None)
        return usb.view() if usb is not None else None

    # ---------- снимок для интерфейса ----------

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "mode": self.settings.get("mode", "normal"),
                "speed": self.speed,
                "dev_tools": self.dev_tools,
                "state": self.state,
                "state_label": STATE_LABELS[self.state],
                "session": self._session_view(),
                "activity": {**self.activity, "available": self.monitor.available,
                             "monitor": self.monitor.name, "error": self.monitor.last_error,
                             "hint": getattr(self.monitor, "hint", None),
                             "forced_category": self.forced_category},
                "phone": {"docked": self.phone.is_docked(), "source": self.phone.source,
                          "usb": self.usb_view()},
                "device": self._device_view(),
                "protection": {**self.settings.get("protection", {}),
                               **self.blocker.view(self.clock.now()),
                               "extension_connected": self.extension_connected(),
                               "phones_online": self.phones.online_count(),
                               "strict": self.strict_view()},
                "message": self.message,
                "pomodoro": self.settings.get("pomodoro", {}),
            }

    def _session_view(self):
        s = self.session
        if not s:
            return None
        return {
            "id": s["id"],
            "elapsed_s": s["elapsed_s"],
            "planned_s": s["planned_s"],
            "remaining_s": max(0.0, s["planned_s"] - s["elapsed_s"]),
            "totals": s["totals"],
            "paused": self.paused,
            "notebook": self.notebook,
            "ask_presence": self.sm.ask_presence,
            "no_phone": s.get("no_phone", False),
            "pomodoro": self._pomodoro_view(s),
        }

    def _pomodoro_view(self, s):
        pomo = s.get("pomo")
        if not pomo:
            return None
        on_break = s["phase"] == "break"
        return {
            "phase": s["phase"],
            "cycle": s["cycle"],                    # сколько перерывов уже было
            "cycles": pomo["cycles"],
            "break_long": s["break_long"] if on_break else False,
            "phase_left_s": max(0.0, (s["break_len_s"] if on_break else pomo["work_s"]) - s["phase_s"]),
            "break_s": s["totals"].get(BREAK, 0.0),
            "phase_total_s": s["break_len_s"] if on_break else pomo["work_s"],
        }

    def _device_view(self):
        device = self.device
        return {
            "connected": device.is_connected(),
            "source": device.source,
            "led": getattr(device, "led", None),
            "last_sound": getattr(device, "last_sound", None),
            "error": self.reactions.device_error,
            "status": getattr(device, "status_text", lambda: None)(),
        }
