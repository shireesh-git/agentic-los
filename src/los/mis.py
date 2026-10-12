"""
Management MIS (LOS Phase 7): pipeline, turnaround, SLA, decision quality,
sanction / disbursement and copilot adoption, computed from the applications and
the append-only audit trail (nothing is stored separately).

Time in a step is measured between the event that moved the application into the
step and the event that moved it out; SLA compliance compares that with the step's
SLA (calendar days, as the workflow does). Seeded demo history is included and the
MIS says so.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from src.los.workflow import TERMINAL, sla_state

AGE_BUCKETS = [(0, 15, "0–15 days"), (15, 30, "16–30 days"), (30, 60, "31–60 days"), (60, 10 ** 6, "Over 60 days")]
_DECISIONS = {"approve": "approved", "sanction": "approved", "submit": "approved",
              "return": "returned", "reject": "rejected"}


def _days(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 86400


def step_visits(app: dict, events: list[dict], wf) -> list[dict]:
    """Completed visits: {step, stage, days, within_sla} from the moves in the audit trail."""
    visits, entered = [], {}
    for e in sorted(events, key=lambda e: (e["at"], e.get("event_id") or 0)):
        if e["action"] == "create" and e.get("to_step"):
            entered[e["to_step"]] = e["at"]
            continue
        src, dst = e.get("from_step"), e.get("to_step")
        if not src or src == dst or src not in entered:
            continue
        step = wf.step(src)
        days = _days(entered.pop(src), e["at"])
        visits.append({"step": src, "step_name": step.name, "stage": step.stage_id, "role": step.role,
                       "days": days, "within_sla": days <= step.sla_days, "sla_days": step.sla_days})
        if dst:
            entered[dst] = e["at"]
    return visits


def build_mis(apps: list[dict], events_by_app: dict[str, list[dict]], wf, now: datetime,
              copilot_events: Optional[list[dict]] = None) -> dict:
    active = [a for a in apps if a["status"] not in TERMINAL]
    stages = {s["id"]: s["name"] for s in wf.stages}

    # Pipeline
    pipeline = {sid: {"stage": name, "count": 0, "amount_cr": 0.0} for sid, name in stages.items()}
    for a in active:
        p = pipeline[a["stage_id"]]
        p["count"] += 1
        p["amount_cr"] += a.get("amount_cr") or 0
    ageing = {label: 0 for _, _, label in AGE_BUCKETS}
    for a in active:
        age = _days(a["created_at"], now.isoformat())
        ageing[next(label for lo, hi, label in AGE_BUCKETS if lo <= age < hi)] += 1

    # Turnaround and SLA (completed visits)
    by_step: dict[str, list[dict]] = defaultdict(list)
    stage_time: dict[str, list[float]] = defaultdict(list)
    for a in apps:
        visits = step_visits(a, events_by_app.get(a["application_id"], []), wf)
        per_stage: dict[str, float] = defaultdict(float)
        for v in visits:
            by_step[v["step"]].append(v)
            per_stage[v["stage"]] += v["days"]
        current = a.get("stage_id") if a["status"] not in TERMINAL else None
        for st, d in per_stage.items():
            if st != current:                                   # only stages the application has left
                stage_time[st].append(d)
    tat_steps = []
    for step in wf.steps:
        vs = by_step.get(step.id) or []
        if vs:
            tat_steps.append({"id": step.id, "step": step.name, "stage": stages[step.stage_id], "visits": len(vs),
                              "avg_days": round(sum(v["days"] for v in vs) / len(vs), 1), "sla_days": step.sla_days,
                              "within_sla_pct": round(100 * sum(v["within_sla"] for v in vs) / len(vs))})
    tat_stages = [{"stage": stages[sid], "applications": len(stage_time[sid]),
                   "avg_days": round(sum(stage_time[sid]) / len(stage_time[sid]), 1)}
                  for sid in stages if stage_time.get(sid)]
    all_visits = [v for vs in by_step.values() for v in vs]

    # Live SLA breaches by role
    breaches: dict[str, int] = defaultdict(int)
    for a in active:
        if not a.get("step_id"):
            continue
        step = wf.step(a["step_id"])
        if sla_state(datetime.fromisoformat(a["step_entered_at"]), step, now)["breached"]:
            breaches[wf.roles.get(step.role, step.role)] += 1

    # Decision quality at review and committee steps
    decisions: dict[str, dict] = {}
    returned_apps = set()
    for a in apps:
        for e in events_by_app.get(a["application_id"], []):
            kind = _DECISIONS.get(e["action"])
            if not kind or not e.get("from_step"):
                continue
            step = wf.step(e["from_step"])
            if step.kind not in ("checker", "committee", "vp_review"):
                continue
            d = decisions.setdefault(step.id, {"id": step.id, "step": step.name, "stage": step.stage_id,
                                               "approved": 0, "returned": 0, "rejected": 0})
            d[kind] += 1
            if kind == "returned":
                returned_apps.add(a["application_id"])
    for d in decisions.values():
        total = d["approved"] + d["returned"] + d["rejected"]
        d["return_rate_pct"] = round(100 * d["returned"] / total) if total else 0
    decided = {a["application_id"] for a in apps
               if any(_DECISIONS.get(e["action"]) for e in events_by_app.get(a["application_id"], []))}

    # Sanctions, disbursement, conditions
    final = [a["sanctions"]["AP"] for a in apps if (a.get("sanctions") or {}).get("AP")]
    sanctioned = sum(s["sanctioned_cr"] for s in final)
    requested = sum(s.get("requested_cr") or 0 for s in final)
    tranches = [t for a in apps for t in (a.get("disbursement") or {}).get("tranches") or []]
    today = now.date().isoformat()
    conds = [c for a in apps for c in a.get("conditions") or []]

    copilot_events = copilot_events or []
    return {
        "as_of": now.isoformat(timespec="minutes"),
        "note": "Includes seeded demo history; turnaround uses calendar days.",
        "headline": {
            "active": len(active), "pipeline_cr": round(sum(p["amount_cr"] for p in pipeline.values()), 2),
            "avg_step_days": round(sum(v["days"] for v in all_visits) / len(all_visits), 1) if all_visits else None,
            "sla_compliance_pct": round(100 * sum(v["within_sla"] for v in all_visits) / len(all_visits))
            if all_visits else None,
            "live_breaches": sum(breaches.values()),
            "first_time_right_pct": round(100 * (len(decided - returned_apps)) / len(decided)) if decided else None,
            "final_sanctions": len(final), "sanctioned_cr": round(sanctioned, 2),
            "sanction_to_request_pct": round(100 * sanctioned / requested) if requested else None,
            "disbursed_cr": round(sum(t["amount_cr"] for t in tranches if t["status"] == "disbursed"), 2),
        },
        "pipeline": [dict(p, amount_cr=round(p["amount_cr"], 2)) for p in pipeline.values()],
        "ageing": [{"bucket": k, "count": v} for k, v in ageing.items()],
        "tat_stages": tat_stages, "tat_steps": tat_steps,
        "breaches_by_role": sorted([{"role": r, "count": n} for r, n in breaches.items()], key=lambda x: -x["count"]),
        "decisions": [decisions[s.id] for s in wf.steps if s.id in decisions],
        "sanctions": {"ip": sum(1 for a in apps if (a.get("sanctions") or {}).get("IP")), "final": len(final),
                      "deviating": sum(1 for a in apps for s in (a.get("sanctions") or {}).values()
                                       if s.get("deviates_from_recommendation")),
                      "below_request": sum(1 for s in final if s.get("requested_cr") and
                                           s["sanctioned_cr"] < s["requested_cr"] - 1e-6)},
        "conditions": {"cp_open": sum(1 for c in conds if c["type"] == "CP" and c["status"] == "open"),
                       "cs_overdue": sum(1 for c in conds if c["type"] == "CS" and c["status"] in ("open", "deferred")
                                         and c.get("due") and c["due"] < today),
                       "waived": sum(1 for c in conds if c["status"] == "waived"),
                       "deferred": sum(1 for c in conds if c["status"] == "deferred")},
        "copilot": {"tasks_run": sum(1 for e in copilot_events if e["action"] == "copilot_action"),
                    "questions": sum(1 for e in copilot_events if e["action"] == "copilot_ask"),
                    "applications": len({e["application_id"] for e in copilot_events})},
    }
