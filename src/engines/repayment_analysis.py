"""
Cash Flow & Repayment Analysis — deterministic.

A credit view of whether the borrower can service and repay its debt, built
from figures the existing engines already produce in the fact pack:

  * financial_summary    — EBITDA, operating cash flow, total debt (per period)
  * ratio_analysis       — DSCR, interest coverage, Debt/EBITDA, OCF/Debt (ratio engine)
  * cash_flow_repayment  — finance cost (interest obligation), capex, free cash flow
  * collateral_analysis  — security for the secondary repayment source
  * policy_thresholds    — the bank's minimums / maximums

Nothing is recomputed. Two simple, labelled ratios are added: OCF / EBITDA
(cash conversion) and OCF / interest (can operating cash pay the interest).
Each period is graded so the latest year can be compared with history; no
forecasting or stress testing is done here.

Bands: ``repayment_analysis`` in config/rules.yaml.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.engines.ratio_engine import as_pct

ENGINE_VERSION = "repayment_v1"
GENERATED_BY = f"repayment_analysis/{ENGINE_VERSION}"

CAPACITY_LEVELS = ["STRONG", "ADEQUATE", "MODERATE", "STRESSED"]
RISK_LEVELS = ["LOW", "MODERATE", "HIGH", "VERY_HIGH"]
_CAPACITY_RISK = {"STRONG": "LOW", "ADEQUATE": "LOW", "MODERATE": "MODERATE", "STRESSED": "HIGH"}

_DEFAULT_BANDS = {
    "dscr": [1.5, "policy", 1.0],
    "interest_coverage_ratio": [3.0, "policy", 1.5],
    "debt_to_ebitda": [3.0, "policy", 5.0],
    "ocf_to_ebitda_pct": [70, 50, 25],
    "ocf_to_interest": [3.0, 1.5, 1.0],
}
_POLICY_KEY = {"dscr": "min_dscr", "interest_coverage_ratio": "min_interest_coverage",
               "debt_to_ebitda": "max_debt_to_ebitda"}
_LOWER_IS_BETTER = {"debt_to_ebitda"}

# (key, label, unit, where the figure comes from)
METRICS = [
    ("ebitda_cr", "EBITDA", "cr", "financial_summary"),
    ("operating_cash_flow_cr", "Operating cash flow", "cr", "financial_summary"),
    ("ocf_to_ebitda_pct", "OCF / EBITDA (cash conversion)", "pct", "derived: OCF / EBITDA"),
    ("finance_cost_cr", "Interest obligation (finance cost)", "cr", "cash_flow_repayment"),
    ("ocf_to_interest", "OCF / interest", "x", "derived: OCF / finance cost"),
    ("total_debt_cr", "Total debt", "cr", "financial_summary"),
    ("debt_to_ebitda", "Debt / EBITDA", "x", "ratio_engine"),
    ("interest_coverage_ratio", "Interest coverage (EBIT / interest)", "x", "ratio_engine"),
    ("dscr", "DSCR", "x", "ratio_engine"),
    ("ocf_to_debt", "OCF / Debt", "pct", "ratio_engine"),
    ("capex_cr", "Capex", "cr", "cash_flow_repayment"),
    ("free_cash_flow_cr", "Free cash flow (OCF − capex)", "cr", "cash_flow_repayment"),
]
_GRADED = ("dscr", "interest_coverage_ratio", "debt_to_ebitda", "ocf_to_ebitda_pct", "ocf_to_interest")


def repayment_config() -> dict:
    from src.core.config_manager import config
    return config.get("rules", "repayment_analysis", default={}) or {}


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


class _Facts:
    def __init__(self, fact_pack: dict, settings: dict):
        self.fp = fact_pack or {}
        self.fin = (self.fp.get("financial_summary") or {}).get("periods") or {}
        self.ratios = self.fp.get("ratio_analysis") or {}
        self.cash = (self.fp.get("cash_flow_repayment") or {}).get("periods") or {}
        self.policy = self.fp.get("policy_thresholds") or {}
        self.periods = sorted(self.fin) or sorted(self.ratios)
        self.bands = {**_DEFAULT_BANDS, **(settings.get("bands") or {})}
        self.cover = {"strong": 1.5, "partial": 1.0, **(settings.get("secondary_cover") or {})}

    def ratio(self, period, name):
        entry = (self.ratios.get(period) or {}).get(name)
        return _num(entry.get("value") if isinstance(entry, dict) else entry)

    def values(self, period: str) -> dict:
        fin, cash = self.fin.get(period) or {}, self.cash.get(period) or {}
        ebitda, ocf = _num(fin.get("ebitda_cr")), _num(fin.get("operating_cash_flow_cr"))
        interest = _num(cash.get("finance_cost_cr"))
        ocf_debt = self.ratio(period, "ocf_to_debt")
        return {
            "ebitda_cr": ebitda,
            "operating_cash_flow_cr": ocf,
            "ocf_to_ebitda_pct": round(ocf / ebitda * 100, 1) if (ocf is not None and ebitda) else None,
            "finance_cost_cr": interest,
            "ocf_to_interest": round(ocf / interest, 2) if (ocf is not None and interest) else None,
            "total_debt_cr": _num(fin.get("total_debt_cr")),
            "debt_to_ebitda": self.ratio(period, "debt_to_ebitda"),
            "interest_coverage_ratio": self.ratio(period, "interest_coverage_ratio"),
            "dscr": self.ratio(period, "dscr"),
            "ocf_to_debt": as_pct(ocf_debt),
            "capex_cr": _num(cash.get("capex_cr")),
            "free_cash_flow_cr": _num(cash.get("free_cash_flow_cr")),
        }

    def band(self, key: str) -> list[float]:
        raw = list(self.bands[key])
        policy = _num(self.policy.get(_POLICY_KEY.get(key, ""), None))
        return [policy if b == "policy" else _num(b) for b in raw]

    def grade(self, key: str, value: Optional[float]) -> Optional[str]:
        if value is None:
            return None
        strong, adequate, weak = self.band(key)
        if key in _LOWER_IS_BETTER:
            return ("strong" if value <= strong else "adequate" if value <= adequate
                    else "weak" if value <= weak else "critical")
        return ("strong" if value >= strong else "adequate" if value >= adequate
                else "weak" if value >= weak else "critical")


def _capacity(grades: dict, fcf: Optional[float]) -> tuple[str, list[str]]:
    """Capacity from the graded metrics (and free cash flow); returns (level, reasons)."""
    g = [v for v in grades.values() if v]
    weak = [k for k, v in grades.items() if v == "weak"] + (["free_cash_flow"] if fcf is not None and fcf < 0 else [])
    critical = [k for k, v in grades.items() if v == "critical"]
    if critical or len(weak) >= 3:
        level = "STRESSED"
    elif weak:
        level = "MODERATE"
    elif sum(1 for v in g if v == "strong") >= 3:
        level = "STRONG"
    else:
        level = "ADEQUATE"
    label = {key: lbl for key, lbl, _, _ in METRICS} | {"free_cash_flow": "negative free cash flow"}
    reasons = []
    if critical:
        reasons.append("critical: " + ", ".join(label.get(k, k) for k in critical))
    if weak:
        reasons.append("weak: " + ", ".join(label.get(k, k) for k in weak))
    if not reasons:
        reasons.append(f"{sum(1 for v in g if v == 'strong')} of {len(g)} measures strong, none weak")
    return level, reasons


def _secondary(fp: dict, f: _Facts, observations: dict) -> dict:
    col = fp.get("collateral_analysis") or {}
    items = col.get("collaterals") or []
    amount = _num(col.get("facility_amount_cr")) or _num((fp.get("facility_details") or {}).get("amount_requested_cr"))
    fsv, cover = _num(col.get("total_forced_sale_value_cr")), _num(col.get("coverage_ratio_fsv"))
    if not items or not fsv:
        return {"source": "None evidenced", "description": "No security is recorded for this facility; recovery would "
                "depend on promoter support or refinancing, neither of which is evidenced.",
                "adequacy": "INADEQUATE", "metrics": {}}
    current = [c for c in items if "current" in str(c.get("type", "")).lower()]
    hard = [c for c in items if c not in current]
    hard_fsv = round(sum(_num(c.get("forced_sale_value_cr")) or 0 for c in hard), 2)
    hard_cover = round(hard_fsv / amount, 2) if amount else None
    adequacy = "ADEQUATE" if cover >= f.cover["strong"] else "PARTIAL" if cover >= f.cover["partial"] else "INADEQUATE"
    overlap = bool(current) and any(r in observations for r in ("WC_DETERIORATION", "RECEIVABLE_COLLECTION",
                                                                "INVENTORY_BUILDUP"))
    desc = (f"Security of {', '.join(str(c.get('type')) for c in items)} with forced-sale value {_cr(fsv)} "
            f"against the facility of {_cr(amount)} ({_x(cover)} cover).")
    if current:
        desc += (f" Excluding hypothecated current assets, hard security of {_cr(hard_fsv)} covers {_x(hard_cover)}.")
    if overlap:
        desc += (" The current assets charged are the same receivables and stock the analysis has flagged, so this "
                 "part of the security weakens together with the primary source.")
    return {"source": "Security (collateral)", "description": desc, "adequacy": adequacy, "overlaps_primary": overlap,
            "metrics": {"forced_sale_value_cr": fsv, "fsv_cover": cover, "hard_security_fsv_cr": hard_fsv,
                        "hard_security_cover": hard_cover, "facility_amount_cr": amount}}


def analyse_repayment(fact_pack: dict, case_id: str, observations: list[dict] | None = None,
                      created_at: str | None = None, settings: dict | None = None) -> dict:
    """Structured repayment assessment for the latest period, with the history it is compared against."""
    settings = repayment_config() if settings is None else settings
    f = _Facts(fact_pack, settings)
    if not f.periods:
        return {"available": False, "reason": "No financial periods in the fact pack."}
    latest = f.periods[-1]
    prior = f.periods[-2] if len(f.periods) >= 2 else None
    obs = {o["trigger"]["rule_id"]: o for o in observations or []
           if o.get("trigger") and o.get("status") not in ("EXPLAINED", "ACCEPTED", "DISMISSED")}

    history = {p: f.values(p) for p in f.periods}
    grades = {p: {k: f.grade(k, history[p][k]) for k in _GRADED} for p in f.periods}
    capacity_by_period = {p: _capacity(grades[p], history[p]["free_cash_flow_cr"])[0] for p in f.periods}
    capacity, capacity_reasons = _capacity(grades[latest], history[latest]["free_cash_flow_cr"])
    now, before = history[latest], history.get(prior) or {}

    key_metrics = []
    for key, label, unit, source in METRICS:
        bands = f.band(key) if key in _GRADED else None
        key_metrics.append({
            "metric": key, "label": label, "unit": unit, "source": source,
            "by_period": {p: history[p][key] for p in f.periods},
            "latest": now[key], "prior": before.get(key),
            "grade": grades[latest].get(key), "prior_grade": grades[prior].get(key) if prior else None,
            "policy": _num(f.policy.get(_POLICY_KEY[key])) if key in _POLICY_KEY else None,
            "bands": bands,
        })

    # ── Primary source: cash generated by operations ──
    facility = fact_pack.get("facility_details") or {}
    wc = facility.get("facility_type") == "working_capital"
    primary = {
        "source": "Operating cash flow",
        "description": ("Cash accruals from operations, realised through collection of the receivables and sale of the "
                        "stock that the working-capital limit finances." if wc else
                        "Cash accruals from operations after interest, available for principal repayment."),
        "adequacy": {"STRONG": "ADEQUATE", "ADEQUATE": "ADEQUATE", "MODERATE": "PARTIAL", "STRESSED": "INADEQUATE"}[capacity],
        "metrics": {k: now[k] for k in ("operating_cash_flow_cr", "ocf_to_ebitda_pct", "ocf_to_interest", "dscr",
                                        "free_cash_flow_cr")},
    }
    secondary = _secondary(fact_pack, f, obs)

    # ── Risk: capacity, adjusted by the strength of the fallback ──
    risk = _CAPACITY_RISK[capacity]
    risk_steps = [f"Repayment capacity {capacity} → base risk {risk}."]
    idx = RISK_LEVELS.index(risk)
    if secondary["adequacy"] == "INADEQUATE":
        idx = min(idx + 1, len(RISK_LEVELS) - 1)
        risk_steps.append("Raised one level: the secondary source does not cover the facility.")
    elif secondary["adequacy"] == "ADEQUATE" and not secondary.get("overlaps_primary") and capacity != "STRESSED":
        idx = max(idx - 1, 0)
        risk_steps.append("Lowered one level: security independently covers the facility.")
    risk = RISK_LEVELS[idx]

    positives, concerns = _factors(f, latest, prior, now, before, grades, capacity_by_period, secondary, obs)
    reasoning = ([f"{p}: {capacity_by_period[p]}" for p in f.periods]
                 + [f"Latest-year capacity {capacity} ({'; '.join(capacity_reasons)})."] + risk_steps)
    trend = (f"Repayment capacity moved from {capacity_by_period[prior]} in {prior} to {capacity} in {latest}"
             if prior and capacity_by_period[prior] != capacity else f"Repayment capacity is {capacity} in {latest}")
    summary = (f"{trend}. Operating cash flow of {_cr(now['operating_cash_flow_cr'])} is "
               f"{_x(now['ocf_to_interest'])} the interest obligation of {_cr(now['finance_cost_cr'])} and DSCR is "
               f"{_x(now['dscr'])}; "
               f"repayment risk is {risk.replace('_', ' ')}.")
    return {
        "available": True,
        "case_id": case_id,
        "summary": summary,
        "period": latest,
        "prior_period": prior,
        "periods": f.periods,
        "repayment_capacity": capacity,
        "capacity_by_period": capacity_by_period,
        "primary_repayment_source": primary,
        "secondary_repayment_source": secondary,
        "key_metrics": key_metrics,
        "positive_factors": positives,
        "concerns": concerns,
        "repayment_risk": risk,
        "reasoning": reasoning,
        "generated_by": GENERATED_BY,
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
        "ai_explanation": None,
    }


def _factors(f, latest, prior, now, before, grades, capacity_by_period, secondary, obs):
    """Positive factors and concerns, each with the figures behind it."""
    pos, con = [], []

    def concern(text, evidence, severity, rule=None):
        con.append({"concern": text, "evidence": evidence, "severity": severity,
                    "linked_observation_id": obs[rule]["observation_id"] if rule in obs else None})

    e0, e1 = before.get("ebitda_cr"), now["ebitda_cr"]
    o0, o1 = before.get("operating_cash_flow_cr"), now["operating_cash_flow_cr"]
    d0, d1 = before.get("total_debt_cr"), now["total_debt_cr"]
    growth = (lambda a, b: round((b - a) / a * 100, 1) if (a and b is not None and a > 0) else None)
    eg, og, dg = growth(e0, e1), growth(o0, o1), growth(d0, d1)

    # Concerns
    if eg is not None and og is not None and eg >= 0 and og < 0:
        concern("Operating cash flow declining despite EBITDA growth",
                f"EBITDA {_cr(e0)} → {_cr(e1)} ({eg:+.1f}%); OCF {_cr(o0)} → {_cr(o1)} ({og:+.1f}%); cash conversion "
                f"{before.get('ocf_to_ebitda_pct')}% → {now['ocf_to_ebitda_pct']}%.", "HIGH", "EARNINGS_CASH_CONVERSION")
    if dg is not None and eg is not None and dg - eg >= 15:
        concern("Debt increasing faster than EBITDA",
                f"Total debt {_cr(d0)} → {_cr(d1)} ({dg:+.1f}%) against EBITDA {eg:+.1f}%; Debt/EBITDA "
                f"{_x(before.get('debt_to_ebitda'))} → {_x(now['debt_to_ebitda'])}.", "HIGH", "LEVERAGE_INCREASE")
    if now["dscr"] is not None and before.get("dscr") is not None and now["dscr"] < before["dscr"] \
            and grades[latest]["dscr"] in ("weak", "critical"):
        concern("DSCR deterioration",
                f"DSCR {_x(before['dscr'])} → {_x(now['dscr'])}, below the policy minimum of "
                f"{_x(_num(f.policy.get('min_dscr')))}.", "HIGH", "DEBT_SERVICING_PRESSURE")
    if now["ocf_to_interest"] is not None and now["ocf_to_interest"] < 1.0:
        concern("Operating cash flow does not cover interest",
                f"OCF {_cr(o1)} against interest of {_cr(now['finance_cost_cr'])} ({_x(now['ocf_to_interest'])}).",
                "HIGH")
    if now["free_cash_flow_cr"] is not None and now["free_cash_flow_cr"] < 0:
        concern("Negative free cash flow",
                f"Free cash flow {_cr(now['free_cash_flow_cr'])} after capex of {_cr(now['capex_cr'])}; the gap was "
                f"funded by borrowing (debt {_cr(d0)} → {_cr(d1)}).", "MEDIUM")
    if grades[latest]["interest_coverage_ratio"] in ("weak", "critical"):
        concern("Interest coverage below policy",
                f"Interest coverage {_x(now['interest_coverage_ratio'])} against a minimum of "
                f"{_x(_num(f.policy.get('min_interest_coverage')))}.", "HIGH")
    if secondary.get("overlaps_primary"):
        concern("Secondary source overlaps the primary",
                "Part of the security is hypothecated receivables and stock — the same assets whose collection is in "
                f"question. Hard security alone covers {_x(secondary['metrics'].get('hard_security_cover'))}.", "MEDIUM")
    elif secondary["adequacy"] == "INADEQUATE":
        concern("Weak fallback", secondary["description"], "MEDIUM")

    # Positive factors
    history_strong = [p for p in f.periods[:-1] if capacity_by_period[p] in ("STRONG", "ADEQUATE")]
    if history_strong and capacity_by_period[latest] not in ("STRONG", "ADEQUATE"):
        pos.append({"factor": "Track record before the latest year",
                    "evidence": f"Repayment capacity was {', '.join(f'{p} {capacity_by_period[p]}' for p in history_strong)} "
                                f"before {latest}."})
    if eg is not None and eg > 0:
        pos.append({"factor": "EBITDA still growing", "evidence": f"EBITDA {_cr(e0)} → {_cr(e1)} ({eg:+.1f}%)."})
    ocfs =[f.values(p)["operating_cash_flow_cr"] for p in f.periods]
    if all(v is not None and v > 0 for v in ocfs):
        pos.append({"factor": "Operating cash flow positive in every year",
                    "evidence": "OCF " + ", ".join(f"{p} {_cr(v)}" for p, v in zip(f.periods, ocfs)) + "."})
    if grades[latest]["interest_coverage_ratio"] in ("strong", "adequate"):
        pos.append({"factor": "Interest coverage within policy",
                    "evidence": f"Interest coverage {_x(now['interest_coverage_ratio'])} (minimum "
                                f"{_x(_num(f.policy.get('min_interest_coverage')))})."})
    de = f.ratio(latest, "debt_to_equity")
    max_de = _num(f.policy.get("max_debt_to_equity"))
    if de is not None and max_de is not None and de <= max_de / 2:
        pos.append({"factor": "Moderate gearing on the balance sheet",
                    "evidence": f"Debt/Equity {_x(de)} against a policy maximum of {_x(max_de)}."})
    if secondary["adequacy"] in ("ADEQUATE", "PARTIAL"):
        pos.append({"factor": "Security available as a fallback",
                    "evidence": f"Forced-sale value {_cr(secondary['metrics'].get('forced_sale_value_cr'))} "
                                f"({_x(secondary['metrics'].get('fsv_cover'))} cover)."})
    return pos, con
