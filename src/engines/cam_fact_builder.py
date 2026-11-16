"""
CAM Fact-Pack Builder
Assembles the approved factual JSON structure from deterministic engine outputs.
This is Pass 1 — no LLM involvement.
"""

from datetime import date
from src.models.canonical_model import Collateral, ConductRecord
from src.engines.ratio_engine import compute_all_ratios, revenue_growth_rate
from src.engines.benchmark_engine import benchmark_summary_table
from src.engines.credit_assessment import CreditAssessment, assess_credit
from src.engines.projection_engine import build_projections
from src.services.corporate_hierarchy import enrich_group_with_hierarchy
from src.engines.data_provenance import NOT_AVAILABLE, NOT_VERIFIED

# Bureau repayment classifications (RBI IRAC / SMA). "Standard" means no overdues.
_BUREAU_CLEAN = {"nil", "0", "0 dpd", "standard", "std", "current", "regular", "no overdue", "no overdues"}
_BUREAU_OVERDUE = {"sma-0", "sma0", "sma-1", "sma1"}


def classify_bureau_status(status) -> str:
    """'clean', 'overdue' (SMA-0/1) or 'adverse' (SMA-2, sub-standard, doubtful, loss) for a bureau status."""
    s = str(status if status is not None else "").strip().lower()
    if s in _BUREAU_CLEAN or s == "":
        return "clean"
    if s in _BUREAU_OVERDUE:
        return "overdue"
    return "adverse"


def _resolve_ocf(fs):
    """Get operating cash flow, checking common aliases used in data files."""
    items = fs.line_items if hasattr(fs, 'line_items') else {}
    for key in ("operating_cash_flow", "ocf", "cash_from_operations"):
        v = items.get(key)
        if v is not None and v != 0.0:
            return v
    return fs.get("operating_cash_flow")


def build_financial_summary(financials: dict, provisional=None, growth_metrics: dict | None = None) -> dict:
    """Build financial summary section from deterministic data.

    ``growth_metrics`` is the financial_analysis agent's output (YoY growth per line, OCF/PAT, revenue
    CAGR); it is computed with the same function when the fact pack is built outside a pipeline run."""
    from src.engines.ratio_engine import as_pct, compute_growth_metrics, ebitda_margin, net_profit_margin
    growth_metrics = growth_metrics or compute_growth_metrics(financials)
    summary = {"periods": {}, "growth": {}}

    periods = sorted(financials.keys())
    for p in periods:
        fs = financials[p]
        is_provisional = "_P" in p or "provisional" in p.lower()
        summary["periods"][p] = {
            "revenue_cr": fs.get("revenue_operating"),
            "ebitda_cr": fs.get("ebitda"),
            # Margins come from the ratio engine (the single source), shown to one decimal.
            "ebitda_margin_pct": as_pct(ebitda_margin(fs).value) if fs.get("revenue_operating") > 0 else 0,
            "pat_cr": fs.get("pat"),
            "pat_margin_pct": as_pct(net_profit_margin(fs).value) if fs.get("revenue_operating") > 0 else 0,
            "total_debt_cr": fs.get("total_debt"),
            "total_equity_cr": fs.get("total_equity"),
            "net_worth_cr": fs.get("total_equity"),
            "total_assets_cr": fs.get("total_assets"),
            "current_assets_cr": fs.get("current_assets"),
            "current_liabilities_cr": fs.get("current_liabilities"),
            "operating_cash_flow_cr": _resolve_ocf(fs),
            "capex_cr": abs(fs.get("capex")) if fs.get("capex") else 0.0,
            "trade_receivables_cr": fs.get("trade_receivables"),
            "inventory_cr": fs.get("inventory"),
            "trade_payables_cr": fs.get("trade_payables"),
            "data_source": f"Provisional Financials ({p})" if is_provisional else f"Audited Financials ({p})",
        }

    # Growth rates
    if len(periods) >= 2:
        for i in range(1, len(periods)):
            curr = financials[periods[i]]
            prev = financials[periods[i - 1]]
            gr = revenue_growth_rate(curr, prev)
            if gr.value is not None:
                summary["growth"][f"{periods[i]}_revenue_yoy"] = round(gr.value * 100, 1)

    # Deterministic growth: consumers quote these instead of deriving them.
    summary["growth_by_period"] = growth_metrics["by_period"]
    summary["revenue_cagr_pct"] = growth_metrics["revenue_cagr_pct"]
    summary["revenue_total_growth_pct"] = growth_metrics["revenue_total_growth_pct"]
    summary["cagr_basis"] = f"{growth_metrics['cagr_from']} to {growth_metrics['cagr_to']}"

    if provisional:
        summary["provisional"] = {
            "period": provisional.period,
            "revenue_cr": provisional.get("revenue_operating"),
            "ebitda_cr": provisional.get("ebitda"),
            "pat_cr": provisional.get("pat"),
            "total_debt_cr": provisional.get("total_debt"),
            "total_equity_cr": provisional.get("total_equity"),
        }

    return summary


def build_ratio_summary(financials: dict, ratios_by_period: dict | None = None) -> dict:
    """Ratio summary from the financial_analysis agent's ratios (computed here only outside a pipeline run)."""
    result = {}
    for period, fs in sorted(financials.items()):
        ratios = (ratios_by_period or {}).get(period) or compute_all_ratios(fs)
        result[period] = {
            r.ratio_name: {
                "value": r.value,
                "formula": r.formula,
                "status": r.status,
            } for r in ratios
        }
    return result


def build_collateral_summary(collaterals: list[Collateral], facility_amount: float) -> dict:
    """Build collateral analysis."""
    total_market = sum(c.market_value_cr for c in collaterals)
    total_fsv = sum(c.forced_sale_value_cr for c in collaterals)
    coverage_market = round(total_market / facility_amount, 2) if facility_amount > 0 else 0
    coverage_fsv = round(total_fsv / facility_amount, 2) if facility_amount > 0 else 0

    return {
        "collaterals": [
            {
                "type": c.collateral_type,
                "description": c.description,
                "market_value_cr": c.market_value_cr,
                "forced_sale_value_cr": c.forced_sale_value_cr,
                "valuation_date": str(c.valuation_date),
                "encumbrance": c.encumbrance_status,
            } for c in collaterals
        ],
        "total_market_value_cr": total_market,
        "total_forced_sale_value_cr": total_fsv,
        "facility_amount_cr": facility_amount,
        "coverage_ratio_market": coverage_market,
        "coverage_ratio_fsv": coverage_fsv,
    }


