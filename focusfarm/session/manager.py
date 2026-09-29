"""Менеджер сессии: жизненный цикл сессии и тик раз в секунду.

Каждую секунду:
1. читаем монитор активности и датчик телефона;
2. машина состояний решает, в каком мы состоянии;
3. игра двигает рост/сорняки;
4. всё сохраняется в базу, события уходят в шину (а оттуда — в интерфейс
   и на подставку).

Демо-режим: «игровое» время идёт в `speed` раз быстрее настоящего. Им
измеряются пороги и рост. Время простоя клавиатуры (idle_seconds) НЕ
ускоряем: иначе в демо «кажется, отвлёкся» включалось бы через 6 секунд
без движения мыши, и показывать было бы неудобно.
"""
import threading

from focusfarm.activity.classifier import CATEGORIES, Classifier, load_rules
from focusfarm.activity.fallback import FallbackMonitor
from focusfarm.activity.monitor import SafeMonitor
from focusfarm.clock import Clock, RealClock
from focusfarm.config import speed_of
from focusfarm.device.output import MockDeviceOutput
from focusfarm.events import EventBus
from focusfarm.game.engine import GameEngine, GameError, quality_for
from focusfarm.reactions import Reactions
from focusfarm.sensors.phone import MockPhoneSensor
from focusfarm.session.state_machine import (
    FOCUS, IDLE, MAYBE_DISTRACTED, PAUSED, Inputs, StateMachine,
)
from focusfarm.storage.db import Database

STATE_LABELS = {
    "IDLE": "Сессия не идёт",
    "FOCUS": "Работаешь",
    "NOTEBOOK": "Пишешь в тетради",
    "MAYBE_DISTRACTED": "Кажется, отвлёкся",
    "DISTRACTED": "Отвлёкся",
    "PHONE_OUT": "Телефон вынут",
    "PAUSED": "Пауза",
}

MAX_DT_S = 5  # если компьютер «уснул», не засчитываем пропущенное время разом


