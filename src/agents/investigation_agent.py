"""
Investigation Agent — decides what must be checked next for a case.

Consumes the credit observations (src/engines/observation_engine.py) and, with
deterministic routing, opens investigation tasks: which investigation applies,
why, which evidence is needed, how urgent it is, and which observation it
answers. Figures quoted in reasons and evidence come from the observation's own
trigger values; nothing is recomputed. It is not a pipeline agent: it runs
after the pipeline (and again whenever observations change), so the 7-agent
CAM pipeline is unchanged.

Which observations need an investigation:
  * status INVESTIGATION_REQUIRED — always (the analyst asked for it);
  * status NEW and severity CRITICAL / HIGH / MEDIUM;
  * EXPLAINED, ACCEPTED, DISMISSED or LOW / INFO — no task.

Priority (P1 before committee, P2 before sanction, P3 pre-disbursement condition):
  base from the most severe linked observation (CRITICAL → P1, HIGH → P2,
  MEDIUM / LOW → P3), raised one level when the task blocks the decision itself
  (data reliability, policy deviation) or when two or more observations point
  to the same issue.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from src.models.investigations import Investigation, InvestigationPriority as P, InvestigationStatus
from src.models.observations import SEVERITY_ORDER

AGENT_VERSION = "investigation_agent/inv_v1"

_ACTIVE_STATUSES = {"NEW", "INVESTIGATION_REQUIRED"}
_AUTO_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM"}
_BASE_PRIORITY = {"CRITICAL": P.P1, "HIGH": P.P2, "MEDIUM": P.P3, "LOW": P.P3, "INFO": P.P3}
_DUE = {P.P1.value: "before the case goes to credit committee", P.P2.value: "before sanction",
        P.P3.value: "as a pre-disbursement condition"}


# ─── Reading an observation ──────────────────────────────────────────────────

def _observed(obs: dict, key: str):
    return ((obs or {}).get("trigger") or {}).get("observed", {}).get(key)


def _metric(obs: dict, metric: str, period: Optional[str] = None):
    """Value of a metric from the observation (latest period unless one is given)."""
    rows = [m for m in (obs or {}).get("metrics") or [] if m.get("metric") == metric]
    if period:
        rows = [m for m in rows if m.get("period") == period]
    return rows[-1].get("value") if rows else None


def _period(obs: dict) -> str:
    pc = (obs or {}).get("period_comparison") or {}
    if pc.get("to_period"):
        return pc["to_period"]
    return next((m.get("period") for m in (obs or {}).get("metrics") or [] if m.get("period")), "the latest year")


def _cr(v) -> str:
    return f"₹{v:,.2f} Cr" if isinstance(v, (int, float)) else "the reported amount"


def _signed(v) -> str:
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "n/a"


def _ev(item: str, description: str, purpose: str, source: str) -> dict:
    return {"item": item, "description": description, "purpose": purpose, "source": source}


# ─── Investigation types ─────────────────────────────────────────────────────
# Each builder receives (primary observation, {rule_id: observation}) for the
# observations routed to it and returns (title, reason, required_evidence).

def _receivables(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    wc, coll = linked.get("WC_DETERIORATION"), linked.get("RECEIVABLE_COLLECTION")
    period = _period(primary)
    facts = []
    if wc:
        facts.append(f"receivables grew {_observed(wc, 'receivables_growth_pct')}% against revenue growth of "
                     f"{_observed(wc, 'revenue_growth_pct')}%")
    if coll:
        facts.append(f"debtor days reached {_observed(coll, 'debtor_days')}")
    receivables = _metric(wc, "trade_receivables_cr", period) if wc else None
    reason = (f"In {period} " + " and ".join(facts) + ". The bank needs to establish whether the build-up is "
              "collectible (timing of milestone billing) or reflects slow-paying, disputed or doubtful debtors, "
              "because receivables drive both repayment cash flow and drawing power.")
    evidence = [
        _ev("Debtor ageing schedule",
            f"Customer-wise ageing as at the {period} balance-sheet date in 0-30 / 31-90 / 91-180 / >180-day buckets, "
            f"reconciled to trade receivables of {_cr(receivables)}.",
            "Shows how much of the increase is overdue and how much is current.", "Borrower (CFO)"),
        _ev("Top-10 customer exposure",
            "Top 10 debtors with balance, share of total receivables, contractual credit period, actual days "
            "outstanding, and whether government / municipal.",
            "Tests concentration and the credit quality of the main counterparties.", "Borrower"),
        _ev("Collection history",
            "Month-wise billing vs collections for the last 12 months, tied to credits in the main operating "
            "accounts' bank statements.",
            "Confirms whether collections have actually slowed.", "Borrower / bank statements"),
    ]
    if coll and _observed(coll, "debtor_days") and (coll.get("trigger") or {}).get("thresholds", {}).get(
            "policy_max_debtor_days"):
        evidence.append(_ev("Disputed, retention and arbitration amounts",
                            "Receivables under dispute, retention money withheld and claims under arbitration, "
                            "with expected realisation dates.",
                            "These should be excluded from drawing power.", "Borrower"))
    return "Receivable deterioration — debtor quality and collections", reason, evidence


def _inventory(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    period = _period(primary)
    days, inc = _observed(primary, "inventory_days"), _observed(primary, "increase_days")
    stock = _metric(primary, "inventory_cr", period)
    reason = (f"Inventory days rose by {inc} days to {days} in {period}. The bank needs to know whether the stock "
              "is usable for current orders or slow-moving / obsolete, since it is part of the security and the "
              "drawing-power base.")
    return "Inventory build-up — ageing, movement and utilisation", reason, [
        _ev("Inventory ageing",
            f"Item-wise / site-wise ageing of inventory of {_cr(stock)} (0-90 / 91-180 / >180 days), with "
            "slow-moving and non-moving items flagged.",
            "Identifies stock that may need write-down.", "Borrower"),
        _ev("Stock movement statement",
            "Opening stock, purchases, consumption and closing stock by quarter for the last 4 quarters.",
            "Shows whether purchases have run ahead of consumption.", "Borrower"),
        _ev("Inventory utilisation",
            "Inventory linked to specific orders / project sites, with expected consumption dates; latest stock "
            "audit or site-visit report.",
            "Confirms the stock is tied to live, funded work.", "Borrower / stock auditor"),
    ]


def _earnings_cash(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    period = _period(primary)
    reason = (f"In {period} EBITDA moved {_signed(_observed(primary, 'ebitda_growth_pct'))} while operating cash flow "
              f"moved {_signed(_observed(primary, 'ocf_growth_pct'))}, so only {_observed(primary, 'ocf_to_ebitda_pct')}% of EBITDA "
              "became operating cash. Debt is serviced from cash, so the bank must see where the cash went and "
              "whether the gap reverses.")
    return "Earnings-to-cash gap — cash flow and working-capital movement", reason, [
        _ev("Cash-flow statement with notes",
            f"Audited {period} cash-flow statement with the reconciliation from EBITDA to cash from operations.",
            "Locates the lines absorbing cash.", "Borrower / auditor"),
        _ev("Working-capital movement",
            "Year-on-year change in receivables, unbilled revenue / contract assets, inventory, advances and "
            "payables, with reasons for each material movement.",
            "Separates timing effects from structural deterioration.", "Borrower (CFO)"),
        _ev("Bank collections",
            "12 months of statements for all operating accounts; total credits compared with revenue booked.",
            "Independent check that reported sales are turning into cash.", "Borrower / other lenders"),
    ]


def _leverage(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    period = _period(primary)
    debt = _metric(primary, "total_debt_cr", period)
    reason = (f"Debt grew {_observed(primary, 'debt_growth_pct')}% against EBITDA growth of "
              f"{_observed(primary, 'ebitda_growth_pct')}%, taking Debt/EBITDA to {_observed(primary, 'debt_to_ebitda')}x. "
              "The bank needs the full borrowing picture — who lent, for what, on what security and when it falls "
              "due — before adding exposure.")
    return "Increasing leverage — debt schedule and new borrowings", reason, [
        _ev("Lender-wise debt schedule",
            f"Each facility: lender, type, sanctioned limit, outstanding, rate, security and maturity, reconciled to "
            f"total debt of {_cr(debt)}.",
            "Confirms total indebtedness and existing charges on assets.", "Borrower"),
        _ev(f"New borrowings in {period}",
            "Sanction letters for facilities raised during the year, with purpose and end-use certificate.",
            "Shows what the incremental debt funded (capex, working capital or losses).", "Borrower / CA certificate"),
        _ev("Repayment schedule",
            "Principal repayments by quarter for the next 5 years across all term facilities.",
            "Feeds the repayment-capacity assessment.", "Borrower"),
    ]


def _debt_service(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    thresholds = (primary.get("trigger") or {}).get("thresholds") or {}
    reason = (f"DSCR is {_observed(primary, 'dscr')}x against a policy minimum of {thresholds.get('min_dscr')}x and "
              f"interest cover is {_observed(primary, 'interest_coverage_ratio')}x. The engine's DSCR assumes a "
              "standard principal repayment; the bank needs the actual obligations and projected cash flow to "
              "confirm the proposed facility can be serviced.")
    return "Debt servicing pressure — obligations and projected cash flow", reason, [
        _ev("Repayment schedule",
            "Month-wise principal due over the next 24 months for existing and proposed facilities.",
            "Replaces the assumed principal in DSCR with actual obligations.", "Borrower / lenders"),
        _ev("Interest obligations",
            "Rate, reset frequency and annual interest for each facility, including the proposed limit.",
            "Tests sensitivity to rate changes.", "Borrower"),
        _ev("Projected cash flow",
            "Quarterly cash-flow projection for the facility tenor with assumptions, and DSCR computed on actual "
            "repayments.",
            "Shows whether coverage recovers above the policy minimum.", "Borrower; reviewed by credit team"),
    ]


# Which correct source to request for each conflicting-data exception.
_SOURCE_REQUESTS = {
    "XSRC_GST_REVENUE_MISMATCH": ("GST returns and turnover reconciliation",
                                  "GSTR-1 and GSTR-3B for the year, with a reconciliation of GST turnover to audited "
                                  "revenue (unbilled revenue, exempt supplies, timing).", "Borrower / GSTN"),
    "XSRC_DEBT_BUREAU_MISMATCH": ("Lender balance confirmations",
                                  "Balance confirmations from each lender as at the balance-sheet date.",
                                  "Lenders / borrower"),
    "XSRC_REVENUE_MISMATCH": ("Exchange filings and management reconciliation",
                              "Filed quarterly results and a reconciliation to the provisional figures submitted.",
                              "Stock exchange / borrower"),
    "DOC_REVENUE_CROSS_SOURCE": ("Signed financial statements",
                                 "Signed audited financials for the period so extracted figures can be re-checked.",
                                 "Borrower / auditor"),
}
_STRUCTURAL = ("Signed audited financial statements",
               "Complete signed statements with schedules for the period, to correct the figures captured.",
               "Borrower / auditor")


def _data_reliability(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    conflicts = _observed(primary, "exceptions") or []
    evidence = []
    for c in conflicts:
        code = c.get("code") or ""
        item, description, source = _SOURCE_REQUESTS.get(code, _STRUCTURAL)
        evidence.append(_ev(f"{item} ({code})",
                            f"{description} Conflict: {c.get('observed')} vs {c.get('expected')}.",
                            "Establishes which figure is correct before it is relied on.", source))
    reason = (f"{len(conflicts)} figure(s) disagree across sources ("
              + ", ".join(c.get("code") or "" for c in conflicts) + "). Until the correct source is confirmed, the "
              "ratios and recommendation built on these figures cannot be relied upon.")
    return "Data reliability — confirm the correct source", reason, evidence


# Usual mitigants credit teams accept for each policy threshold.
_MITIGANTS = {
    "min_dscr": "DSRA of 1-2 quarters' debt service, cash sweep, or repayment re-profiling",
    "min_interest_coverage": "interest-servicing reserve or promoter support undertaking",
    "min_current_ratio": "higher margin on working capital, or longer-tenor funding for long-term uses",
    "max_debt_to_equity": "promoter equity infusion or a deleveraging covenant",
    "max_debt_to_ebitda": "promoter equity / sub-debt infusion, debt-reduction plan with a Debt/EBITDA covenant",
    "max_tol_tnw": "equity infusion or restriction on further borrowing",
    "min_roe_pct": "profitability improvement plan (usually noted rather than mitigated)",
    "max_debtor_days": "exclude receivables > 90 days from drawing power; receivable ageing covenant",
    "min_ebitda_margin_pct": "price-escalation clauses on new orders; margin covenant",
}


def _policy(primary: dict, linked: dict) -> tuple[str, str, list[dict]]:
    breaches = _observed(primary, "breaches") or []
    failed = _observed(primary, "failed_hard_rules") or []
    evidence = [_ev(f"Hard rule {rule} — resolution",
                    "A failed hard rule cannot be approved by deviation; evidence that the underlying condition "
                    "is resolved.", "Required before the case can proceed.", "Credit team / borrower")
                for rule in failed]
    evidence += [_ev(f"Deviation note — {b.get('label')}",
                     f"{b.get('label')} is {b.get('value')} against a policy {b.get('limit_type')} of {b.get('limit')} "
                     f"({b.get('threshold_key')}). Business justification and proposed mitigant: "
                     f"{_MITIGANTS.get(b.get('threshold_key'), 'to be proposed by the RM')}.",
                     "Needed for the sanctioning authority to approve the deviation.", "RM / credit team")
                 for b in breaches]
    names = [b.get("label") for b in breaches] + list(failed)
    reason = (f"The proposal is outside credit policy on {len(names)} item(s): {', '.join(names)}. Each needs a "
              "recorded justification and mitigant, approved at the authority empowered for deviations.")
    return "Policy exception — justification and mitigants", reason, evidence


# (investigation type, observation rule_ids routed to it, builder, raise priority because it blocks the decision)
ROUTES: list[tuple[str, tuple[str, ...], Callable, bool]] = [
    ("RECEIVABLE_DETERIORATION", ("WC_DETERIORATION", "RECEIVABLE_COLLECTION"), _receivables, False),
    ("INVENTORY_BUILDUP", ("INVENTORY_BUILDUP",), _inventory, False),
    ("EARNINGS_TO_CASH", ("EARNINGS_CASH_CONVERSION",), _earnings_cash, False),
    ("LEVERAGE", ("LEVERAGE_INCREASE",), _leverage, False),
    ("DEBT_SERVICING", ("DEBT_SERVICING_PRESSURE",), _debt_service, False),
    ("DATA_RELIABILITY", ("DATA_RELIABILITY",), _data_reliability, True),
    ("POLICY_EXCEPTION", ("POLICY_DEVIATION",), _policy, True),
]


def _raise(priority: P) -> P:
    return {P.P3: P.P2, P.P2: P.P1, P.P1: P.P1}[priority]


def _needs_investigation(obs: dict) -> bool:
    if obs.get("status") == "INVESTIGATION_REQUIRED":
        return True
    return obs.get("status") in _ACTIVE_STATUSES and obs.get("severity") in _AUTO_SEVERITIES


class InvestigationAgent:
    """Deterministic routing from observations to investigation tasks."""

    name = "investigation"

    def plan(self, observations: list[dict], case_id: str, created_at: str | None = None) -> list[dict]:
        created_at = created_at or datetime.now().isoformat(timespec="seconds")
        by_rule = {o["trigger"]["rule_id"]: o for o in observations or [] if o.get("trigger")}
        tasks = []
        for inv_type, rules, builder, blocks_decision in ROUTES:
            linked = {r: by_rule[r] for r in rules if r in by_rule and _needs_investigation(by_rule[r])}
            if not linked:
                continue
            ordered = sorted(linked.values(), key=lambda o: (SEVERITY_ORDER[o["severity"]],
                                                            rules.index(o["trigger"]["rule_id"])))
            primary = ordered[0]
            title, reason, evidence = builder(primary, linked)

            steps = [f"{o['observation_id']} ({o['severity']}, status {o['status']}) needs investigation "
                     f"and routes to {inv_type}." for o in ordered]
            priority = _BASE_PRIORITY[primary["severity"]]
            steps.append(f"Base priority {priority.value} from the most severe linked observation ({primary['severity']}).")
            if blocks_decision:
                priority = _raise(priority)
                steps.append(f"Raised to {priority.value}: the credit decision cannot rely on the case until this is cleared.")
            elif len(ordered) >= 2:
                priority = _raise(priority)
                steps.append(f"Raised to {priority.value}: {len(ordered)} observations point to the same issue.")
            steps.append(f"Due {_DUE[priority.value]}; {len(evidence)} evidence item(s) requested.")

            tasks.append(Investigation(
                investigation_id=f"INV-{case_id}-{inv_type}",
                case_id=case_id,
                observation_id=primary["observation_id"],
                title=title,
                reason=reason,
                priority=priority.value,
                required_evidence=evidence,
                status=InvestigationStatus.OPEN.value,
                agent_reasoning=steps,
                investigation_type=inv_type,
                related_observation_ids=[o["observation_id"] for o in ordered[1:]],
                observation_title=primary.get("title", ""),
                observation_severity=primary["severity"],
                created_at=created_at,
                generated_by=AGENT_VERSION,
            ).to_dict())
        tasks.sort(key=lambda t: (t["priority"], [r[0] for r in ROUTES].index(t["investigation_type"])))
        return tasks

    def unrouted(self, observations: list[dict]) -> list[dict]:
        """Observations needing investigation that no MVP investigation type covers yet."""
        routed = {r for _, rules, _, _ in ROUTES for r in rules}
        return [{"observation_id": o["observation_id"], "title": o.get("title"), "severity": o.get("severity")}
                for o in observations or []
                if _needs_investigation(o) and o.get("trigger", {}).get("rule_id") not in routed]


def sync_investigations(planned: list[dict], existing: list[dict] | None) -> list[dict]:
    """Merge a fresh plan with stored tasks.

    Analyst work is kept: a task the plan still wants keeps its status, note and
    phrasing; a task the plan no longer wants (its observation was dismissed or
    explained) is dropped while still OPEN, and kept if work already started.
    """
    stored = {t["investigation_id"]: t for t in existing or []}
    merged = []
    for task in planned:
        old = stored.pop(task["investigation_id"], None)
        if old:
            task = {**task, "status": old.get("status", task["status"]), "review": old.get("review") or {},
                    "request_text": old.get("request_text"), "created_at": old.get("created_at", task["created_at"])}
        merged.append(task)
    merged += [t for t in stored.values() if t.get("status") != InvestigationStatus.OPEN.value]
    return merged
