"""Реакции подставки на состояние (раздел 10 ТЗ).

Свет меняется сразу. Звуки — с ограничением частоты, чтобы не раздражать:
- любые два звука не чаще, чем раз в sound.min_gap_s;
- «отвлёкся» (SOUND 2) не чаще раза в sound.distracted_repeat_s;
- «телефон вынут» (SOUND 1) — один раз за эпизод.
Время для ограничений — настоящее (Clock), а не ускоренное демо-время.
"""
from focusfarm import nudge_sounds
from focusfarm.session.state_machine import (
    DISTRACTED, FOCUS, IDLE, MAYBE_DISTRACTED, NOTEBOOK, PAUSED, PHONE_OUT,
)

LED_FOR_STATE = {
    IDLE: "OFF",
    FOCUS: "GREEN",
    NOTEBOOK: "GREEN",
    MAYBE_DISTRACTED: "YELLOW",
    DISTRACTED: "RED",
    PHONE_OUT: "BLINK_RED",
    PAUSED: "BLUE",
    "BREAK": "BLUE",     # перерыв Pomodoro (состояния нет в машине состояний, им управляет менеджер)
}

SOUND_SOFT, SOUND_DISTRACTED, SOUND_START = 1, 2, 4   # номер 3 в прошивке свободен

# Мягкие уведомления в интерфейсе.
NOTICE_FOR_STATE = {
    MAYBE_DISTRACTED: "Кажется, ты отвлёкся. Вернись к работе",
    DISTRACTED: "Ты отвлёкся: вернись к работе",
    PHONE_OUT: "Телефон отключён — верни его на подставку или подключи кабель",
}


NUDGE_DEFAULTS = {"enabled": True, "after_s": [60, 180, 360, 600], "repeat_s": 120, "volume": 0.6}


class Reactions:
    def __init__(self, device, clock, bus, sound_cfg: dict | None = None, nudge_player=None):
        self.device = device
        self.clock = clock
        self.bus = bus
        self.cfg = {"enabled": True, "distracted_repeat_s": 180, "min_gap_s": 5}
        self.nudge_cfg = dict(NUDGE_DEFAULTS)
        self.set_sound_cfg(sound_cfg)
        # Проигрыватель системного звука: play(level, volume) -> bool. Без явного проигрывателя
        # молчим (тесты, демо); настоящий (nudge_sounds.play_system) ставит build_manager.
        self.nudge_player = nudge_player or (lambda level, volume: False)
        self._last_sound_at = None
        self._last_distracted_at = None
        self.device_error = None
        self._distracted_since = None   # когда началось непрерывное отвлечение (настоящее время)
        self._nudge_done = 0            # сколько уровней уже прозвучало в этом эпизоде
        self._last_nudge_at = None

        bus.subscribe("state_changed", self._on_state_changed)
        bus.subscribe("session_started", lambda d: self.play(SOUND_START))

    def set_sound_cfg(self, sound_cfg: dict):
        cfg = dict(sound_cfg or {})
        self.nudge_cfg.update(cfg.pop("nudge", None) or {})
        self.cfg.update(cfg)

    def tick(self, speed: float = 1.0):
        """Раз в секунду: если отвлечение затянулось, включает следующий уровень звука-«возвращалки».

        speed — ускорение демо: пороги меряются игровым временем, как и всё остальное.
        """
        cfg = self.nudge_cfg
        if self._distracted_since is None or not self.cfg["enabled"] or not cfg["enabled"]:
            return
        steps = sorted(cfg["after_s"])
        if not steps:
            return
        now = self.clock.now()
        elapsed = (now - self._distracted_since) * speed
        due = sum(1 for s in steps if elapsed >= s)
        if due > self._nudge_done:
            self._nudge_done = due
            self._nudge(due)
        elif due == len(steps) and self._last_nudge_at is not None:
            if (now - self._last_nudge_at) * speed >= max(10, cfg["repeat_s"]):
                self._nudge(due)

    def _nudge(self, level: int):
        """Звук уровня level (1..4) системным плеером; если не вышло — браузер сыграет свой тон."""
        now = self.clock.now()
        self._last_nudge_at = now
        self._last_sound_at = now
        try:
            played = bool(self.nudge_player(level, self.nudge_cfg["volume"]))
        except Exception as exc:
            self.device_error = str(exc)
            played = False
        self.bus.publish("nudge", {"level": level, "system": played})

    def _on_state_changed(self, data: dict):
        state, prev = data["state"], data.get("prev")
        self.set_led(LED_FOR_STATE.get(state, "OFF"))
        if state != DISTRACTED:           # вернулся, пауза, перерыв, конец сессии — эпизод закончен
            self._distracted_since = None
        elif prev != DISTRACTED or self._distracted_since is None:
            self._distracted_since = self.clock.now()
            self._nudge_done = 0
            self._last_nudge_at = None
        if state in NOTICE_FOR_STATE:
            self.bus.publish("notice", {"text": NOTICE_FOR_STATE[state], "state": state})
        if state == DISTRACTED:
            now = self.clock.now()
            last = self._last_distracted_at
            if last is None or now - last >= self.cfg["distracted_repeat_s"]:
                if self.play(SOUND_DISTRACTED):
                    self._last_distracted_at = now
        elif state == PHONE_OUT and prev != PHONE_OUT:
            self.play(SOUND_SOFT)

    def set_led(self, color: str):
        try:
            self.device.set_led(color)
            self.device_error = None
        except Exception as exc:  # ошибка подставки не роняет программу
            self.device_error = str(exc)

    def play(self, n: int) -> bool:
        """Проигрывает звук, если можно. Возвращает True, если звук прозвучал."""
        if not self.cfg["enabled"]:
            return False
        now = self.clock.now()
        if self._last_sound_at is not None and now - self._last_sound_at < self.cfg["min_gap_s"]:
            return False
        self._last_sound_at = now
        try:
            self.device.play_sound(n)
        except Exception as exc:
            self.device_error = str(exc)
        self.bus.publish("sound", {"n": n})   # браузер может проиграть свой звук
        return True
