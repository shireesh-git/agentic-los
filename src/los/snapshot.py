"""Approval snapshot and material-change revalidation (Client One GAP-P0-11).

A sanction decision binds the exact versions of the proposal, parties,
facilities, projects, financials, ratings, securities, checks and documents it
was made against, by storing a hashed, content-addressed snapshot. Any later
change to a governed domain marks it *material*, lists the changed domains and
blocks the next approval decision until the change is reviewed (accepted or
rejected with remarks) — the documented behaviour: "No downstream approval may
silently rely on outdated upstream information" (§12).

The snapshot is a labelled governance record. Its physical immutability /
tamper-evidence design is confirmation-required (spec §22/P0-11, §28) — the
hash chain here proves content identity, not cryptographic tamper-evidence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

DOMAINS = ("identity", "parties", "facilities", "projects", "financials", "ratings", "cma",
           "securities", "checks", "documents", "proposal", "pricing", "esms", "conditions")


def domain_payloads(app: dict) -> dict:
    """The governed content, domain by domain, exactly as an approval sees it."""
    return {
        "identity": {k: app.get(k) for k in ("entity_id", "borrower_name", "identity", "customer_id_selection")},
        "parties": app.get("related_parties") or [],
        "facilities": [{k: f.get(k) for k in ("facility_id", "proposed_cr", "tenor_months", "facility_type",
                                              "facility_nature", "pricing", "repayment", "purpose",
                                              "sanctioned_cr", "committed_cr")} for f in app.get("facilities", [])],
        "projects": app.get("projects") or [],
        "financials": {"assessment_run": (app.get("assessment_case") or {}).get("run_id"),
                       "summary": app.get("assessment_summary") or {}},
        "ratings": app.get("ratings") or {},
        "cma": app.get("cma") or {},
        "securities": app.get("securities") or [],
        "checks": {c["id"]: {k: c.get(k) for k in ("status", "result", "last_triggered", "mandatory")}
                   for c in ((app.get("due_diligence") or {}).get("checks") or [])},
        # The approval package binds the pre-sanction input documents (and their versions);
        # post-sanction execution evidence (POS/DIS stage, generated outputs) is not a review input.
        "documents": {d["doc_id"]: [v["v"] for v in d["versions"]] for d in app.get("documents") or []
                      if d.get("category") != "generated" and d.get("mandatory_stage") in (None, "PS", "IP", "AP")},
        "proposal": app.get("proposal") or {},
        "pricing": app.get("pricing") or {},
        "esms": app.get("esms") or {},
        "conditions": {c["id"]: c.get("status") for c in app.get("conditions") or []},
    }


def domain_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:20]


def build_snapshot(app: dict, ref: str, at: str, by_name: str) -> dict:
    payloads = domain_payloads(app)
    seq = max((s.get("seq", 0) for s in (app.get("snapshots") or [])), default=0) + 1
    return {"ref": ref, "at": at, "by": by_name, "seq": seq,
            "domains": {d: domain_hash(p) for d, p in payloads.items()},
            "packages": {d: p for d, p in payloads.items()},
            "content_hash": domain_hash(payloads),
            "note": "Approval-version package (labelled governance record); tamper-evidence design is "
                    "confirmation-required (spec §22/P0-11, §28)."}


def record_snapshot(app: dict, ref: str, at: str, by_name: str) -> dict:
    snap = build_snapshot(app, ref, at, by_name)
    snaps = [s for s in (app.get("snapshots") or []) if s.get("ref") != ref]
    snaps.append(snap)
    app["snapshots"] = snaps
    app["material_changes"] = []
    app["material_change_reviews"] = []
    return snap


def _latest_snapshot(app: dict) -> dict:
    snaps = app.get("snapshots") or []
    return max(snaps, key=lambda s: (s.get("seq", 0), s.get("at") or "")) if snaps else None


def material_changes(app: dict) -> list[str]:
    """Domains whose content hash differs from the latest recorded snapshot."""
    snaps = app.get("snapshots") or []
    if not snaps:
        return []
    latest = _latest_snapshot(app)
    payloads = domain_payloads(app)
    return [d for d in DOMAINS if domain_hash(payloads.get(d)) != (latest.get("domains") or {}).get(d)]


def material_change_gate(app: dict) -> Optional[str]:
    """An unreviewed material change after the approval snapshot blocks the next approval.
    The *conditions* domain is excluded: post-sanction condition work (satisfy/defer/waive) is
    tracked by the condition tracker with checker approval, not by the approval snapshot."""
    snaps = app.get("snapshots") or []
    if not snaps:
        return None
    changed = set(material_changes(app)) - {"conditions"}
    if not changed:
        return None
    reviewed: set = set()
    for r in app.get("material_change_reviews", []):
        if "ALL" in (r.get("domains") or []):
            reviewed = set(DOMAINS)
        else:
            reviewed |= set(r.get("domains") or [])
    unreviewed = sorted(changed - reviewed)
    if unreviewed:
        return ("Material change(s) since the approval snapshot in: " + ", ".join(unreviewed) +
                " — review the change (accept or reject with remarks) before the next approval")
    return None


def review_material_changes(app: dict, decision: str, by_name: str, at: str, remarks: str) -> dict:
    if decision not in ("accept", "reject"):
        raise ValueError("decision must be accept or reject")
    changed = material_changes(app)
    review = {"decision": decision, "by": by_name, "at": at, "remarks": remarks or None,
              "domains": changed or ["ALL"]}
    app.setdefault("material_change_reviews", []).append(review)
    return review
