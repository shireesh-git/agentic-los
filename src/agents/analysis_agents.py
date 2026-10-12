"""
Deterministic analysis agents: ratios, validations, peer benchmarks and credit
policy. The rules live in ``src.engines.credit_assessment`` so the case record
and the CAM fact pack use one computation.
"""

from src.agents.base_agent import BaseAgent


class FinancialAnalysisAgent(BaseAgent):
    name = "financial_analysis"
    description = "Compute financial ratios and growth metrics"
    # Reads no ingestion *result*, but ingestion rewrites company_data["financials"]
    # from uploaded statements, so it must finish first (matters when agents run in parallel).
    requires = ("data_ingestion",)

    def run(self, context):
        from src.engines.ratio_engine import compute_growth_metrics, compute_multi_period_ratios

        financials = context["company_data"]["financials"]
        if not financials:
            raise ValueError(
                "No financial statements available. "
                "Re-onboard the company or upload audited financials first."
            )
        latest_period = sorted(financials.keys())[-1]
        by_period = compute_multi_period_ratios(financials)
        return {
            # Authoritative ratios for every period: benchmark and the narrative fact pack use these.
            "multi_period_ratios": by_period,
            "latest_ratios": by_period[latest_period],
            "latest_period": latest_period,
            "growth_metrics": compute_growth_metrics(financials),
        }


class ValidationAgent(BaseAgent):
    name = "validation"
    description = "Run structural, cross-source, and policy validations"
    requires = ("data_ingestion",)

    def run(self, context):
        from src.engines.credit_assessment import validate

        ingestion = context["results"].get("data_ingestion", {})
        return {
            "exceptions": validate(context["company_data"],
                                   ingestion.get("bureau_data") or {},
                                   ingestion.get("gst_data") or {}),
        }


class BenchmarkAgent(BaseAgent):
    name = "benchmark"
    description = "Compare borrower metrics against sector peer benchmarks"
    requires = ("financial_analysis",)

    def run(self, context):
        from src.engines.credit_assessment import benchmark

        view = benchmark(context["company_data"],
                         ratios_by_period=context["results"]["financial_analysis"]["multi_period_ratios"])
        return {
            "view": view,
            "benchmarks": view.by_period,
            "latest_benchmarks": view.latest,
            "worst_benchmarks": view.worst,
        }


class PolicyAgent(BaseAgent):
    name = "policy"
    description = "Execute hard rules, risk scoring, and recommendation assembly"
    requires = ("financial_analysis", "validation", "benchmark")

    def run(self, context):
        from src.engines.credit_assessment import decide

        r = context["results"]
        outcome = decide(
            context["company_data"],
            exceptions=r["validation"]["exceptions"],
            latest_ratios=r["financial_analysis"]["latest_ratios"],
            latest_benchmarks=r["benchmark"]["latest_benchmarks"],
            bureau_data=r.get("data_ingestion", {}).get("bureau_data") or {},
        )
        return {
            "outcome": outcome,
            "tier1_decisions": outcome.tier1_decisions,
            "risk_score": outcome.risk_score,
            "recommendation": outcome.recommendation,
            "collateral_coverage": outcome.collateral_coverage,
        }
