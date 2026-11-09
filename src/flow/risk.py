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
VERSION = 3          # bump when assess() gains fields: stored summaries older than this are rebuilt on load

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
    return {"v": VERSION, "recommendation": rec or None, "label": label, "tone": "bad" if failed else tone,
            "rationale": engine.get("rationale"), "rating": engine.get("risk_grade"),
            "score": _num(engine.get("composite_score")), "period": period,
            "hard_rules": {"failed": failed, "not_verified": unverified,
                           "passed": sum(1 for r in rules if r.get("result") == "pass"), "total": len(rules)},
            "ratios": ratios, "breaches": sum(1 for r in ratios if r["status"] == "bad"),
            "headroom": amount_advice(engine), "run_id": engine.get("run_id"), "thresholds": limits,
            "quality": _quality(fp)}


GRADE_TONE = {"A": "good", "B": "good", "C": "warn", "D": "bad", "E": "bad"}


def verdict(risk: Optional[dict], checks: Optional[dict], authority: str) -> Optional[dict]:
    """What the engine's verdict means and what to do about it, in one or two plain sentences (fix list E2).

    ``checks`` is the checks view (src/flow/checks.view); ``authority`` names who decides next, e.g.
    "Vikram Shah (Sanctioning Authority)". Credit quality and outstanding checks are toned separately, so an
    amber "checks outstanding" never reads as a verdict on the borrower.
    """
    if not risk:
        return None
    rec = risk.get("recommendation") or ""
    grade, score = risk.get("rating") or "—", risk.get("score")
    quality = f"{grade}" + (f", score {score:g}/100" if score is not None else "")
    credit_tone = GRADE_TONE.get(str(grade)[:1], "warn")
    checks = checks or {}
    open_items = [i for i in checks.get("items") or [] if i.get("open")]
    failed = [i for i in open_items if i["status"] == "fail"]
    unverified = [i for i in open_items if i["status"] == "not_verified"]
    resolved = [i for i in checks.get("items") or [] if i["status"] != "pass" and i.get("note")]
    breaches = [r["label"] for r in risk.get("ratios") or [] if r.get("status") == "bad"]
    label, tone = risk.get("label"), risk.get("tone")
    names = lambda xs: ", ".join(i["label"].lower() for i in xs)        # noqa: E731
    if rec in ("decline", "reject") or failed:
        why = []
        if failed:
            why.append(f"{'a mandatory check failed' if len(failed) == 1 else 'mandatory checks failed'} "
                       f"({names(failed)})")
        if str(grade)[:1] in ("D", "E"):
            why.append(f"credit quality is weak ({quality})")
        if breaches:
            why.append(f"{', '.join(breaches)} outside policy")
        text = (f"The engine recommends Decline: {'; '.join(why) or 'see the rationale below'}. Proceeding needs a "
                f"written justification; it is recorded as a deviation and shown to {authority}.")
        label, tone = "Decline", "bad"
    elif rec == "refer" and unverified and str(grade)[:1] in ("A", "B"):
        text = (f"Credit quality is {'strong' if str(grade)[:1] == 'A' else 'acceptable'} ({quality}). The engine "
                f"refers the case only because {len(unverified)} mandatory check(s) could not be run: "
                f"{names(unverified)}. Verify them from evidence, or record why you are proceeding; "
                f"{authority} sees what you record.")
        label, tone = "Refer: checks outstanding", "warn"
    elif rec == "refer" and not unverified and resolved and str(grade)[:1] in ("A", "B"):
        text = (f"Credit quality is {'strong' if str(grade)[:1] == 'A' else 'acceptable'} ({quality}). The checks the "
                f"engine could not run have been addressed by an officer ({names(resolved)}); {authority} "
                f"decides with those notes in view.")
        label, tone = "Refer: checks addressed", "good"
    elif rec == "refer":
        text = (f"Credit quality is borderline ({quality}){'; ' + ', '.join(breaches) + ' outside policy' if breaches else ''}"
                f". The engine asks for a higher approval level: {authority} decides, and the bank's credit committee "
                f"if the delegation requires it.")
        label = "Refer to higher authority"
    else:
        cond = "with conditions" if "condition" in str(label).lower() else ""
        text = (f"Credit quality is {'strong' if str(grade)[:1] == 'A' else 'acceptable'} ({quality}) and all "
                f"mandatory checks are clear. The engine supports approval {cond}".rstrip() + "; review the key risk "
                f"challenges below before you move the proposal on.")
    return {"label": label, "tone": tone, "text": text, "credit_tone": credit_tone, "quality": quality,
            "checks_open": len(open_items)}


