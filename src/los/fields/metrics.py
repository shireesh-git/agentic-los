"""
Populate → Verify metrics for the MIS: how much the agents filled in, how much people verified,
and how much they accepted unchanged — the POC's headline numbers.

Computed from the applications' field stores and the audit trail (nothing is stored separately).
"""

from __future__ import annotations

from src.los.fields.model import available
from src.los.fields.registry import FieldRegistry


def _pct(n: int, d: int):
    return round(100 * n / d, 1) if d else None


def agent_metrics(apps: list[dict], events: list[dict], registry: FieldRegistry) -> dict:
    by_domain: dict[str, dict] = {}
    for app in apps:
        for rec in (app.get("fields") or {}).values():
            d = by_domain.setdefault(rec.get("domain") or "?", {"fields": 0, "populated": 0, "confirmed": 0,
                                                                "overridden": 0, "conflict": 0, "applications": set()})
            prop = rec.get("proposal") or {}
            d["fields"] += 1
            d["applications"].add(app["application_id"])
            d["populated"] += int(available(prop.get("value"), prop.get("provenance")))
            if rec.get("status") in ("confirmed", "overridden", "conflict"):
                d[rec["status"]] += 1
    cam = {"fields": 0, "populated": 0, "confirmed": 0, "overridden": 0}
    for app in apps:                                   # values read from an uploaded CAM
        for rec in (app.get("fields") or {}).values():
            prop = rec.get("proposal") or {}
            if prop.get("resolver") != "cam_document":
                continue
            cam["fields"] += 1
            cam["populated"] += int(available(prop.get("value"), prop.get("provenance")))
            if rec.get("status") in ("confirmed", "overridden"):
                cam[rec["status"]] += 1
    started = [(e.get("detail") or {}).get("mode") for e in events if e["action"] == "cam_attached"]
    cam["applications"] = {mode: started.count(mode) for mode in ("workspace", "document", "generate")}
    cam["accepted_unchanged_pct"] = _pct(cam["confirmed"], cam["confirmed"] + cam["overridden"])
    # S9 / S10: what the T&C agent and the carry-forward agent contributed after the credit decision
    def block(domain: str) -> dict:
        d = by_domain.get(domain) or {"fields": 0, "populated": 0, "confirmed": 0, "overridden": 0, "applications": set()}
        return {"applications": len(d["applications"]), "fields": d["fields"], "populated": d["populated"],
                "confirmed": d["confirmed"], "overridden": d["overridden"],
                "accepted_unchanged_pct": _pct(d["confirmed"], d["confirmed"] + d["overridden"])}
    carry, tnc = block("dis_carry"), block("tnc")
    rows, tot = [], {"fields": 0, "populated": 0, "confirmed": 0, "overridden": 0, "conflict": 0}
    for domain, d in sorted(by_domain.items(), key=lambda kv: -kv[1]["fields"]):
        decided = d["confirmed"] + d["overridden"]
        rows.append({"domain": domain, "label": registry.domain_label(domain), "applications": len(d["applications"]),
                     "fields": d["fields"], "populated": d["populated"], "populated_pct": _pct(d["populated"], d["fields"]),
                     "verified_pct": _pct(decided, d["fields"]), "confirmed": d["confirmed"], "overridden": d["overridden"],
                     "accepted_unchanged_pct": _pct(d["confirmed"], decided), "conflicts": d["conflict"]})
        for k in tot:
            tot[k] += d[k]
    decided = tot["confirmed"] + tot["overridden"]
    prepared = [e for e in events if e["action"] == "application_prepared"]
    durations = [(e.get("detail") or {}).get("duration_ms") for e in prepared]
    durations = [d for d in durations if isinstance(d, (int, float))]
    return {
        "headline": {"fields": tot["fields"], "populated": tot["populated"],
                     "populated_pct": _pct(tot["populated"], tot["fields"]),
                     "verified_pct": _pct(decided, tot["fields"]),
                     "accepted_unchanged_pct": _pct(tot["confirmed"], decided),
                     "overridden": tot["overridden"], "open_conflicts": tot["conflict"],
                     # values that arrived filled and were accepted as they were: keying the person did not do
                     "values_not_keyed": tot["confirmed"]},
        "domains": rows,
        "activity": {"preparations": len(prepared),
                     "avg_preparation_s": round(sum(durations) / len(durations) / 1000, 1) if durations else None,
                     "population_runs": sum(1 for e in events if e["action"] == "fields_populated"),
                     "feedback_reruns": sum(1 for e in events if e["action"] == "assessment_started"
                                            and str(e.get("comment") or "").startswith("Re-running the credit case")),
                     "prospects_from_documents": sum(1 for e in events if e["action"] == "prospect_sourced"),
                     "applications_from_cam": sum(cam["applications"].values())},
        "cam": cam, "carry_forward": carry, "terms": tnc,
        "note": "Populated = a value proposed by an agent with its evidence; verified = a person confirmed or "
                "overrode it; accepted unchanged = confirmed ÷ verified.",
    }
