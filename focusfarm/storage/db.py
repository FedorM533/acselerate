"""Хранение в SQLite (data/focusfarm.db).

Заголовки окон сюда НЕ попадают: в events пишем только состояние,
категорию и имя процесса.

Миграции: список SQL-скриптов MIGRATIONS. Номер последнего применённого
хранится в таблице schema_version. Чтобы изменить схему — добавь новый
скрипт в конец списка (старые не трогай).
"""
import json
import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_PATH = DATA_DIR / "focusfarm.db"

MIGRATIONS = [
    # 1 — первая версия схемы
    """
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start REAL NOT NULL,
        end REAL,
        planned_min REAL,
        focus_s REAL DEFAULT 0,
        notebook_s REAL DEFAULT 0,
        maybe_s REAL DEFAULT 0,
        distracted_s REAL DEFAULT 0,
        phone_out_s REAL DEFAULT 0,
        paused_s REAL DEFAULT 0,
        crop_id TEXT,
        end_reason TEXT
    );
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ts REAL NOT NULL,
        state TEXT NOT NULL,
        category TEXT,
        process_name TEXT
    );
    CREATE INDEX events_session ON events(session_id);
    CREATE INDEX events_ts ON events(ts);
    CREATE TABLE plots (
        x INTEGER, y INTEGER,
        crop_id TEXT,
        progress_s REAL DEFAULT 0,
        weeds INTEGER DEFAULT 0,
        quality_hits INTEGER DEFAULT 0,
        PRIMARY KEY (x, y)
    );
    CREATE TABLE wallet (id INTEGER PRIMARY KEY CHECK (id = 1), coins INTEGER NOT NULL);
    CREATE TABLE farm (id INTEGER PRIMARY KEY CHECK (id = 1), size INTEGER NOT NULL);
    CREATE TABLE unlocks (item TEXT PRIMARY KEY);
    CREATE TABLE streak (day TEXT PRIMARY KEY, focus_s REAL NOT NULL);
    CREATE TABLE settings_overrides (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # 2 — коллекция рыбок, задания дня, ачивки; «тренировка без телефона» помечается в sessions
    """
    ALTER TABLE sessions ADD COLUMN practice INTEGER DEFAULT 0;
    CREATE TABLE collection (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fish_id TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        stars INTEGER NOT NULL,
        released_at REAL NOT NULL
    );
    CREATE TABLE quest_claims (
        day TEXT NOT NULL,
        quest_id TEXT NOT NULL,
        coins INTEGER NOT NULL,
        seen INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, quest_id)
    );
    CREATE TABLE achievements (
        id TEXT PRIMARY KEY,
        unlocked_at REAL NOT NULL,
        coins INTEGER NOT NULL DEFAULT 0,
        seen INTEGER NOT NULL DEFAULT 0
    );
    """,
]

# Секунды каждого состояния → колонка в sessions.
STATE_COLUMNS = {
    "FOCUS": "focus_s", "NOTEBOOK": "notebook_s", "MAYBE_DISTRACTED": "maybe_s",
    "DISTRACTED": "distracted_s", "PHONE_OUT": "phone_out_s", "PAUSED": "paused_s",
}


class Database:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Базу используют и цикл тиков, и обработчики API — поэтому один
        # общий замок и check_same_thread=False.
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.migrate()

    # ---------- схема ----------

    def migrate(self):
        with self.lock, self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self.conn.execute("SELECT version FROM schema_version").fetchone()
            version = row["version"] if row else 0
            if row is None:
                self.conn.execute("INSERT INTO schema_version VALUES (0)")
            for number, script in enumerate(MIGRATIONS, start=1):
                if number > version:
                    self.conn.executescript(script)
                    self.conn.execute("UPDATE schema_version SET version = ?", (number,))

    def schema_version(self) -> int:
        return self.conn.execute("SELECT version FROM schema_version").fetchone()["version"]

    # ---------- ферма ----------

    def load_farm(self) -> dict:
        with self.lock:
            c = self.conn
            wallet = c.execute("SELECT coins FROM wallet WHERE id = 1").fetchone()
            farm = c.execute("SELECT size FROM farm WHERE id = 1").fetchone()
            data = {
                "coins": wallet["coins"] if wallet else 0,
                "unlocks": [r["item"] for r in c.execute("SELECT item FROM unlocks")],
                "days": {r["day"]: r["focus_s"] for r in c.execute("SELECT day, focus_s FROM streak")},
                "plots": [dict(r) for r in c.execute("SELECT * FROM plots")],
            }
            if farm:
                data["size"] = farm["size"]
            return data

    def save_farm(self, data: dict):
        with self.lock, self.conn:
            c = self.conn
            c.execute("INSERT OR REPLACE INTO wallet VALUES (1, ?)", (data["coins"],))
            c.execute("INSERT OR REPLACE INTO farm VALUES (1, ?)", (data["size"],))
            c.executemany("INSERT OR IGNORE INTO unlocks VALUES (?)", [(u,) for u in data["unlocks"]])
            c.executemany("INSERT OR REPLACE INTO streak VALUES (?, ?)", list(data["days"].items()))
            c.executemany(
                "INSERT OR REPLACE INTO plots VALUES (:x, :y, :crop_id, :progress_s, :weeds, :quality_hits)",
                data["plots"],
            )

    # ---------- сессии и события ----------

    def start_session(self, start: float, planned_min: float, crop_id: str | None,
                      practice: bool = False) -> int:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions (start, planned_min, crop_id, practice) VALUES (?, ?, ?, ?)",
                (start, planned_min, crop_id, int(practice)),
            )
            return cur.lastrowid

    def update_session(self, session_id: int, totals: dict, end: float | None = None,
                       end_reason: str | None = None):
        """totals — секунды по состояниям, например {"FOCUS": 120, ...}."""
        fields = {STATE_COLUMNS[s]: v for s, v in totals.items() if s in STATE_COLUMNS}
        if end is not None:
            fields["end"] = end
            fields["end_reason"] = end_reason
        if not fields:
            return
        sql = "UPDATE sessions SET " + ", ".join(f"{k} = ?" for k in fields) + " WHERE id = ?"
        with self.lock, self.conn:
            self.conn.execute(sql, (*fields.values(), session_id))

    def add_event(self, session_id: int | None, ts: float, state: str,
                  category: str | None, process_name: str | None):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO events (session_id, ts, state, category, process_name) VALUES (?, ?, ?, ?, ?)",
                (session_id, ts, state, category, process_name),
            )

    def close_unfinished_sessions(self):
        """Если программа упала посреди сессии — закрываем её при следующем запуске."""
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sessions SET end = COALESCE((SELECT MAX(ts) FROM events "
                "WHERE session_id = sessions.id), start), end_reason = 'crash' WHERE end IS NULL"
            )

    # ---------- статистика ----------

    def sessions_since(self, since: float) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE start >= ? ORDER BY start", (since,)
            ).fetchall()
            return [dict(r) for r in rows]

    def events_since(self, since: float) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE ts >= ? ORDER BY ts, id", (since,)
            ).fetchall()
            return [dict(r) for r in rows]

    def session_events(self, session_id: int) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY ts, id", (session_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def last_session(self) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def all_sessions(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM sessions ORDER BY start")]

    # ---------- коллекция рыбок ----------

    def add_fish(self, fish_id: str, name: str, stars: int, released_at: float) -> int:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO collection (fish_id, name, stars, released_at) VALUES (?, ?, ?, ?)",
                (fish_id, name, stars, released_at))
            return cur.lastrowid

    def list_fish(self) -> list[dict]:
        """Все выпущенные рыбки, новые первыми."""
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM collection ORDER BY id DESC")]

    def collection_summary(self) -> dict:
        """{fish_id: {"count": сколько выпущено, "best_stars": лучшие звёзды}}."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT fish_id, COUNT(*) AS n, MAX(stars) AS best FROM collection GROUP BY fish_id")
            return {r["fish_id"]: {"count": r["n"], "best_stars": r["best"]} for r in rows}

    def count_fish_since(self, since: float) -> int:
        with self.lock:
            return self.conn.execute(
                "SELECT COUNT(*) AS n FROM collection WHERE released_at >= ?", (since,)).fetchone()["n"]

    # ---------- задания и ачивки ----------

    def quest_claims(self, day: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM quest_claims WHERE day = ?", (day,))]

    def add_quest_claim(self, day: str, quest_id: str, coins: int):
        with self.lock, self.conn:
            self.conn.execute("INSERT OR IGNORE INTO quest_claims (day, quest_id, coins) VALUES (?, ?, ?)",
                              (day, quest_id, coins))

    def achievements_list(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM achievements ORDER BY unlocked_at")]

    def add_achievement(self, achievement_id: str, ts: float, coins: int):
        with self.lock, self.conn:
            self.conn.execute("INSERT OR IGNORE INTO achievements (id, unlocked_at, coins) VALUES (?, ?, ?)",
                              (achievement_id, ts, coins))

    def unseen_rewards(self) -> int:
        with self.lock:
            q = self.conn.execute("SELECT COUNT(*) AS n FROM quest_claims WHERE seen = 0").fetchone()["n"]
            a = self.conn.execute("SELECT COUNT(*) AS n FROM achievements WHERE seen = 0").fetchone()["n"]
            return q + a

    def mark_rewards_seen(self):
        with self.lock, self.conn:
            self.conn.execute("UPDATE quest_claims SET seen = 1")
            self.conn.execute("UPDATE achievements SET seen = 1")

    # ---------- настройки из интерфейса ----------

    def get_overrides(self) -> dict:
        with self.lock:
            rows = self.conn.execute("SELECT key, value FROM settings_overrides").fetchall()
            return {r["key"]: json.loads(r["value"]) for r in rows}

    def set_overrides(self, overrides: dict):
        """Полностью заменяет сохранённые изменения настроек."""
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM settings_overrides")
            self.conn.executemany(
                "INSERT INTO settings_overrides VALUES (?, ?)",
                [(k, json.dumps(v, ensure_ascii=False)) for k, v in overrides.items()],
            )
