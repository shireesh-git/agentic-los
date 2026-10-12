"""
Credit Challenge Agent — questions the proposed facility instead of supporting it.

Reads the case's fact pack (facility, drawing power, cash flow, projections,
ratios, benchmarks, policy), its credit observations and its investigation
tasks, and raises a challenge wherever a deterministic rule finds that the
proposal leans on something the analysis puts in doubt. Seven areas:

  facility amount · repayment capacity · working-capital requirement ·
  leverage · financial performance · policy exceptions · unresolved investigations

Figures come from the existing engines. The only new arithmetic is transparent
and stated with its formula in ``supporting_metrics`` (e.g. trade working
capital at last year's cycle, the receivables level at which drawing power
equals the requested limit). The agent never approves, declines or changes a
policy calculation; it is not a pipeline agent and leaves the CAM untouched.

Thresholds: ``credit_challenges`` in config/rules.yaml.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

from src.models.challenges import ChallengeStatus, CreditChallenge
from src.models.observations import SEVERITY_ORDER

log = logging.getLogger(__name__)

AGENT_VERSION = "challenge_agent/chl_v1"

_OPEN_TASK = {"OPEN", "IN_PROGRESS"}
_CLOSED_OBS = {"EXPLAINED", "ACCEPTED", "DISMISSED"}


def challenge_config() -> dict:
    from src.core.config_manager import config
    return config.get("rules", "credit_challenges", default={}) or {}


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


def _m(metric: str, label: str, value, unit: str, period: str | None, source: str) -> dict:
    return {"metric": metric, "label": label, "value": value, "unit": unit, "period": period, "source": source}


class _Case:
    """Read-only view of everything the rules use."""

    def __init__(self, fact_pack: dict, observations: list[dict], investigations: list[dict], settings: dict):
        self.fp = fact_pack or {}
        self.settings = settings
        self.fin = (self.fp.get("financial_summary") or {}).get("periods") or {}
        self.ratios = self.fp.get("ratio_analysis") or {}
        periods = sorted(self.fin) or sorted(self.ratios)
        self.latest = periods[-1] if periods else None
        self.prior = periods[-2] if len(periods) >= 2 else None
        self.facility = self.fp.get("facility_details") or {}
        self.policy = self.fp.get("policy_thresholds") or {}
        # Observations the analyst has explained, accepted or dismissed no longer support a challenge.
        self.obs = {o["trigger"]["rule_id"]: o for o in observations or []
                    if o.get("trigger") and o.get("status") not in _CLOSED_OBS}
        self.tasks = {t["investigation_type"]: t for t in investigations or []}

    def cfg(self, area: str) -> dict:
        return self.settings.get(area) or {}

    def line(self, period, key):
        return _num((self.fin.get(period) or {}).get(key)) if period else None

    def ratio(self, period, name):
        entry = (self.ratios.get(period) or {}).get(name) if period else None
        return _num(entry.get("value") if isinstance(entry, dict) else entry)

    def observed(self, rule_id, key):
        return ((self.obs.get(rule_id) or {}).get("trigger") or {}).get("observed", {}).get(key)

    def links(self, rule_ids=(), task_types=()) -> tuple[list[str], list[str]]:
        obs = [self.obs[r]["observation_id"] for r in rule_ids if r in self.obs]
        tasks = [self.tasks[t]["investigation_id"] for t in task_types if t in self.tasks]
        return obs, tasks

    def task_note(self, task_type) -> str:
        t = self.tasks.get(task_type)
        return f" Linked investigation {t['investigation_id']} is {t['status']}." if t else ""

    @property
    def limit(self) -> Optional[float]:
        """The amount being challenged: the enhancement when there is an existing limit, else the request."""
        proposed = _num(self.facility.get("proposed_limit_cr")) or _num(self.facility.get("amount_requested_cr"))
        existing = _num(self.facility.get("existing_limit_cr"))
        return proposed - existing if (proposed and existing) else proposed

    def proposal_text(self) -> str:
        f = self.facility
        kind = str(f.get("facility_type") or "facility").replace("_", " ")
        existing, proposed = _num(f.get("existing_limit_cr")), _num(f.get("proposed_limit_cr") or f.get("amount_requested_cr"))
        if existing:
            return f"{kind.title()} limit enhancement {_cr(existing)} → {_cr(proposed)}"
        return f"New {kind} limit of {_cr(proposed)}"


# ─── Rules: one per area; each returns a challenge dict (or None) ────────────

def _facility_amount(c: _Case) -> Optional[dict]:
    """Working-capital ask that the lengthening cycle, not growth, would explain."""
    cfg = c.cfg("facility_amount")
    if c.facility.get("facility_type") != "working_capital" or not c.prior:
        return None
    wcc0, wcc1 = c.ratio(c.prior, "working_capital_cycle"), c.ratio(c.latest, "working_capital_cycle")
    rev1 = c.line(c.latest, "revenue_cr")
    nwc = {}
    for p in (c.prior, c.latest):
        parts = [c.line(p, k) for k in ("trade_receivables_cr", "inventory_cr", "trade_payables_cr")]
        nwc[p] = None if None in parts else round(parts[0] + parts[1] - parts[2], 2)
    if None in (wcc0, wcc1, rev1, nwc[c.prior], nwc[c.latest]) or wcc1 - wcc0 < cfg.get("min_cycle_increase_days", 15):
        return None
    increase = round(nwc[c.latest] - nwc[c.prior], 2)
    at_old_cycle = round(rev1 * wcc0 / 365, 2)
    from_growth = round(at_old_cycle - nwc[c.prior], 2)
    from_cycle = round(nwc[c.latest] - at_old_cycle, 2)
    if increase <= 0 or from_cycle <= 0:
        return None
    share = round(from_cycle / increase * 100, 1)
    if share < cfg.get("min_cycle_share_pct", 50):
        return None
    limit = c.limit
    severity = "HIGH" if (limit and from_cycle >= limit) else "MEDIUM"
    rec_g, rev_g = c.observed("WC_DETERIORATION", "receivables_growth_pct"), c.observed("WC_DETERIORATION", "revenue_growth_pct")
    growth_text = (f"Receivables grew {rec_g}% while revenue grew {rev_g}%. " if rec_g is not None else "")
    obs, tasks = c.links(("WC_DETERIORATION", "RECEIVABLE_COLLECTION", "INVENTORY_BUILDUP"),
                         ("RECEIVABLE_DETERIORATION", "INVENTORY_BUILDUP"))
    return dict(
        rule_id="FACILITY_AMOUNT_CYCLE", category="Facility amount", title="Requested amount reflects a slower cycle",
        challenge=(f"{growth_text}Of the {_cr(increase)} rise in trade working capital in {c.latest}, about "
                   f"{_cr(from_cycle)} ({share}%) comes from the cycle lengthening by {round(wcc1 - wcc0, 2)} days "
                   f"(from {wcc0} to {wcc1}) and only "
                   f"{_cr(from_growth)} from revenue growth. The requested {_cr(limit)} may be funding deterioration in "
                   f"collections and stock rather than business growth."),
        rationale=("A working-capital limit should fund the operating cycle of a growing business, not finance "
                   "slower collections or idle stock. If the cycle returned to last year's level, most of the "
                   "funding gap would disappear; if it does not, the limit may be absorbed by doubtful receivables."),
        supporting_metrics=[
            _m("working_capital_cycle", "Working capital cycle", wcc0, "days", c.prior, f"ratio_engine:{c.prior}.working_capital_cycle"),
            _m("working_capital_cycle", "Working capital cycle", wcc1, "days", c.latest, f"ratio_engine:{c.latest}.working_capital_cycle"),
            _m("working_capital_cycle_change", "Cycle lengthened by", round(wcc1 - wcc0, 2), "days", c.latest,
               "challenge_agent: latest cycle − prior cycle"),
            _m("trade_nwc_cr", "Trade working capital (receivables + inventory − payables)", nwc[c.prior], "cr", c.prior, "financial_summary"),
            _m("trade_nwc_cr", "Trade working capital (receivables + inventory − payables)", nwc[c.latest], "cr", c.latest, "financial_summary"),
            _m("trade_nwc_at_prior_cycle_cr", f"Trade working capital at the {c.prior} cycle", at_old_cycle, "cr", c.latest,
               f"challenge_agent: revenue {c.latest} × cycle {c.prior} / 365"),
            _m("nwc_increase_from_cycle_cr", "Increase explained by the slower cycle", from_cycle, "cr", c.latest, "challenge_agent"),
            _m("requested_limit_cr", "Requested limit / enhancement", limit, "cr", None, "facility_details"),
        ],
        required_response=["Provide debtor and inventory ageing and explain why the cycle lengthened.",
                           f"Assess the limit on a normalised cycle (e.g. the {c.prior} level) and justify any amount above it.",
                           "Show how much of the limit will fund new orders versus existing receivables and stock."],
        proposal_reference=c.proposal_text(), linked=(obs, tasks), severity=severity,
        reasoning=[f"Working capital cycle {wcc0} → {wcc1} days (≥ {cfg.get('min_cycle_increase_days', 15)}-day trigger).",
                   f"{share}% of the trade WC increase is cycle-driven (≥ {cfg.get('min_cycle_share_pct', 50)}% trigger).",
                   f"Severity {severity}: cycle-driven increase {'≥' if severity == 'HIGH' else '<'} the requested amount."],
    )


def _repayment_capacity(c: _Case) -> Optional[dict]:
    cfg = c.cfg("repayment_capacity")
    dscr, icr = c.ratio(c.latest, "dscr"), c.ratio(c.latest, "interest_coverage_ratio")
    min_dscr, min_icr = _num(c.policy.get("min_dscr")), _num(c.policy.get("min_interest_coverage"))
    cf = ((c.fp.get("cash_flow_repayment") or {}).get("periods") or {}).get(c.latest) or {}
    ocf, ebitda, fcf, capex = (_num(cf.get("operating_cash_flow_cr")), _num(cf.get("ebitda_cr")),
                               _num(cf.get("free_cash_flow_cr")), _num(cf.get("capex_cr")))
    conversion = round(ocf / ebitda * 100, 1) if (ocf is not None and ebitda) else None
    breach = (dscr is not None and min_dscr is not None and dscr < min_dscr) or \
             (icr is not None and min_icr is not None and icr < min_icr)
    weak_cash = fcf is not None and fcf < 0 and conversion is not None and conversion < cfg.get("min_ocf_to_ebitda_pct", 50)
    if not breach and not weak_cash:
        return None
    severity = "CRITICAL" if (dscr is not None and dscr < 1.0) else "HIGH" if breach else "MEDIUM"
    obs, tasks = c.links(("DEBT_SERVICING_PRESSURE", "EARNINGS_CASH_CONVERSION"), ("DEBT_SERVICING", "EARNINGS_TO_CASH"))
    return dict(
        rule_id="REPAYMENT_CAPACITY", category="Repayment capacity", title="Cash flow does not yet support the proposal",
        challenge=(f"DSCR is {dscr}x against a policy minimum of {min_dscr}x and interest cover is {icr}x. In {c.latest} "
                   f"operating cash flow was {_cr(ocf)} against EBITDA of {_cr(ebitda)}, and after capex of {_cr(capex)} "
                   f"free cash flow was {_cr(fcf)}. Servicing an additional limit from internal accruals is not "
                   f"demonstrated by the latest year."),
        rationale=("Debt is repaid from cash, not from accounting profit. With coverage at or below the policy floor and "
                   "negative free cash flow, the proposal depends on collections improving or on further borrowing."
                   + c.task_note("DEBT_SERVICING")),
        supporting_metrics=[
            _m("dscr", "DSCR", dscr, "x", c.latest, f"ratio_engine:{c.latest}.dscr"),
            _m("min_dscr", "Policy minimum DSCR", min_dscr, "x", None, "policy_thresholds.min_dscr"),
            _m("interest_coverage_ratio", "Interest coverage", icr, "x", c.latest, f"ratio_engine:{c.latest}.interest_coverage_ratio"),
            _m("operating_cash_flow_cr", "Operating cash flow", ocf, "cr", c.latest, "cash_flow_repayment"),
            _m("ebitda_cr", "EBITDA", ebitda, "cr", c.latest, "cash_flow_repayment"),
            _m("capex_cr", "Capex", capex, "cr", c.latest, "cash_flow_repayment"),
            _m("free_cash_flow_cr", "Free cash flow", fcf, "cr", c.latest, "cash_flow_repayment"),
        ],
        required_response=["Provide month-wise repayment and interest obligations for existing and proposed facilities.",
                           "Provide a cash-flow projection showing coverage back above the policy minimum, with assumptions.",
                           "Explain how the negative free cash flow was funded and whether it recurs."],
        proposal_reference=c.proposal_text(), linked=(obs, tasks), severity=severity,
        reasoning=[f"Coverage breach: {breach}; negative free cash flow with OCF/EBITDA {conversion}%: {weak_cash}.",
                   f"Severity {severity}."],
    )


def _working_capital(c: _Case) -> Optional[dict]:
    """Drawing power that relies on receivables the analysis puts in doubt."""
    dp = c.fp.get("drawing_power") or {}
    comps = {x.get("name", ""): x for x in dp.get("components") or []}
    rec = next((v for k, v in comps.items() if "Receivable" in k), None)
    inv = next((v for k, v in comps.items() if "Inventory" in k), None)
    pay = next((v for k, v in comps.items() if "Creditor" in k), None)
    total, limit = _num(dp.get("total_dp_cr")), c.limit
    days, max_days = c.ratio(c.latest, "debtor_days"), _num(c.policy.get("max_debtor_days"))
    if not (rec and total and limit) or days is None or max_days is None or days <= max_days:
        return None
    rec_value, rec_margin = _num(rec.get("value_cr")), _num(rec.get("margin_pct"))
    other_dp = (_num((inv or {}).get("dp_cr")) or 0) + (_num((pay or {}).get("dp_cr")) or 0)
    break_even = round((limit - other_dp) / (1 - rec_margin / 100), 2) if rec_margin is not None else None
    share = round(break_even / rec_value * 100, 1) if (break_even and rec_value) else None
    open_task = (c.tasks.get("RECEIVABLE_DETERIORATION") or {}).get("status") in _OPEN_TASK
    severity = "HIGH" if open_task else "MEDIUM"
    obs, tasks = c.links(("RECEIVABLE_COLLECTION", "WC_DETERIORATION"), ("RECEIVABLE_DETERIORATION",))
    return dict(
        rule_id="WORKING_CAPITAL_DP", category="Working-capital requirement", title="Drawing power leans on aged receivables",
        challenge=(f"Drawing power of {_cr(total)} counts all trade receivables of {_cr(rec_value)} as eligible, although "
                   f"debtor days are {days} against a policy maximum of {max_days:.0f}. The requested {_cr(limit)} stays "
                   f"within drawing power only while eligible receivables are at least {_cr(break_even)} "
                   f"({share}% of the book)."),
        rationale=("Receivables older than 90 days are normally excluded from drawing power. Until the ageing is known, "
                   "the bank cannot confirm the limit is backed by collectible current assets."
                   + c.task_note("RECEIVABLE_DETERIORATION")),
        supporting_metrics=[
            _m("total_dp_cr", "Drawing power", total, "cr", c.latest, "drawing_power.total_dp_cr"),
            _m("receivables_in_dp_cr", "Receivables counted in drawing power", rec_value, "cr", c.latest, "drawing_power.components"),
            _m("debtor_days", "Debtor days", days, "days", c.latest, f"ratio_engine:{c.latest}.debtor_days"),
            _m("max_debtor_days", "Policy maximum debtor days", max_days, "days", None, "policy_thresholds.max_debtor_days"),
            _m("requested_limit_cr", "Requested limit / enhancement", limit, "cr", None, "facility_details"),
            _m("eligible_receivables_break_even_cr", "Eligible receivables needed for drawing power to cover the limit",
               break_even, "cr", c.latest, "challenge_agent: (limit − inventory DP − creditors DP) / (1 − receivable margin)"),
        ],
        required_response=["Provide customer-wise receivable ageing at the latest balance-sheet date.",
                           "Recompute drawing power excluding receivables over 90 days, disputed and retention amounts.",
                           "Confirm the latest stock and book-debt statement submitted to existing lenders."],
        proposal_reference=c.proposal_text(), linked=(obs, tasks), severity=severity,
        reasoning=[f"Debtor days {days} > policy {max_days:.0f}, yet drawing power uses all receivables.",
                   f"Severity {severity}: receivable investigation {'open' if open_task else 'not open'}."],
    )


def _leverage(c: _Case) -> Optional[dict]:
    cfg = c.cfg("leverage")
    de0, de1 = c.ratio(c.prior, "debt_to_ebitda"), c.ratio(c.latest, "debt_to_ebitda")
    max_de = _num(c.policy.get("max_debt_to_ebitda"))
    debt, ebitda = c.line(c.latest, "total_debt_cr"), c.line(c.latest, "ebitda_cr")
    if de1 is None or max_de is None:
        return None
    rising = de0 is not None and de1 - de0 >= cfg.get("min_debt_to_ebitda_increase", 0.5)
    above = de1 > max_de
    if not (rising or above):
        return None
    # Post-facility debt: the projection engine's debt basis when available (existing debt + proposed limit).
    proj = (c.fp.get("financial_projections") or {}).get("assumptions") or {}
    pro_forma_debt = _num(proj.get("debt_basis_cr"))
    pro_forma = round(pro_forma_debt / ebitda, 2) if (pro_forma_debt and ebitda) else None
    cf = ((c.fp.get("cash_flow_repayment") or {}).get("periods") or {}).get(c.latest) or {}
    capex, ocf = _num(cf.get("capex_cr")), _num(cf.get("operating_cash_flow_cr"))
    severity = "HIGH" if above or (pro_forma is not None and pro_forma > max_de) else "MEDIUM"
    obs, tasks = c.links(("LEVERAGE_INCREASE",), ("LEVERAGE",))
    text = f"Debt/EBITDA rose from {de0}x to {de1}x against a policy maximum of {max_de}x."
    if pro_forma is not None:
        text += f" With the proposed limit drawn, debt of {_cr(pro_forma_debt)} would be {pro_forma}x EBITDA."
    if capex and ocf is not None and capex > ocf:
        text += f" {c.latest} capex of {_cr(capex)} exceeded operating cash flow of {_cr(ocf)}, so it was largely debt-funded."
    return dict(
        rule_id="LEVERAGE", category="Leverage", title="Leverage already above policy before this facility",
        challenge=text,
        rationale=("Adding exposure to a borrower whose leverage is already outside policy increases the bank's loss "
                   "given default and leaves little headroom if earnings fall. The proposal should show how leverage "
                   "comes back within policy." + c.task_note("LEVERAGE")),
        supporting_metrics=[
            _m("debt_to_ebitda", "Debt / EBITDA", de0, "x", c.prior, f"ratio_engine:{c.prior}.debt_to_ebitda"),
            _m("debt_to_ebitda", "Debt / EBITDA", de1, "x", c.latest, f"ratio_engine:{c.latest}.debt_to_ebitda"),
            _m("max_debt_to_ebitda", "Policy maximum Debt / EBITDA", max_de, "x", None, "policy_thresholds.max_debt_to_ebitda"),
            _m("total_debt_cr", "Total debt", debt, "cr", c.latest, "financial_summary"),
            _m("pro_forma_debt_cr", "Debt with proposed limit", pro_forma_debt, "cr", None, "financial_projections.assumptions.debt_basis_cr"),
            _m("pro_forma_debt_to_ebitda", "Debt / EBITDA with proposed limit", pro_forma, "x", None,
               "challenge_agent: debt with proposed limit / latest EBITDA"),
            _m("capex_cr", "Capex", capex, "cr", c.latest, "cash_flow_repayment"),
        ],
        required_response=["Provide the lender-wise debt schedule and the end-use of borrowings raised in the latest year.",
                           "Set out a deleveraging plan (equity infusion, debt reduction) with a Debt/EBITDA covenant.",
                           "Confirm no further borrowing is planned during the facility tenor without the bank's consent."],
        proposal_reference=c.proposal_text(), linked=(obs, tasks), severity=severity,
        reasoning=[f"Debt/EBITDA {de0} → {de1} (rising: {rising}; above policy {max_de}: {above}).",
                   f"Pro-forma Debt/EBITDA {pro_forma}; severity {severity}."],
    )


def _financial_performance(c: _Case) -> Optional[dict]:
    cfg = c.cfg("financial_performance")
    rev0, rev1 = c.line(c.prior, "revenue_cr"), c.line(c.latest, "revenue_cr")
    m0, m1 = c.line(c.prior, "ebitda_margin_pct"), c.line(c.latest, "ebitda_margin_pct")
    o0, o1 = c.line(c.prior, "operating_cash_flow_cr"), c.line(c.latest, "operating_cash_flow_cr")
    if None in (rev0, rev1, m0, m1) or not rev0:
        return None
    rev_g = round((rev1 - rev0) / rev0 * 100, 1)
    decline_bps = round((m0 - m1) * 100)
    ocf_g = round((o1 - o0) / o0 * 100, 1) if (o0 and o1 is not None and o0 > 0) else None
    margin_hit = decline_bps >= cfg.get("min_margin_decline_bps", 200)
    cash_hit = ocf_g is not None and ocf_g <= -cfg.get("min_ocf_decline_pct", 20)
    if rev_g <= 0 or not (margin_hit or cash_hit):
        return None
    proj = (c.fp.get("financial_projections") or {}).get("assumptions") or {}
    proj_margin = _num(proj.get("avg_ebitda_margin_pct"))
    optimistic = proj_margin is not None and proj_margin - m1 >= cfg.get("min_projection_margin_gap_pp", 1.0)
    weak_peers = [r.get("metric") for r in (c.fp.get("benchmark_summary") or {}).get("benchmarks") or []
                  if r.get("status") == "worse_than_peer"]
    floor = _num(c.policy.get("min_ebitda_margin_pct"))
    severity = "HIGH" if (floor is not None and m1 < floor) else "MEDIUM"
    text = f"Revenue grew {rev_g}% in {c.latest}, but EBITDA margin fell from {m0}% to {m1}% ({decline_bps} bps)"
    text += f" and operating cash flow fell {abs(ocf_g)}%." if cash_hit else "."
    if optimistic:
        text += f" The projections assume an average EBITDA margin of {proj_margin}%, above the latest {m1}%."
    obs, tasks = c.links(("MARGIN_COMPRESSION", "EARNINGS_CASH_CONVERSION", "SECTOR_UNDERPERFORMANCE"), ("EARNINGS_TO_CASH",))
    return dict(
        rule_id="FINANCIAL_PERFORMANCE", category="Financial performance", title="Growth is not translating into profit or cash",
        challenge=text,
        rationale=("Growth bought with thinner margins and slower cash conversion weakens, rather than strengthens, "
                   "repayment capacity. Any projection that assumes a margin recovery needs evidence from the order book."
                   + (f" The borrower is also weaker than sector peers on {len(weak_peers)} benchmark metric(s)." if weak_peers else "")),
        supporting_metrics=[
            _m("revenue_growth_pct", "Revenue growth", rev_g, "pct", c.latest, "financial_summary"),
            _m("ebitda_margin_pct", "EBITDA margin", m0, "pct", c.prior, "financial_summary"),
            _m("ebitda_margin_pct", "EBITDA margin", m1, "pct", c.latest, "financial_summary"),
            _m("ocf_growth_pct", "Operating cash flow change", ocf_g, "pct", c.latest, "financial_summary"),
            _m("projected_avg_ebitda_margin_pct", "Projected average EBITDA margin", proj_margin, "pct", None,
               "financial_projections.assumptions.avg_ebitda_margin_pct"),
            _m("metrics_worse_than_peers", "Benchmark metrics worse than peers", len(weak_peers), "count", c.latest, "benchmark_summary"),
        ],
        required_response=["Explain the cost drivers behind the margin decline (input costs, fixed-price contracts, bidding).",
                           "Provide the order book with contract-wise margins and price-escalation terms.",
                           "Justify the margin assumed in the projections, or re-base them on the latest year."],
        proposal_reference=c.proposal_text(), linked=(obs, tasks), severity=severity,
        reasoning=[f"Revenue +{rev_g}%; margin −{decline_bps} bps ({margin_hit}); OCF {ocf_g}% ({cash_hit}).",
                   f"Projection margin above latest: {optimistic}; severity {severity}."],
    )


def _policy_exceptions(c: _Case) -> Optional[dict]:
    cfg = c.cfg("policy_exceptions")
    failed = [d for d in (c.fp.get("policy_decisions") or {}).get("tier1_hard_rules") or []
              if str(d.get("result", "")).lower() == "fail"]
    breaches = c.observed("POLICY_DEVIATION", "breaches") or []
    if not failed and not breaches:
        return None
    severity = ("CRITICAL" if failed else
                "HIGH" if len(breaches) >= cfg.get("high_severity_min_breaches", 3) else "MEDIUM")
    names = [f"{b.get('label')} {b.get('value')} vs {b.get('limit_type')} {b.get('limit')}" for b in breaches]
    text = ""
    if failed:
        text += f"{len(failed)} hard rule(s) failed ({', '.join(d.get('rule') for d in failed)}); these cannot be deviated. "
    if breaches:
        text += f"The proposal breaches {len(breaches)} policy threshold(s): {'; '.join(names)}."
    obs, tasks = c.links(("POLICY_DEVIATION",), ("POLICY_EXCEPTION",))
    return dict(
        rule_id="POLICY_EXCEPTIONS", category="Policy exceptions", title="Proposal sits outside credit policy",
        challenge=text.strip(),
        rationale=("Each breach must be justified and mitigated, and approved by an authority empowered to sanction "
                   "deviations. Several simultaneous breaches suggest the proposal, not just one ratio, is outside "
                   "appetite." + c.task_note("POLICY_EXCEPTION")),
        supporting_metrics=[_m(b.get("metric"), b.get("label"), b.get("value"), "value", c.latest,
                               f"policy_thresholds.{b.get('threshold_key')} = {b.get('limit')}") for b in breaches]
                           + [_m(d.get("rule"), d.get("description"), "fail", "text", None, "policy_engine.tier1") for d in failed],
        required_response=["Record a deviation note for each breach with business justification.",
                           "Propose a mitigant per breach (security, covenant, DSRA, equity infusion, pricing).",
                           "Confirm the sanctioning authority empowered to approve these deviations."],
        proposal_reference=c.proposal_text(), linked=(obs, tasks), severity=severity,
        reasoning=[f"{len(failed)} failed hard rule(s), {len(breaches)} threshold breach(es); severity {severity}."],
    )


def _unresolved_investigations(c: _Case) -> Optional[dict]:
    cfg = c.cfg("unresolved_investigations")
    wanted = set(cfg.get("priorities") or ["P1"])
    open_tasks = [t for t in c.tasks.values() if t.get("priority") in wanted and t.get("status") in _OPEN_TASK]
    if not open_tasks:
        return None
    open_tasks.sort(key=lambda t: t["investigation_id"])
    return dict(
        rule_id="UNRESOLVED_INVESTIGATIONS", category="Unresolved investigations",
        title="Key questions are still open",
        challenge=(f"{len(open_tasks)} investigation(s) that must be closed before credit committee are still open: "
                   + "; ".join(t["title"] for t in open_tasks) + ". The proposal rests on figures and assumptions these "
                   "investigations are meant to verify."),
        rationale=("Presenting the proposal before these are answered means the committee would be relying on unverified "
                   "receivables, revenue or policy positions."),
        supporting_metrics=[_m("investigation", t["title"], t["status"], "text", None, t["investigation_id"])
                            for t in open_tasks],
        required_response=[f"Close or formally waive: {t['title']} ({len(t.get('required_evidence') or [])} evidence item(s))."
                           for t in open_tasks],
        proposal_reference=c.proposal_text(),
        linked=([t["observation_id"] for t in open_tasks], [t["investigation_id"] for t in open_tasks]),
        severity="HIGH",
        reasoning=[f"{len(open_tasks)} open investigation(s) with priority in {sorted(wanted)}."],
    )


RULES: list[tuple[str, Callable[[_Case], Optional[dict]]]] = [
    ("facility_amount", _facility_amount),
    ("repayment_capacity", _repayment_capacity),
    ("working_capital", _working_capital),
    ("leverage", _leverage),
    ("financial_performance", _financial_performance),
    ("policy_exceptions", _policy_exceptions),
    ("unresolved_investigations", _unresolved_investigations),
]


class CreditChallengeAgent:
    name = "credit_challenge"

    def challenge(self, fact_pack: dict, observations: list[dict], investigations: list[dict], case_id: str,
                  created_at: str | None = None, settings: dict | None = None) -> list[dict]:
        """Challenges to the proposal, most severe first. Deterministic for the same inputs."""
        if not fact_pack:
            return []
        settings = challenge_config() if settings is None else settings
        case = _Case(fact_pack, observations, investigations, settings)
        created_at = created_at or datetime.now().isoformat(timespec="seconds")
        found = []
        for index, (area, rule) in enumerate(RULES):
            if not (settings.get(area) or {}).get("enabled", True):
                continue
            try:
                raw = rule(case)
            except Exception as e:   # defensive: incomplete fact packs from older runs
                log.warning("Challenge rule %s failed for %s: %s", area, case_id, e)
                continue
            if not raw:
                continue
            obs_ids, task_ids = raw.pop("linked")
            reasoning = raw.pop("reasoning")
            found.append((index, CreditChallenge(
                challenge_id=f"CHL-{case_id}-{raw['rule_id']}",
                case_id=case_id,
                status=ChallengeStatus.OPEN.value,
                linked_observation_ids=obs_ids,
                linked_investigation_ids=task_ids,
                agent_reasoning=reasoning,
                created_at=created_at,
                generated_by=AGENT_VERSION,
                **raw,
            )))
        found.sort(key=lambda item: (SEVERITY_ORDER.get(item[1].severity, 9), item[0]))
        return [ch.to_dict() for _, ch in found]


def sync_challenges(planned: list[dict], existing: list[dict] | None) -> list[dict]:
    """Merge fresh challenges with stored ones, keeping the analyst's status and response.

    A challenge whose trigger has gone (e.g. its investigations were resolved) is
    dropped while still OPEN, and kept once the analyst has dealt with it.
    """
    stored = {ch["challenge_id"]: ch for ch in existing or []}
    merged = []
    for ch in planned:
        old = stored.pop(ch["challenge_id"], None)
        if old:
            ch = {**ch, "status": old.get("status", ch["status"]), "review": old.get("review") or {},
                  "ai_wording": old.get("ai_wording") if old.get("challenge") == ch["challenge"] else None,
                  "created_at": old.get("created_at", ch["created_at"])}
        merged.append(ch)
    merged += [ch for ch in stored.values() if ch.get("status") != ChallengeStatus.OPEN.value]
    return merged
