"""Demo stand-ins for the bureau, MCA and regulatory-list APIs that are not connected yet (fix list E5).

The six data hard rules (wilful defaulter, company active, bureau status, fraud registry, RBI defaulter,
suits filed) need a commercial bureau report, the MCA company master and the RBI / CIC lists. None of
those is available free, so for the demo each borrower can have one file:

    storage/demo_registry/<ENTITY_ID>.json      (or <CIN>.json for a new prospect)

    {"entity_id", "cin", "company_name", "as_of",
     "bureau":     {credit_score, cmr_rank, dpd_status, max_dpd_last_12m, total_exposure_cr, total_outstanding_cr,
                    total_lenders},
     "mca":        {company_name, cin, status, date_of_incorporation, ...},
     "registries": {wilful_defaulter, rbi_defaulter_list, fraud_flag, suit_filed_amount_cr, suits: [...],
                    nclt_cases: [...]}}

Each section becomes the same envelope a live connector returns (``source``, ``source_status``,
``payload``, ``provenance``), with ``provenance.via = "demo_file"``. Switching a source to its real API
later changes nothing downstream. Every record says it is demo data, so the screens, the CAM and the
Copilot can say so too.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.runtime_paths import STORAGE_ROOT

ROOT = STORAGE_ROOT / "demo_registry"

PROVIDER = {
    "bureau": "Demo bureau file (stands in for a CIBIL / CRIF commercial report)",
    "mca": "Demo MCA file (stands in for the MCA21 company master)",
    "registries": "Demo regulatory-list file (stands in for the RBI / CIC wilful-defaulter and defaulter lists, "
                  "the RBI CFMC fraud registry and court / NCLT records)",
}
RECORD_TYPE = {"bureau": "commercial_report", "mca": "company_master", "registries": "regulatory_lists"}

# registry field → the list it stands for (shown as the source of each check)
REGISTRY_FIELDS = {"wilful_defaulter": "RBI / CIC wilful-defaulter list",
                   "rbi_defaulter_list": "RBI defaulter list",
                   "fraud_flag": "RBI CFMC fraud registry",
                   "suit_filed_amount_cr": "Suit-filed accounts and NCLT records"}


def path_for(entity_id: Optional[str] = None, cin: Optional[str] = None, root: Optional[Path] = None) -> Optional[Path]:
    root = root or ROOT
    for key in (entity_id, cin):
        if key:
            p = root / f"{str(key).strip().upper()}.json"
            if p.exists():
                return p
    return None


def load(entity_id: Optional[str] = None, cin: Optional[str] = None, root: Optional[Path] = None) -> Optional[dict]:
    p = path_for(entity_id, cin, root)
    if not p:
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    data["_file"] = f"demo_registry/{p.name}"
    return data


def envelope(data: dict, section: str) -> Optional[dict]:
    """One section of a demo file as a connector envelope; None when the file has no such section."""
    payload = data.get(section)
    if not isinstance(payload, dict) or not payload:
        return None
    return {"source": section, "record_type": RECORD_TYPE[section], "source_status": "success",
            "entity_key": data.get("cin") or data.get("entity_id"), "as_of_date": data.get("as_of"),
            "payload": dict(payload), "demo": True,
            "identity": {"cin": data.get("cin")}, "name_found": data.get("company_name"),
            "provenance": {"via": "demo_file", "provider": PROVIDER[section], "document": data.get("_file"),
                           "fetched_at": datetime.now().isoformat(timespec="seconds"), "demo": True}}


def merge_registries(bureau_env: Optional[dict], registry_env: Optional[dict]) -> Optional[dict]:
    """The policy engine reads the list checks from the bureau payload: fold the registry fields in, keeping
    a note of where each came from."""
    if not registry_env:
        return bureau_env
    reg = registry_env.get("payload") or {}
    fields = {k: reg[k] for k in REGISTRY_FIELDS if k in reg}
    extra = {k: reg[k] for k in ("suits", "nclt_cases") if k in reg}
    sources = {k: REGISTRY_FIELDS[k] + (" (demo)" if registry_env.get("demo") else "") for k in fields}
    if not bureau_env:
        return {**{k: v for k, v in registry_env.items() if k != "payload"},
                "payload": {**fields, **extra, "_field_sources": sources}}
    base = bureau_env.get("payload") or {}
    prov = dict(bureau_env.get("provenance") or {})
    prov["registries"] = registry_env.get("provenance")
    return {**bureau_env, "payload": {**base, **fields, **extra,
                                      "_field_sources": {**(base.get("_field_sources") or {}), **sources}},
            "provenance": prov}


def external_data(entity_id: Optional[str], cin: Optional[str] = None, root: Optional[Path] = None) -> dict:
    """``{"bureau_data", "mca_data"}`` from the borrower's demo file (empty when it has none)."""
    data = load(entity_id, cin, root)
    if not data:
        return {}
    out = {}
    bureau = merge_registries(envelope(data, "bureau"), envelope(data, "registries"))
    if bureau:
        out["bureau_data"] = _strip(bureau)
    mca = envelope(data, "mca")
    if mca:
        out["mca_data"] = _strip(mca)
    return out


def _strip(env: dict) -> dict:
    return {k: v for k, v in env.items() if k not in ("identity", "name_found")}
