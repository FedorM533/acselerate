"""Пруд поверх журнала сессий: считает состояние, хранит открытия и их даты.

Пруд только отображает прогресс. Он не влияет на таймер и блокировку, а сбой пруда
не может отнять засчитанное время (всё пересчитывается из журнала).
"""
import datetime as dt
import json

from focusfarm.paths import CONFIG_DIR
from focusfarm.pond.engine import compute_pond

POND_DIR = CONFIG_DIR / "pond"
NOTE_MAX = 80


def _read(name: str) -> dict:
    return json.loads((POND_DIR / name).read_text(encoding="utf-8"))


def load_config() -> dict:
    """Всё, что нужно клиенту для отрисовки: правила, визуал, тексты, причины, палитра."""
    strings = {**_read("strings_ru.json"), **_read("strings_v2_ru.json")}
    return {"progression": _read("progression.json"), "visual": _read("visual_v2.json"),
            "strings": {k: v for k, v in strings.items() if not k.startswith("_")},
            "reasons": _read("interrupt_reasons.json"), "palette": _read("palette.json")}


class PondService:
    def __init__(self, db, clock, config: dict | None = None):
        self.db, self.clock = db, clock
        self.config = config or load_config()
        self.progression = self.config["progression"]
        self.reason_codes = {r["code"] for r in self.config["reasons"]["reasons"]}

    # ---------- журнал ----------

    def journal(self) -> list[dict]:
        """Завершённые сессии с телефоном (тренировка без телефона в пруд не идёт)."""
        log = []
        for row in self.db.all_sessions():
            if row["end"] is None or row.get("practice"):
                continue
            ended = dt.datetime.fromtimestamp(row["end"])
            log.append({
                "id": str(row["id"]).zfill(9),   # строковая сортировка совпадает с числовой
                "endedAt": int(row["end"] * 1000),
                "localDate": ended.date().isoformat(),
                "plannedMinutes": row["planned_min"] or 0,
                "focusedSeconds": int((row["focus_s"] or 0) + (row["notebook_s"] or 0)),
                "endReason": "completed" if row["end_reason"] == "time_up" else "interrupted",
                "reasonCode": row.get("reason_code"),
            })
        return log

    def normalize_reason(self, code: str | None, note: str | None) -> tuple[str | None, str | None]:
        if code not in self.reason_codes:
            return None, None
        note = (note or "").strip()[:NOTE_MAX] if code == "other" else ""
        return code, note or None

    # ---------- состояние ----------

    def state(self) -> dict:
        """Пересчитывает пруд и сохраняет новые открытия. Капли наружу не отдаём."""
        stored = self.db.pond_unlocks()
        pond = compute_pond(self.journal(), self.progression, [u["id"] for u in stored])
        if pond["newlyUnlocked"]:
            self.db.add_pond_unlocks(pond["newlyUnlocked"], self.clock.today().isoformat())
            stored = self.db.pond_unlocks()
        titles = {u["id"]: u["title"] for u in self.progression["unlocks"]}
        order = {u["id"]: u["order"] for u in self.progression["unlocks"]}
        items = sorted(stored, key=lambda u: order.get(u["id"], 0))
        counted = sum(s["base"] for s in pond["sessions"])
        return {
            "unlocked": [{"id": u["id"], "title": titles.get(u["id"], u["id"]), "date": u["unlocked_at"]} for u in items],
            "unseen": [u["id"] for u in items if not u["seen"]],
            "journal": {"focus_min": counted, "days": pond["focusDays"]},
        }

    def mark_seen(self, ids: list[str]):
        self.db.mark_pond_seen([i for i in ids if isinstance(i, str)])

    def result(self, session_id: int | None = None) -> dict | None:
        """Итог одной сессии для экрана результата (по умолчанию — последней)."""
        pond = compute_pond(self.journal(), self.progression)
        want = str(session_id).zfill(9) if session_id is not None else None
        rows = pond["sessions"]
        row = next((r for r in rows if r["id"] == want), None) if want else (rows[-1] if rows else None)
        if row is None:
            return None
        golden = self.config["visual"]["timeTrail"]["goldenForReasonBonus"]
        return {"status": row["status"], "base": row["base"], "bonus": row["bonus"], "minutes": row["base"],
                "golden": golden if row["status"] == "interrupted_with_reason" and row["bonus"] > 0 else 0,
                "completed": row["status"] == "completed"}
