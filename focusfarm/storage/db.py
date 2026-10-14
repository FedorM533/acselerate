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

from focusfarm.paths import DATA_DIR  # noqa: E402  (в собранном приложении база лежит в профиле)

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
    # 3: телефоны, сопряжённые по Wi-Fi. Токен в открытом виде не храним — только его хеш.
    """
    CREATE TABLE phone_devices (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        created_at REAL NOT NULL,
        last_seen REAL
    );
    """,
    # 4: секреты строгого режима (хеш пароля). Сам пароль не хранится.
    """
    CREATE TABLE secrets (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # 5: перерывы Pomodoro — отдельная колонка, в «время фокуса» они не входят
    """
    ALTER TABLE sessions ADD COLUMN break_s REAL DEFAULT 0;
    """,
    # 6: старая игра (пруд с рыбками, монеты, задания) удалена вместе со своими таблицами.
    # Колонка sessions.crop_id остаётся пустой: SQLite не любит удаление колонок в старых версиях.
    """
    DROP TABLE IF EXISTS plots;
    DROP TABLE IF EXISTS wallet;
    DROP TABLE IF EXISTS farm;
    DROP TABLE IF EXISTS unlocks;
    DROP TABLE IF EXISTS streak;
    DROP TABLE IF EXISTS collection;
    DROP TABLE IF EXISTS quest_claims;
    DROP TABLE IF EXISTS achievements;
    """,
    # 7: новый пруд — причина прерывания сессии и открытия пруда с датой появления.
    # reason_note хранится только локально (до 80 символов, только для причины «other»).
    """
    ALTER TABLE sessions ADD COLUMN reason_code TEXT;
    ALTER TABLE sessions ADD COLUMN reason_note TEXT;
    CREATE TABLE pond_unlocks (
        id TEXT PRIMARY KEY,
        unlocked_at TEXT NOT NULL,
        seen INTEGER NOT NULL DEFAULT 0
    );
    """,
]

# Секунды каждого состояния → колонка в sessions.
STATE_COLUMNS = {
    "FOCUS": "focus_s", "NOTEBOOK": "notebook_s", "MAYBE_DISTRACTED": "maybe_s",
    "DISTRACTED": "distracted_s", "PHONE_OUT": "phone_out_s", "PAUSED": "paused_s",
    "BREAK": "break_s",
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

    # ---------- сессии и события ----------

    def start_session(self, start: float, planned_min: float, practice: bool = False) -> int:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions (start, planned_min, practice) VALUES (?, ?, ?)",
                (start, planned_min, int(practice)),
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

    # ---------- пруд ----------

    def set_session_reason(self, session_id: int, code: str | None, note: str | None):
        with self.lock, self.conn:
            self.conn.execute("UPDATE sessions SET reason_code = ?, reason_note = ? WHERE id = ?",
                              (code, note, session_id))

    def pond_unlocks(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM pond_unlocks ORDER BY unlocked_at, rowid")]

    def add_pond_unlocks(self, ids: list[str], day: str):
        with self.lock, self.conn:
            self.conn.executemany("INSERT OR IGNORE INTO pond_unlocks (id, unlocked_at) VALUES (?, ?)",
                                  [(i, day) for i in ids])

    def mark_pond_seen(self, ids: list[str]):
        with self.lock, self.conn:
            self.conn.executemany("UPDATE pond_unlocks SET seen = 1 WHERE id = ?", [(i,) for i in ids])

    # ---------- телефоны по Wi-Fi ----------

    def add_phone_device(self, device_id: str, name: str, token_hash: str, now: float):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO phone_devices (id, name, token_hash, created_at) VALUES (?, ?, ?, ?)",
                (device_id, name, token_hash, now))

    def find_phone_device(self, token_hash: str) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT id, name FROM phone_devices WHERE token_hash = ?",
                                    (token_hash,)).fetchone()
            return dict(row) if row else None

    def list_phone_devices(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT id, name, created_at, last_seen FROM phone_devices ORDER BY created_at")]

    def touch_phone_device(self, device_id: str, now: float):
        with self.lock, self.conn:
            self.conn.execute("UPDATE phone_devices SET last_seen = ? WHERE id = ?", (now, device_id))

    def delete_phone_device(self, device_id: str) -> bool:
        with self.lock, self.conn:
            return self.conn.execute("DELETE FROM phone_devices WHERE id = ?", (device_id,)).rowcount > 0

    # ---------- секреты (хеш пароля строгого режима) ----------

    def get_secret(self, key: str) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT value FROM secrets WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_secret(self, key: str, value: str | None):
        with self.lock, self.conn:
            if value is None:
                self.conn.execute("DELETE FROM secrets WHERE key = ?", (key,))
            else:
                self.conn.execute("INSERT OR REPLACE INTO secrets VALUES (?, ?)", (key, value))

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