def _quality(fp: dict) -> dict:
    """The quality checks for the risk strip: earnings quality, revenue truth, early-warning flags."""
    eq, rt, ews = fp.get("earnings_quality") or {}, fp.get("revenue_truth") or {}, fp.get("ews_indicators") or {}
    return {"earnings": {"score": eq.get("score"), "status": eq.get("status") or "na",
                         "detail": "; ".join(f"{m['label']} {m['display']}" for m in eq.get("metrics") or [])},
            "revenue_truth": {"score": rt.get("score"), "status": rt.get("status") or "na",
                              "detail": rt.get("summary") or ""},
            "ews": {"flags": ews.get("flags"), "status": ews.get("status") or "na", "checked": ews.get("checked"),
                    "not_checked": ews.get("not_checked"),
                    "items": [{**{k: i[k] for k in ("id", "label", "status")}, "detail": _plain_flag(i),
                               "action": EWS_ACTION.get(i["id"], ("Note it in the CAM", "none"))[0],
                               "act": EWS_ACTION.get(i["id"], ("", "none"))[1]}
                              for i in ews.get("indicators") or [] if i["status"] == "flag"],
                    "unchecked": [{"label": i["label"], "needs": i["detail"]}
                                  for i in ews.get("indicators") or [] if i["status"] == "na"]}} if (eq or rt or ews) else {}


def _plain_flag(ind: dict) -> str:
    """An indicator's finding in words: "588 days old (as_of_date=2025-03-31)" → "about 19 months old (31 Mar 2025)"."""
    import re
    detail = str(ind.get("detail") or "")
    m = re.search(r"(FY\d{4}) is (\d+) days old \(as_of_date=(\d{4})-(\d{2})-(\d{2})\)", detail)
    if m:
        fy, days, y, mo, d = m.groups()
        month = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()[int(mo) - 1]
        return (f"The latest audited statements ({fy}, to {int(d)} {month} {y}) are about {round(int(days) / 30.4)} "
                f"months old")
    return re.sub(r"\s*\(?\b\w+_\w+=[^)\s]+\)?", "", detail).strip()


EWS_ABOUT = ("Early-warning flags are signs, found at origination, that the account may need closer watching "
             "after disbursement. A flag is not a rejection: each one says what to do about it.")
