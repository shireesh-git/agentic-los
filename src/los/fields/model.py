"""
FieldValue records on the application (``app["fields"]``), and the rules for changing them.

A record:

    {"field_id", "domain", "label",
     "status":   proposed | confirmed | overridden | conflict | unavailable,
     "value":    what the LOS uses now (the human value once decided, else the proposal),
     "proposal": the latest system proposal {value, provenance, source, evidence, confidence,
                 issues, resolver, run_id, at},
     "decision": the person's decision {status, value, basis, basis_provenance, reason, by, by_name, at}
                 — basis is the proposal value the person decided on,
     "history":  the last few events}

Merge rules (the single writer applies them under the application's lock):
  * a new field arrives ``proposed`` (``unavailable`` when the source has no value);
  * an undecided field takes the new proposal;
  * a decided field (confirmed / overridden) **keeps the person's value**; when the new
    proposal differs from the value the person decided on, it becomes a ``conflict``;
    a conflict whose proposal returns to that value resolves by itself.

Pure functions over dicts: no I/O, no clock (the caller passes ``at``).
"""

from __future__ import annotations

from typing import Iterable, Optional

from src.engines.data_provenance import NOT_AVAILABLE
from src.los.fields.registry import FieldRegistry

DECIDED = ("confirmed", "overridden")
OPEN = ("proposed", "conflict")
ACTIONS = ("confirm", "override", "keep", "reopen")


class FieldActionError(ValueError):
    pass


def available(value, provenance: Optional[str] = None) -> bool:
    return provenance != "unavailable" and value not in (None, "", NOT_AVAILABLE, [], {})


def _log(rec: dict, event: str, at: str, limit: int, **detail) -> None:
    rec.setdefault("history", []).append({"at": at, "event": event, **{k: v for k, v in detail.items() if v is not None}})
    del rec["history"][:-limit]


def _proposal(p: dict, at: str) -> dict:
    out = {"value": p.get("value"), "provenance": p.get("provenance"), "source": p.get("source"),
           "evidence": p.get("evidence") or {}, "confidence": p.get("confidence"), "issues": list(p.get("issues") or []),
           "resolver": p.get("resolver"), "run_id": p.get("run_id"), "at": at}
    # Workspace fields: where the value lives in the application, and its type (for write-back).
    for key in ("target", "value_type"):
        if p.get(key) is not None:
            out[key] = p[key]
    return out


# ── merge (system proposals) ─────────────────────────────────────────────────

def merge(fields: dict, proposals: Iterable[dict], registry: FieldRegistry, at: str) -> dict:
    """Apply proposals to ``fields`` in place. Returns counts of what changed."""
    summary = {"new": 0, "updated": 0, "unchanged": 0, "conflicts": 0, "resolved": 0}
    lim = registry.history_limit
    for p in proposals:
        fid = p["field_id"]
        prop = _proposal(p, at)
        is_available = available(prop["value"], prop["provenance"])
        rec = fields.get(fid)
        if rec is None:
            fields[fid] = rec = {"field_id": fid, "domain": p.get("domain") or registry.domain_of(fid),
                                 "label": p.get("label") or fid, "proposal": prop, "decision": None,
                                 "status": "proposed" if is_available else "unavailable", "value": prop["value"]}
            _log(rec, "proposed", at, lim, value=prop["value"], resolver=prop["resolver"])
            summary["new"] += 1
            continue
        previous = (rec.get("proposal") or {}).get("value")
        rec["proposal"], rec["label"] = prop, p.get("label") or rec.get("label")
        decision = rec.get("decision")
        if decision and rec["status"] in (*DECIDED, "conflict"):
            if prop["value"] == decision["basis"]:
                if rec["status"] == "conflict":
                    rec["status"] = decision["status"]
                    _log(rec, "conflict_resolved", at, lim, value=prop["value"])
                    summary["resolved"] += 1
                else:
                    summary["unchanged"] += 1
            elif rec["status"] != "conflict" or previous != prop["value"]:
                rec["status"] = "conflict"
                _log(rec, "conflict", at, lim, value=prop["value"], kept=rec["value"])
                summary["conflicts"] += 1
            else:
                summary["unchanged"] += 1
            continue
        rec["status"], rec["value"] = ("proposed" if is_available else "unavailable"), prop["value"]
        if previous != prop["value"]:
            _log(rec, "updated", at, lim, value=prop["value"], was=previous)
            summary["updated"] += 1
        else:
            summary["unchanged"] += 1
    return summary


# ── verify (people) ──────────────────────────────────────────────────────────

