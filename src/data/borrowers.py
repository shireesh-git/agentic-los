"""Borrower records live in data files, not in code (round 8).

One JSON file per borrower, ``data/borrowers/<ENTITY_ID>.json``, holding everything the platform knows about it:
identity, group, directors, audited statements, the facility requested, collateral, lenders, account conduct,
covenants, sector KPIs and the documents profile. This module only turns a file into the canonical records
(src/models/canonical_model.py) and back; it holds no borrower data.

Provenance is in the file: ``latest_statement_source`` for statements read from an annual report
(scripts/read_fy2026_statements.py), ``data_provider`` / ``catalog_source`` for the rest. Figures that are not public
(collateral, conduct, existing exposure, covenants, core banking) are demo values and are marked so on screen.
"""

from __future__ import annotations

import dataclasses
import json
import typing
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.runtime_paths import PROJECT_ROOT
from src.models import canonical_model as cm

BORROWERS_ROOT = PROJECT_ROOT / "data" / "borrowers"

# the typed parts of a record; everything else in a file is plain JSON
_TYPED: dict[str, Any] = {
    "borrower": cm.Borrower, "group": cm.GroupEntity, "facility": cm.FacilityRequest,
    "provisional": cm.FinancialStatement, "exchange_filing": cm.FinancialStatement,
    "directors": [cm.DirectorPromoter], "collateral": [cm.Collateral], "market_signals": [cm.MarketSignal],
    "existing_exposure": [cm.ExistingExposure], "conduct": [cm.ConductRecord], "covenants": [cm.CovenantRecord],
    "financials": {str: cm.FinancialStatement},
}


# ── record → JSON ────────────────────────────────────────────────────────────

def _plain(v: Any) -> Any:
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {f.name: _plain(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def to_json(record: dict) -> dict:
    return {k: _plain(v) for k, v in record.items()}


# ── JSON → record ────────────────────────────────────────────────────────────

def _typed(hint: Any, v: Any) -> Any:
    if v is None:
        return None
    origin = typing.get_origin(hint)
    if origin is typing.Union:                                    # Optional[X]
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        return _typed(args[0], v) if len(args) == 1 else v
    if isinstance(hint, type) and issubclass(hint, Enum):
        return hint(v)
    if hint is date:
        return date.fromisoformat(v) if isinstance(v, str) else v
    if dataclasses.is_dataclass(hint):
        return _dataclass(hint, v)
    return v


def _dataclass(cls: type, data: dict) -> Any:
    hints = typing.get_type_hints(cls)
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: _typed(hints[k], v) for k, v in data.items() if k in names})


def from_json(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        spec = _TYPED.get(k)
        if spec is None or v is None:
            out[k] = v
        elif isinstance(spec, list):
            out[k] = [_dataclass(spec[0], x) for x in v]
        elif isinstance(spec, dict):
            out[k] = {p: _dataclass(cm.FinancialStatement, x) for p, x in v.items()}
        else:
            out[k] = _dataclass(spec, v)
    return out


# ── files ────────────────────────────────────────────────────────────────────

def path_of(entity_id: str, root: Path = BORROWERS_ROOT) -> Path:
    return root / f"{entity_id}.json"


def load(entity_id: str, root: Path = BORROWERS_ROOT) -> dict:
    return from_json(json.loads(path_of(entity_id, root).read_text(encoding="utf-8")))


def load_all(root: Path = BORROWERS_ROOT) -> dict[str, dict]:
    return {p.stem: from_json(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(root.glob("*.json"))}


def ids(root: Path = BORROWERS_ROOT) -> list[str]:
    return sorted(p.stem for p in root.glob("*.json"))


def save(entity_id: str, record: dict, root: Path = BORROWERS_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = path_of(entity_id, root)
    p.write_text(json.dumps(to_json(record), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p
