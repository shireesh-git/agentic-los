"""
LOS persistence: applications and their audit trail, in the platform's SQLite
runtime database (own tables, so the CAM platform's tables are untouched).

Every state change is written with its audit event in one transaction; the
audit trail is append-only.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS los_applications (
    application_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    borrower_name TEXT NOT NULL,
    stage_id TEXT,
    step_id TEXT,
    status TEXT NOT NULL,
    assignee_id TEXT,
    amount_cr REAL,
    priority TEXT,
    escalated INTEGER NOT NULL DEFAULT 0,
    step_entered_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_los_app_step ON los_applications(step_id);
CREATE INDEX IF NOT EXISTS idx_los_app_assignee ON los_applications(assignee_id);

CREATE TABLE IF NOT EXISTS los_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id TEXT NOT NULL,
    at TEXT NOT NULL,
    actor_id TEXT,
    actor_role TEXT,
    action TEXT NOT NULL,
    from_step TEXT,
    to_step TEXT,
    status TEXT,
    comment TEXT,
    detail_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_los_events_app ON los_events(application_id, event_id);

CREATE TABLE IF NOT EXISTS los_sequence (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""

_COLUMNS = ("application_id", "entity_id", "borrower_name", "stage_id", "step_id", "status", "assignee_id",
            "amount_cr", "priority", "escalated", "step_entered_at", "created_at", "updated_at")


class LosStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ── ids ──────────────────────────────────────────────────────────────────
    def next_application_id(self, year: int) -> str:
        with self._connect() as conn:
            name = f"app-{year}"
            row = conn.execute("SELECT value FROM los_sequence WHERE name = ?", (name,)).fetchone()
            value = (row["value"] if row else 0) + 1
            conn.execute("INSERT INTO los_sequence(name, value) VALUES (?, ?) "
                         "ON CONFLICT(name) DO UPDATE SET value = excluded.value", (name, value))
        return f"LOS-{year}-{value:05d}"

    # ── applications ─────────────────────────────────────────────────────────
    @staticmethod
    def _row(app: dict) -> tuple:
        return tuple(app.get(c) for c in _COLUMNS[:-4]) + (int(bool(app.get("escalated"))), app["step_entered_at"],
                                                          app["created_at"], app["updated_at"])

    def save(self, app: dict, event: Optional[dict] = None) -> None:
        """Insert or update an application, and append its audit event in the same transaction."""
        payload = json.dumps(app, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO los_applications({', '.join(_COLUMNS)}, payload_json) "
                f"VALUES ({', '.join('?' * len(_COLUMNS))}, ?) "
                "ON CONFLICT(application_id) DO UPDATE SET "
                + ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS[1:]) + ", payload_json = excluded.payload_json",
                self._row(app) + (payload,))
            if event:
                self._append(conn, event)

    def get(self, application_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM los_applications WHERE application_id = ?",
                               (application_id,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload_json FROM los_applications ORDER BY updated_at DESC").fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM los_applications").fetchone()[0]

    # ── audit ────────────────────────────────────────────────────────────────
    @staticmethod
    def _append(conn, e: dict) -> None:
        conn.execute(
            "INSERT INTO los_events(application_id, at, actor_id, actor_role, action, from_step, to_step, status, "
            "comment, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e["application_id"], e["at"], e.get("actor_id"), e.get("actor_role"), e["action"], e.get("from_step"),
             e.get("to_step"), e.get("status"), e.get("comment"), json.dumps(e.get("detail") or {}, default=str)))

    def events(self, application_id: Optional[str] = None, limit: int = 500) -> list[dict]:
        sql = "SELECT * FROM los_events"
        args: tuple = ()
        if application_id:
            sql += " WHERE application_id = ?"
            args = (application_id,)
        sql += " ORDER BY event_id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(sql, args + (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d.pop("detail_json") or "{}")
            out.append(d)
        return out

    def clear(self) -> None:
        """Remove every LOS application and event (demo reset)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM los_events")
            conn.execute("DELETE FROM los_applications")
            conn.execute("DELETE FROM los_sequence")
