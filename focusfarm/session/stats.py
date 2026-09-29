"""Статистика для вкладки «Статистика» (GET /api/stats)."""
import datetime as dt
from collections import Counter

from focusfarm.storage.db import STATE_COLUMNS, Database

BAD = ("DISTRACTED", "PHONE_OUT")
DISTRACTION_STATES = ("MAYBE_DISTRACTED", "DISTRACTED")


def range_start(now: float, range_: str) -> float:
    """Начало сегодняшнего дня или начало 7-дневного периода (локальное время)."""
    today = dt.datetime.fromtimestamp(now).date()
    days_back = 6 if range_ == "week" else 0
    start = dt.datetime.combine(today - dt.timedelta(days=days_back), dt.time())
    return start.timestamp()


def compute_stats(db: Database, now: float, range_: str = "day") -> dict:
    since = range_start(now, range_)
    sessions = db.sessions_since(since)
    events = db.events_since(since)

    # Время по состояниям (сумма по сессиям).
    by_state = {state: sum(s[col] or 0 for s in sessions) for state, col in STATE_COLUMNS.items()}

    # Эпизоды отвлечения: переход из «нормального» состояния в DISTRACTED/PHONE_OUT.
    episodes = Counter()
    prev = {}
    for e in events:
        sid = e["session_id"]
        if e["state"] in BAD and prev.get(sid) not in BAD:
            episodes["phone" if e["state"] == "PHONE_OUT" else "window"] += 1
        prev[sid] = e["state"]

    # Куда отвлекались: процессы и категории при MAYBE/DISTRACTED.
    distracting = [e for e in events if e["state"] in DISTRACTION_STATES]
    top_processes = Counter(e["process_name"] for e in distracting
                            if e["process_name"] and e["process_name"] != "unknown")
    top_categories = Counter(e["category"] for e in distracting if e["category"])

    return {
        "range": range_,
        "sessions": len(sessions),
        "by_state_s": by_state,
        "focus_s": by_state["FOCUS"] + by_state["NOTEBOOK"],
        "distractions": sum(episodes.values()),
        "distraction_reasons": {"window": episodes["window"], "phone": episodes["phone"]},
        "top_processes": [{"name": n, "count": c} for n, c in top_processes.most_common(5)],
        "top_categories": [{"name": n, "count": c} for n, c in top_categories.most_common(3)],
        "days": _days(sessions, now, 7 if range_ == "week" else 1),
        "timeline": timeline(db, now),
    }


def _days(sessions: list[dict], now: float, count: int) -> list[dict]:
    """Минуты фокуса по дням (для недельного графика)."""
    today = dt.datetime.fromtimestamp(now).date()
    result = {(today - dt.timedelta(days=i)).isoformat(): 0.0 for i in range(count - 1, -1, -1)}
    for s in sessions:
        day = dt.datetime.fromtimestamp(s["start"]).date().isoformat()
        if day in result:
            result[day] += ((s["focus_s"] or 0) + (s["notebook_s"] or 0)) / 60
    return [{"day": d, "focus_min": round(m, 1)} for d, m in result.items()]


def timeline(db: Database, now: float) -> dict | None:
    """Хронология последней сессии: отрезки [начало, конец) по состояниям,
    в секундах от начала сессии."""
    session = db.last_session()
    if not session:
        return None
    end = session["end"] or now
    events = [e for e in db.session_events(session["id"]) if e["state"] != "IDLE"]
    segments = []
    for i, e in enumerate(events):
        seg_end = events[i + 1]["ts"] if i + 1 < len(events) else end
        if seg_end > e["ts"]:
            segments.append({"state": e["state"], "from_s": e["ts"] - session["start"],
                             "to_s": seg_end - session["start"]})
    return {"session_id": session["id"], "start": session["start"], "end": session["end"],
            "duration_s": end - session["start"], "segments": segments}
