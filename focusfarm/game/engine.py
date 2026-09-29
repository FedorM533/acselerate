"""Игровая логика «Фокус-фермы» (раздел 9 ТЗ): рост, сорняки, качество,
урожай, монеты, серия дней, магазин.

Движок ничего не знает про базу данных и время компьютера: ему передают
состояние, прошедшие секунды `dt` и сегодняшнюю дату. Сохранением
занимается менеджер сессии (через to_dict / from_dict).
"""
import datetime as dt
import math
import random
from dataclasses import asdict, dataclass

from focusfarm.game.crops import Crop, load_crops, stage_for
from focusfarm.session.state_machine import DISTRACTED, GOOD_STATES, PHONE_OUT

BAD_STATES = (DISTRACTED, PHONE_OUT)  # за них появляются сорняки и падает качество

DEFAULT_GAME = {
    "start_size": 3,
    "expansions": {"expand_4": {"size": 4, "price": 200}, "expand_5": {"size": 5, "price": 500}},
    "decor": {"scarecrow": {"name": "Пугало", "price": 20},
              "fence": {"name": "Забор", "price": 40},
              "bench": {"name": "Скамейка", "price": 60}},
    "weed_every_s": 60,
    "max_weeds": 3,
    "weed_unlock_focus_s": 300,
    "weed_penalty": 0.2,
    "streak_day_min": 25,
    "rain_streak_days": 3,
    "rain_bonus": 0.1,
}


class GameError(Exception):
    """Действие невозможно (текст показываем пользователю)."""


@dataclass
class Plot:
    crop_id: str | None = None
    progress_s: float = 0.0   # сколько секунд фокуса накоплено
    weeds: int = 0            # 0 или 1 сорняк на грядке
    quality_hits: int = 0     # эпизодов отвлечения во время роста


def quality_for(hits: int) -> tuple[int, float]:
    """Звёзды и множитель монет по числу эпизодов отвлечения."""
    if hits == 0:
        return 3, 1.5
    if hits <= 2:
        return 2, 1.0
    return 1, 0.7


