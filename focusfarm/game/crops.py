"""Таблица растений. Числа берутся из settings.yaml (game.crops),
а если там пусто — из таблицы по умолчанию ниже (раздел 9.1 ТЗ)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Crop:
    id: str
    name: str
    focus_min: float   # сколько минут фокуса нужно, чтобы созреть
    coins: int         # монет за урожай (до множителей)
    price: int         # цена открытия в магазине (0 — открыт сразу)

    @property
    def grow_s(self) -> float:
        return self.focus_min * 60


DEFAULT_CROPS = {
    "radish":    {"name": "Редис",     "focus_min": 10, "coins": 5,  "price": 0},
    "carrot":    {"name": "Морковь",   "focus_min": 25, "coins": 15, "price": 30},
    "potato":    {"name": "Картофель", "focus_min": 40, "coins": 25, "price": 80},
    "sunflower": {"name": "Подсолнух", "focus_min": 60, "coins": 45, "price": 150},
    "pumpkin":   {"name": "Тыква",     "focus_min": 90, "coins": 80, "price": 300},
}


def load_crops(game_cfg: dict | None = None) -> dict[str, Crop]:
    table = (game_cfg or {}).get("crops") or DEFAULT_CROPS
    return {
        crop_id: Crop(crop_id, c["name"], c["focus_min"], int(c["coins"]), int(c["price"]))
        for crop_id, c in table.items()
    }


# Стадии роста по доле прогресса (для картинок).
STAGES = [(0.15, "seed"), (0.40, "sprout"), (0.70, "young"), (1.0, "adult")]


def stage_for(progress: float) -> str:
    """progress — доля от 0 до 1."""
    for limit, name in STAGES:
        if progress < limit:
            return name
    return "ready"
