"""Реакции подставки на состояние (раздел 10 ТЗ).

Свет меняется сразу. Звуки — с ограничением частоты, чтобы не раздражать:
- любые два звука не чаще, чем раз в sound.min_gap_s;
- «отвлёкся» (SOUND 2) не чаще раза в sound.distracted_repeat_s;
- «телефон вынут» (SOUND 1) — один раз за эпизод.
Время для ограничений — настоящее (Clock), а не ускоренное демо-время.
"""
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
}

SOUND_SOFT, SOUND_DISTRACTED, SOUND_HARVEST, SOUND_START = 1, 2, 3, 4

# Мягкие уведомления в интерфейсе.
NOTICE_FOR_STATE = {
    MAYBE_DISTRACTED: "Кажется, ты отвлёкся. Растения ждут 🌱",
    DISTRACTED: "Рост на паузе: вернись к работе, и пруд снова станет чистым.",
    PHONE_OUT: "Телефон отключён — рыбки ждут, когда он вернётся.",
}


class Reactions:
    def __init__(self, device, clock, bus, sound_cfg: dict | None = None):
        self.device = device
        self.clock = clock
        self.bus = bus
        self.cfg = {"enabled": True, "distracted_repeat_s": 180, "min_gap_s": 5, **(sound_cfg or {})}
        self._last_sound_at = None
        self._last_distracted_at = None
        self.device_error = None

        bus.subscribe("state_changed", self._on_state_changed)
        bus.subscribe("session_started", lambda d: self.play(SOUND_START))
        # Звук «рыбка выпущена» — когда человек сам выпустил рыбку, а не посреди работы.
        bus.subscribe("harvested", lambda d: self.play(SOUND_HARVEST))

    def set_sound_cfg(self, sound_cfg: dict):
        self.cfg.update(sound_cfg or {})

    def _on_state_changed(self, data: dict):
        state, prev = data["state"], data.get("prev")
        self.set_led(LED_FOR_STATE.get(state, "OFF"))
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
