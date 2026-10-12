"""
Credit assessment — the single definition of how a case is validated,
benchmarked, scored and recommended.

The pipeline agents call the step functions; the CAM fact-pack builder
receives the resulting ``CreditAssessment`` instead of recomputing it, so the
dashboard, the case record and the CAM narrative can never disagree.
"""

from dataclasses import dataclass

from src.engines.benchmark_engine import benchmark_all_periods, get_worst_benchmarks
from src.engines.policy_engine import (
    CreditRecommendation, RiskScore, tier1_hard_rules, tier2_scoring, tier3_recommendation,
)
from src.engines.ratio_engine import compute_all_ratios
from src.engines.validation_engine import run_all_validations


@dataclass
class BenchmarkView:
    by_period: dict
    latest_period: str
    latest: list
    worst: list


@dataclass
class PolicyOutcome:
    tier1_decisions: list
    risk_score: RiskScore
    recommendation: CreditRecommendation
    collateral_coverage: float


@dataclass
class CreditAssessment:
    exceptions: list
    benchmarks: BenchmarkView
    latest_ratios: list
    policy: PolicyOutcome


def external_payloads(company_data: dict) -> tuple[dict, dict]:
    """Bureau and GST payloads from the cached verified public-record bundle."""
    external = company_data.get("external_data") or {}
    return external.get("bureau_data") or {}, external.get("gst_data") or {}


def latest_period(financials: dict) -> str:
    return sorted(financials.keys())[-1]


def validate(company_data: dict, bureau_data: dict, gst_data: dict) -> list:
    facility = company_data["facility"]
    return run_all_validations(
        borrower=company_data["borrower"],
        financials=company_data["financials"],
        provisional=company_data.get("provisional"),
        exchange_filing=company_data.get("exchange_filing"),
        bureau_payload=bureau_data,
        gst_payload=gst_data,
        market_signals=company_data.get("market_signals", []),
        conduct_records=company_data.get("conduct", []),
        covenants=company_data.get("covenants", []),
        case_type=facility.case_type,
        extraction=company_data.get("extraction"),
        etb_analysis=company_data.get("etb_analysis_data") or company_data.get("etb_analysis"),
        document_inventory=company_data.get("document_inventory"),
    )


def benchmark(company_data: dict, ratios_by_period: dict | None = None) -> BenchmarkView:
    borrower = company_data["borrower"]
    financials = company_data["financials"]
    by_period = benchmark_all_periods(borrower.entity_id, borrower.sector, financials,
                                      subsector=borrower.subsector or "", ratios_by_period=ratios_by_period)
    period = latest_period(financials)
    return BenchmarkView(by_period=by_period, latest_period=period,
                         latest=by_period.get(period, []),
                         worst=get_worst_benchmarks(by_period, period))


def collateral_coverage(company_data: dict) -> float:
    """Security cover on forced-sale value (the conservative basis)."""
    amount = company_data["facility"].amount_requested_cr
    total_fsv = sum(c.forced_sale_value_cr for c in company_data.get("collateral") or [])
    return round(total_fsv / amount, 2) if amount > 0 else 0


def decide(company_data: dict, exceptions: list, latest_ratios: list, latest_benchmarks: list,
           bureau_data: dict) -> PolicyOutcome:
    borrower = company_data["borrower"]
    facility = company_data["facility"]
    group = company_data.get("group")
    infra_metrics = company_data.get("infra_metrics") or None

    mca = ((company_data.get("external_data") or {}).get("mca_data") or {}).get("payload") or {}
    demo = company_data.get("catalog_source") == "demo_catalog" or company_data.get("data_provider") == "synthetic_demo"
    tier1 = tier1_hard_rules(borrower, facility, exceptions, bureau_data,
                             document_inventory=company_data.get("document_inventory"),
                             mca_status=mca.get("status"), demo_evidence=demo)
    risk_score = tier2_scoring(
        borrower=borrower,
        ratios=latest_ratios,
        benchmarks=latest_benchmarks,
        conduct=company_data.get("conduct", []),
        covenants=company_data.get("covenants", []),
        directors=company_data.get("directors", []),
        group_entities=len(group.entities) if group else 0,
        market_signals=company_data.get("market_signals", []),
        infra_metrics=infra_metrics,
    )
    coverage = collateral_coverage(company_data)
    recommendation = tier3_recommendation(
        tier1_decisions=tier1,
        risk_score=risk_score,
        exceptions=exceptions,
        facility=facility,
        collateral_coverage=coverage,
        infra_metrics=infra_metrics,
    )
    return PolicyOutcome(tier1_decisions=tier1, risk_score=risk_score,
                         recommendation=recommendation, collateral_coverage=coverage)


def assess_credit(company_data: dict) -> CreditAssessment:
    """Run every step outside the pipeline (e.g. re-rendering a CAM from stored data)."""
    bureau_data, gst_data = external_payloads(company_data)
    exceptions = validate(company_data, bureau_data, gst_data)
    benchmarks = benchmark(company_data)
    latest_ratios = compute_all_ratios(company_data["financials"][benchmarks.latest_period])
    policy = decide(company_data, exceptions, latest_ratios, benchmarks.latest, bureau_data)
    return CreditAssessment(exceptions=exceptions, benchmarks=benchmarks,
                            latest_ratios=latest_ratios, policy=policy)