class SessionManager:
    def __init__(self, settings: dict, db: Database, clock: Clock | None = None,
                 bus: EventBus | None = None, monitor=None, classifier=None,
                 phone=None, device=None, rng=None):
        self.clock = clock or RealClock()
        self.bus = bus or EventBus()
        self.db = db
        self.monitor = monitor if isinstance(monitor, SafeMonitor) else SafeMonitor(monitor or FallbackMonitor())
        self.classifier = classifier or Classifier(load_rules())
        # Без подставки в обычном режиме считаем, что телефон «лежит» —
        # иначе сессию нельзя было бы вести. В dev/demo телефон кладут вручную.
        self.phone = phone or MockPhoneSensor(docked=settings.get("mode", "normal") == "normal")
        self.device = device or MockDeviceOutput()
        self.lock = threading.RLock()

        self.game = GameEngine(settings.get("game"), rng)
        self.game.load_dict(db.load_farm())
        self.reactions = Reactions(self.device, self.clock, self.bus, settings.get("sound"))
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

    # ---------- настройки ----------

    def apply_settings(self, settings: dict):
        with self.lock:
            self.settings = settings
            self.speed = speed_of(settings)
            if self.sm:
                self.sm.th.update(settings["thresholds"])
            self.reactions.set_sound_cfg(settings.get("sound"))

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

    def start_session(self, plot=None, crop: str | None = None, length_min: float | None = None):
        with self.lock:
            if self.session:
                raise GameError("Сессия уже идёт")
            length = float(length_min or self.default_length_min())
            if length <= 0:
                raise GameError("Длина сессии должна быть больше нуля")
            pos = self.game.begin_session(tuple(plot) if plot else None, crop, length)
            crop_id = self.game.plot(*pos).crop_id if pos else None
            now = self.clock.now()
            self.session = {
                "id": self.db.start_session(now, length, crop_id),
                "start": now,
                "planned_s": length * 60,
                "elapsed_s": 0.0,
                "totals": {},
                "plot": pos,
            }
            self.sm = StateMachine(self.settings["thresholds"], start_state=FOCUS)
            self.paused = self.notebook = False
            self.message = None if pos else "Все грядки заняты урожаем — собери его, чтобы посадить новое."
            self.bus.publish("session_started", {"plot": pos, "crop": crop_id, "length_min": length})
            self._set_state(FOCUS)
            self._save()
            return self.snapshot()

    def end_session(self, reason: str = "manual"):
        with self.lock:
            if not self.session:
                raise GameError("Сессия не идёт")
            s = self.session
            self.db.update_session(s["id"], s["totals"], end=self.clock.now(), end_reason=reason)
            self._set_state(IDLE)
            self.game.end_session()
            self._save()
            focus_min = round((s["totals"].get("FOCUS", 0) + s["totals"].get("NOTEBOOK", 0)) / 60)
            break_min = self.settings["session"].get("break_min", 5)
            self.message = {
                "time_up": f"Время вышло! Ты в фокусе {focus_min} мин. Отдохни {break_min} минут ☕",
                "phone_out": "Сессия завершена: телефон долго был вне подставки.",
            }.get(reason, f"Сессия завершена. В фокусе: {focus_min} мин.")
            self.bus.publish("session_ended", {"reason": reason, "focus_min": focus_min,
                                               "message": self.message})
            self.session = None
            self.sm = None
            self.paused = self.notebook = False

    def _require_session(self):
        if not self.session:
            raise GameError("Сессия не идёт")

    def pause(self):
        with self.lock:
            self._require_session()
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
            self.notebook = bool(on)
            self._update_state()

    def confirm_presence(self):
        """Ответ «Я здесь» на вопрос в режиме тетради."""
        with self.lock:
            self._require_session()
            self.sm.confirm_presence(self.game_now)

    def _update_state(self):
        """Пересчитать состояние сразу (по кнопке), не дожидаясь тика."""
        inp = Inputs(self.phone.is_docked(), self.activity["idle_s"], self.activity["category"],
                     self.notebook, self.paused)
        new_state = self.sm.update(inp, self.game_now)
        if new_state != self.state:
            self._set_state(new_state)

    # ---------- тик ----------

    def tick(self):
        with self.lock:
            now = self.clock.now()
            dt_real = max(0.0, min(now - self.last_tick, MAX_DT_S))
            self.last_tick = now
            dt = dt_real * self.speed
            self.game_now += dt

            self._read_activity()
            docked = self.phone.is_docked()
            just_docked = docked and not self.prev_docked
            self.prev_docked = docked

            if self.session is None:
                if just_docked and self.settings["session"].get("auto_start_on_dock", True):
                    self.start_session()
                return

            self._update_state()
            for event in self.game.tick(self.state, dt, self.clock.today()):
                self.bus.publish(event["type"], event)

            s = self.session
            s["totals"][self.state] = s["totals"].get(self.state, 0.0) + dt
            if self.state != PAUSED:
                s["elapsed_s"] += dt
            self._save()
            self._check_auto_end()

    def _read_activity(self):
        sample = self.monitor.sample()
        category = self.classifier.classify(sample.process_name, sample.window_title)
        idle = sample.idle_seconds
        if self.forced_category:
            category, idle = self.forced_category, 0.0   # «разработчик сам решает»
        # Заголовок окна дальше не передаём и не сохраняем.
        self.activity = {"category": category, "process": sample.process_name, "idle_s": idle}

    def _check_auto_end(self):
        s = self.session
        limit_s = self.settings["session"]["auto_end_after_phone_out_min"] * 60
        phone_out_since = self.sm.phone_out_since
        if phone_out_since is not None and self.game_now - phone_out_since >= limit_s:
            self.end_session("phone_out")
        elif s["elapsed_s"] >= s["planned_s"]:
            self.end_session("time_up")

    def _save(self):
        self.db.save_farm(self.game.to_dict())
        if self.session:
            self.db.update_session(self.session["id"], self.session["totals"])

    # ---------- действия на ферме ----------

    def harvest(self, x: int, y: int) -> dict:
        with self.lock:
            result = self.game.harvest(x, y)
            self._save()
            self.bus.publish("harvested", result)
            return result

    def weed(self, x: int, y: int):
        with self.lock:
            self.game.weed(x, y)
            self._save()
            self.bus.publish("weeded", {"x": x, "y": y})

    def buy(self, item: str):
        with self.lock:
            self.game.buy(item)
            self._save()
            self.bus.publish("bought", {"item": item})

    # ---------- панель разработчика ----------

    def set_phone_docked(self, docked: bool):
        with self.lock:
            if not hasattr(self.phone, "set_docked"):
                raise GameError("Датчик телефона не виртуальный")
            self.phone.set_docked(bool(docked))

    def set_forced_category(self, category: str | None):
        with self.lock:
            if category not in (None, *CATEGORIES):
                raise GameError(f"Категория должна быть одной из {CATEGORIES}")
            self.forced_category = category

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
                             "forced_category": self.forced_category},
                "phone": {"docked": self.phone.is_docked(), "source": self.phone.source},
                "device": self._device_view(),
                "farm": self._farm_view(),
                "message": self.message,
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
            "plot": s["plot"],
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

    def _farm_view(self):
        g = self.game
        today = self.clock.today()
        plots = []
        for (x, y), p in sorted(g.plots.items()):
            view = {"x": x, "y": y, "crop": p.crop_id, "stage": g.stage(x, y), "weeds": p.weeds,
                    "active": self.session is not None and g.active_plot == (x, y)}
            if p.crop_id:
                crop = g.crops[p.crop_id]
                ripe = g.is_ripe(x, y)
                view.update({
                    "crop_name": crop.name,
                    "progress": min(1.0, p.progress_s / crop.grow_s),
                    "left_s": max(0.0, crop.grow_s - p.progress_s),
                    "ripe": ripe,
                    "stars": quality_for(p.quality_hits)[0],
                    "value": g.harvest_value(x, y)["coins"] if ripe else None,
                    "thirsty": view["active"] and self.state == MAYBE_DISTRACTED,
                })
            plots.append(view)
        focus_s = g.session_focus_s
        return {
            "size": g.size,
            "coins": g.coins,
            "streak": g.streak(today),
            "raining": g.is_raining(today),
            "today_focus_s": g.days.get(today.isoformat(), 0.0),
            "can_weed": g.can_weed(),
            "weed_unlock_left_s": max(0.0, g.cfg["weed_unlock_focus_s"] - focus_s),
            "plots": plots,
            "decor": sorted(u.split(":", 1)[1] for u in g.unlocks if u.startswith("decor:")),
            "crops": [{"id": c.id, "name": c.name, "focus_min": c.focus_min, "coins": c.coins,
                       "price": c.price, "unlocked": c.id in g.unlocks} for c in g.crops.values()],
            "shop": g.shop_items(),
        }
