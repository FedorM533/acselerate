"""Машина состояний учебной сессии (раздел 8 ТЗ).

Здесь нет ввода-вывода: только входы → состояние. Время передаётся
параметром `now` (секунды), поэтому логику легко проверять тестами.
"""
from dataclasses import dataclass

IDLE = "IDLE"
FOCUS = "FOCUS"
NOTEBOOK = "NOTEBOOK"
MAYBE_DISTRACTED = "MAYBE_DISTRACTED"
DISTRACTED = "DISTRACTED"
PHONE_OUT = "PHONE_OUT"
PAUSED = "PAUSED"

ALL_STATES = (IDLE, FOCUS, NOTEBOOK, MAYBE_DISTRACTED, DISTRACTED, PHONE_OUT, PAUSED)
GOOD_STATES = (FOCUS, NOTEBOOK)  # в них растут рыбки
# Из этих состояний возвращаемся в FOCUS только после recover_s «хороших» секунд.
HYSTERESIS_STATES = (MAYBE_DISTRACTED, DISTRACTED, PHONE_OUT)


@dataclass
class Inputs:
    """Что машина получает каждую секунду."""
    phone_docked: bool = True
    idle_seconds: float = 0
    category: str = "work"      # work | neutral | distraction
    notebook_mode: bool = False
    paused: bool = False


DEFAULT_THRESHOLDS = {
    "phone_grace_s": 30,
    "distraction_confirm_s": 30,
    "neutral_limit_s": 90,
    "idle_limit_s": 180,
    "maybe_to_distracted_s": 180,
    "recover_s": 5,
    "notebook_max_min": 45,
    "notebook_answer_s": 120,
}


class StateMachine:
    def __init__(self, thresholds: dict | None = None, start_state: str = FOCUS):
        self.th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.state = start_state
        self._reset_timers()

    # ---------- служебное ----------

    def _reset_timers(self):
        self.phone_out_since = None   # когда вынули телефон
        self.category = None          # текущая категория окна
        self.category_since = None    # с какого момента эта категория
        self.maybe_since = None       # с какого момента «неуверенное» MAYBE (правило 6)
        self.good_since = None        # с какого момента идут «хорошие» сигналы (гистерезис)
        self.notebook_since = None    # с какого момента включён режим тетради
        self.ask_presence = False     # показать вопрос «Ты ещё здесь?»

    def confirm_presence(self, now: float):
        """Пользователь ответил «Я здесь» — режим тетради считается заново."""
        if self.notebook_since is not None:
            self.notebook_since = now
        self.ask_presence = False

    # ---------- основная логика ----------

    def update(self, inp: Inputs, now: float) -> str:
        """Один тик. Возвращает новое состояние (и сохраняет его в self.state)."""
        self.state = self._next_state(inp, now)
        return self.state

    def _next_state(self, inp: Inputs, now: float) -> str:
        th = self.th

        # Правило 1: пауза важнее всего. Таймеры сбрасываем,
        # чтобы после паузы начать «с чистого листа».
        if inp.paused:
            self._reset_timers()
            return PAUSED

        self._track_timers(inp, now)

        # Правило 2: телефон вынут. Льготный период — оставляем прошлое состояние.
        if not inp.phone_docked:
            self.good_since = None
            if now - self.phone_out_since >= th["phone_grace_s"]:
                return PHONE_OUT
            return self.state if self.state != PAUSED else FOCUS

        raw = self._raw_state(inp, now)
        return self._apply_hysteresis(raw, now)

    def _track_timers(self, inp: Inputs, now: float):
        """Запоминает, с какого момента длится каждое условие."""
        if inp.phone_docked:
            self.phone_out_since = None
        elif self.phone_out_since is None:
            self.phone_out_since = now

        if inp.category != self.category:
            self.category = inp.category
            self.category_since = now

        if inp.notebook_mode:
            if self.notebook_since is None:
                self.notebook_since = now
        else:
            self.notebook_since = None
            self.ask_presence = False

    def _raw_state(self, inp: Inputs, now: float) -> str:
        """Правила 3–7 без учёта гистерезиса."""
        th = self.th
        in_category = now - self.category_since

        # Правило 3: развлекательное окно.
        if inp.category == "distraction":
            self.maybe_since = None
            if in_category >= th["distraction_confirm_s"]:
                return DISTRACTED
            return MAYBE_DISTRACTED

        # Правило 4: режим «пишу в тетради» (простой клавиатуры не важен).
        if inp.notebook_mode:
            return self._notebook_state(now)

        # Правило 5: рабочее окно и человек что-то вводит.
        if inp.category == "work" and inp.idle_seconds < th["idle_limit_s"]:
            self.maybe_since = None
            return FOCUS

        # Правило 6: долго в нейтральном окне или долго без ввода.
        neutral_too_long = inp.category == "neutral" and in_category >= th["neutral_limit_s"]
        idle_too_long = inp.idle_seconds >= th["idle_limit_s"]
        if neutral_too_long or idle_too_long:
            return self._maybe_or_distracted(now)

        # Правило 7: всё остальное — фокус.
        self.maybe_since = None
        return FOCUS

    def _maybe_or_distracted(self, now: float) -> str:
        """MAYBE, а если оно затянулось — DISTRACTED."""
        if self.maybe_since is None:
            self.maybe_since = now
        if now - self.maybe_since >= self.th["maybe_to_distracted_s"]:
            return DISTRACTED
        return MAYBE_DISTRACTED

    def _notebook_state(self, now: float) -> str:
        """Тетрадь ограничена notebook_max_min, затем спрашиваем «Ты ещё здесь?»."""
        limit = self.th["notebook_max_min"] * 60
        in_notebook = now - self.notebook_since
        if in_notebook < limit:
            self.ask_presence = False
            self.maybe_since = None
            return NOTEBOOK
        self.ask_presence = True
        if in_notebook < limit + self.th["notebook_answer_s"]:
            return NOTEBOOK
        # Не ответил — считаем, что, возможно, отвлёкся.
        return self._maybe_or_distracted(now)

    def _apply_hysteresis(self, raw: str, now: float) -> str:
        """Из плохих состояний в хорошие — только после recover_s секунд подряд."""
        if raw not in GOOD_STATES or self.state not in HYSTERESIS_STATES:
            self.good_since = None
            return raw
        if self.good_since is None:
            self.good_since = now
        if now - self.good_since >= self.th["recover_s"]:
            self.good_since = None
            return raw
        return self.state
