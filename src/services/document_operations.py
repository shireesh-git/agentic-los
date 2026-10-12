"""Persistent history for document-generation operations."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.core.runtime_paths import DOCUMENTS_ROOT

OPS_FILE = DOCUMENTS_ROOT / "_document_operations.json"


class DocumentOperationsStore:
    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or OPS_FILE
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.file_path.write_text(json.dumps(entries[-200:], indent=2), encoding="utf-8")

    def record(self, operation: dict[str, Any]) -> dict[str, Any]:
        entries = self._load()
        payload = {
            "operation_id": operation.get("operation_id") or uuid4().hex,
            "operation_type": operation.get("operation_type", "document_generation"),
            "entity_id": operation.get("entity_id"),
            "status": operation.get("status", "success"),
            "started_at": operation.get("started_at") or datetime.now().isoformat(),
            "completed_at": operation.get("completed_at") or datetime.now().isoformat(),
            "summary": operation.get("summary", ""),
            "details": operation.get("details", {}),
        }
        entries.append(payload)
        self._save(entries)
        return payload

    def list(self, entity_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        entries = list(reversed(self._load()))
        if entity_id:
            entries = [entry for entry in entries if entry.get("entity_id") == entity_id]
        return entries[:limit]


document_operations = DocumentOperationsStore()