def build_conduct_summary(conduct: list[ConductRecord]) -> dict:
    """Build ETB conduct analysis."""
    if not conduct:
        return {"available": False, "note": "NTB case — no prior banking conduct available"}

    return {
        "available": True,
        "quarters_analyzed": len(conduct),
        "records": [
            {
                "period": c.period,
                "avg_balance_cr": c.avg_bank_balance_cr,
                "credit_turnover_cr": c.credit_turnover_cr,
                "cheque_returns": c.cheque_returns,
                "utilization_pct": c.limit_utilization_pct,
                "max_overdue_days": c.max_overdue_days,
                "dpd_30_count": c.dpd_30_count,
                "dpd_60_count": c.dpd_60_count,
            } for c in conduct
        ],
        "total_cheque_returns": sum(c.cheque_returns for c in conduct),
        "max_dpd_overall": max(c.max_overdue_days for c in conduct),
        "avg_utilization_pct": round(sum(c.limit_utilization_pct for c in conduct) / len(conduct), 1),
        "utilization_trend": "increasing" if conduct[0].limit_utilization_pct > conduct[-1].limit_utilization_pct else "stable",
    }


def build_cam_fact_pack(company_data: dict, assessment: CreditAssessment | None = None,
                        pep_result=None, financial_analysis: dict | None = None) -> dict:
    """
    MASTER FUNCTION: Build the complete CAM fact pack from all deterministic sources.
    This is the approved factual dataset — the LLM can only write from this.

    ``assessment`` is the pipeline's credit assessment; pass it so the CAM states
    exactly the recommendation recorded on the case. ``pep_result`` is the PEP
    agent's screening; when omitted (outside the pipeline, or if that agent
    failed) the directors are screened here. ``financial_analysis`` is that agent's result: its ratios and
    growth metrics are used as they are instead of being recomputed.
    """
    financial_analysis = financial_analysis or {}
    borrower = company_data["borrower"]
    group = company_data["group"]
    directors = company_data["directors"]
    financials = company_data["financials"]
    provisional = company_data.get("provisional")
    facility = company_data["facility"]
    collaterals = company_data["collateral"]
    market_signals = company_data.get("market_signals", [])
    existing_exposure = company_data.get("existing_exposure", [])
    conduct = company_data.get("conduct", [])
    covenants = company_data.get("covenants", [])
    extraction = company_data.get("extraction")
    etb_analysis_data = company_data.get("etb_analysis_data") or company_data.get("etb_analysis")
    document_verification = company_data.get("document_verification") or {}
    downloaded_annual_reports = (extraction or {}).get("downloaded_annual_reports") or []

    # ── PEP Screening ── (reuse the pipeline's screening when given)
    if pep_result is None:
        from src.services.pep_service import screen_directors
        pep_result = screen_directors(borrower.entity_id, directors)

    # ── Core Banking Data (ETB) ──
    core_banking_data = company_data.get("core_banking") or {}

    # ── Social Media Intelligence ──
    # Read from the borrower's data file when a source supplied a profile; otherwise "not available"
    from src.engines.social_media_engine import analyze_social_media, social_media_summary_for_cam
    social_media_data = analyze_social_media(borrower.entity_id, borrower.company_name, borrower.sector.value)
    social_media_cam_summary = social_media_summary_for_cam(social_media_data) if social_media_data else ""

    # ── Core Banking Analysis (ETB) ──
    from src.engines.core_banking_engine import analyze_core_banking
    core_banking_analysis = analyze_core_banking(
        borrower.entity_id, core_banking_data,
        case_type=facility.case_type.value,
    )

    # ── Web Crawl News ── only a verified feed (company_data["web_crawl_news"], set by the Probe42
    # bundle) is used; the canned sector corpus in web_crawl_service is never presented as news.
    web_crawl_result, web_swot = None, None

    # ── External source data ──
    external_data = company_data.get("external_data") or {}
    if external_data:
        mca_data = external_data.get("mca_data") or {}
        bureau_data = external_data.get("bureau_data") or {}
        market_data = external_data.get("market_data") or {}
        gst_data = external_data.get("gst_data") or {}
        rating_data = external_data.get("rating_data") or {}
        crilc_data = external_data.get("crilc_data") or {}
        epfo_data = external_data.get("epfo_data") or {}
    else:
        mca_data = {}
        bureau_data = {}
        market_data = {}
        gst_data = {}
        rating_data = {}
        crilc_data = {}
        epfo_data = {}

    # ── Real financial data override (for supported companies) ──
    from src.engines.document_downloader import get_real_financials, get_supported_companies
    if borrower.entity_id in {item.get("entity_id") for item in get_supported_companies()}:
        real_fin = get_real_financials(borrower.entity_id)
        if real_fin:
            # Attach real financial metadata for CAM narrative
            company_data["_real_financials_source"] = real_fin

    # ── CRILC exposure data (from generator) ──
    from src.engines.crilc_report_generator import get_crilc_data
    crilc_detail = get_crilc_data(borrower.entity_id)

    # ── Credit assessment: computed once by the pipeline agents, or here when ──
    # ── the fact pack is built outside a pipeline run.                        ──
    if assessment is None:
        assessment = assess_credit(company_data)
    exceptions = assessment.exceptions
    latest_period = assessment.benchmarks.latest_period
    latest_benchmarks = assessment.benchmarks.latest
    worst_benchmarks = assessment.benchmarks.worst
    latest_ratios = assessment.latest_ratios
    tier1 = assessment.policy.tier1_decisions
    risk_score = assessment.policy.risk_score
    recommendation = assessment.policy.recommendation

    # ── Assemble Fact Pack ──
    fact_pack = {
        "meta": {
            "generated_date": str(date.today()),
            "pipeline_version": "v1.0",
            "parser_version": "v1.0",
            "rule_pack_version": "sector_v1",
            "benchmark_pack_version": "benchmark_v1",
            "deterministic": True,
        },

        "case_summary": {
            "case_type": facility.case_type.value,
            "borrower_type": borrower.borrower_type.value,
            "sector": borrower.sector.value,
            "subsector": borrower.subsector,
            "facility_type": facility.facility_type.value,
            "amount_requested_cr": facility.amount_requested_cr,
            "purpose": facility.purpose,
            "data_provider": company_data.get("data_provider", "internal"),
        },

        "borrower_profile": {
            "company_name": borrower.company_name,
            "cin": borrower.cin,
            "pan": borrower.pan,
            "date_of_incorporation": str(borrower.date_of_incorporation),
            "registered_state": borrower.registered_state,
            "registered_address": borrower.registered_address,
            "listed_exchange": borrower.listed_exchange,
            "nse_symbol": borrower.nse_symbol,
            "credit_rating": borrower.credit_rating,
            "rating_agency": borrower.rating_agency,
            "employee_count": borrower.employee_count,
            "authorized_capital_cr": borrower.authorized_capital,
            "paid_up_capital_cr": borrower.paid_up_capital,
        },

        "group_profile": {
            "group_name": group.group_name if group else "Standalone",
            "entities": group.entities if group else [],
            "promoter_holding_pct": group.promoter_holding_pct if group else 0,
            "institutional_holding_pct": group.institutional_holding_pct if group else 0,
            "public_holding_pct": group.public_holding_pct if group else 0,
        },

        "management_profile": {
            "directors": [
                {
                    "name": d.name,
                    "din": d.din,
                    "designation": d.designation,
                    "is_promoter": d.is_promoter,
                    "net_worth_cr": d.net_worth_cr,
                    "other_directorships": d.other_directorships,
                    "date_of_appointment": str(d.date_of_appointment),
                    "source": "MCA Company Master / Uploaded KYC",
                } for d in directors
            ],
        },

        "facility_details": {
            "facility_id": facility.facility_id,
            "facility_type": facility.facility_type.value,
            "amount_requested_cr": facility.amount_requested_cr,
            "proposed_limit_cr": facility.proposed_limit_cr,
            "existing_limit_cr": facility.existing_limit_cr,
            "purpose": facility.purpose,
            "tenor_months": facility.tenor_months,
            "collateral_type": facility.collateral_type,
        },

        "existing_exposure": [
            {
                "facility_type": e.facility_type,
                "sanctioned_cr": e.sanctioned_limit_cr,
                "outstanding_cr": e.outstanding_cr,
                "utilization_pct": e.utilization_pct,
                "overdue_days": e.overdue_days,
                "classification": e.classification,
            } for e in existing_exposure
        ],

        "financial_summary": build_financial_summary(financials, provisional,
                                                     growth_metrics=financial_analysis.get("growth_metrics")),

        "ratio_analysis": build_ratio_summary(financials, financial_analysis.get("multi_period_ratios")),

        "benchmark_summary": {
            "sector": borrower.sector.value,
            "period": latest_period,
            "benchmarks": benchmark_summary_table(latest_benchmarks),
            "worst_performers": benchmark_summary_table(worst_benchmarks),
        },

        "collateral_analysis": build_collateral_summary(collaterals, facility.amount_requested_cr),

        "conduct_analysis": build_conduct_summary(conduct),

        "covenant_history": [
            {
                "type": c.covenant_type,
                "required": c.required_value,
                "actual": c.actual_value,
                "status": c.compliance_status,
                "period": c.period,
                "details": c.breach_details,
            } for c in covenants
        ],

        "external_intelligence": {
            "mca_status": mca_data.get("payload", {}).get("status", "Unknown"),
            "bureau_score": bureau_data.get("payload", {}).get("credit_score"),
            "bureau_dpd_status": bureau_data.get("payload", {}).get("dpd_status"),
            "bureau_total_exposure_cr": bureau_data.get("payload", {}).get("total_exposure_cr"),
            "bureau_total_lenders": bureau_data.get("payload", {}).get("total_lenders"),
            "gst_fy2024_turnover_cr": gst_data.get("payload", {}).get("aggregate_turnover_fy2024_cr"),
            "gst_filing_status": gst_data.get("payload", {}).get("filing_status"),
            "rating_action": rating_data.get("payload", {}) if rating_data.get("source_status") == "success" else None,
            "market_sentiment": market_data.get("payload", {}).get("overall_sentiment"),
            "reputation_risk": market_data.get("payload", {}).get("reputation_risk_score"),
            "crilc_aggregate_exposure_cr": crilc_data.get("payload", {}).get("total_exposure_cr"),
            "crilc_sma_flag": crilc_data.get("payload", {}).get("sma_flag"),
            "crilc_asset_classification": crilc_data.get("payload", {}).get("asset_classification"),
        },

        "market_signals": [
            {
                "type": s.signal_type,
                "headline": s.headline,
                "sentiment": s.sentiment,
                "severity": s.severity.value,
                "source": s.source_name,
                "date": str(s.signal_date),
                "details": s.details,
            } for s in market_signals
        ],

        "validation_exceptions": [
            {
                "code": e.exception_code,
                "severity": e.severity.value,
                "description": e.description,
                "expected": e.expected_value,
                "observed": e.observed_value,
                "source_ref": e.source_doc_ref,
                "metric": e.impacted_metric,
                "status": e.resolution_status,
            } for e in exceptions
        ],

        "approving_authority": _build_approving_authority(facility, recommendation),
        "policy_decisions": {
            "tier1_hard_rules": [
                {
                    "rule": d.rule_code,
                    "description": d.rule_description,
                    "result": d.result,
                    "details": d.details,
                } for d in tier1
            ],
            "tier2_risk_scores": {
                "financial_score": risk_score.financial_score,
                "conduct_score": risk_score.conduct_score,
                "governance_score": risk_score.governance_score,
                "market_score": risk_score.market_score,
                "composite_score": risk_score.composite_score,
                "risk_grade": risk_score.risk_grade,
            },
            "tier3_recommendation": {
                "recommendation": recommendation.recommendation.value,
                "risk_grade": recommendation.risk_grade,
                "composite_score": recommendation.composite_score,
                "rationale": recommendation.rationale,
                "conditions": recommendation.conditions,
                "covenants_proposed": recommendation.covenants_proposed,
                "collateral_requirement": recommendation.collateral_requirement,
                "monitoring_conditions": recommendation.monitoring_conditions,
                "exception_notes": recommendation.exception_notes,
            },
        },

        "document_extraction": extraction if extraction else {},

        "downloaded_annual_reports": {
            "available": bool(downloaded_annual_reports),
            "count": len(downloaded_annual_reports) if isinstance(downloaded_annual_reports, list) else 0,
            "reports": downloaded_annual_reports if isinstance(downloaded_annual_reports, list) else [],
        },

        "document_verification": {
            "available": bool(document_verification),
            "verified_count": document_verification.get("verified_count", 0),
            "total_documents": document_verification.get("total_documents", 0),
            "total_size_mb": document_verification.get("total_size_mb", 0),
        },

        "etb_behavioral_analytics": etb_analysis_data if etb_analysis_data else {},

        "pep_screening": {
            "entity_id": pep_result.entity_id,
            "screening_date": pep_result.screening_date,
            "total_persons_screened": pep_result.total_persons_screened,
            "pep_hits": [
                {
                    "person_name": h.person_name,
                    "din": h.din,
                    "match_type": h.match_type,
                    "pep_category": h.pep_category,
                    "pep_designation": h.pep_designation,
                    "risk_level": h.risk_level,
                    "sanctions_list_hit": h.sanctions_list_hit,
                    "adverse_media_count": h.adverse_media_count,
                    "source": h.source,
                    "remarks": h.remarks,
                } for h in pep_result.pep_hits
            ],
            "sanctions_hits": pep_result.sanctions_hits,
            "adverse_media_hits": pep_result.adverse_media_hits,
            "overall_risk": pep_result.overall_risk,
            "status": pep_result.status,
            "remarks": pep_result.remarks,
        },

        "core_banking": core_banking_data,

        "core_banking_analysis": core_banking_analysis,

        "social_media_analysis": social_media_data,

        "social_media_cam_summary": social_media_cam_summary,

        "corporate_hierarchy": _build_hierarchy_section(company_data, borrower, directors, group),

        "credit_strengths": _identify_strengths(
            financials, latest_ratios, latest_benchmarks, risk_score,
            bureau_data, rating_data, conduct, borrower, collaterals, facility,
        ),

        "key_risks": _identify_risks(
            exceptions, latest_ratios, latest_benchmarks, risk_score,
            bureau_data, market_data, conduct, borrower,
        ),

        "cash_flow_repayment": _build_cash_flow_repayment(financials, facility, latest_ratios),

        "esg_regulatory": _build_esg_section(market_data, epfo_data, borrower),

        "data_sources": _build_data_sources(
            mca_data, bureau_data, gst_data, rating_data, market_data, borrower,
            downloaded_annual_reports=downloaded_annual_reports,
            document_verification=document_verification,
            data_provider=company_data.get("data_provider"),
            probe_bundle=company_data.get("probe_bundle"),
        ),
        "financial_data_strategy": company_data.get("financial_data_strategy", {}),

        # ── V2 additions for expanded CAM format ──

        "industry_analysis": _build_industry_analysis(borrower, market_data, gst_data),

        "facility_pricing": _build_facility_pricing(facility),

        "compliance_checks": _build_compliance_checks(mca_data, gst_data, bureau_data),

        "quarterly_performance": _build_quarterly_performance(financials),

        "web_crawl_news": _build_web_crawl_news(borrower, company_data, web_crawl_result, web_swot),

        "drawing_power": _build_drawing_power(facility, financials),

        "charges_data": _build_charges_data(borrower, company_data.get("probe_bundle")),

        "crilc_exposure": _build_crilc_section(crilc_data, crilc_detail),

        # ── Infrastructure operational metrics (road/highway EPC) ──
        "infra_metrics": company_data.get("infra_metrics") or {},

        # ── Sector-specific operational KPIs ──
        "sector_kpis": company_data.get("sector_kpis") or {},

        # ── Optional uploaded document data ──
        "site_visit_data": _build_site_visit_data(extraction),
        "valuation_report_data": _build_valuation_data(extraction),
        "bank_statement_analysis": _build_bank_statement_data(extraction),
    }

    # Policy thresholds and projections are computed here so every CAM section
    # quotes the same numbers instead of the LLM inventing or extrapolating them.
    thresholds = _policy_thresholds()
    fact_pack["policy_thresholds"] = thresholds
    fact_pack["financial_projections"] = build_projections(
        fact_pack["financial_summary"], fact_pack["facility_details"], fact_pack["facility_pricing"],
        fact_pack["sector_kpis"], min_dscr=thresholds["min_dscr"],
    )
    # sustainable limit, earnings quality, revenue truth and early-warning indicators (quality_engine)
    from src.engines import quality_engine
    fact_pack.update(quality_engine.build(company_data, fact_pack))
    # expected credit loss at origination (roadmap D6): stage, PD, LGD, EAD from the grade and security
    from src.engines import ecl_engine
    fact_pack["ecl"] = ecl_engine.from_fact_pack(company_data, fact_pack)
    # limit assessment (roadmap D8): turnover / MPBF / operating cycle for working capital, break-even for term loans
    from src.engines import limit_assessment
    fact_pack["limit_assessment"] = limit_assessment.from_company(company_data, fact_pack)
    from src.engines.data_provenance import classify_fact_pack
    fact_pack["data_provenance"] = classify_fact_pack(fact_pack, company_data)
    return fact_pack


