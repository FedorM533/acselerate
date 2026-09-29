"""Простая шина событий (издатель-подписчик).

Пример:
    bus.subscribe("state_changed", lambda data: print(data))
    bus.publish("state_changed", {"state": "FOCUS"})

Подписка на "*" получает все события: handler(topic, data).
"""
import logging
from collections import defaultdict

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, topic: str, handler):
        self._handlers[topic].append(handler)

    def publish(self, topic: str, data: dict | None = None):
        data = data or {}
        for handler in list(self._handlers[topic]):
            self._call(handler, data)
        for handler in list(self._handlers["*"]):
            self._call(handler, topic, data)

    @staticmethod
    def _call(handler, *args):
        # Ошибка одного подписчика не должна ломать остальных.
        try:
            handler(*args)
        except Exception:
            log.exception("Ошибка в обработчике события")