def apply_action(rec: dict, action: str, *, by: dict, at: str, registry: FieldRegistry,
                 value=None, reason: str = "") -> dict:
    """A person's decision on one field. ``by`` = {"id", "name"}. Returns the record."""
    if action not in ACTIONS:
        raise FieldActionError(f"action must be one of {', '.join(ACTIONS)}")
    reason = (reason or "").strip()
    prop = rec.get("proposal") or {}
    lim = registry.history_limit

    def decide(status: str, new_value):
        rec["decision"] = {"status": status, "value": new_value, "basis": prop.get("value"),
                           "basis_provenance": prop.get("provenance"), "reason": reason or None,
                           "by": by.get("id"), "by_name": by.get("name"), "at": at}
        rec["status"], rec["value"] = status, new_value

    if action == "confirm":
        # Confirming an unavailable field records that the person agrees the value is not
        # available from the submitted information (it stays unpopulated in the stats).
        decide("confirmed", prop.get("value"))
        _log(rec, "confirmed", at, lim, value=prop.get("value"), by=by.get("name"))
    elif action == "override":
        text = "" if value is None else str(value).strip()
        if not text or not reason:
            raise FieldActionError(f"Override of '{rec['label']}' needs a value and a reason")
        decide("overridden", text)
        _log(rec, "overridden", at, lim, value=text, was=prop.get("value"), reason=reason, by=by.get("name"))
    elif action == "keep":
        if rec.get("status") != "conflict":
            raise FieldActionError(f"'{rec['label']}' has no conflict to resolve")
        if not reason:
            raise FieldActionError(f"Keeping your value for '{rec['label']}' over the new proposal needs a reason")
        kept = rec.get("value")
        if kept == prop.get("value"):
            decide("confirmed", kept)
        else:
            decide("overridden", kept)
        _log(rec, "kept", at, lim, value=kept, proposal=prop.get("value"), reason=reason, by=by.get("name"))
    else:  # reopen
        rec["decision"] = None
        rec["status"] = "proposed" if available(prop.get("value"), prop.get("provenance")) else "unavailable"
        rec["value"] = prop.get("value")
        _log(rec, "reopened", at, lim, by=by.get("name"))
    return rec


# ── views ────────────────────────────────────────────────────────────────────

def preticked(rec: dict, registry: FieldRegistry) -> bool:
    """Arrives ticked for bulk confirmation: open proposal, bulk policy, confident, no critic issues."""
    prop = rec.get("proposal") or {}
    return (rec.get("status") == "proposed" and registry.spec(rec["field_id"]).verify == "bulk"
            and (prop.get("confidence") or 0) >= registry.pretick_confidence and not prop.get("issues"))


def bulk_eligible(rec: dict, registry: FieldRegistry) -> bool:
    prop = rec.get("proposal") or {}
    return (rec.get("status") == "proposed" and registry.spec(rec["field_id"]).verify == "bulk"
            and not prop.get("issues") and available(prop.get("value"), prop.get("provenance")))


def queue(fields: dict, registry: FieldRegistry, step_id: Optional[str]) -> list[dict]:
    """What the holder of ``step_id`` should look at, most important first."""
    domains = registry.domains_verified_at(step_id)
    order = {d: i for i, d in enumerate(domains)}
    items = []
    for rec in fields.values():
        if rec.get("domain") not in order or rec.get("status") not in OPEN:
            continue
        spec, prop = registry.spec(rec["field_id"]), rec.get("proposal") or {}
        conf = prop.get("confidence") or 0
        if rec["status"] == "conflict":
            rank, why = 0, f"New proposal {prop.get('value')!s} differs from the decided value {rec.get('value')!s}"
        elif spec.verify == "must_verify":
            rank, why = 1, ("Drafted text: read it before accepting" if rec.get("domain") == "narrative"
                            else "Decision-driving field: confirm individually")
        elif prop.get("issues"):
            rank, why = 2, "; ".join(prop["issues"][:3])
        elif conf < registry.pretick_confidence:
            rank, why = 3, ("Demo stand-in for a bank model" if prop.get("provenance") == "synthetic_demo"
                            else f"Confidence {conf:.0%}")
        else:
            rank, why = 4, "High-confidence proposal"
        items.append({"field_id": rec["field_id"], "domain": rec["domain"], "domain_label": registry.domain_label(rec["domain"]),
                      "label": rec.get("label"), "status": rec["status"], "value": rec.get("value"),
                      "proposal": {k: prop.get(k) for k in ("value", "provenance", "source", "confidence", "issues",
                                                            "resolver", "evidence")},
                      "decision": rec.get("decision"), "verify": spec.verify, "rank": rank, "why": why,
                      "preticked": preticked(rec, registry), "bulk": bulk_eligible(rec, registry)})
    items.sort(key=lambda i: (i["rank"], order[i["domain"]], str(i["label"])))
    return items


def stats(fields: dict, registry: FieldRegistry, domains: Optional[Iterable[str]] = None) -> dict:
    """Population and verification counts (the POC's headline metrics)."""
    scope = set(domains) if domains is not None else None
    recs = [r for r in fields.values() if scope is None or r.get("domain") in scope]
    count = {s: sum(1 for r in recs if r.get("status") == s)
             for s in ("proposed", "confirmed", "overridden", "conflict", "unavailable")}
    total = len(recs)
    # Populated = the system proposed a value (a person's override of a gap does not count).
    populated = sum(1 for r in recs if available((r.get("proposal") or {}).get("value"),
                                                 (r.get("proposal") or {}).get("provenance")))
    decided = count["confirmed"] + count["overridden"]
    return {"total": total, "populated": populated, **count, "pending": count["proposed"] + count["conflict"],
            "preticked": sum(1 for r in recs if preticked(r, registry)),
            "populated_pct": round(100 * populated / total, 1) if total else None,
            "verified_pct": round(100 * decided / total, 1) if total else None,
            "accepted_unchanged_pct": round(100 * count["confirmed"] / decided, 1) if decided else None}


def legacy_reviews(fields: dict) -> dict:
    """The decided fields in the shape of the earlier ``field_reviews`` record (committee pack, audit)."""
    out = {}
    for fid, rec in fields.items():
        d = rec.get("decision")
        if not d:
            continue
        out[fid] = {"status": d["status"], "original": d.get("basis"), "original_provenance": d.get("basis_provenance"),
                    "value": d.get("value"), "reason": d.get("reason") or "", "label": rec.get("label"),
                    "by": d.get("by"), "by_name": d.get("by_name"), "at": d.get("at")}
    return out