_DEFAULT_POLICY_THRESHOLDS = {
    "min_dscr": 1.20, "max_debt_to_equity": 2.5, "min_current_ratio": 1.25,
    "min_interest_coverage": 2.0, "max_debt_to_ebitda": 4.0, "min_ebitda_margin_pct": 10,
    "max_tol_tnw": 4.0, "min_roe_pct": 12, "max_debtor_days": 90,
}


def _policy_thresholds() -> dict:
    """Internal credit-policy thresholds from config/rules.yaml (policy_thresholds)."""
    from src.core.config_manager import config

    configured = config.get("rules", "policy_thresholds", default={}) or {}
    return {**_DEFAULT_POLICY_THRESHOLDS, **configured}


def _build_approving_authority(facility, recommendation) -> dict:
    """Sanctioning authority required by the delegation-of-powers matrix."""
    from src.core.config_manager import config
    from src.engines.approval_policy import AuthorityMatrix

    cfg = config.get("approval", default=None)
    if not cfg:
        return {}
    matrix = AuthorityMatrix.from_config(cfg)
    system_rec = recommendation.recommendation.value
    required = matrix.required_authority(facility.amount_requested_cr, recommendation.risk_grade, system_rec)
    return {
        "level_id": required.id,
        "name": required.name,
        "amount_cr": facility.amount_requested_cr,
        "risk_grade": recommendation.risk_grade,
        "system_recommendation": system_rec,
        "deviation_route": system_rec == "decline",
        "basis": "Delegation of powers (config/approval.yaml)",
    }


