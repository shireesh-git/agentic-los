"""The CAM engine's verdict in a form every officer can act on (fix list F11–F13).

    assess        the engine's recommendation, hard-rule results and the key ratios against policy, coloured by
                  policy (good / warn / bad); shown as the risk strip on every role's screen
    challenges    the Credit Challenge Agent's challenges, each with plain "what is wrong / why it matters" and
                  suggested actions that the screen turns into buttons (override a figure, reduce the amount,
                  return for documents, record a justification, decline)
    amount_advice whether a smaller amount brings leverage within policy, computed from the engine's figures
    plan          numbered next steps for the officer the proposal is with (Credit Copilot)

Every figure here comes from the engine's record; nothing is estimated.
"""

from __future__ import annotations

from typing import Optional

SEVERITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# ratio id → label, policy threshold key, direction ("min": higher is better)
RATIOS = [("dscr", "DSCR", "min_dscr", "min"),
          ("interest_coverage_ratio", "Interest cover", "min_interest_coverage", "min"),
          ("debt_to_ebitda", "Debt / EBITDA", "max_debt_to_ebitda", "max"),
          ("current_ratio", "Current ratio", "min_current_ratio", "min"),
          ("tol_tnw", "TOL / TNW", "max_tol_tnw", "max"),
          ("debt_to_equity", "Debt / equity", "max_debt_to_equity", "max")]
WARN_BAND = 0.10        # within 10% of the limit on the good side → amber

REC = {"approve": ("Approve", "good"), "approve_with_conditions": ("Approve with conditions", "good"),
       "conditional_approve": ("Approve with conditions", "good"), "refer": ("Refer to higher authority", "warn"),
       "decline": ("Decline", "bad"), "reject": ("Decline", "bad")}


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _latest(ratio_analysis: dict) -> tuple[Optional[str], dict]:
    periods = sorted(k for k in (ratio_analysis or {}) if isinstance(ratio_analysis[k], dict))
    return (periods[-1], ratio_analysis[periods[-1]]) if periods else (None, {})


def _x(v: float) -> str:
    return f"{v:.2f}x"


def assess(engine: Optional[dict]) -> Optional[dict]:
    """The risk strip: recommendation, hard rules, ratios against policy. None without an engine run."""
    if not engine:
        return None
    fp = engine.get("fact_pack") or {}
    rec = str(engine.get("recommendation") or "").lower()
    label, tone = REC.get(rec, (rec.replace("_", " ").capitalize() or "—", "warn"))
    rules = (fp.get("policy_decisions") or {}).get("tier1_hard_rules") or []
    failed = [{"code": r.get("rule"), "label": r.get("description"), "detail": r.get("details")}
              for r in rules if r.get("result") == "fail"]
    unverified = [{"code": r.get("rule"), "label": r.get("description"), "detail": r.get("details")}
                  for r in rules if r.get("result") == "not_verified"]
    limits = fp.get("policy_thresholds") or {}
    period, latest = _latest(fp.get("ratio_analysis") or {})
    ratios = []
    for rid, rlabel, key, way in RATIOS:
        v, lim = _num((latest.get(rid) or {}).get("value")), _num(limits.get(key))
        if v is None:
            continue
        status = "na"
        if lim is not None:
            if way == "min":
                status = "bad" if v < lim else "warn" if v < lim * (1 + WARN_BAND) else "good"
            else:
                status = "bad" if v > lim or v < 0 else "warn" if v > lim * (1 - WARN_BAND) else "good"
        ratios.append({"id": rid, "label": rlabel, "value": v, "display": _x(v), "period": period,
                       "limit": lim, "limit_display": (f"{'min' if way == 'min' else 'max'} {_x(lim)}"
                                                       if lim is not None else "no policy limit"),
                       "status": status})
    return {"recommendation": rec or None, "label": label, "tone": "bad" if failed else tone,
            "rationale": engine.get("rationale"), "rating": engine.get("risk_grade"),
            "score": _num(engine.get("composite_score")), "period": period,
            "hard_rules": {"failed": failed, "not_verified": unverified,
                           "passed": sum(1 for r in rules if r.get("result") == "pass"), "total": len(rules)},
            "ratios": ratios, "breaches": sum(1 for r in ratios if r["status"] == "bad"),
            "headroom": amount_advice(engine), "run_id": engine.get("run_id"), "thresholds": limits,
            "quality": _quality(fp)}


