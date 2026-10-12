"""Project finance module (Client One GAP-P1-01).

Multiple projects per application, each linked to facilities, with the
documented fields: identification, TEV and consultant report, total project
cost and means of finance, promoter contribution, commercial viability,
repayment/DSRA/disbursement plan, the risk register (pre-construction,
sponsor/group, funding, other) with levels, and the change record (cost,
original vs revised DCCO, repayment shift, scope, overrun) that triggers
reappraisal.

Reapproval thresholds for DCCO, cost and scope changes are confirmation-required
(spec §23/P1-01) — the app flags changes for review and does not invent a
numeric threshold.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from src.application.errors import InvalidRequestError

PROJECT_NATURES = ("greenfield", "brownfield", "expansion", "refinancing", "other")
NIP = ("NIP", "NMP")
RISK_LEVELS = ("Low", "Medium", "High")
RISK_CATEGORIES = ("pre_construction", "sponsor_group", "funding", "other")


def blank_project(index: int) -> dict:
    return {"project_id": f"PRJ-{index:03d}", "name": None, "type": None, "funding_type": None,
            "purpose": None, "refinancing": False, "nip_nmp": None, "description": None, "location": None,
            "state": None, "current_performance": None,
            "tev": {"total_cr": None, "details": None, "consultant": None, "agency": None,
                    "report": None, "report_date": None},
            "cost": {"total_cr": None, "appraised_cr": None, "incurred_cr": None,
                     "financing_arrangement": None, "means_of_finance": None,
                     "promoter_contribution_cr": None, "tied_up_loans": None},
            "commercial_viability": None,
            "plan": {"repayment_schedule": None, "dsra": None, "disbursement_plan": None,
                     "original_dcco": None, "revised_dcco": None, "repayment_shift": None},
            "group_project_status": None, "shareholder_agreements": None, "escrow_tra": None,
            "state_support": None, "consultant_inputs": None, "equity_infusion": None,
            "standby_arrangements": None, "promoter_capability": None,
            "risks": [], "stage": "initiated", "status": "active",
            "changes": [], "facility_ids": [], "evidence": []}


def _n(value, name: str):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        raise InvalidRequestError(f"{name} must be a number")


def _d(value, name: str) -> Optional[str]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise InvalidRequestError(f"{name} must be YYYY-MM-DD")


def normalise_project(raw: dict, index: int, known_facilities: set, existing: Optional[dict] = None) -> dict:
    rec = {**(existing or {})}
    rec.update({k: v for k, v in dict(raw or {}).items() if v not in (None, "")})
    if not str(rec.get("name") or "").strip():
        raise InvalidRequestError(f"Project {index}: the project name is required")
    if rec.get("type") and str(rec["type"]) not in PROJECT_NATURES:
        raise InvalidRequestError(f"Project {index}: type must be one of {', '.join(PROJECT_NATURES)}")
    if rec.get("nip_nmp") and str(rec["nip_nmp"]) not in NIP:
        raise InvalidRequestError(f"Project {index}: NIP/NMP must be NIP or NMP")
    facility_ids = [str(f).strip() for f in rec.get("facility_ids") or [] if str(f).strip()]
    unknown = [f for f in facility_ids if f not in known_facilities]
    if unknown:
        raise InvalidRequestError(f"Project {index}: unknown facility linkage(s) {', '.join(unknown)}")
    rec["facility_ids"] = facility_ids
    tev = rec.get("tev") or {}
    cost = rec.get("cost") or {}
    plan = rec.get("plan") or {}
    tev["total_cr"] = _n(tev.get("total_cr"), "project TEV")
    tev["report_date"] = _d(tev.get("report_date"), "TEV report date")
    for k in ("total_cr", "appraised_cr", "incurred_cr", "promoter_contribution_cr"):
        cost[k] = _n(cost.get(k), f"project cost {k}")
    for k in ("original_dcco", "revised_dcco"):
        plan[k] = _d(plan.get(k), k)
    rec["tev"], rec["cost"], rec["plan"] = tev, cost, plan
    risks = []
    for i, r in enumerate(rec.get("risks") or [], 1):
        desc = str(r.get("description") or "").strip()
        level = str(r.get("level") or "").strip()
        if not desc:
            raise InvalidRequestError(f"Project {index} risk {i}: the risk description is required")
        if level not in RISK_LEVELS:
            raise InvalidRequestError(f"Project {index} risk {i}: level must be Low, Medium or High")
        cat = str(r.get("category") or "other").strip()
        risks.append({"id": f"RSK-{i:02d}", "category": cat if cat in RISK_CATEGORIES else "other",
                      "description": desc, "allocated_party": (str(r.get("allocated_party") or "").strip() or None),
                      "residual_comments": (str(r.get("residual_comments") or "").strip() or None), "level": level})
    rec["risks"] = risks
    rec.setdefault("changes", [])
    return rec


def record_change(project: dict, raw: dict, at: str, by_name: str) -> dict:
    """A project cost / DCCO / scope change — flagged for reappraisal (GAP-P2-02)."""
    fields = ("field", "previous", "current", "reason", "impact_on_repayment", "impact_on_finance")
    change = {}
    for f in fields:
        v = raw.get(f)
        change[f] = (str(v).strip() if v is not None else None)
    if not change.get("field") or change.get("current") in (None, ""):
        raise InvalidRequestError("A project change needs the field and the current value")
    change.update(id=f"CHG-{len(project.get('changes', [])) + 1:02d}", at=at, by=by_name,
                  status="flagged for reappraisal")
    project.setdefault("changes", []).append(change)
    if change["field"] in ("cost", "dcco", "scope") or "cost" in str(change["field"]).lower():
        project["status"] = "reappraisal_required"
    return change


def project_summary(projects: list[dict]) -> dict:
    return {"total": len(projects),
            "reappraisal_required": [p["project_id"] for p in projects if p.get("status") == "reappraisal_required"],
            "high_risks": [r["description"] for p in projects for r in p.get("risks", []) if r["level"] == "High"]}
