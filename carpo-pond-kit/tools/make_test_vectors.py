#!/usr/bin/env python3
"""Независимая реализация правил на Python -> config/progress_test_vectors.json.
JS-эталон (reference/progressEngine.js) сверяется с этими векторами: node reference/checkVectors.mjs
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config", "progression.json"), encoding="utf-8"))
SC = CFG["scoring"]


def pceil(base, pct):
    return (base * pct + 99) // 100


def score(sessions):
    ss = sorted(sessions, key=lambda s: (s["endedAt"], s["id"]))
    base_day, rb_day, res, drops = {}, {}, [], 0
    for s in ss:
        d = s["localDate"]
        if s["focusedSeconds"] < SC["minCountedSeconds"]:
            res.append(dict(id=s["id"], status="too_short", base=0, bonus=0))
            continue
        sec = min(s["focusedSeconds"], s["plannedMinutes"] * 60, SC["maxSessionMinutes"] * 60)
        mins = sec // SC["secondsPerDrop"]
        used = base_day.get(d, 0)
        base = max(0, min(mins, SC["dailyBaseCapDrops"] - used))
        base_day[d] = used + base
        bonus = 0
        if s["endReason"] == "completed":
            st = "completed"
            bonus = min(SC["completionBonus"]["max"], pceil(base, SC["completionBonus"]["percent"]))
        elif s.get("reasonCode"):
            st = "interrupted_with_reason"
            rb = SC["reasonBonus"]
            u = rb_day.get(d, 0)
            if base >= rb["minBaseDrops"] and u < rb["maxPerDay"]:
                bonus = min(rb["max"], pceil(base, rb["percent"]))
                rb_day[d] = u + 1
        else:
            st = "interrupted_no_reason"
        drops += base + bonus
        res.append(dict(id=s["id"], status=st, base=base, bonus=bonus))
    focus_days = sum(1 for v in base_day.values() if v >= SC["focusDayMinBaseDrops"])
    return drops, focus_days, res


def unlocks(drops, days):
    us = [u for u in CFG["unlocks"] if drops >= u["requires"]["drops"] and days >= u["requires"]["focusDays"]]
    return [u["id"] for u in sorted(us, key=lambda u: u["order"])]


def stage(drops):
    st = CFG["stages"][0]["id"]
    for s in CFG["stages"]:
        if drops >= s["fromDrops"]:
            st = s["id"]
    return st


T0 = 1_790_000_000_000  # условная точка отсчёта, ms
DAY = 86_400_000


def S(i, day, planned, focused_sec, end, reason=None, t=0):
    return dict(id=f"s{i:03d}", endedAt=T0 + day * DAY + t * 60_000, localDate=f"2026-10-{day + 1:02d}",
                plannedMinutes=planned, focusedSeconds=focused_sec, endReason=end, reasonCode=reason)


cases = []


def case(name, desc, sessions):
    drops, days, res = score(sessions)
    cases.append(dict(name=name, description=desc, input=sessions,
                      expected=dict(drops=drops, focusDays=days, stage=stage(drops),
                                    unlocked=unlocks(drops, days), sessions=res)))


case("completed_45", "Завершённая сессия 45 мин: 45 + бонус 20% (9)",
     [S(1, 0, 45, 45 * 60, "completed")])
case("interrupted_with_reason_20_of_45", "Прервана через 20 мин с причиной: 20 + 2",
     [S(1, 0, 45, 20 * 60 + 30, "interrupted", "urgent")])
case("interrupted_no_reason_20_of_45", "Прервана без причины: только 20, без бонуса",
     [S(1, 0, 45, 20 * 60 + 30, "interrupted")])
case("too_short_90s", "Меньше 2 минут не считается совсем",
     [S(1, 0, 25, 90, "interrupted", "urgent")])
case("reason_bonus_min_base", "Прервана с причиной через 4.5 мин: база 4 < 5 — бонуса нет",
     [S(1, 0, 25, 270, "interrupted", "break")])
case("reason_bonus_daily_limit", "4 прерывания с причиной за день: бонус только у первых трёх",
     [S(i, 0, 25, 10 * 60, "interrupted", "distracted", t=i * 20) for i in range(1, 5)])
case("reason_limit_resets_next_day", "Лимит бонусов за причину сбрасывается на следующий день",
     [S(i, 0, 25, 10 * 60, "interrupted", "urgent", t=i * 20) for i in range(1, 5)] +
     [S(5, 1, 25, 10 * 60, "interrupted", "urgent")])
case("completion_bonus_cap", "Завершённая 100 мин: бонус упирается в максимум 10",
     [S(1, 0, 100, 100 * 60, "completed")])
case("focused_more_than_planned", "Таймер насчитал больше плана (сон устройства): режем до плана",
     [S(1, 0, 25, 1600, "completed")])
case("max_session_cap", "Сессия 240 мин режется до 180",
     [S(1, 0, 240, 240 * 60, "completed")])
case("daily_base_cap", "5 сессий по 180 мин в один день: базовых капель максимум 720 в день",
     [S(i, 0, 180, 180 * 60, "completed", t=i * 200) for i in range(1, 6)])
case("float_trap_45", "Проверка целочисленной математики: 20% от 45 = 9, а не 10",
     [S(1, 0, 45, 45 * 60, "completed")])
case("completed_with_reason_code", "Код причины у завершённой сессии игнорируется — только бонус завершения",
     [S(1, 0, 30, 30 * 60, "completed", "urgent")])
case("unsorted_input", "Входной список не отсортирован — движок сортирует по endedAt",
     [S(3, 0, 25, 10 * 60, "interrupted", "urgent", t=60), S(1, 0, 25, 10 * 60, "interrupted", "urgent", t=0),
      S(4, 0, 25, 10 * 60, "interrupted", "urgent", t=90), S(2, 0, 25, 10 * 60, "interrupted", "urgent", t=30)])
case("focus_days", "День фокуса = за день набрано >= 10 базовых капель (можно несколькими сессиями)",
     [S(1, 0, 25, 9 * 60, "interrupted"), S(2, 1, 25, 10 * 60, "interrupted"),
      S(3, 2, 25, 5 * 60, "interrupted", t=0), S(4, 2, 25, 5 * 60, "interrupted", t=30)])
case("first_unlock_at_15", "Завершённая 13 мин: 13 + бонус 3 = 16 >= 15 — открывается первая кувшинка",
     [S(1, 0, 13, 13 * 60, "completed")])
case("ogon_needs_days", "700 капель за 2 дня — золотой карп ещё закрыт (нужно 5 дней фокуса)",
     [S(i, i % 2, 60, 60 * 60, "completed", t=i * 70) for i in range(1, 11)])
case("ogon_unlocked", "Те же 700 капель, но за 5 разных дней — золотой карп открыт",
     [S(i, i % 5, 60, 60 * 60, "completed", t=i * 70) for i in range(1, 11)])
case("month_of_work", "Месяц: 25 дней по 2 сессии 45 мин + одна прерванная с причиной",
     [S(d * 3 + k, d, 45, 45 * 60 if k < 2 else 20 * 60, "completed" if k < 2 else "interrupted",
        None if k < 2 else "wrong_time", t=k * 60) for d in range(25) for k in range(3)])

out = dict(
    _comment="Тест-векторы движка прогресса. Для каждого case: прогнать input через движок с config/progression.json "
             "и сравнить drops, focusDays, stage, unlocked и по-сессионный разбор (id, status, base, bonus).",
    configVersion=CFG["version"], cases=cases)
path = os.path.join(ROOT, "config", "progress_test_vectors.json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for c in cases:
    e = c["expected"]
    print(f'{c["name"]:36s} drops={e["drops"]:5d} days={e["focusDays"]:2d} stage={e["stage"]:14s} unlocked={len(e["unlocked"])}')