def _quality(fp: dict) -> dict:
    """The quality checks for the risk strip: earnings quality, revenue truth, early-warning flags."""
    eq, rt, ews = fp.get("earnings_quality") or {}, fp.get("revenue_truth") or {}, fp.get("ews_indicators") or {}
    return {"earnings": {"score": eq.get("score"), "status": eq.get("status") or "na",
                         "detail": "; ".join(f"{m['label']} {m['display']}" for m in eq.get("metrics") or [])},
            "revenue_truth": {"score": rt.get("score"), "status": rt.get("status") or "na",
                              "detail": rt.get("summary") or ""},
            "ews": {"flags": ews.get("flags"), "status": ews.get("status") or "na", "checked": ews.get("checked"),
                    "not_checked": ews.get("not_checked"),
                    "items": [{k: i[k] for k in ("label", "status", "detail")} for i in ews.get("indicators") or []
                              if i["status"] == "flag"]}} if (eq or rt or ews) else {}


def needs_justification(risk: Optional[dict]) -> list[str]:
    """Why moving the proposal forward must be justified in writing (empty: no justification needed)."""
    if not risk:
        return []
    out = []
    if risk.get("recommendation") in ("decline", "reject"):
        out.append("the CAM engine recommends Decline")
    if risk["hard_rules"]["failed"]:
        out.append("hard rule(s) failed: " + ", ".join(r["label"] or r["code"] for r in risk["hard_rules"]["failed"]))
    return out


# ── amount ───────────────────────────────────────────────────────────────────

def amount_advice(engine: Optional[dict]) -> Optional[dict]:
    """How much can be lent within policy. From the engine's debt capacity (every policy limit, and the
    structure that passes) when the run has it; older runs: whether a smaller amount brings Debt/EBITDA
    within policy, from the engine's debt basis and EBITDA."""
    if not engine:
        return None
    fp = engine.get("fact_pack") or {}
    dc = fp.get("debt_capacity") or {}
    if dc.get("available"):
        rec = dc.get("recommendation") or {}
        return {"source": "capacity", "fits": dc["fits"], "requested_cr": dc["requested_cr"],
                "sustainable_cr": dc["sustainable_cr"], "binding": dc.get("binding"),
                "max_amount_cr": rec.get("amount_cr") or 0.0, "tenor_months": rec.get("tenor_months"),
                "current_tenor": dc.get("tenor_months"), "text": rec.get("text"), "period": dc.get("period"),
                "not_fixable": dc.get("not_fixable") or [],
                "constraints": [{k: c[k] for k in ("label", "limit_display", "max_amount_cr", "binding")}
                                for c in dc.get("constraints") or []]}
    max_de = _num((fp.get("policy_thresholds") or {}).get("max_debt_to_ebitda"))
    fac = fp.get("facility_details") or {}
    amount = _num(fac.get("proposed_limit_cr")) or _num(fac.get("amount_requested_cr")) or _num(
        engine.get("requested_amount_cr"))
    basis = _num(((fp.get("financial_projections") or {}).get("assumptions") or {}).get("debt_basis_cr"))
    period, _ = _latest(fp.get("ratio_analysis") or {})
    cf = ((fp.get("cash_flow_repayment") or {}).get("periods") or {}).get(period) or {}
    ebitda = _num(cf.get("ebitda_cr"))
    if ebitda is None:
        fs = (fp.get("financial_summary") or {}).get(period) or {}
        ebitda = _num(fs.get("ebitda") if isinstance(fs, dict) else None)
    if None in (max_de, amount, basis, ebitda) or ebitda <= 0:
        return None
    existing = round(basis - amount, 2)
    capacity = round(max_de * ebitda, 2)
    room = round(capacity - existing, 2)
    return {"max_debt_to_ebitda": max_de, "ebitda_cr": ebitda, "period": period, "existing_debt_cr": existing,
            "debt_capacity_cr": capacity, "requested_cr": amount, "max_amount_cr": max(room, 0.0),
            "fits": room >= amount, "pro_forma": round(basis / ebitda, 2)}


