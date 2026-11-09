"""SQLite storage for the agentic LOS: one JSON document per case and an append-only event log
(the audit trail, the time-saving report and the timeline are all read from the events)."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_cases (
    case_id    TEXT PRIMARY KEY,
    entity_id  TEXT NOT NULL,
    status     TEXT NOT NULL,
    payload    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS flow_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id    TEXT NOT NULL,
    at         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    stage      TEXT,
    actor_id   TEXT,
    actor_name TEXT,
    role       TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS flow_events_case ON flow_events(case_id, id);
"""


class FlowStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    # ── cases ────────────────────────────────────────────────────────────────

    def save(self, case: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO flow_cases(case_id, entity_id, status, payload, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(case_id) DO UPDATE SET entity_id=excluded.entity_id, status=excluded.status, "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                (case["case_id"], case["entity_id"], case["status"],
                 json.dumps(case, ensure_ascii=False, default=str), case["updated_at"]))

    def get(self, case_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM flow_cases WHERE case_id = ?", (case_id,)).fetchone()
        return _upgrade(json.loads(row["payload"])) if row else None

    def all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM flow_cases ORDER BY updated_at DESC").fetchall()
        return [_upgrade(json.loads(r["payload"])) for r in rows]

    def delete_entity(self, entity_id: str) -> list[str]:
        """Every case of a borrower, and its events (a reset). Returns the case ids removed."""
        with self._lock, self._connect() as conn:
            ids = [r["case_id"] for r in conn.execute("SELECT case_id FROM flow_cases WHERE entity_id = ?",
                                                       (entity_id,))]
            conn.executemany("DELETE FROM flow_events WHERE case_id = ?", [(i,) for i in ids])
            conn.execute("DELETE FROM flow_cases WHERE entity_id = ?", (entity_id,))
        return ids

    def delete_case(self, case_id: str) -> bool:
        """One proposal and its events; the borrower's other proposals stay."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM flow_events WHERE case_id = ?", (case_id,))
            return conn.execute("DELETE FROM flow_cases WHERE case_id = ?", (case_id,)).rowcount > 0

    # ── events ───────────────────────────────────────────────────────────────

    def log(self, case_id: str, at: str, kind: str, stage: Optional[str] = None, actor: Optional[dict] = None,
            detail: Optional[dict] = None) -> None:
        actor = actor or {}
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO flow_events(case_id, at, kind, stage, actor_id, actor_name, role, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, at, kind, stage, actor.get("id"), actor.get("name"), actor.get("role"),
                 json.dumps(detail or {}, ensure_ascii=False, default=str)))

    def events(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM flow_events WHERE case_id = ? ORDER BY id", (case_id,)).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]


def _upgrade(case: dict) -> dict:
    """Older proposals in the current shape: conditions saved before the precedent / subsequent split were
    precedent ones; challenges saved before they had ids get one."""
    for c in case.get("conditions") or []:
        c.setdefault("when", "precedent")
    for i, a in enumerate(case.get("against") or []):      # challenges saved before they had ids and actions
        a.setdefault("id", f"legacy-{i + 1}")
        a.setdefault("actions", [])
        a.setdefault("what", a.get("challenge"))
        a.setdefault("asks", [a["ask"]] if a.get("ask") else [])
    return case