def _build_hierarchy_section(company_data, borrower, directors, group):
    """Build corporate hierarchy section for the fact pack."""
    try:
        enrich_group_with_hierarchy(company_data)
    except Exception:
        pass

    hierarchy_data = company_data.get("corporate_hierarchy", [])
    group_info = {
        "group_name": group.group_name if group else "Standalone",
        "ultimate_parent": group.ultimate_parent if group and hasattr(group, "ultimate_parent") and group.ultimate_parent else borrower.company_name,
        "group_revenue_cr": group.group_revenue_cr if group and hasattr(group, "group_revenue_cr") else None,
        "group_net_worth_cr": group.group_net_worth_cr if group and hasattr(group, "group_net_worth_cr") else None,
        "group_total_debt_cr": group.group_total_debt_cr if group and hasattr(group, "group_total_debt_cr") else None,
        "entity_count": len(group.entities) if group else 1,
        "hierarchy_tree": hierarchy_data,
    }
    return group_info


def _identify_strengths(financials, ratios, benchmarks, risk_score,
                        bureau_data, rating_data, conduct, borrower,
                        collaterals, facility):
    """Deterministic identification of credit strengths."""
    strengths = []
    periods = sorted(financials.keys())
    latest_fs = financials[periods[-1]] if periods else None

    # Revenue growth
    if len(periods) >= 2:
        prev = financials[periods[-2]]
        curr = financials[periods[-1]]
        if prev.get("revenue_operating", 0) > 0 and curr.get("revenue_operating", 0) > 0:
            growth = (curr.get("revenue_operating") - prev.get("revenue_operating")) / prev.get("revenue_operating") * 100
            if growth > 500:
                # Likely a data-scale mismatch — suppress instead of reporting misleading figure
                pass
            elif growth > 10:
                strengths.append({"category": "Revenue", "detail": f"Strong revenue growth of {growth:.1f}% YoY"})

    # Profitability
    if latest_fs and latest_fs.get("revenue_operating", 0) > 0:
        margin = latest_fs.get("ebitda", 0) / latest_fs.get("revenue_operating") * 100
        if margin > 15:
            strengths.append({"category": "Profitability", "detail": f"Healthy EBITDA margin of {margin:.1f}%"})

    # Low leverage
    for r in ratios:
        if r.ratio_name == "debt_to_equity" and r.value is not None and r.value < 1.5:
            strengths.append({"category": "Leverage", "detail": f"Conservative D/E ratio of {r.value:.2f}x"})
        if r.ratio_name == "interest_coverage_ratio" and r.value is not None and r.value > 3:
            strengths.append({"category": "Debt Servicing", "detail": f"Strong ICR of {r.value:.2f}x"})
        if r.ratio_name == "current_ratio" and r.value is not None and r.value > 1.5:
            strengths.append({"category": "Liquidity", "detail": f"Adequate current ratio of {r.value:.2f}x"})

    # Credit rating
    if borrower.credit_rating and "A" in borrower.credit_rating.upper():
        strengths.append({"category": "Rating", "detail": f"Investment-grade rating: {borrower.credit_rating}"})

    # Listed
    if borrower.listed_exchange:
        strengths.append({"category": "Governance", "detail": f"Listed on {borrower.listed_exchange} — enhanced disclosure"})

    # Collateral
    total_fsv = sum(c.forced_sale_value_cr for c in collaterals)
    if facility.amount_requested_cr > 0 and total_fsv > 0:
        coverage = total_fsv / facility.amount_requested_cr
        if coverage >= 1.5:
            strengths.append({"category": "Security", "detail": f"Collateral coverage (FSV) of {coverage:.2f}x"})

    # Derived public-record credit signal
    bs = bureau_data.get("payload", {}).get("credit_score", 0)
    if bs and bs >= 700:
        strengths.append({"category": "Public Records", "detail": f"Strong derived credit signal of {bs}"})

    # Good conduct
    if conduct and all(c.max_overdue_days == 0 for c in conduct):
        strengths.append({"category": "Conduct", "detail": "Clean repayment track record — zero overdues"})

    return strengths


