"""
Resolvers: turn engine, record and document output into field proposals.

A proposal is ``{field_id, domain, label, value, provenance, source, evidence, confidence,
resolver, run_id}`` where ``source`` is one of the critic's source kinds (document,
external, engine, record, ai_draft) and ``evidence`` carries what that kind must show.
"""

from __future__ import annotations

from typing import Optional

from src.los.fields.registry import FieldRegistry

# Provenance class (data_provenance) → the critic's source kind.
_SOURCE_OF = {"source": "record", "external": "external", "calculated": "engine", "derived": "engine",
              "synthetic_demo": "engine", "template": "engine", "ai": "ai_draft", "unavailable": "record"}


def _evidence(source: str, provenance: str, origin: str, section: str, run_id: Optional[str]) -> dict:
    origin = origin or "credit case"
    ev = {"section": section, "run_id": run_id}
    if source == "record":
        ev["path"] = origin
    elif source == "external":
        ev["system"] = origin
    else:
        ev["engine"] = origin
    if provenance == "synthetic_demo":
        ev["demo"] = True
    return ev


def risk_maker_proposals(view: dict, registry: FieldRegistry, run_id: Optional[str] = None) -> list[dict]:
    """Every field of the Risk Maker view as a proposal (the credit case as the source)."""
    if not view or not view.get("available"):
        return []
    run_id = run_id or view.get("run_id")
    out = []
    for tab in view.get("tabs") or []:
        for sec in tab.get("sections") or []:
            for f in sec.get("fields") or []:
                prov = f.get("provenance") or "derived"
                source = _SOURCE_OF.get(prov, "engine")
                out.append({"field_id": f["id"], "domain": tab["id"], "label": f["label"], "value": f["value"],
                            "provenance": prov, "source": source,
                            "evidence": _evidence(source, prov, f.get("source", ""), sec.get("title", ""), run_id),
                            "confidence": registry.confidence_for(prov), "resolver": "risk_maker", "run_id": run_id})
    return out