def amount_text(h: Optional[dict]) -> str:
    if not h:
        return "The engine record does not hold the debt and EBITDA figures needed to size the amount."
    if h.get("source") == "capacity":
        limits = "; ".join(f"{c['label']} ({c['limit_display']}) allows "
                           + (f"₹{c['max_amount_cr']:,.2f} Cr" if c["max_amount_cr"] >= 0 else "nothing — already outside")
                           for c in h["constraints"])
        return (f"Sustainable limit at the current tenor: ₹{h['sustainable_cr']:,.2f} Cr, bound by {h['binding']}. "
                f"{limits}. {h['text']}")
    head = (f"At the policy maximum of {_x(h['max_debt_to_ebitda'])} Debt/EBITDA, {h['period']} EBITDA of "
            f"₹{h['ebitda_cr']:,.2f} Cr supports debt of ₹{h['debt_capacity_cr']:,.2f} Cr. Existing debt is "
            f"₹{h['existing_debt_cr']:,.2f} Cr")
    if h["fits"]:
        return head + f", so the requested ₹{h['requested_cr']:,.2f} Cr fits within policy."
    if h["max_amount_cr"] > 0:
        return (head + f", so the limit that keeps leverage within policy is ₹{h['max_amount_cr']:,.2f} Cr "
                       f"(requested ₹{h['requested_cr']:,.2f} Cr). Reducing the recommended limit to that amount "
                       f"addresses leverage; coverage (DSCR) still needs the borrower's cash-flow evidence.")
    return (head + ", already above that capacity — no amount brings leverage within policy. Options: return to "
                   "the RM for a deleveraging plan (equity infusion or debt reduction), record a policy deviation "
                   "with mitigants for the Sanctioning Authority, or decline.")


def structure_action(h: Optional[dict]) -> Optional[dict]:
    """The one-click change that brings the proposal within policy, when one exists."""
    if not h or h["fits"] or not h.get("max_amount_cr") or h["max_amount_cr"] <= 0:
        return None
    tenor = h.get("tenor_months") if h.get("source") == "capacity" and h.get("tenor_months") != h.get("current_tenor") else None
    if h.get("source") == "capacity" and h["max_amount_cr"] >= h["requested_cr"] and tenor:
        return {"kind": "reduce_amount", "label": f"Extend tenor to {tenor} months", "field": "tenor_months",
                "value": tenor, "reason": h.get("text") or "Passes policy with a longer tenor"}
    return {"kind": "reduce_amount", "label": f"Set limit to ₹{h['max_amount_cr']:,.2f} Cr"
                                              + (f" over {tenor} months" if tenor else ""),
            "field": "recommended_cr", "value": h["max_amount_cr"], "tenor": tenor,
            "reason": h.get("text") if h.get("source") == "capacity" else
            f"Brings Debt/EBITDA within the policy maximum of {_x(h['max_debt_to_ebitda'])}"}


# ── challenges with actions ─────────────────────────────────────────────────

# what each kind of challenge can be answered with, in order of preference
_PLAYBOOK = {
    "REPAYMENT_CAPACITY": ["reduce_amount", "send_back", "justify", "reject"],
    "LEVERAGE": ["reduce_amount", "send_back", "justify", "reject"],
    "POLICY_EXCEPTIONS": ["send_back", "justify", "reject"],
    "UNRESOLVED_INVESTIGATIONS": ["send_back", "justify"],
    "FACILITY_AMOUNT_CYCLE": ["reduce_amount", "justify"],
    "WORKING_CAPITAL_DP": ["reduce_amount", "send_back", "justify"],
    "FINANCIAL_PERFORMANCE": ["override", "send_back", "justify"],
}
_FIELD = {"FINANCIAL_PERFORMANCE": "ebitda_cr"}


def _why_short(text: Optional[str]) -> str:
    t = (text or "").split(" Linked investigation")[0].strip()
    first = t.split(". ")[0].rstrip(".")
    return first + "." if first else ""


def challenges(engine: Optional[dict], limit: int = 5) -> list[dict]:
    """The engine's challenges, most severe first, each with suggested actions (see _PLAYBOOK)."""
    items = sorted((engine or {}).get("challenges") or [], key=lambda c: SEVERITY.get(str(c.get("severity")), 9))
    head = amount_advice(engine)
    out = []
    for c in items[:limit]:
        rid = c.get("rule_id") or ""
        asks = c.get("required_response") or []
        asks = asks if isinstance(asks, list) else [asks]
        actions = []
        for kind in _PLAYBOOK.get(rid, ["send_back", "justify"]):
            if kind == "reduce_amount":
                act = structure_action(head)
                if act:
                    actions.append(act)
                elif not head or head["fits"]:
                    actions.append({"kind": "reduce_amount", "label": "Review the recommended limit",
                                    "field": "recommended_cr", "value": None, "reason": ""})
            elif kind == "override":
                actions.append({"kind": "override", "label": "Override a figure", "field": _FIELD.get(rid)})
            elif kind == "send_back":
                actions.append({"kind": "send_back", "label": "Return for documents",
                                "prefill": f"{c.get('title')}: please provide — " + "; ".join(asks[:3])})
            elif kind == "justify":
                actions.append({"kind": "justify", "label": "Record justification"})
            elif kind == "reject":
                actions.append({"kind": "reject", "label": "Decline",
                                "prefill": f"Declined: {c.get('title')}. {_why_short(c.get('challenge'))}"})
        out.append({"id": c.get("challenge_id") or rid, "rule_id": rid, "title": c.get("title") or c.get("category"),
                    "category": c.get("category"), "severity": c.get("severity"),
                    "what": c.get("challenge"), "why": _why_short(c.get("rationale")),
                    "challenge": c.get("challenge"), "asks": asks, "ask": asks[0] if asks else None,
                    "actions": actions,
                    "amount_note": amount_text(head) if rid in ("LEVERAGE", "REPAYMENT_CAPACITY") and head else None})
    return out