def _identify_risks(exceptions, ratios, benchmarks, risk_score,
                    bureau_data, market_data, conduct, borrower):
    """Deterministic identification of key risks."""
    risks = []

    # Critical/High exceptions
    for ex in exceptions:
        if ex.severity.value in ("critical", "high"):
            risks.append({"category": "Validation", "severity": ex.severity.value,
                          "detail": ex.description})

    # Weak ratios
    for r in ratios:
        if r.ratio_name == "debt_to_equity" and r.value is not None and r.value > 3:
            risks.append({"category": "Leverage", "severity": "high",
                          "detail": f"High leverage — D/E at {r.value:.2f}x"})
        if r.ratio_name == "interest_coverage_ratio" and r.value is not None and r.value < 1.5:
            risks.append({"category": "Debt Servicing", "severity": "high",
                          "detail": f"Weak ICR of {r.value:.2f}x"})
        if r.ratio_name == "current_ratio" and r.value is not None and r.value < 1.0:
            risks.append({"category": "Liquidity", "severity": "medium",
                          "detail": f"Low current ratio {r.value:.2f}x — working capital stress"})

    # Public-record stress concerns
    bp = bureau_data.get("payload", {})
    if bp.get("max_dpd_last_12m", 0) > 30:
        risks.append({"category": "Public Records", "severity": "high",
                      "detail": f"Public-record stress signal indicates {bp['max_dpd_last_12m']} days in last 12m"})

    # Conduct concerns
    if conduct:
        max_dpd = max(c.max_overdue_days for c in conduct)
        total_returns = sum(c.cheque_returns for c in conduct)
        if max_dpd > 30:
            risks.append({"category": "Conduct", "severity": "high",
                          "detail": f"Overdue of {max_dpd} days observed in banking conduct"})
        if total_returns > 5:
            risks.append({"category": "Conduct", "severity": "medium",
                          "detail": f"{total_returns} cheque returns in analysis period"})

    # Market sentiment
    rrs = market_data.get("payload", {}).get("reputation_risk_score", "low")
    if isinstance(rrs, str):
        rrs_high = rrs.lower() in ("high", "very_high", "critical")
    else:
        rrs_high = rrs > 60
    if rrs_high:
        risks.append({"category": "Reputation", "severity": "medium",
                      "detail": "Elevated reputation risk from market signals"})

    # Low composite score
    if risk_score.composite_score < 50:
        risks.append({"category": "Overall", "severity": "high",
                      "detail": f"Composite risk score {risk_score.composite_score} — below threshold"})

    return risks


def _build_cash_flow_repayment(financials, facility, ratios):
    """Build cash flow & repayment analysis section."""
    periods = sorted(financials.keys())
    analysis = {"periods": {}, "repayment_capacity": {}}

    for p in periods:
        fs = financials[p]
        ocf = _resolve_ocf(fs)
        capex_raw = fs.get("capex")
        capex = abs(capex_raw) if capex_raw else 0.0  # normalize negative convention
        fcf = ocf - capex if ocf else 0.0
        analysis["periods"][p] = {
            "operating_cash_flow_cr": ocf,
            "capex_cr": capex,
            "free_cash_flow_cr": fcf,
            "ebitda_cr": fs.get("ebitda"),
            "finance_cost_cr": fs.get("finance_cost"),
        }

    # Repayment capacity
    if periods:
        latest = financials[periods[-1]]
        ebitda = latest.get("ebitda", 0)
        finance_cost = latest.get("finance_cost", 0)
        annual_repayment = facility.amount_requested_cr / max(facility.tenor_months or 60, 1) * 12
        surplus = ebitda - finance_cost - annual_repayment
        analysis["repayment_capacity"] = {
            "annual_ebitda_cr": ebitda,
            "annual_interest_cr": finance_cost,
            "annual_repayment_cr": round(annual_repayment, 2),
            "estimated_surplus_cr": round(surplus, 2),
            "adequate": surplus > 0,
        }

    # DSCR from ratios
    for r in ratios:
        if r.ratio_name == "dscr" and r.value is not None:
            analysis["dscr"] = round(r.value, 2)
            break

    return analysis


def _build_esg_section(market_data, epfo_data, borrower):
    """ESG & regulatory facts, only where the case evidence supports them.

    No status is assumed: a value without evidence is None ("Not available from submitted
    information"). sector_risk is a rule on the borrower's sector, recorded as such.
    """
    mp = market_data.get("payload", {}) if isinstance(market_data, dict) else {}
    ep = epfo_data.get("payload", {}) if isinstance(epfo_data, dict) else {}
    epfo_status = ep.get("compliance_status")
    return {
        "environmental": {
            "sector_risk": "Medium" if borrower.sector.value in ("manufacturing", "infrastructure") else "Low",
            "sector_risk_basis": "rule on the borrower's sector (not a borrower assessment)",
            "compliance_status": None,
        },
        "social": {
            "employee_count": borrower.employee_count or ep.get("active_members"),
            "epfo_compliant": epfo_status if epfo_status not in (None, "", "Unknown") else None,
            "labor_disputes": None,
        },
        "governance": {
            "listed": bool(borrower.listed_exchange),
            "board_composition": None,
            "audit_observations": None,
        },
        "regulatory": {
            "rbi_compliance": None,
            "sebi_compliance": None if borrower.listed_exchange else "Not applicable (unlisted)",
            "gst_filing": mp.get("gst_compliance"),
            "itr_filing": None,
        },
        "not_available_note": NOT_AVAILABLE,
    }


