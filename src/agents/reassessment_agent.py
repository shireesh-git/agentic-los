"""
Credit Reassessment Agent — reconsiders the proposed facility after M1–M5.

Reads the case's credit observations, investigations (and their status),
credit challenges (and how the analyst dealt with them), the repayment
assessment and the stress-test scenarios, plus the fact pack's facility,
drawing power, policy thresholds and the policy engine's original
recommendation. It then:

  1. classifies each risk as RESOLVED, MITIGATED or UNRESOLVED;
  2. reads repayment capacity under the base, downside and severe scenarios;
  3. reassesses leverage, liquidity, cash flow and policy exceptions;
  4. re-sizes the facility from deterministic caps and decides whether the
     proposal is SUPPORTED, SUPPORTED_WITH_CONDITIONS, REDUCED_MODIFIED,
     DEFERRED or NOT_SUPPORTED;
  5. proposes mitigants, conditions precedent and conditions subsequent.

Every figure comes from the earlier steps or from a stated formula on them
(see ``supporting_metrics``). The result is compared with the original request
and with the policy engine's recommendation, so the change is explicit.
No LLM is used. Thresholds: ``credit_reassessment`` in config/rules.yaml.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

AGENT_VERSION = "reassessment_agent/reas_v1"

DECISIONS = ["SUPPORTED", "SUPPORTED_WITH_CONDITIONS", "REDUCED_MODIFIED", "DEFERRED", "NOT_SUPPORTED"]
DECISION_LABELS = {
    "SUPPORTED": "Supported",
    "SUPPORTED_WITH_CONDITIONS": "Supported with conditions",
    "REDUCED_MODIFIED": "Reduced / modified",
    "DEFERRED": "Deferred pending information",
    "NOT_SUPPORTED": "Not supported",
}
_DEFAULTS = {"amount_rounding_cr": 5, "min_reduction_pct": 5, "defer_if_open_p1_at_least": 4,
             "book_debt_margin_pct": 40, "stock_margin_pct": 40, "interest_reserve_quarters": 1,
             "hard_security_target_cover": 1.0}
_OPEN_TASK = {"OPEN", "IN_PROGRESS"}
_SEV_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def reassessment_config() -> dict:
    from src.core.config_manager import config
    return config.get("rules", "credit_reassessment", default={}) or {}


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _cr(v) -> str:
    if v is None:
        return "n/a"
    return f"-₹{abs(v):,.2f} Cr" if v < 0 else f"₹{v:,.2f} Cr"


def _x(v) -> str:
    return "n/a" if v is None else f"{v:.2f}x"


def _m(metric, label, value, unit, source) -> dict:
    return {"metric": metric, "label": label, "value": value, "unit": unit, "source": source}


class _Case:
    def __init__(self, case: dict, settings: dict):
        self.case = case
        self.cfg = {**_DEFAULTS, **(settings or {})}
        self.fp = case.get("fact_pack") or {}
        self.policy = self.fp.get("policy_thresholds") or {}
        self.facility = self.fp.get("facility_details") or {}
        self.observations = case.get("observations") or []
        self.tasks = case.get("investigations") or []
        self.challenges = case.get("challenges") or []
        self.repayment = case.get("repayment_analysis") or {}
        stress = case.get("stress_test") or {}
        self.scenarios = {s["scenario"]: s for s in stress.get("scenarios") or []}
        self.stress_period = stress.get("period")

    def metric(self, scenario: str, key: str) -> Optional[float]:
        return _num(((self.scenarios.get(scenario) or {}).get("stressed_metrics") or {}).get(key))

    @property
    def requested(self) -> Optional[float]:
        return _num(self.facility.get("proposed_limit_cr")) or _num(self.facility.get("amount_requested_cr"))

    def tasks_for(self, observation_id: str) -> list[dict]:
        return [t for t in self.tasks
                if t.get("observation_id") == observation_id or observation_id in (t.get("related_observation_ids") or [])]

    def challenges_for(self, observation_id: str) -> list[dict]:
        return [c for c in self.challenges if observation_id in (c.get("linked_observation_ids") or [])]


# ─── 1. Risk status ──────────────────────────────────────────────────────────

def _risk_register(c: _Case) -> list[dict]:
    """Each observation as a risk: RESOLVED, MITIGATED or UNRESOLVED, with why."""
    register = []
    for o in c.observations:
        tasks, chls = c.tasks_for(o["observation_id"]), c.challenges_for(o["observation_id"])
        if o.get("status") in ("EXPLAINED", "DISMISSED"):
            status, why = "RESOLVED", f"Observation marked {o['status'].lower()} by the analyst."
        elif tasks and all(t.get("status") in ("RESOLVED", "WAIVED") for t in tasks):
            status, why = "RESOLVED", "Linked investigation(s) " + ", ".join(
                f"{t['investigation_id']} {t['status'].lower()}" for t in tasks) + "."
        elif o.get("status") == "ACCEPTED" or any(ch.get("status") == "ACCEPTED" for ch in chls):
            status, why = "MITIGATED", "Risk accepted by the analyst" + (
                " (challenge accepted)." if any(ch.get("status") == "ACCEPTED" for ch in chls) else ".")
        else:
            open_tasks = [t["investigation_id"] for t in tasks if t.get("status") in _OPEN_TASK]
            status = "UNRESOLVED"
            why = ("Investigation still open: " + ", ".join(open_tasks) + "." if open_tasks
                   else "No investigation or analyst decision closes it yet.")
        register.append({"observation_id": o["observation_id"], "title": o.get("title"), "category": o.get("category"),
                         "severity": o.get("severity"), "status": status, "why": why,
                         "investigation_ids": [t["investigation_id"] for t in tasks],
                         "challenge_ids": [ch["challenge_id"] for ch in chls]})
    register.sort(key=lambda r: ({"UNRESOLVED": 0, "MITIGATED": 1, "RESOLVED": 2}[r["status"]], _SEV_RANK.get(r["severity"], 9)))
    return register


# ─── 2–3. Dimension reassessment ─────────────────────────────────────────────

def _dimensions(c: _Case) -> dict:
    p = c.policy
    base, down, severe = (lambda k: c.metric("base", k)), (lambda k: c.metric("downside", k)), (lambda k: c.metric("severe", k))
    min_dscr = _num(p.get("min_dscr"))
    max_de, min_cr = _num(p.get("max_debt_to_ebitda")), _num(p.get("min_current_ratio"))

    def status(ok: bool, weak: bool) -> str:
        return "WITHIN POLICY" if ok else "WEAK" if weak else "OUTSIDE POLICY"

    def below(v, floor):
        return v is not None and floor is not None and v < floor

    dims = {
        "repayment_capacity": {
            "status": c.repayment.get("repayment_capacity", "n/a"),
            "detail": f"Base DSCR {_x(base('dscr'))}, downside {_x(down('dscr'))}, severe {_x(severe('dscr'))} "
                      f"(policy minimum {_x(min_dscr)}).",
        },
        "stress_resilience": {
            "status": ("FAILS SEVERE" if below(severe("dscr"), 1.0) or below(severe("interest_coverage_ratio"), 1.0)
                       else "FAILS DOWNSIDE" if below(down("dscr"), min_dscr) else "RESILIENT"),
            "detail": f"Downside: DSCR {_x(down('dscr'))}, ICR {_x(down('interest_coverage_ratio'))}; severe: DSCR "
                      f"{_x(severe('dscr'))}, ICR {_x(severe('interest_coverage_ratio'))}.",
        },
        "leverage": {
            "status": status(not (base("debt_to_ebitda") is not None and max_de is not None and base("debt_to_ebitda") > max_de),
                             False),
            "detail": f"Debt/EBITDA {_x(base('debt_to_ebitda'))} base, {_x(down('debt_to_ebitda'))} downside, "
                      f"{_x(severe('debt_to_ebitda'))} severe (policy maximum {_x(max_de)}).",
        },
        "liquidity": {
            "status": status(not below(base("current_ratio"), min_cr), base("current_ratio") is not None
                             and base("current_ratio") >= 1.0),
            "detail": f"Current ratio {_x(base('current_ratio'))} (policy minimum {_x(min_cr)}).",
        },
        "cash_flow": {
            "status": ("NEGATIVE UNDER STRESS" if (down("operating_cash_flow_cr") or 0) < 0
                       else "WEAK" if (c.repayment.get("primary_repayment_source") or {}).get("adequacy") != "ADEQUATE"
                       else "ADEQUATE"),
            "detail": f"Operating cash flow {_cr(base('operating_cash_flow_cr'))} base, {_cr(down('operating_cash_flow_cr'))} "
                      f"downside, {_cr(severe('operating_cash_flow_cr'))} severe.",
        },
        "policy_exceptions": {
            "status": (f"{len((c.scenarios.get('base') or {}).get('policy_breaches') or [])} BREACH(ES)"
                       if (c.scenarios.get("base") or {}).get("policy_breaches") else "NONE"),
            "detail": ", ".join(f"{b['label']} {b['value']} vs {b['limit_type']} {b['limit']}"
                                for b in (c.scenarios.get("base") or {}).get("policy_breaches") or []) or "No breaches.",
        },
    }
    return dims


# ─── 4. Facility sizing ──────────────────────────────────────────────────────

def _sizing(c: _Case) -> dict:
    """Deterministic caps on the amount the bank can support; each with its formula."""
    p = c.policy
    ebit, interest, debt, ebitda = (c.metric("base", "ebit_cr"), c.metric("base", "finance_cost_cr"),
                                    c.metric("base", "total_debt_cr"), c.metric("base", "ebitda_cr"))
    rate = ((c.scenarios.get("base") or {}).get("working") or {}).get("interest_rate_pct")
    min_icr, max_de = _num(p.get("min_interest_coverage")), _num(p.get("max_debt_to_ebitda"))
    caps = []
    if None not in (ebit, interest, rate, min_icr) and rate:
        headroom = round((ebit / min_icr - interest) / (rate / 100), 2)
        caps.append({"cap": "interest_cover", "label": f"Keeps interest coverage at the {min_icr}x policy minimum",
                     "amount_cr": headroom,
                     "formula": f"(EBIT {_cr(ebit)} / {min_icr} − interest {_cr(interest)}) / rate {rate}%"})
        d_ebit, d_int = c.metric("downside", "ebit_cr"), c.metric("downside", "finance_cost_cr")
        d_rate = ((c.scenarios.get("downside") or {}).get("working") or {}).get("stressed_interest_rate_pct")
        if None not in (d_ebit, d_int, d_rate) and d_rate:
            caps.append({"cap": "interest_cover_downside", "label": "Same test in the downside scenario (information)",
                         "amount_cr": round((d_ebit / min_icr - d_int) / (d_rate / 100), 2), "binding": False,
                         "formula": f"(downside EBIT {_cr(d_ebit)} / {min_icr} − interest {_cr(d_int)}) / rate {d_rate}%"})
    dp = c.fp.get("drawing_power") or {}
    comps = {x.get("name", ""): x for x in dp.get("components") or []}
    rec = next((v for k, v in comps.items() if "Receivable" in k), None)
    days, max_days = c.metric("base", "debtor_days"), _num(p.get("max_debtor_days"))
    if rec and days and max_days:
        rec_value, margin = _num(rec.get("value_cr")), _num(rec.get("margin_pct")) or 25.0
        eligible = round(rec_value * min(1.0, max_days / days), 2)
        other = sum(_num(v.get("dp_cr")) or 0 for k, v in comps.items() if v is not rec)
        caps.append({"cap": "eligible_drawing_power",
                     "label": f"Drawing power counting receivables only up to {max_days:.0f} days",
                     "amount_cr": round(eligible * (1 - margin / 100) + other, 2),
                     "formula": f"receivables {_cr(rec_value)} × {max_days:.0f}/{days} days × (1 − {margin}%) + "
                                f"inventory and creditor drawing power {_cr(other)}"})
    leverage_headroom = round(max_de * ebitda - debt, 2) if None not in (max_de, ebitda, debt) else None
    binding = [cap for cap in caps if cap.get("binding", True)]
    requested = c.requested
    limit = min([requested] + [cap["amount_cr"] for cap in binding]) if requested else None
    step = c.cfg["amount_rounding_cr"]
    recommended = (math.floor(limit / step) * step if limit and limit > 0 else 0.0) if limit is not None else None
    return {"requested_cr": requested, "caps": caps, "leverage_headroom_cr": leverage_headroom,
            "recommended_cr": recommended,
            "binding_cap": min(binding, key=lambda cap: cap["amount_cr"])["cap"] if binding else None}


# ─── 5. Mitigants and conditions ─────────────────────────────────────────────

def _mitigants(c: _Case, register: list[dict], sizing: dict, decision: str) -> tuple[list, list, list]:
    """(mitigants, conditions precedent, conditions subsequent), each item linked to what it answers."""
    unresolved = {r["observation_id"] for r in register if r["status"] == "UNRESOLVED"}
    rule_of = {o["observation_id"]: o["trigger"]["rule_id"] for o in c.observations}
    open_rules = {rule_of[i] for i in unresolved if i in rule_of}
    amount = sizing.get("recommended_cr")
    rate = ((c.scenarios.get("base") or {}).get("working") or {}).get("interest_rate_pct")
    mit, cp, cs = [], [], []

    def add(bucket, text, answers, metric=None):
        bucket.append({"item": text, "addresses": answers, **({"metric": metric} if metric else {})})

    if open_rules & {"WC_DETERIORATION", "RECEIVABLE_COLLECTION"}:
        add(mit, f"Drawing power to exclude receivables older than {c.policy.get('max_debtor_days', 90)} days, "
                 f"disputed and retention amounts; book-debt margin raised to {c.cfg['book_debt_margin_pct']}%.",
            ["Receivable deterioration"])
        add(cs, "Monthly stock and book-debt statements with customer-wise ageing; quarterly receivable audit.",
            ["Receivable deterioration"])
    if "INVENTORY_BUILDUP" in open_rules:
        add(mit, f"Stock margin raised to {c.cfg['stock_margin_pct']}%; non-moving stock (> 180 days) excluded from "
                 "drawing power.", ["Inventory build-up"])
        add(cs, "Half-yearly stock audit by a bank-empanelled auditor.", ["Inventory build-up"])
    down_dscr, min_dscr = c.metric("downside", "dscr"), _num(c.policy.get("min_dscr"))
    if amount and rate and down_dscr is not None and min_dscr is not None and down_dscr < min_dscr:
        reserve = round(amount * rate / 100 / 4 * c.cfg["interest_reserve_quarters"], 2)
        add(cp, f"Interest-servicing reserve of {_cr(reserve)} ({c.cfg['interest_reserve_quarters']} quarter(s) of "
                f"interest on the recommended limit) to be created.", ["Stressed repayment capacity"],
            _m("interest_reserve_cr", "Interest-servicing reserve", reserve, "cr",
               f"recommended limit × {rate}% / 4 × {c.cfg['interest_reserve_quarters']}"))
    headroom = sizing.get("leverage_headroom_cr")
    if headroom is not None and amount and headroom < amount:
        position = (f"debt is already {_cr(-headroom)} above the policy Debt/EBITDA limit" if headroom < 0
                    else f"only {_cr(headroom)} of headroom at the policy Debt/EBITDA limit")
        add(cp, "No net increase in total borrowings: the limit to replace existing short-term lines of an equal "
                f"amount ({position}).", ["Leverage above policy"],
            _m("leverage_headroom_cr", "Debt headroom at policy Debt/EBITDA", headroom, "cr",
               "max Debt/EBITDA × EBITDA − total debt"))
        add(cs, f"Debt/EBITDA covenant ≤ {c.policy.get('max_debt_to_ebitda')}x tested on annual audited accounts; "
                "no further borrowing without the bank's consent.", ["Leverage above policy"])
    sec = (c.repayment.get("secondary_repayment_source") or {}).get("metrics") or {}
    hard = _num(sec.get("hard_security_fsv_cr"))
    target = c.cfg["hard_security_target_cover"]
    # Extra hard security only matters when the bank may have to fall back on it.
    fallback_matters = (c.repayment.get("repayment_capacity") in ("MODERATE", "STRESSED")
                        or (c.repayment.get("secondary_repayment_source") or {}).get("overlaps_primary"))
    if amount and hard is not None and hard < amount * target and fallback_matters:
        extra = round(amount * target - hard, 2)
        add(cp, f"Additional immovable security with forced-sale value of at least {_cr(extra)} so that hard security "
                f"covers the recommended limit {target}x.", ["Weak secondary repayment source"],
            _m("additional_security_cr", "Additional hard security needed", extra, "cr",
               f"recommended limit × {target} − hard security {_cr(hard)}"))
    for t in c.tasks:
        if t.get("status") in _OPEN_TASK and t.get("priority") == "P1":
            add(cp, f"Close investigation: {t['title']}.", [t["investigation_id"]])
    breaches = (c.scenarios.get("base") or {}).get("policy_breaches") or []
    if breaches:
        add(cp, "Deviation approval for " + ", ".join(b["label"] for b in breaches)
                + " at the authority empowered to sanction deviations.", ["Policy exceptions"])
    if "EARNINGS_CASH_CONVERSION" in open_rules:
        add(cs, "Quarterly cash-flow statement; review triggered if OCF / EBITDA falls below 50%.",
            ["Earnings-to-cash conversion"])
    if "MARGIN_COMPRESSION" in open_rules:
        add(cs, "Order-book review each half-year with contract margins and price-escalation terms.", ["Margin compression"])
    if decision in ("REDUCED_MODIFIED", "SUPPORTED_WITH_CONDITIONS") and c.fp.get("management_profile"):
        add(mit, "Personal guarantee of the promoter directors.", ["Overall credit risk"])
    return mit, cp, cs


# ─── Decision ────────────────────────────────────────────────────────────────

def reassess(case: dict, settings: dict | None = None, created_at: str | None = None) -> dict:
    settings = reassessment_config() if settings is None else settings
    c = _Case(case, settings)
    if not c.scenarios or not c.repayment.get("available"):
        return {"available": False, "reason": "Repayment analysis and stress test are needed for a reassessment."}

    register = _risk_register(c)
    dims = _dimensions(c)
    sizing = _sizing(c)
    requested, recommended = sizing["requested_cr"], sizing["recommended_cr"]
    tier1 = (c.fp.get("policy_decisions") or {}).get("tier1_hard_rules") or []
    failed_rules = [d.get("rule") for d in tier1 if str(d.get("result", "")).lower() == "fail"]
    open_p1 = [t for t in c.tasks if t.get("priority") == "P1" and t.get("status") in _OPEN_TASK]
    critical_data = [r for r in register if r["status"] == "UNRESOLVED" and r["category"] == "Data Quality"
                     and r["severity"] == "CRITICAL"]
    unresolved_high = [r for r in register if r["status"] == "UNRESOLVED" and r["severity"] in ("CRITICAL", "HIGH")]
    base_dscr, base_icr = c.metric("base", "dscr"), c.metric("base", "interest_coverage_ratio")
    base_breaches = (c.scenarios.get("base") or {}).get("policy_breaches") or []
    down_breaches = (c.scenarios.get("downside") or {}).get("policy_breaches") or []
    steps = []

    if failed_rules:
        decision = "NOT_SUPPORTED"
        steps.append(f"Hard rule(s) failed: {', '.join(failed_rules)} — cannot be approved by deviation.")
    elif (base_dscr is not None and base_dscr < 1.0) or (base_icr is not None and base_icr < 1.0):
        decision = "NOT_SUPPORTED"
        steps.append(f"Latest-year cash accruals do not cover obligations (DSCR {_x(base_dscr)}, ICR {_x(base_icr)}).")
    elif recommended is not None and recommended <= 0:
        decision = "NOT_SUPPORTED"
        steps.append("No headroom for any additional facility within the interest-cover policy.")
    elif critical_data or len(open_p1) >= c.cfg["defer_if_open_p1_at_least"]:
        decision = "DEFERRED"
        steps.append(f"{len(open_p1)} P1 investigation(s) open" + (" and a critical data conflict unresolved"
                                                                    if critical_data else "")
                     + " — the facility cannot be sized reliably yet.")
    elif requested and recommended is not None and recommended < requested * (1 - c.cfg["min_reduction_pct"] / 100):
        decision = "REDUCED_MODIFIED"
        steps.append(f"Supportable amount {_cr(recommended)} is below the requested {_cr(requested)} "
                     f"(binding cap: {sizing['binding_cap']}).")
    elif sizing["leverage_headroom_cr"] is not None and requested and sizing["leverage_headroom_cr"] < requested:
        decision = "REDUCED_MODIFIED"
        steps.append("Amount can be supported but the structure must change: leverage is at or above policy.")
    elif unresolved_high or base_breaches or down_breaches:
        decision = "SUPPORTED_WITH_CONDITIONS"
        steps.append(f"{len(unresolved_high)} high risk(s) unresolved, {len(base_breaches)} base and "
                     f"{len(down_breaches)} downside policy breach(es).")
    else:
        decision = "SUPPORTED"
        steps.append("No unresolved high risks and no policy breach in the base or downside scenario.")
    if decision == "REDUCED_MODIFIED" and sizing["leverage_headroom_cr"] is not None and recommended \
            and sizing["leverage_headroom_cr"] < recommended:
        steps.append("Structure modified as well: total debt cannot rise while Debt/EBITDA is above policy.")

    mitigants, cps, css = _mitigants(c, register, sizing, decision)
    if decision == "SUPPORTED" and cps:
        decision = "SUPPORTED_WITH_CONDITIONS"
        steps.append(f"{len(cps)} condition(s) precedent apply, so support is conditional.")
    amount_final = (recommended if decision in ("REDUCED_MODIFIED", "SUPPORTED_WITH_CONDITIONS", "SUPPORTED")
                    else (0.0 if decision == "NOT_SUPPORTED" else None))
    if decision in ("SUPPORTED", "SUPPORTED_WITH_CONDITIONS"):
        amount_final = requested

    original = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    orig_rec = original.get("recommendation") or case.get("recommendation")
    kind = str(c.facility.get("facility_type") or "facility").replace("_", " ")
    facility_rec = {
        "facility_type": kind,
        "requested_cr": requested,
        "recommended_cr": amount_final,
        "change_cr": round(amount_final - requested, 2) if (amount_final is not None and requested) else None,
        "structure": ("Replacement of existing short-term lines (no net increase in borrowings)"
                      if any("No net increase" in x["item"] for x in cps) else "As proposed"),
        "sizing": sizing,
        "original_policy_recommendation": orig_rec,
        "original_risk_grade": (c.fp.get("policy_decisions") or {}).get("tier2_risk_scores", {}).get("risk_grade"),
        "deviation_route_required": bool(orig_rec == "decline" and decision != "NOT_SUPPORTED"),
    }
    if orig_rec:
        steps.append(f"Policy engine recommendation was '{orig_rec}' (grade {facility_rec['original_risk_grade']}); "
                     f"the reassessment is '{DECISION_LABELS[decision]}'"
                     + (" — adopting it needs the deviation route." if facility_rec["deviation_route_required"] else "."))

    supporting = [{"factor": p_["factor"], "evidence": p_["evidence"]}
                  for p_ in c.repayment.get("positive_factors") or []]
    supporting += [{"factor": f"Challenge {ch['category'].lower()} answered ({ch['status'].lower()})",
                    "evidence": (ch.get("review") or {}).get("response") or ch["title"]}
                   for ch in c.challenges if ch.get("status") in ("ADDRESSED", "ACCEPTED", "OVERRIDDEN")]
    key_risks = [{"risk": r["title"], "severity": r["severity"], "status": r["status"], "why": r["why"],
                  "observation_id": r["observation_id"]} for r in register if r["severity"] in ("CRITICAL", "HIGH")]
    unresolved_issues = (
        [{"type": "investigation", "id": t["investigation_id"], "title": t["title"], "priority": t.get("priority"),
          "status": t["status"]} for t in c.tasks if t.get("status") in _OPEN_TASK]
        + [{"type": "challenge", "id": ch["challenge_id"], "title": ch["title"], "severity": ch["severity"],
            "status": ch["status"]} for ch in c.challenges if ch.get("status") == "OPEN"])

    counts = {s: sum(1 for r in register if r["status"] == s) for s in ("RESOLVED", "MITIGATED", "UNRESOLVED")}
    overall = {
        "rating": {"STRONG": "SOUND", "ADEQUATE": "SOUND", "MODERATE": "ACCEPTABLE WITH CONDITIONS",
                   "STRESSED": "WEAK"}.get(c.repayment.get("repayment_capacity"), "n/a"),
        "dimensions": dims,
        "risk_status_counts": counts,
    }
    amount_text = (f"{_cr(amount_final)} against {_cr(requested)} requested" if amount_final is not None else "not sized")
    summary = (f"After reviewing {len(register)} observation(s) ({counts['UNRESOLVED']} unresolved, {counts['MITIGATED']} "
               f"mitigated, {counts['RESOLVED']} resolved), {len(c.tasks)} investigation(s), {len(c.challenges)} "
               f"challenge(s) and three stress scenarios, the proposal is reassessed as "
               f"{DECISION_LABELS[decision].upper()}: {amount_text}. Repayment capacity is "
               f"{c.repayment.get('repayment_capacity')}; DSCR is {_x(base_dscr)} in the base case, "
               f"{_x(c.metric('downside', 'dscr'))} in the downside and {_x(c.metric('severe', 'dscr'))} in the severe case.")
    rationale = steps + [f"Risks: {counts['UNRESOLVED']} unresolved, {counts['MITIGATED']} mitigated, "
                         f"{counts['RESOLVED']} resolved.",
                         f"{len(cps)} condition(s) precedent and {len(css)} condition(s) subsequent proposed."]

    supporting_metrics = [
        _m("requested_cr", "Requested limit", requested, "cr", "facility_details"),
        _m("recommended_cr", "Recommended limit", amount_final, "cr", "reassessment sizing"),
        *[_m(cap["cap"], cap["label"], cap["amount_cr"], "cr", cap["formula"]) for cap in sizing["caps"]],
        _m("leverage_headroom_cr", "Debt headroom at policy Debt/EBITDA", sizing["leverage_headroom_cr"], "cr",
           "max Debt/EBITDA × EBITDA − total debt"),
        *[_m(f"{s}_{k}", f"{(c.scenarios[s] or {}).get('label', s)} {label}", c.metric(s, k), unit, f"stress_test.{s}")
          for s in ("base", "downside", "severe") if s in c.scenarios
          for k, label, unit in (("dscr", "DSCR", "x"), ("interest_coverage_ratio", "ICR", "x"),
                                 ("debt_to_ebitda", "Debt/EBITDA", "x"), ("operating_cash_flow_cr", "OCF", "cr"))],
    ]
    return {
        "available": True,
        "case_id": case.get("entity_id"),
        "overall_credit_assessment": overall,
        "reassessment_summary": summary,
        "decision": decision,
        "decision_label": DECISION_LABELS[decision],
        "facility_recommendation": facility_rec,
        "key_supporting_factors": supporting,
        "key_risks": key_risks,
        "risk_register": register,
        "unresolved_issues": unresolved_issues,
        "recommended_mitigants": mitigants,
        "conditions_precedent": cps,
        "conditions_subsequent": css,
        "rationale": rationale,
        "supporting_metrics": supporting_metrics,
        "linked_observations": [o["observation_id"] for o in c.observations],
        "linked_investigations": [t["investigation_id"] for t in c.tasks],
        "linked_challenges": [ch["challenge_id"] for ch in c.challenges],
        "linked_stress_scenarios": [{"scenario": s, "label": v.get("label"), "severity": v.get("severity"),
                                     "period": c.stress_period} for s, v in c.scenarios.items()],
        "generated_by": AGENT_VERSION,
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
    }