# ── next steps for the officer (Credit Copilot) ─────────────────────────────

def plan(stage: str, available: list[str], risk: Optional[dict], against: list[dict], responses: dict,
         blockers: list[str], editable: bool, focus: Optional[str] = None,
         register: Optional[list] = None) -> tuple[str, list[dict]]:
    """Numbered next steps and the buttons that go with them. ``available`` is the stage's actions."""
    steps, buttons = [], []
    reg = register or []
    if stage in ("rm", "credit_risk"):
        todo = [d for d in reg if d["deviable"] and d["status"] in ("open", "rejected")]
        if todo:
            steps.append(f"Record a mitigant and justification for {len(todo)} policy deviation(s) in the Deviation "
                         f"Register: " + "; ".join(d["label"] for d in todo[:4]) + ".")
            buttons.append({"kind": "goto", "label": "Open the Deviation Register", "target": "sec-dev"})
    elif stage == "sanction":
        pend = [d for d in reg if d["deviable"] and d["status"] == "proposed"]
        if pend:
            steps.append(f"Approve or reject {len(pend)} deviation(s) with Underwriting's mitigants: "
                         + "; ".join(d["label"] for d in pend[:4]) + ".")
            buttons.append({"kind": "goto", "label": "Open the Deviation Register", "target": "sec-dev"})
    if risk and risk.get("tone") == "bad":
        why = needs_justification(risk)
        steps.append(f"Note the engine's verdict: {risk['label']}" + (f" — {'; '.join(why)}" if why else "") + ".")
    open_ = [a for a in against if a["id"] not in responses]
    if focus:
        open_ = [a for a in against if focus.lower() in (a["title"] or "").lower()] or open_
    shown = []
    for a in open_[:3]:
        options = [x for x in a["actions"] if _allowed(x["kind"], available, editable)]
        if not options:
            continue
        shown.append(a)
        names = " or ".join(x["label"].lower() if i else x["label"] for i, x in enumerate(options[:3]))
        steps.append(f"{a['title']} ({str(a['severity']).lower()}): {names}."
                     + (f" {a['amount_note']}" if a.get("amount_note") and any(
                         x["kind"] == "reduce_amount" for x in options) else ""))
    # one button per kind of action, not one per challenge
    reduce = next((x | {"challenge": a["id"]} for a in shown for x in a["actions"]
                   if x["kind"] == "reduce_amount" and x.get("value") and editable), None)
    if reduce:
        buttons.append(reduce)
    if shown:
        buttons.append({"kind": "goto", "label": "Answer the challenges", "target": "sec-chal"})
    if shown and "send_back" in available:
        asks = [a["asks"][0] for a in shown if a.get("asks")]
        buttons.append({"kind": "send_back", "label": "Return for documents",
                        "prefill": "Please provide: " + "; ".join(asks) if asks else ""})
    if shown and "reject" in available and risk and risk.get("tone") == "bad":
        buttons.append({"kind": "reject", "label": "Decline",
                        "prefill": f"Declined: the CAM engine recommends {risk['label']} — "
                                   + "; ".join(a["title"] for a in shown) + "."})
    done = [a for a in against if a["id"] in responses]
    if done:
        steps.append(f"Already answered: {', '.join(a['title'] for a in done)}.")
    for b in blockers:
        steps.append(f"Before you can proceed: {b}.")
    proceed = "approve" in available and not blockers
    if proceed:
        why = needs_justification(risk)
        steps.append(("To proceed, write a justification (required because " + "; ".join(why) + "). "
                      if why else "Then proceed. ") + "Otherwise return or decline with remarks.")
        buttons.append({"kind": "approve", "label": "Proceed"})
    if not steps:
        steps.append("Nothing is outstanding for you on this proposal.")
    text = "Next steps:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    return text, buttons


def _allowed(kind: str, available: list[str], editable: bool) -> bool:
    return {"reduce_amount": editable, "override": editable, "send_back": "send_back" in available,
            "reject": "reject" in available, "justify": True}.get(kind, False)
