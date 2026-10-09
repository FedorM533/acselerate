"""Задания дня и ачивки — чистая логика (без базы и без времени компьютера).

Главное правило: награды НЕ отвлекают от работы. Эта часть только считает;
когда показывать и выдавать, решает `session/reward_service.py`
(только на паузе и между сессиями).

Задания всегда про фокус (а не про «зайди в приложение»), не сгорают
с наказанием и дают немного монет: не больше DAILY_COIN_CAP в день.
"""
import datetime as dt
import random

DAILY_COIN_CAP = 30

# kind — какое число из дневной статистики сравниваем с target:
#   focus_min — минут фокуса за день; releases — выпущено рыбок за день;
#   sessions — сессий от 10 минут за день; clean_min — самая длинная сессия без отвлечений.
QUESTS = {
    "focus20": {"id": "focus20", "kind": "focus_min", "target": 20, "reward": 10, "title": "20 минут фокуса"},
    "focus45": {"id": "focus45", "kind": "focus_min", "target": 45, "reward": 15, "title": "45 минут фокуса"},
    "release1": {"id": "release1", "kind": "releases", "target": 1, "reward": 10, "title": "Выпусти одну рыбку"},
    "sessions2": {"id": "sessions2", "kind": "sessions", "target": 2, "reward": 10, "title": "Две сессии за день"},
    "clean15": {"id": "clean15", "kind": "clean_min", "target": 15, "reward": 12,
                "title": "15 минут подряд без отвлечений"},
}
FOCUS_QUESTS = ("focus20", "focus45")
OTHER_QUESTS = ("release1", "sessions2", "clean15")


def daily_quests(day: dt.date) -> list[dict]:
    """Три задания на дату: одно про минуты фокуса и два других. Один день — один набор."""
    rng = random.Random(day.toordinal())
    ids = [rng.choice(FOCUS_QUESTS), *rng.sample(OTHER_QUESTS, 2)]
    return [QUESTS[i] for i in ids]


def quest_progress(quest: dict, stats: dict) -> int:
    """Сколько выполнено (не больше цели)."""
    return int(min(quest["target"], stats.get(quest["kind"], 0)))


def cap_reward(already: int, reward: int, cap: int = DAILY_COIN_CAP) -> int:
    """Сколько монет можно выдать, если сегодня уже выдано `already`."""
    return max(0, min(reward, cap - already))


# ---------- ачивки ----------
# totals: fish_total, species_owned, best_stars, streak, focus_total_h,
#         clean_best_min, buildings_owned.
# Награда: coins (один раз) и/или building (бесплатное здание).

ACHIEVEMENTS = [
    {"id": "first_fish", "title": "Первая рыбка", "desc": "Выпусти первую рыбку в пруд",
     "coins": 5, "check": lambda t: t["fish_total"] >= 1},
    {"id": "fish_5", "title": "Новоселье", "desc": "Выпусти 5 рыбок — получишь домик",
     "building": "house", "check": lambda t: t["fish_total"] >= 5},
    {"id": "fish_25", "title": "Большая семья", "desc": "Выпусти 25 рыбок",
     "coins": 30, "check": lambda t: t["fish_total"] >= 25},
    {"id": "all_species", "title": "Коллекционер", "desc": "Выпусти все 5 видов рыбок",
     "coins": 50, "check": lambda t: t["species_owned"] >= 5},
    {"id": "star3", "title": "Идеальная рыбка", "desc": "Выпусти рыбку с тремя звёздами",
     "coins": 10, "check": lambda t: t["best_stars"] >= 3},
    {"id": "streak3", "title": "Три дня подряд", "desc": "3 дня подряд по 25+ минут фокуса",
     "coins": 15, "check": lambda t: t["streak"] >= 3},
    {"id": "streak7", "title": "Неделя фокуса", "desc": "7 дней подряд — получишь мостик",
     "building": "bridge", "check": lambda t: t["streak"] >= 7},
    {"id": "focus_10h", "title": "10 часов фокуса", "desc": "Суммарно 10 часов — получишь маяк",
     "building": "lighthouse", "check": lambda t: t["focus_total_h"] >= 10},
    {"id": "focus_50h", "title": "50 часов фокуса", "desc": "Суммарно 50 часов",
     "coins": 60, "check": lambda t: t["focus_total_h"] >= 50},
    {"id": "clean45", "title": "Без единой отвлекашки", "desc": "45 минут подряд без отвлечений",
     "coins": 30, "check": lambda t: t["clean_best_min"] >= 45},
    {"id": "builder", "title": "Застройщик", "desc": "Собери все три здания",
     "coins": 25, "check": lambda t: t["buildings_owned"] >= 3},
]
ACHIEVEMENT_BY_ID = {a["id"]: a for a in ACHIEVEMENTS}


def new_achievements(totals: dict, unlocked: set) -> list[dict]:
    """Ачивки, условие которых выполнено, а выдать ещё не успели."""
    return [a for a in ACHIEVEMENTS if a["id"] not in unlocked and a["check"](totals)]
