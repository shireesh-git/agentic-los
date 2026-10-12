"""
Review & committee pack (LOS Phase 3): what the Risk Reviewer, EVP and Sanction
Committee need to decide, assembled from the credit case and the application.

Presentation only — nothing is recomputed:
  headline, decision trail, unresolved risks, open due diligence and challenges,
  deviations and conditions come from M1–M6 and the composed CAM;
  the analyst's overrides, review status, comments and sanctions come from the
  LOS application and its audit trail;
  the committee brief is the existing number-guarded CAM interpretation (AI).
"""

from __future__ import annotations

from typing import Optional

from src.engines.cam_composer import fmt

PACK_VERSION = "los_committee_pack/v1"
BRIEF_SECTIONS = ("executive_summary", "final_recommendation")
_COMMENT_ACTIONS = ("submit", "approve", "return", "reject", "sanction", "escalate", "allocate", "field_review")


def committee_deviations(case: Optional[dict]) -> list[list]:
    """Policy exceptions the sanction accepts: failed / unverified hard rules, base-case policy-limit breaches and a
    reassessed recommendation that differs from the system recommendation. [[deviation, value, basis], ...]"""
    if not case:
        return []
    fr = ((case.get("reassessment") or {}).get("facility_recommendation")) or {}
    pol = ((case.get("fact_pack") or {}).get("policy_decisions") or {}).get("tier3_recommendation") or {}
    hard = [r for r in case.get("tier1_decisions") or [] if r.get("result") in ("fail", "not_verified")]
    base = next((s for s in (case.get("stress_test") or {}).get("scenarios") or [] if s.get("scenario") == "base"), {})
    return ([[f"Hard rule: {r.get('rule_description') or r.get('rule_code')}",
              {"fail": "Failed", "not_verified": "Not verified"}[r["result"]], r.get("details") or ""] for r in hard]
            + [[f"Policy limit: {b['label']}", f"{b['value']} vs {b['limit_type']} {b['limit']}",
                "Base case (latest audited year)"] for b in base.get("policy_breaches") or []]
            + ([["System recommendation", str(pol.get("recommendation") or "").replace("_", " ").title(),
                 "Reassessed recommendation differs — deviation route required"]]
               if fr.get("deviation_route_required") else []))


def build_committee_pack(case: Optional[dict], final_cam: Optional[dict], app: dict, events: list[dict],
                         review_summary: Optional[dict] = None, step_names: Optional[dict] = None) -> dict:
    if not case or not (final_cam or {}).get("available"):
        return {"available": False, "reason": "No credit assessment is available for this application yet."}
    step_names = step_names or {}
    rea = case.get("reassessment") or {}
    fr = rea.get("facility_recommendation") or {}
    fp = case.get("fact_pack") or {}
    pol = (fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    headline = final_cam.get("headline") or {}
    sections = {s["id"]: s for s in final_cam.get("sections") or []}

    brief = {sid: (sections.get(sid) or {}).get("ai_interpretation") for sid in BRIEF_SECTIONS}

    overrides = [{"field_id": fid, "label": r.get("label"), "original": r.get("original"), "value": r.get("value"),
                  "reason": r.get("reason"), "by_name": r.get("by_name"), "at": r.get("at"),
                  "tab": fid.split(".", 1)[0]}
                 for fid, r in (app.get("field_reviews") or {}).items() if r.get("status") == "overridden"]

    deviations = committee_deviations(case)

    comments = [{"at": e["at"], "actor": e.get("actor_name"), "role": e.get("actor_role_name"), "action": e["action"],
                 "step": step_names.get(e.get("from_step"), e.get("from_step")), "comment": e["comment"]}
                for e in events if e.get("comment") and e["action"] in _COMMENT_ACTIONS]

    recommended = fr.get("recommended_cr")
    return {
        "available": True, "version": PACK_VERSION, "run_id": case.get("run_id"), "run_at": case.get("run_at"),
        "headline": {
            "decision": rea.get("decision"), "decision_label": rea.get("decision_label"),
            "decision_sentence": headline.get("decision_sentence"),
            "requested_cr": fr.get("requested_cr"), "recommended_cr": recommended,
            "structure": fr.get("structure"),
            "risk_grade": pol.get("risk_grade") or case.get("risk_grade"),
            "composite_score": pol.get("composite_score") or case.get("composite_score"),
            "overall_assessment": (rea.get("overall_credit_assessment") or {}).get("rating"),
            "repayment_capacity": (case.get("repayment_analysis") or {}).get("repayment_capacity"),
            "resilience_implication": headline.get("resilience_implication"),
            "approving_authority": headline.get("approving_authority"),
            "deviation_route_required": bool(fr.get("deviation_route_required")),
        },
        "brief": brief,
        "trail": final_cam.get("decision_trail") or {},
        "review_status": review_summary or {},
        "overrides": overrides,
        "risks": [{"risk": r["risk"], "severity": r["severity"], "status": r["status"], "why": r["why"]}
                  for r in rea.get("key_risks") or []],
        "open_items": [{"type": u.get("type"), "title": u.get("title"), "priority": u.get("priority") or u.get("severity"),
                        "status": u.get("status")} for u in rea.get("unresolved_issues") or []],
        "deviations": deviations,
        "conditions": {k: [x["item"] for x in rea.get(f"conditions_{k}") or []] for k in ("precedent", "subsequent")}
        | {"mitigants": [x["item"] for x in rea.get("recommended_mitigants") or []]},
        "comments": comments,
        "sanctions": app.get("sanctions") or {},
        "recommended_sanction_cr": recommended if recommended not in (None, 0) else None,
        "recommended_sanction_label": fmt(recommended, "cr") if recommended not in (None, 0) else "Not supported",
        "links": {"final_cam_pdf": f"/api/cases/{app['entity_id']}/final-cam-pdf",
                  "final_cam_html": f"/api/cases/{app['entity_id']}/final-cam-html"},
    }