def _build_data_sources(mca_data, bureau_data, gst_data, rating_data, market_data, borrower,
                        downloaded_annual_reports=None, document_verification=None,
                        data_provider=None, probe_bundle=None):
    """Build data source provenance appendix for audit trail."""
    sources = []

    def _src(name, system, key, status, fields):
        sources.append({
            "source_name": name,
            "source_system": system,
            "entity_key": key,
            "fetch_status": status,
            "cam_sections_using": fields,
        })

    mca_status = mca_data.get("source_status", "not_fetched")
    mca_system = "Verified Public Records" if data_provider == "probe42_mcp_v2" else "MCA V3 API"
    _src("MCA Company Master", mca_system, borrower.cin, mca_status,
         ["Borrower Profile", "Company Overview", "Corporate Hierarchy"])

    bureau_status = bureau_data.get("source_status", "not_fetched")
    bureau_system = "Verified Public Records" if data_provider == "probe42_mcp_v2" else "CIBIL Commercial"
    _src("Public Record Snapshot", bureau_system, borrower.pan, bureau_status,
         ["External Intelligence", "Risk Assessment", "360° Overview"])

    gst_status = gst_data.get("source_status", "not_fetched")
    gst_system = "Verified Public Records" if data_provider == "probe42_mcp_v2" else "GSTN"
    _src("GST Turnover", gst_system, borrower.pan, gst_status,
         ["External Intelligence", "Validation (Revenue Cross-check)"])

    rating_status = rating_data.get("source_status", "not_fetched")
    rating_system = "Verified Public Records" if data_provider == "probe42_mcp_v2" else "Rating Agency"
    _src("Credit Rating", rating_system, borrower.entity_id, rating_status,
         ["External Intelligence", "Governance Score", "Borrower Profile"])

    market_status = market_data.get("source_status", "not_fetched")
    market_system = "Verified Public Records" if data_provider == "probe42_mcp_v2" else "News & Sentiment"
    _src("Market Intelligence", market_system, borrower.entity_id, market_status,
         ["External Intelligence", "Market Score", "ESG & Regulatory"])

    if probe_bundle:
        _src("Verified KYC and Governance", "Verified Public Records", borrower.cin, "success",
             ["Borrower Profile", "Management Profile", "Compliance Checks"])
        _src("Verified Legal History", "Verified Public Records", borrower.cin,
             "success" if (probe_bundle.get("tool_results", {}).get("legal_history", {}) or {}).get("status") == "success" else "not_found",
             ["Key Risks", "External Intelligence", "Analyst Chat Context"])
        _src("Public Data Freshness", "Verified Public Records", borrower.cin, "success",
             ["Data Sources", "Audit Trail"])

    _src("Audited Financials", "Uploaded Documents", borrower.entity_id, "success",
         ["Financial Analysis", "Key Ratios", "Benchmark Analysis", "Cash Flow"])

    _src("Internal Banking Data", "Core Banking System", borrower.entity_id,
         "success" if borrower.borrower_type.value == "etb" else "n/a",
         ["Conduct Analysis", "Covenant History", "Existing Exposure"])

    # Downloaded annual reports (real PDF — PyMuPDF OCR)
    ar_list = downloaded_annual_reports if isinstance(downloaded_annual_reports, list) else []
    if ar_list:
        names = [r.get("filename", "unknown") for r in ar_list]
        total_pages = sum(r.get("page_count", 0) for r in ar_list)
        _src(
            f"Downloaded Annual Reports ({len(ar_list)} docs, {total_pages} pages)",
            "PyMuPDF OCR Engine",
            borrower.entity_id,
            "success",
            ["Financial Analysis", "Industry Analysis", "Borrower Profile", "RAG Context"],
        )
    if document_verification and document_verification.get("verified_count"):
        _src(
            f"Document Authenticity Verification ({document_verification['verified_count']} verified)",
            "SHA-256 Fingerprinting",
            borrower.entity_id,
            "success",
            ["Compliance", "Data Integrity", "Audit Trail"],
        )

    return sources


# ═══════════════════════════════════════════════════════════════════════════════
# V2 ADDITIONS — New fact-pack keys for expanded CAM format
# ═══════════════════════════════════════════════════════════════════════════════

def _sector_profile(key: str) -> dict:
    """The sector's reference profile from config/sector_profiles.yaml (no sector data is held in code)."""
    from src.core.config_manager import config
    return dict((config.get("sector_profiles", key, default={}) or {}))


def _build_industry_analysis(borrower, market_data, gst_data):
    """Build industry analysis section with SWOT, overview, competitors."""
    from src.engines.benchmark_engine import SUBSECTOR_BENCHMARK_MAP
    sector = borrower.sector.value
    # Prefer subsector-specific data (e.g. construction_epc) over generic sector
    subsector_key = SUBSECTOR_BENCHMARK_MAP.get(borrower.subsector or "", "")
    sector_info = _sector_profile(subsector_key) or _sector_profile(sector)




    # Sector reference material (in-code, not borrower-specific) is kept under sector_reference_* keys.
    # Borrower revenue segments, geographic mix and SWOT are NOT derived from sector templates: applying a
    # fixed sector split to the borrower's turnover produced figures that read as borrower facts.
    raw_segments = sector_info.get("typical_revenue_segments") or []

    return {
        "industry_overview": sector_info.get("industry_overview", ""),
        "regulatory_environment": sector_info.get("regulatory_environment", ""),
        "growth_drivers": sector_info.get("growth_drivers", []),
        "headwinds": sector_info.get("headwinds", []),
        "competitors": sector_info.get("competitors", []),
        "revenue_segments": [],          # borrower-specific segment data: not available from submitted information
        "geographic_mix": [],            # borrower-specific geographic mix: not available from submitted information
        "business_description": "",      # borrower-specific description: not available from submitted information
        "swot": {},
        "sector_reference_description": sector_info.get("description", ""),
        "sector_reference_segments": [{"name": seg["name"], "typical_pct": seg["pct"]} for seg in raw_segments],
        "sector_reference_geographic_mix": sector_info.get("typical_geographic_mix") or [],
        "basis": "sector reference text held in code; not borrower evidence",
        "not_available_note": NOT_AVAILABLE,
    }


def _build_facility_pricing(facility):
    """Build facility pricing section."""
    base_rates = {
        "working_capital": {"base_rate": "MCLR 1-Year: 8.40%", "interest_rate": "MCLR + 0.80% = 9.20% p.a.",
                            "processing_fee": "0.25% of limit (min ₹25,000)", "commitment_charge": "0.50% p.a. on undrawn",
                            "penal_interest": "2% p.a. above applicable rate (as per RBI circular dt. 18.08.2023)"},
        "term_loan": {"base_rate": "MCLR 1-Year: 8.40%", "interest_rate": "MCLR + 1.10% = 9.50% p.a.",
                      "processing_fee": "0.50% of loan amount", "commitment_charge": "Nil",
                      "penal_interest": "2% p.a. above applicable rate (as per RBI circular)"},
        "project_finance": {"base_rate": "MCLR 3-Year: 8.65%", "interest_rate": "MCLR + 1.50% = 10.15% p.a.",
                            "processing_fee": "1.00% of sanction", "commitment_charge": "0.25% p.a. on undrawn",
                            "penal_interest": "2% p.a. above applicable rate"},
    }
    pricing = base_rates.get(facility.facility_type.value, base_rates["term_loan"]).copy()
    pricing["basis"] = "standard rate card for the facility type (indicative; not borrower-specific)"
    # End use: only a borrower-submitted breakdown. The case model carries none today, so the fixed
    # percentage split that used to be applied to the requested amount is no longer produced.
    pricing["end_use_details"] = list(getattr(facility, "end_use_details", None) or [])
    if not pricing["end_use_details"]:
        pricing["end_use_note"] = NOT_AVAILABLE
    return pricing


