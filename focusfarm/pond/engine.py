"""Движок прогресса пруда: чистые функции, порт carpo-pond-kit/reference/progressEngine.js.

Единица прогресса — «капля» (1 полная минута фокуса). Источник правды — журнал сессий:
состояние пруда всегда пересчитывается из него. Проценты считаем только целыми числами.
Правила и числа лежат в config/pond/progression.json; поведение закреплено тест-векторами
(tests/data/progress_test_vectors.json).
"""


def percent_ceil(base: int, percent: int) -> int:
    """ceil(base * percent / 100) без плавающей точки."""
    return (base * percent + 99) // 100


def score_sessions(sessions: list[dict], scoring: dict) -> dict:
    """Начисление капель. Порядок важен (дневные лимиты): сортируем по endedAt, затем по id."""
    ordered = sorted(sessions, key=lambda s: (s["endedAt"], s["id"]))
    base_by_day: dict[str, int] = {}
    reason_bonuses_by_day: dict[str, int] = {}
    results = []
    drops = 0
    for s in ordered:
        day = s["localDate"]
        if s["focusedSeconds"] < scoring["minCountedSeconds"]:
            results.append({"id": s["id"], "status": "too_short", "base": 0, "bonus": 0})
            continue
        capped = min(s["focusedSeconds"], s["plannedMinutes"] * 60, scoring["maxSessionMinutes"] * 60)
        minutes = int(capped // scoring["secondsPerDrop"])
        used_today = base_by_day.get(day, 0)
        base = max(0, min(minutes, scoring["dailyBaseCapDrops"] - used_today))
        base_by_day[day] = used_today + base

        bonus = 0
        if s["endReason"] == "completed":
            status = "completed"
            cb = scoring["completionBonus"]
            bonus = min(cb["max"], percent_ceil(base, cb["percent"]))
        elif s.get("reasonCode"):
            status = "interrupted_with_reason"
            rb = scoring["reasonBonus"]
            used = reason_bonuses_by_day.get(day, 0)
            if base >= rb["minBaseDrops"] and used < rb["maxPerDay"]:
                bonus = min(rb["max"], percent_ceil(base, rb["percent"]))
                reason_bonuses_by_day[day] = used + 1
        else:
            status = "interrupted_no_reason"
        drops += base + bonus
        results.append({"id": s["id"], "status": status, "base": base, "bonus": bonus})

    focus_days = sum(1 for v in base_by_day.values() if v >= scoring["focusDayMinBaseDrops"])
    return {"drops": drops, "focusDays": focus_days, "sessions": results}


def compute_unlocks(drops: int, focus_days: int, unlocks: list[dict]) -> list[str]:
    """Какие открытия доступны при данных каплях и днях (по порядку order)."""
    ready = [u for u in unlocks if drops >= u["requires"]["drops"] and focus_days >= u["requires"]["focusDays"]]
    return [u["id"] for u in sorted(ready, key=lambda u: u["order"])]


def merge_unlocked(stored: list[str], computed: list[str]) -> list[str]:
    """Открытое однажды не отбирается: пруд никогда не «откатывается»."""
    return list(dict.fromkeys([*stored, *computed]))


def current_stage(drops: int, stages: list[dict]) -> str:
    stage = stages[0]
    for s in stages:
        if drops >= s["fromDrops"]:
            stage = s
    return stage["id"]


def compute_pond(sessions: list[dict], config: dict, stored_unlocked: list[str] | None = None) -> dict:
    """Полный пересчёт пруда из журнала сессий (идемпотентно)."""
    stored = list(stored_unlocked or [])
    scored = score_sessions(sessions, config["scoring"])
    computed = compute_unlocks(scored["drops"], scored["focusDays"], config["unlocks"])
    unlocked = merge_unlocked(stored, computed)
    return {
        "drops": scored["drops"],
        "focusDays": scored["focusDays"],
        "stage": current_stage(scored["drops"], config["stages"]),
        "unlocked": unlocked,
        "newlyUnlocked": [u for u in unlocked if u not in stored],
        "sessions": scored["sessions"],
    }