# indicator → (what to do, the screen action that does it: send_back = return to the RM for it, none = note only)
EWS_ACTION = {
    "stale_financials": ("Ask the RM for the latest audited or provisional results", "send_back"),
    "statutory_dues": ("Ask for GST filing evidence, or the reason for the delay", "send_back"),
    "cheque_returns": ("Ask the RM for the reason for the returns and the banker's conduct note", "send_back"),
    "bureau_stress": ("Get a no-dues or regularisation letter from the lender with the overdue", "send_back"),
    "revenue_mismatch": ("Ask for a reconciliation of revenue with GST turnover and bank credits", "send_back"),
    "non_operating_profit": ("No action before sanction: assess repayment on operating profit only", "none"),
    "negative_ocf": ("Ask for a cash-flow plan; consider tighter monitoring covenants", "send_back"),
    "receivables_decoupled": ("Ask for the receivables ageing and the top debtors", "send_back"),
    "forensic_beneish": ("Review the accounting policies; consider a forensic review", "none"),
    "distress": ("Weigh against the debt capacity; usually a Decline signal unless mitigated", "none"),
    "board_independence": ("No action before sanction: note it for governance monitoring", "none"),
}


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
         register: Optional[list] = None, *, labels: Optional[dict] = None, checks: Optional[dict] = None,
         standing: Optional[str] = None) -> tuple[str, list[dict]]:
    """Where the proposal stands, then at most three numbered steps in the order to do them (fix list E4).

    Every step names a button that exists on this officer's screen, by its label (``labels``: the stage's
    labels from config/flow.yaml) and where it is; Decline appears only as the last resort. ``available`` is
    the stage's actions; ``checks`` the mandatory-checks view; ``standing`` one sentence on the verdict.
    """
    labels = labels or {}
    approve_l = labels.get("approve") or "Proceed"
    return_l = labels.get("send_back") or "Return"
    decline_l = labels.get("reject") or "Decline"
    steps, buttons = [], []
    reg = register or []

    open_checks = [i for i in (checks or {}).get("items") or [] if i.get("open")]
    if open_checks and stage != "cad":
        names = ", ".join(i["label"].lower() for i in open_checks)
        how = ("record what evidence you saw (Record verification) or why you proceed without it (Proceed with "
               "justification)")
        if "send_back" in available:
            how += f", or ask for the evidence with **{return_l}**"
        steps.append(f"Clear the mandatory checks still open ({names}): in **Mandatory checks**, {how}.")
        buttons.append({"kind": "goto", "label": "Go to Mandatory checks", "target": "sec-checks"})

    if stage in ("rm", "credit_risk"):
        todo = [d for d in reg if d["deviable"] and d["status"] in ("open", "rejected")]
        if todo:
            steps.append(f"Record a mitigant and justification for {len(todo)} policy deviation(s) in the "
                         f"**Deviation Register**: " + "; ".join(d["label"] for d in todo[:3]) + ".")
            buttons.append({"kind": "goto", "label": "Go to the Deviation Register", "target": "sec-dev"})
    elif stage == "sanction":
        pend = [d for d in reg if d["deviable"] and d["status"] == "proposed"]
        if pend:
            steps.append(f"Approve or reject {len(pend)} deviation(s) in the **Deviation Register**, with "
                         f"Underwriting's mitigants: " + "; ".join(d["label"] for d in pend[:3]) + ".")
            buttons.append({"kind": "goto", "label": "Go to the Deviation Register", "target": "sec-dev"})

    open_ = [a for a in against if a["id"] not in responses]
    if focus:
        open_ = [a for a in against if focus.lower() in (a["title"] or "").lower()] or open_
    shown = []
    for a in open_[:2]:
        options = [x for x in a["actions"] if _allowed(x["kind"], available, editable) and x["kind"] != "reject"]
        if not options:
            continue
        shown.append(a)
        names = " or ".join(f"**{x['label']}**" for x in options[:3])
        steps.append(f"Answer the challenge “{a['title']}” ({str(a['severity']).lower()}): in **Key Risk "
                     f"Challenges**, under that challenge, use {names}."
                     + (f" {a['amount_note']}" if a.get("amount_note") and any(
                         x["kind"] == "reduce_amount" for x in options) else ""))
    reduce = next((x | {"challenge": a["id"]} for a in shown for x in a["actions"]
                   if x["kind"] == "reduce_amount" and x.get("value") and editable), None)
    if reduce:
        buttons.append(reduce)
    if shown:
        buttons.append({"kind": "goto", "label": "Go to Key Risk Challenges", "target": "sec-chal"})
    if shown and "send_back" in available:
        asks = [a["asks"][0] for a in shown if a.get("asks")]
        buttons.append({"kind": "send_back", "label": return_l,
                        "prefill": ("Please provide: " + "; ".join(asks)) if asks else ""})

    for b in blockers:
        steps.append(f"Before you can proceed: {b}.")
    if "approve" in available and not blockers:
        why = needs_justification(risk)
        steps.append(f"{'Then press' if steps else 'Press'} **{approve_l}** in the action bar"
                     + (f"; you will be asked for a written justification, because {'; '.join(why)}" if why else "")
                     + ".")
        buttons.append({"kind": "approve", "label": approve_l})

    more = max(len(steps) - 3, 0)
    steps = steps[:3]
    done = [a for a in against if a["id"] in responses]
    tail = []
    if more:
        tail.append(f"({more} more step(s) after these — ask again once they are done.)")
    if done:
        tail.append(f"Already answered: {', '.join(a['title'] for a in done)}.")
    if "reject" in available and risk and risk.get("tone") == "bad":
        tail.append(f"If the proposal cannot be fixed: **{decline_l}** in the action bar, with your reasons.")
        buttons.append({"kind": "reject", "label": decline_l,
                        "prefill": f"Declined: the CAM engine recommends {risk['label']}"
                                   + (" — " + "; ".join(a["title"] for a in shown) if shown else "") + "."})
    if not steps:
        steps.append("Nothing is outstanding for you on this proposal.")
    head = (standing.strip() + "\n\n") if standing else ""
    text = (head + "Next steps:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
            + ("\n" + "\n".join(tail) if tail else ""))
    return text, buttons


def _allowed(kind: str, available: list[str], editable: bool) -> bool:
    return {"reduce_amount": editable, "override": editable, "send_back": "send_back" in available,
            "reject": "reject" in available, "justify": True}.get(kind, False)