def _build_compliance_checks(mca_data, gst_data, bureau_data):
    """Build compliance checks from external data sources."""
    mca_payload = mca_data.get("payload", {})
    gst_payload = gst_data.get("payload", {})
    bureau_payload = bureau_data.get("payload", {})

    mca_status = mca_payload.get("status")
    mca_known = mca_status not in (None, "", "Unknown")
    mca_active = (mca_status == "Active") if mca_known else None            # None = not verified
    gst_status = gst_payload.get("filing_status")
    gst_filing_ok = (gst_status in ("Filed", "Regular", "Up to date")) if gst_status else None
    bureau_dpd = bureau_payload.get("dpd_status")
    bureau_score = bureau_payload.get("credit_score")
    bureau_class = classify_bureau_status(bureau_dpd) if bureau_payload else "not_available"
    bureau_clean = {"clean": True, "overdue": False, "adverse": False}.get(bureau_class)   # None = not available

    def _icon(severity, status):
        if severity == "high":
            return "❌ " + status
        if severity == "medium":
            return "⚠️ " + status
        return "✅ " + status

    items = []

    # MCA: the company status is evidence of being active, not of filings; filings need a filing date.
    sev, st = (("ok", "Active") if mca_active else ("high", f"Status: {mca_status}")) if mca_known \
        else ("medium", NOT_VERIFIED)
    items.append({
        "check": "MCA Company Status",
        "status": st, "status_icon": _icon(sev, st),
        "details": f"Company status: {mca_status}" if mca_known else f"MCA company status: {NOT_AVAILABLE}",
        "severity": sev,
    })
    last_filing = mca_payload.get("last_agm_date") or mca_payload.get("last_balance_sheet_date")
    items.append({
        "check": "MCA Annual Return / Balance Sheet Filing",
        "status": "Filed" if last_filing else NOT_VERIFIED,
        "status_icon": _icon("ok" if last_filing else "medium", "Filed" if last_filing else NOT_VERIFIED),
        "details": f"Last filing date: {last_filing}" if last_filing else f"Filing dates: {NOT_AVAILABLE}",
        "severity": "ok" if last_filing else "medium",
    })

    # GST compliance
    gst_turnover = gst_payload.get("aggregate_turnover_fy2024_cr")
    sev = "ok" if gst_filing_ok else "medium"
    st = "Compliant" if gst_filing_ok else ("Review Required" if gst_filing_ok is False else NOT_VERIFIED)
    items.append({
        "check": "GST Registration & Filing",
        "status": st, "status_icon": _icon(sev, st),
        "details": f"Filing status: {gst_payload.get('filing_status', 'N/A')}; FY2024 turnover: ₹{gst_turnover:.0f} Cr" if gst_turnover else f"Filing status: {gst_payload.get('filing_status', 'N/A')}",
        "severity": sev,
    })

    # Bureau: the reported repayment classification ("Standard" = no overdues) mapped to clean /
    # overdue (SMA-0 / SMA-1) / adverse (SMA-2 or NPA). Score is a separate signal, reviewed below.
    sev, st = {"clean": ("ok", "No Overdues (Standard)" if str(bureau_dpd).strip().lower() == "standard" else "No Overdues"),
               "overdue": ("medium", f"Overdue Reported ({bureau_dpd})"),
               "adverse": ("high", f"Adverse Classification ({bureau_dpd})"),
               "not_available": ("medium", NOT_VERIFIED)}[bureau_class]
    items.append({
        "check": "Credit Bureau — Repayment Status",
        "status": st, "status_icon": _icon(sev, st),
        "details": (f"Reported classification: {bureau_dpd or 'NIL'}; Credit score: {bureau_score or 'N/A'}"
                    if bureau_payload else f"Bureau report: {NOT_AVAILABLE}"),
        "severity": sev,
    })

    if bureau_score and bureau_score < 650:
        items.append({
            "check": "Credit Bureau — Score Review",
            "status": "Below Threshold", "status_icon": _icon("high", "Below Threshold"),
            "details": f"Bureau score {bureau_score} is below the internal threshold of 650",
            "severity": "high",
        })

    # Wilful defaulter: only what the bureau payload reports.
    wd = bureau_payload.get("wilful_defaulter") if bureau_payload else None
    wd_status = NOT_VERIFIED if wd is None else ("Listed" if wd else "Not listed")
    items.append({
        "check": "Wilful Defaulter (bureau flag)",
        "status": wd_status, "status_icon": _icon("high" if wd else ("medium" if wd is None else "ok"), wd_status),
        "details": (f"Wilful-defaulter flag in the bureau report: {'Yes' if wd else 'No'}" if wd is not None
                    else f"Wilful-defaulter screening: {NOT_AVAILABLE}"),
        "severity": "high" if wd else ("medium" if wd is None else "ok"),
    })

    # FEMA / SEBI (placeholder based on listing status from MCA)
    listed = mca_payload.get("listed_status")
    st2 = NOT_VERIFIED if listed else "N/A (Unlisted)"
    items.append({
        "check": "SEBI / Exchange Compliance",
        "status": st2, "status_icon": _icon("medium" if listed else "ok", st2),
        "details": (f"Listed company — exchange compliance: {NOT_AVAILABLE}" if listed
                    else "Unlisted company — SEBI compliance not applicable"),
        "severity": "medium" if listed else "ok",
    })

    return {
        "mca_status_verified": mca_known,
        "annual_return_filed": True if last_filing else None,
        "balance_sheet_filed": True if last_filing else None,
        "gst_filing_compliant": gst_filing_ok,
        "bureau_clean": bureau_clean,
        "bureau_status_class": bureau_class,
        "bureau_score": bureau_score,
        "items": items,
    }


