"""Задания и ачивки в игре: считаем, выдаём, храним.

ГЛАВНОЕ ПРАВИЛО — не отвлекать. Награды выдаются и объявляются ТОЛЬКО
когда человек не в фокусе: между сессиями или на паузе (см. manager.py).
Пока идёт работа, этот класс ничего не пишет в игру и ничего не публикует —
прогресс просто лежит в базе и виден на вкладке «Задания».
"""
import datetime as dt
import re

from focusfarm.game.rewards import (
    ACHIEVEMENT_BY_ID, ACHIEVEMENTS, DAILY_COIN_CAP, cap_reward, daily_quests, new_achievements,
    quest_progress,
)

NAME_MAX = 20
SESSION_MIN_S = 10 * 60   # сессия короче 10 минут «сессией» в задании не считается
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_name(raw: str | None) -> str:
    """Имя рыбки: без управляющих символов, одинарные пробелы, до 20 символов."""
    text = _CONTROL.sub("", raw or "")
    return re.sub(r"\s+", " ", text).strip()[:NAME_MAX]


class RewardsService:
    def __init__(self, db, game, clock, bus, enabled: bool = True, quest_picker=daily_quests):
        self.db, self.game, self.clock, self.bus = db, game, clock, bus
        self.enabled = enabled
        self.quest_picker = quest_picker
        self.cap = DAILY_COIN_CAP
        self._unseen = self._count_unseen()

    # ---------- что накоплено за день и всего ----------

    def _day_start(self, day: dt.date) -> float:
        return dt.datetime.combine(day, dt.time.min).timestamp()

    def day_stats(self) -> dict:
        today = self.clock.today()
        start = self._day_start(today)
        sessions = [s for s in self.db.sessions_since(start) if not s.get("practice")]
        focus_s = [(s["focus_s"] or 0) + (s["notebook_s"] or 0) for s in sessions]
        clean = [f for s, f in zip(sessions, focus_s)
                 if (s["distracted_s"] or 0) + (s["phone_out_s"] or 0) == 0]
        return {
            "focus_min": sum(focus_s) / 60,
            "sessions": sum(1 for f in focus_s if f >= SESSION_MIN_S),
            "clean_min": max(clean, default=0) / 60,
            "releases": self.db.count_fish_since(start),
        }

    def totals(self) -> dict:
        sessions = [s for s in self.db.all_sessions() if not s.get("practice")]
        focus_s = [(s["focus_s"] or 0) + (s["notebook_s"] or 0) for s in sessions]
        clean = [f for s, f in zip(sessions, focus_s)
                 if (s["distracted_s"] or 0) + (s["phone_out_s"] or 0) == 0]
        summary = self.db.collection_summary()
        return {
            "fish_total": sum(v["count"] for v in summary.values()),
            "species_owned": sum(1 for v in summary.values() if v["count"] > 0),
            "best_stars": max((v["best_stars"] for v in summary.values()), default=0),
            "streak": self.game.streak(self.clock.today()),
            "focus_total_h": sum(focus_s) / 3600,
            "clean_best_min": max(clean, default=0) / 60,
            "buildings_owned": sum(1 for u in self.game.unlocks if u.startswith("building:")),
        }

    # ---------- выдача (вызывается только вне фокуса) ----------

    def evaluate(self) -> list[dict]:
        """Выдаёт всё, что заработано. Возвращает список наград для показа."""
        if not self.enabled:
            return []
        granted = []
        day = self.clock.today().isoformat()
        stats = self.day_stats()
        claims = self.db.quest_claims(day)
        claimed = {c["quest_id"] for c in claims}
        paid_today = sum(c["coins"] for c in claims)
        for quest in self.quest_picker(self.clock.today()):
            if quest["id"] in claimed or quest_progress(quest, stats) < quest["target"]:
                continue
            coins = cap_reward(paid_today, quest["reward"], self.cap)
            paid_today += coins
            self.db.add_quest_claim(day, quest["id"], coins)
            self.game.coins += coins
            granted.append({"kind": "quest", "id": quest["id"], "title": quest["title"], "coins": coins})

        unlocked = {a["id"] for a in self.db.achievements_list()}
        for ach in new_achievements(self.totals(), unlocked):
            granted.append(self._grant_achievement(ach))

        for reward in granted:
            self.bus.publish("reward", reward)
        if granted:
            self._unseen = self._count_unseen()
        return granted

    def _grant_achievement(self, ach: dict) -> dict:
        coins = ach.get("coins", 0)
        self.db.add_achievement(ach["id"], self.clock.now(), coins)
        self.game.coins += coins
        building = ach.get("building")
        if building:
            self.game.unlocks.add(f"building:{building}")
        return {"kind": "achievement", "id": ach["id"], "title": ach["title"],
                "coins": coins, "building": building}

    def grant_for_test(self, achievement_id: str) -> dict:
        """Только для тестов: выдать ачивку без проверки условия."""
        return self._grant_achievement(ACHIEVEMENT_BY_ID[achievement_id])

    # ---------- показ ----------

    def _count_unseen(self) -> int:
        return self.db.unseen_rewards()

    def mark_seen(self):
        self.db.mark_rewards_seen()
        self._unseen = 0

    def summary(self) -> dict:
        """Крошечный кусок для снимка состояния (без запросов к базе каждую секунду)."""
        return {"enabled": self.enabled, "unseen": self._unseen if self.enabled else 0}

    def view(self) -> dict:
        stats = self.day_stats()
        day = self.clock.today().isoformat()
        claimed = {c["quest_id"] for c in self.db.quest_claims(day)}
        unlocked = {a["id"] for a in self.db.achievements_list()}
        quests = []
        for q in self.quest_picker(self.clock.today()):
            progress = quest_progress(q, stats)
            quests.append({"id": q["id"], "title": q["title"], "target": q["target"], "progress": progress,
                           "done": progress >= q["target"], "reward": q["reward"],
                           "paid": q["id"] in claimed})
        achievements = [{"id": a["id"], "title": a["title"], "desc": a["desc"],
                         "unlocked": a["id"] in unlocked, "coins": a.get("coins", 0),
                         "building": a.get("building")} for a in ACHIEVEMENTS]
        return {"enabled": self.enabled, "quests": quests, "achievements": achievements,
                "unseen": self._unseen if self.enabled else 0, "coin_cap": self.cap}