class GameEngine:
    def __init__(self, game_cfg: dict | None = None, rng: random.Random | None = None):
        self.cfg = {**DEFAULT_GAME, **(game_cfg or {})}
        self.crops: dict[str, Crop] = load_crops(game_cfg)
        self.rng = rng or random.Random()

        self.size = self.cfg["start_size"]
        self.plots: dict[tuple[int, int], Plot] = {}
        self._fill_plots()
        self.coins = 0
        self.unlocks: set[str] = {c.id for c in self.crops.values() if c.price == 0}
        self.days: dict[str, float] = {}   # "2026-09-30" → секунд фокуса за день

        # Данные текущей сессии (не сохраняются между запусками).
        self.active_plot: tuple[int, int] | None = None
        self.session_focus_s = 0.0
        self._distract_run_s = 0.0
        self._prev_state = None

    # ---------- огород ----------

    def _fill_plots(self):
        for x in range(self.size):
            for y in range(self.size):
                self.plots.setdefault((x, y), Plot())

    def plot(self, x: int, y: int) -> Plot:
        if (x, y) not in self.plots:
            raise GameError("Такой грядки нет")
        return self.plots[(x, y)]

    def is_ripe(self, x: int, y: int) -> bool:
        p = self.plot(x, y)
        return p.crop_id is not None and p.progress_s >= self.crops[p.crop_id].grow_s

    def stage(self, x: int, y: int) -> str:
        p = self.plot(x, y)
        if p.crop_id is None:
            return "empty"
        return stage_for(p.progress_s / self.crops[p.crop_id].grow_s)

    def weeds_total(self) -> int:
        return sum(p.weeds for p in self.plots.values())

    def weed_nearby(self, x: int, y: int) -> bool:
        """Есть ли сорняк на этой грядке или на соседней (сверху/снизу/слева/справа)."""
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            p = self.plots.get((x + dx, y + dy))
            if p and p.weeds:
                return True
        return False

    # ---------- начало и конец сессии ----------

    def default_crop(self, length_min: float) -> str:
        """Открытое растение, чьё время роста ближе всего к длине сессии."""
        unlocked = [c for c in self.crops.values() if c.id in self.unlocks]
        return min(unlocked, key=lambda c: abs(c.focus_min - length_min)).id

    def default_plot(self) -> tuple[int, int] | None:
        """Сначала недоросшее растение (продолжаем), иначе первая пустая грядка."""
        for pos in sorted(self.plots):
            if self.plots[pos].crop_id and not self.is_ripe(*pos):
                return pos
        for pos in sorted(self.plots):
            if self.plots[pos].crop_id is None:
                return pos
        return None

    def begin_session(self, plot: tuple[int, int] | None = None,
                      crop_id: str | None = None, length_min: float = 25) -> tuple[int, int] | None:
        """Выбирает грядку и растение. Возвращает грядку (или None, если все заняты урожаем)."""
        pos = tuple(plot) if plot is not None else self.default_plot()
        self.session_focus_s = 0.0
        self._distract_run_s = 0.0
        self._prev_state = None
        self.active_plot = None
        if pos is None:
            return None
        p = self.plot(*pos)
        if p.crop_id is None:
            crop_id = crop_id or self.default_crop(length_min)
            if crop_id not in self.crops:
                raise GameError("Нет такого растения")
            if crop_id not in self.unlocks:
                raise GameError("Это растение ещё не открыто")
            self.plots[pos] = Plot(crop_id=crop_id)
        elif self.is_ripe(*pos):
            raise GameError("Сначала собери урожай с этой грядки")
        self.active_plot = pos
        return pos

    def end_session(self):
        self.active_plot = None
        self._prev_state = None

    # ---------- тик ----------

    def tick(self, state: str, dt_s: float, today: dt.date) -> list[dict]:
        """Один шаг игры. Возвращает список событий для интерфейса."""
        events = []
        if state in GOOD_STATES:
            self._distract_run_s = 0.0
            self.session_focus_s += dt_s
            day = today.isoformat()
            self.days[day] = self.days.get(day, 0.0) + dt_s
            events += self._grow(dt_s * self.growth_multiplier(today))
        elif state in BAD_STATES:
            if self._prev_state not in BAD_STATES:
                self._count_episode()
            self._distract_run_s += dt_s
            while self._distract_run_s >= self.cfg["weed_every_s"]:
                self._distract_run_s -= self.cfg["weed_every_s"]
                events += self._spawn_weed()
        else:
            # MAYBE_DISTRACTED / PAUSED — рост на паузе, отвлечение не «непрерывное».
            self._distract_run_s = 0.0
        self._prev_state = state
        return events

    def _grow(self, amount: float) -> list[dict]:
        if self.active_plot is None:
            return []
        x, y = self.active_plot
        if self.is_ripe(x, y):
            return []
        self.plots[(x, y)].progress_s += amount
        if self.is_ripe(x, y):
            return [{"type": "crop_ready", "x": x, "y": y, "crop": self.plots[(x, y)].crop_id}]
        return []

    def _count_episode(self):
        """Новый эпизод DISTRACTED/PHONE_OUT снижает качество растущего растения."""
        if self.active_plot and not self.is_ripe(*self.active_plot):
            self.plots[self.active_plot].quality_hits += 1

    def _spawn_weed(self) -> list[dict]:
        if self.weeds_total() >= self.cfg["max_weeds"]:
            return []
        candidates = [pos for pos, p in sorted(self.plots.items()) if p.crop_id and not p.weeds]
        if not candidates:
            return []
        x, y = self.rng.choice(candidates)
        self.plots[(x, y)].weeds = 1
        return [{"type": "weed", "x": x, "y": y}]

    # ---------- действия игрока ----------

    def can_weed(self) -> bool:
        return self.session_focus_s >= self.cfg["weed_unlock_focus_s"]

    def weed(self, x: int, y: int):
        p = self.plot(x, y)
        if not p.weeds:
            raise GameError("Здесь нет сорняка")
        if not self.can_weed():
            minutes = self.cfg["weed_unlock_focus_s"] // 60
            raise GameError(f"Прополоть можно после {minutes} минут фокуса в этой сессии")
        p.weeds = 0

    def harvest_value(self, x: int, y: int) -> dict:
        p = self.plot(x, y)
        stars, mult = quality_for(p.quality_hits)
        weed_mult = 1 - self.cfg["weed_penalty"] if self.weed_nearby(x, y) else 1.0
        coins = math.floor(self.crops[p.crop_id].coins * mult * weed_mult)
        return {"coins": coins, "stars": stars, "weed_penalty": weed_mult < 1}

    def harvest(self, x: int, y: int) -> dict:
        if not self.is_ripe(x, y):
            raise GameError("Растение ещё не созрело")
        p = self.plot(x, y)
        result = {**self.harvest_value(x, y), "crop": p.crop_id, "x": x, "y": y}
        self.coins += result["coins"]
        self.plots[(x, y)] = Plot(weeds=p.weeds)
        # Если собрали активную грядку во время сессии — сажаем то же растение
        # заново, чтобы фокус не «пропадал».
        if self.active_plot == (x, y):
            self.plots[(x, y)].crop_id = p.crop_id
        return result

    # ---------- серия дней и погода ----------

    def day_counts(self, day: dt.date) -> bool:
        return self.days.get(day.isoformat(), 0) >= self.cfg["streak_day_min"] * 60

    def streak(self, today: dt.date) -> int:
        """Сколько дней подряд был ≥ 25 минут фокуса. Если сегодня норма
        ещё не набрана, серия не обрывается — считаем до вчера."""
        day = today if self.day_counts(today) else today - dt.timedelta(days=1)
        count = 0
        while self.day_counts(day):
            count += 1
            day -= dt.timedelta(days=1)
        return count

    def is_raining(self, today: dt.date) -> bool:
        return self.streak(today) >= self.cfg["rain_streak_days"]

    def growth_multiplier(self, today: dt.date) -> float:
        return 1 + self.cfg["rain_bonus"] if self.is_raining(today) else 1.0

    # ---------- магазин ----------

    def shop_items(self) -> list[dict]:
        items = []
        for c in self.crops.values():
            if c.price > 0:
                items.append({"item": f"crop:{c.id}", "kind": "crop", "name": c.name,
                              "price": c.price, "owned": c.id in self.unlocks})
        prev_size = self.cfg["start_size"]
        for item_id, e in self.cfg["expansions"].items():
            items.append({"item": item_id, "kind": "expand", "name": f"Огород {e['size']}×{e['size']}",
                          "price": e["price"], "owned": self.size >= e["size"],
                          "available": self.size >= prev_size})
            prev_size = e["size"]
        for item_id, d in self.cfg["decor"].items():
            items.append({"item": f"decor:{item_id}", "kind": "decor", "name": d["name"],
                          "price": d["price"], "owned": f"decor:{item_id}" in self.unlocks})
        return items

    def buy(self, item: str):
        found = next((i for i in self.shop_items() if i["item"] == item), None)
        if found is None:
            raise GameError("Такого товара нет")
        if found["owned"]:
            raise GameError("Уже куплено")
        if not found.get("available", True):
            raise GameError("Сначала купи предыдущее расширение")
        if self.coins < found["price"]:
            raise GameError(f"Не хватает монет: нужно {found['price']}, есть {self.coins}")
        self.coins -= found["price"]
        if found["kind"] == "crop":
            self.unlocks.add(item.split(":", 1)[1])
        elif found["kind"] == "expand":
            self.size = self.cfg["expansions"][item]["size"]
            self._fill_plots()
        else:
            self.unlocks.add(item)

    # ---------- сохранение ----------

    def to_dict(self) -> dict:
        return {
            "size": self.size,
            "coins": self.coins,
            "unlocks": sorted(self.unlocks),
            "days": dict(self.days),
            "plots": [{"x": x, "y": y, **asdict(p)} for (x, y), p in sorted(self.plots.items())],
        }

    def load_dict(self, data: dict):
        self.size = data.get("size", self.size)
        self.coins = data.get("coins", 0)
        self.unlocks |= set(data.get("unlocks", []))
        self.days = dict(data.get("days", {}))
        for row in data.get("plots", []):
            crop_id = row["crop_id"] if row["crop_id"] in self.crops else None
            self.plots[(row["x"], row["y"])] = Plot(crop_id, row["progress_s"],
                                                    row["weeds"], row["quality_hits"])
        self._fill_plots()