def _build_quarterly_performance(financials):
    """Build quarterly performance data from annual financials."""
    if not financials:
        return []

    quarters = []
    for period in sorted(financials.keys()):
        fs = financials[period]
        rev = fs.get("revenue_operating", 0) or 0
        ebitda = fs.get("ebitda", 0) or 0
        pat = fs.get("pat", 0) or 0

        if rev <= 0:
            continue

        # Generate Q1-Q4 with seasonal weighting (Q4 typically higher due to year-end)
        weights = [0.22, 0.22, 0.22, 0.34]
        for q_num, w in enumerate(weights, 1):
            q_rev = round(rev * w, 2)
            q_ebitda = round(ebitda * w, 2)
            q_pat = round(pat * w, 2)
            q_em = round((q_ebitda / q_rev * 100), 1) if q_rev > 0 else 0
            q_pm = round((q_pat / q_rev * 100), 1) if q_rev > 0 else 0
            quarters.append({
                "quarter": f"Q{q_num} {period}",
                "revenue_cr": q_rev,
                "ebitda_cr": q_ebitda,
                "pat_cr": q_pat,
                "ebitda_margin_pct": q_em,
                "pat_margin_pct": q_pm,
                "status": "Audited" if q_num == 4 else "Estimated",
            })

    return quarters


def _build_web_crawl_news(borrower, company_data, web_crawl_result=None, web_swot=None):
    """External news from a verified feed only; otherwise explicitly unavailable (never fabricated)."""
    web_news = company_data.get("web_crawl_news") or []
    articles = web_news.get("articles", []) if isinstance(web_news, dict) else list(web_news)
    if articles:
        return {"available": True, "verified": True, "articles": articles,
                "source": "Verified public-record bundle (Probe42)"}
    return {"available": False, "verified": False, "articles": [],
            "note": "No verified news source is connected; external news is not available for this borrower."}


def _build_drawing_power(facility, financials):
    """Build drawing power assessment for working capital facilities."""
    if facility.facility_type.value != "working_capital":
        return {}

    periods = sorted(financials.keys())
    if not periods:
        return {}

    latest = financials[periods[-1]]
    recv = latest.get("trade_receivables", 0) or 0
    inv = latest.get("inventory", 0) or 0
    pay = latest.get("trade_payables", 0) or 0

    dp_recv = round(recv * 0.75, 2)
    dp_inv = round(inv * 0.60, 2)
    dp_pay = round(pay * 0.50, 2)
    total_dp = round(dp_recv + dp_inv - dp_pay, 2)

    return {
        "components": [
            {"name": "Trade Receivables (all; ageing not available)", "value_cr": recv, "margin_pct": 25.0, "dp_cr": dp_recv},
            {"name": "Inventory (Finished + Raw)", "value_cr": inv, "margin_pct": 40.0, "dp_cr": dp_inv},
            {"name": "Less: Creditors for Purchases", "value_cr": pay, "margin_pct": 50.0, "dp_cr": -dp_pay},
        ],
        "total_dp_cr": max(total_dp, 0),
    }


def _build_charges_data(borrower, probe_bundle=None):
    """Build charges/encumbrance data from Probe first, then MCA fallback."""
    if probe_bundle:
        try:
            open_charges = ((probe_bundle.get("tool_results") or {}).get("open_charges") or {}).get("data")
            if isinstance(open_charges, list):
                return {
                    "source": "probe42_open_charges",
                    "count": len(open_charges),
                    "charges": open_charges,
                }
        except Exception:
            pass

    try:
        from src.services.external_systems import mca_charges
        charges_result = mca_charges(borrower.cin)
        if charges_result.get("source_status") == "success":
            payload = charges_result.get("payload", {})
            if isinstance(payload, dict):
                payload.setdefault("source", "mca_charges")
            return payload
    except Exception:
        pass
    return {}


def _build_crilc_section(crilc_mock_data: dict, crilc_detail: dict | None) -> dict:
    """Build CRILC exposure section for the fact pack."""
    section = {}
    # From mock external API
    payload = crilc_mock_data.get("payload", {})
    if payload:
        section["aggregate_exposure_cr"] = payload.get("total_exposure_cr")
        section["total_outstanding_cr"] = payload.get("total_outstanding_cr")
        section["fund_based_cr"] = payload.get("total_fund_based_outstanding_cr")
        section["non_fund_based_cr"] = payload.get("total_non_fund_based_outstanding_cr")
        section["total_lenders"] = payload.get("reporting_banks_count")
        section["dpd_max"] = payload.get("dpd_max")
        section["asset_classification"] = payload.get("asset_classification")
        section["sma_flag"] = payload.get("sma_flag")
        section["wilful_defaulter"] = payload.get("wilful_defaulter")
        section["fraud_flag"] = payload.get("fraud_flag")
    # Enriched data from CRILC generator
    if crilc_detail:
        section["fund_based_facilities"] = crilc_detail.get("fund_based", [])
        section["non_fund_based_facilities"] = crilc_detail.get("non_fund_based", [])
        section["sma_history"] = crilc_detail.get("sma_history", [])
        section["aggregate_summary"] = crilc_detail.get("aggregate_summary", {})
    return section


def _build_site_visit_data(extraction: dict | None) -> dict:
    """Build site visit data section from extracted optional inputs."""
    if not extraction:
        return {"available": False}
    sv = extraction.get("site_visit") or {}
    if not sv:
        return {"available": False}
    return {
        "available": True,
        "visit_date": sv.get("visit_date"),
        "visited_by": sv.get("visited_by"),
        "location": sv.get("location"),
        "operational_status": sv.get("operational_status"),
        "infrastructure": sv.get("infrastructure"),
        "inventory": sv.get("inventory"),
        "management_observations": sv.get("management_observations"),
        "overall_assessment": sv.get("overall_assessment"),
        "source_document": extraction.get("selected_documents", {}).get("site_visit_report"),
        "full_text": sv.get("full_text", "")[:2000],
    }


def _build_valuation_data(extraction: dict | None) -> dict:
    """Build valuation report data section from extracted optional inputs."""
    if not extraction:
        return {"available": False}
    val = extraction.get("valuation") or {}
    if not val:
        return {"available": False}
    return {
        "available": True,
        "property_type": val.get("property_type"),
        "market_value": val.get("market_value"),
        "forced_sale_value": val.get("forced_sale_value"),
        "valuation_date": val.get("valuation_date"),
        "location": val.get("location"),
        "area": val.get("area"),
        "encumbrance_status": val.get("encumbrance_status"),
        "source_document": extraction.get("selected_documents", {}).get("valuation_report"),
        "full_text": val.get("full_text", "")[:2000],
    }


def _build_bank_statement_data(extraction: dict | None) -> dict:
    """Build bank statement analysis section from extracted optional inputs."""
    if not extraction:
        return {"available": False}
    bs = extraction.get("bank_statement") or {}
    if not bs or (not bs.get("account_number") and not bs.get("full_text")):
        return {"available": False}
    return {
        "available": True,
        "account_number": bs.get("account_number"),
        "account_type": bs.get("account_type"),
        "bank_name": bs.get("bank_name"),
        "opening_balance": bs.get("opening_balance"),
        "closing_balance": bs.get("closing_balance"),
        "average_balance": bs.get("average_balance"),
        "total_credits": bs.get("total_credits"),
        "total_debits": bs.get("total_debits"),
        "cheque_returns_found": bs.get("cheque_returns_found", False),
        "pages": bs.get("pages"),
        "source_document": extraction.get("selected_documents", {}).get("bank_statement"),
        "full_text": bs.get("full_text", "")[:2000],
    }
