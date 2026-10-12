"""
360-Degree Dashboard Agent — Comprehensive company view with sell-side perspective.

Provides:
  1. Company Overview (identity, structure, governance)
  2. Financial Health Dashboard (ratios, trends, benchmarks)
  3. Credit Risk Profile (public records, rating, policy decision)
  4. Market Intelligence (sentiment, peer comparison, ESG)
  5. Document Completeness
  6. Sell-Side Perspective (deal attractiveness, pricing guidance, risk-reward)
  7. Red Flags & Watch Items
  8. Recommendation Summary
"""

import re
from datetime import date
from typing import Any, Optional

from src.services.external_systems import (
    crilc_report, _ENTITY_TO_IDS,
)
from src.services.document_store import doc_store


def _safe_get(d: dict, *keys, default=None):
    """Safely traverse nested dict."""
    curr = d
    for k in keys:
        if isinstance(curr, dict):
            curr = curr.get(k, default)
        else:
            return default
    return curr


def _probe_tool_payload(bundle: dict | None, key: str, default=None):
    entry = ((bundle or {}).get("tool_results") or {}).get(key) or {}
    data = entry.get("data")
    if data is None:
        return default
    return data


def _probe_directors(bundle: dict | None) -> list[dict]:
    kyc = _probe_tool_payload(bundle, "kyc_details", default={}) or {}
    candidates = (
        kyc.get("current_directors")
        or kyc.get("directors")
        or _safe_get(kyc, "management", "directors", default=[])
        or []
    )
    directors: list[dict] = []
    for director in candidates:
        if not isinstance(director, dict):
            continue
        directors.append({
            "name": director.get("name"),
            "din": director.get("din"),
            "designation": director.get("designation") or director.get("role"),
            "shareholding_pct": director.get("shareholding_pct", 0),
            "other_companies_count": len(director.get("other_companies", []) or []),
            "status": director.get("status"),
        })
    return directors


def _probe_charges_payload(bundle: dict | None) -> dict:
    open_charges = _probe_tool_payload(bundle, "open_charges", default=[]) or []
    if not isinstance(open_charges, list):
        open_charges = []
    return {
        "total_charges": len(open_charges),
        "open_charges": len(open_charges),
        "satisfied_charges": 0,
        "charges": open_charges,
    }


def _fact_pack(case_result: dict | None) -> dict:
    return (case_result or {}).get("fact_pack") or {}


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _latest_financial_period(financial_summary: dict | None) -> tuple[str, dict]:
    periods = ((financial_summary or {}).get("periods")) or {}
    if not periods:
        return "", {}
    latest = max(periods.keys())
    return latest, periods.get(latest) or {}


def _normalize_directors(directors: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for director in directors or []:
        if not isinstance(director, dict):
            continue
        other_directorships = (
            director.get("other_directorships")
            or director.get("other_companies")
            or []
        )
        normalized.append({
            "name": director.get("name"),
            "din": director.get("din"),
            "designation": director.get("designation") or director.get("role"),
            "shareholding_pct": director.get("shareholding_pct") or director.get("holding_pct") or 0,
            "other_companies_count": len(other_directorships),
            "status": director.get("status") or ("promoter" if director.get("is_promoter") else None),
            "is_promoter": bool(director.get("is_promoter")),
        })
    return normalized


def _parse_percent(text: Any) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text or ""))
    if not match:
        return None
    return _safe_number(match.group(1), default=None)


def _severity_rank(severity: str | None) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(severity or "").lower(), 4)


def _market_stance(market_score: float, positive_signals: int, negative_watch_items: int, negative_high_items: int) -> str:
    if negative_high_items:
        return "Cautious"
    if market_score >= 75 and negative_watch_items == 0 and positive_signals:
        return "Favourable"
    if market_score >= 65 and negative_watch_items <= 1:
        return "Stable with watch items"
    if market_score >= 55:
        return "Mixed"
    return "Cautious"


def _summarize_market_position(overview: dict, competitors: list[dict], rating_text: str) -> str:
    company_name = str(overview.get("company_name") or "").lower()
    company_peer = next(
        (
            peer for peer in competitors or []
            if isinstance(peer, dict) and company_name and company_name.split(" ")[0] in str(peer.get("name") or "").lower()
        ),
        None,
    )
    parts: list[str] = []
    if overview.get("listing_status"):
        parts.append("listed franchise")
    if company_peer and company_peer.get("market_share_pct"):
        parts.append(f"~{company_peer['market_share_pct']}% peer market share")
    if rating_text:
        parts.append(f"{rating_text} external rating")
    sector = overview.get("industrial_class") or "sector"
    if not parts:
        return f"Established participant in {sector}."
    return f"Top-tier {sector.lower()} player with " + ", ".join(parts) + "."


def _aggregate_validation_flags(exceptions: list[dict] | None) -> list[dict]:
    grouped: dict[str, dict[str, Any]] = {}
    for exception in exceptions or []:
        if not isinstance(exception, dict):
            continue
        code = exception.get("exception_code") or exception.get("code") or exception.get("description") or "validation_exception"
        group = grouped.setdefault(code, {
            "count": 0,
            "severity": exception.get("severity", "medium"),
            "description": exception.get("description", ""),
            "source_refs": set(),
        })
        group["count"] += 1
        if _severity_rank(exception.get("severity")) < _severity_rank(group["severity"]):
            group["severity"] = exception.get("severity", group["severity"])
        source_ref = exception.get("source_doc_ref") or exception.get("source_ref")
        if source_ref:
            group["source_refs"].add(str(source_ref))

    flags: list[dict] = []
    for code, group in grouped.items():
        refs_text = " ".join(sorted(group["source_refs"]))
        years = sorted(set(re.findall(r"FY\d{4}", refs_text or group["description"])))
        if code == "STRUCT_EBITDA_INCONSISTENT":
            if years:
                flag = f"EBITDA structure mismatch across {years[0]} to {years[-1]} ({group['count']} period(s))"
            else:
                flag = f"EBITDA structure mismatch across {group['count']} reported period(s)"
        elif code == "STRUCT_PAT_INCONSISTENT":
            flag = f"PAT structure mismatch{' in ' + years[-1] if years else ''}"
        elif code == "XSRC_REVENUE_MISMATCH":
            flag = "Revenue mismatch between borrower submissions and exchange/public disclosures"
        elif code == "DOC_REVENUE_CROSS_SOURCE":
            flag = f"Revenue mismatch across {group['count']} extracted document comparison(s)"
        else:
            flag = group["description"] or str(code).replace("_", " ").title()

        flags.append({
            "severity": group["severity"],
            "category": "validation",
            "flag": flag,
            "source": "validation_engine",
            "detail": group["description"],
        })

    return sorted(flags, key=lambda item: (_severity_rank(item.get("severity")), item.get("flag") or ""))


def _build_market_intelligence(
    overview: dict,
    case_result: dict | None,
    market_p: dict,
    rating_p: dict,
) -> dict:
    fact_pack = _fact_pack(case_result)
    industry = fact_pack.get("industry_analysis") or {}
    competitors = [peer for peer in industry.get("competitors", []) if isinstance(peer, dict)]
    signals = [signal for signal in fact_pack.get("market_signals", []) if isinstance(signal, dict)]
    news_bundle = fact_pack.get("web_crawl_news") or {}
    news_items = news_bundle.get("articles", []) if isinstance(news_bundle, dict) else []

    positive_signals = sum(1 for signal in signals if str(signal.get("sentiment") or "").lower() == "positive")
    negative_signals = sum(1 for signal in signals if str(signal.get("sentiment") or "").lower() == "negative")
    negative_watch_items = sum(
        1 for signal in signals
        if str(signal.get("sentiment") or "").lower() == "negative"
        and str(signal.get("severity") or "").lower() in ("medium", "high", "critical")
    )
    negative_high_items = sum(
        1 for signal in signals
        if str(signal.get("sentiment") or "").lower() == "negative"
        and str(signal.get("severity") or "").lower() in ("high", "critical")
    )

    market_score = _safe_number((case_result or {}).get("market_score"))
    stance = _market_stance(market_score, positive_signals, negative_watch_items, negative_high_items)
    rating_text = rating_p.get("long_term_rating") or rating_p.get("rating") or ""
    market_position = _summarize_market_position(overview, competitors, rating_text)

    growth_drivers = [item for item in industry.get("growth_drivers", []) if item]
    headwinds = [item for item in industry.get("headwinds", []) if item]
    watch_items = [
        {
            "headline": signal.get("headline"),
            "severity": signal.get("severity"),
            "source": signal.get("source"),
            "detail": signal.get("details"),
        }
        for signal in signals
        if str(signal.get("sentiment") or "").lower() == "negative"
    ]

    if growth_drivers or headwinds:
        outlook_bits = []
        if growth_drivers:
            outlook_bits.append(f"Tailwinds: {growth_drivers[0]}")
        if headwinds:
            outlook_bits.append(f"Monitor: {headwinds[0]}")
        industry_outlook = ". ".join(outlook_bits) + "."
    else:
        industry_outlook = market_p.get("industry_outlook") or "Sector outlook not captured in the current case."

    return {
        "sentiment": {
            "overall": stance,
            "score": market_score or market_p.get("sentiment_score"),
            "signal_count": len(signals),
            "news_count_90d": len(news_items),
            "positive": positive_signals,
            "negative": negative_signals,
        },
        "summary": {
            "stance": stance,
            "market_score": market_score,
            "signals_reviewed": len(signals),
            "watch_items": negative_watch_items,
            "positive_signals": positive_signals,
            "news_articles_90d": len(news_items),
        },
        "reputation_risk": "watch" if negative_watch_items else "stable",
        "market_position": market_position,
        "industry_outlook": industry_outlook,
        "peer_comparison": market_p.get("peer_comparison", {}),
        "esg": market_p.get("esg_score", {}),
        "industry": {
            "overview": industry.get("industry_overview"),
            "regulatory_environment": industry.get("regulatory_environment"),
            "growth_drivers": growth_drivers,
            "headwinds": headwinds,
            "revenue_segments": industry.get("revenue_segments", []),
            "geographic_mix": industry.get("geographic_mix", []),
            "business_description": industry.get("business_description"),
        },
        "competitors": competitors,
        "signals": signals,
        "watch_items": watch_items,
    }


def generate_360_view(entity_id: str, company_data: dict = None,
                      case_result: dict = None) -> dict:
    """
    Generate a comprehensive 360-degree view for a company.

    Args:
        entity_id: Company entity ID
        company_data: company_store entry (borrower, financials, etc.)
        case_result: case_store entry (if pipeline was run)

    Returns: Structured dict with all 360-view sections
    """
    borrower = (company_data or {}).get("borrower") or {}
    ids = _ENTITY_TO_IDS.get(entity_id) or {}
    _bget = (lambda k: getattr(borrower, k, None)) if not isinstance(borrower, dict) else borrower.get
    cin = ids.get("cin") or _bget("cin") or ""
    pan = ids.get("pan") or _bget("pan") or ""
    gstin = ids.get("gstin") or _bget("gstin") or ""

    # ── Fetch all external data ──────────────────────────────
    external_data = (company_data or {}).get("external_data") or {}
    probe_bundle = (company_data or {}).get("probe_bundle") or {}
    use_public_bundle = (company_data or {}).get("data_provider") == "probe42_mcp_v2" and bool(external_data)

    crilc = crilc_report(pan) if pan else {}
    crilc_p = _safe_get(crilc, "payload", default={})

    if use_public_bundle:
        mca_p = _safe_get(external_data.get("mca_data", {}), "payload", default={})
        bureau_p = _safe_get(external_data.get("bureau_data", {}), "payload", default={})
        rating_p = _safe_get(external_data.get("rating_data", {}), "payload", default={})
        market_p = _safe_get(external_data.get("market_data", {}), "payload", default={})
        gst_p = _safe_get(external_data.get("gst_data", {}), "payload", default={})
        epfo_p = _safe_get(external_data.get("epfo_data", {}), "payload", default={})
        itr_p = {}
        directors_payload = _probe_directors(probe_bundle)
        charges_payload = _probe_charges_payload(probe_bundle)
        gst_trend = {
            "FY2024": gst_p.get("aggregate_turnover_fy2024_cr"),
            "FY2023": gst_p.get("aggregate_turnover_fy2023_cr"),
            "FY2022": gst_p.get("aggregate_turnover_fy2022_cr"),
        }
    else:
        # No Probe42 bundle loaded — data sections will be empty.
        # Real data is populated only via Probe42 onboarding.
        mca_p = {}
        bureau_p = {}
        rating_p = {}
        market_p = {}
        gst_p = {}
        epfo_p = {}
        itr_p = {}
        directors_payload = []
        charges_payload = {}
        gst_trend = {"FY2024": None, "FY2023": None, "FY2022": None}

    # ════════════════════════════════════════════════════════════
    # 1. COMPANY OVERVIEW
    # ════════════════════════════════════════════════════════════
    overview = {
        "company_name": mca_p.get("company_name", entity_id),
        "cin": cin,
        "pan": pan,
        "gstin": gstin,
        "entity_id": entity_id,
        "status": mca_p.get("status", "Unknown"),
        "company_class": mca_p.get("company_class"),
        "date_of_incorporation": mca_p.get("date_of_incorporation"),
        "registered_state": mca_p.get("registered_state"),
        "registered_office": mca_p.get("registered_office"),
        "listing_status": mca_p.get("listing_status"),
        "listed_exchange": mca_p.get("listed_exchange"),
        "authorized_capital_cr": round(mca_p.get("authorized_capital_inr", 0) / 1e7, 2),
        "paid_up_capital_cr": round(mca_p.get("paid_up_capital_inr", 0) / 1e7, 2),
        "nic_code": mca_p.get("nic_code"),
        "industrial_class": mca_p.get("industrial_class"),
        "employee_count": epfo_p.get("active_members"),
        "gst_nature_of_business": gst_p.get("nature_of_business", []),
    }

    # Directors
    directors = _normalize_directors(directors_payload)
    if not directors:
        directors = _normalize_directors(_fact_pack(case_result).get("management_profile", {}).get("directors"))
    overview["directors"] = directors

    # ════════════════════════════════════════════════════════════
    # 2. FINANCIAL HEALTH
    # ════════════════════════════════════════════════════════════
    financials = {}
    if case_result:
        fp = case_result.get("fact_pack", {})

        # ratio_analysis structure: {period: {metric_name: {value, formula, status}}}
        ra = fp.get("ratio_analysis", {})
        latest_ratio_period = max(ra.keys()) if ra else ""
        if latest_ratio_period:
            period_data = ra.get(latest_ratio_period, {})
            ratio_section = {
                k: (v.get("value") if isinstance(v, dict) else v)
                for k, v in period_data.items()
                if k != "period"
            }
            # All periods for trend tables
            all_periods_ratios = {
                period: {
                    k: (v.get("value") if isinstance(v, dict) else v)
                    for k, v in metrics.items()
                    if k != "period"
                }
                for period, metrics in ra.items()
            }
        else:
            ratio_section = {}
            all_periods_ratios = {}

        # financial_summary structure: {periods: {FY2025: {revenue_cr, ebitda_cr, pat_cr, ...}}}
        fin_sum = fp.get("financial_summary", {})
        fin_periods = fin_sum.get("periods", {})
        latest_fin_period = max(fin_periods.keys()) if fin_periods else ""
        flat_metrics = fin_periods.get(latest_fin_period, {}) if latest_fin_period else {}

        # Revenue trend across periods
        revenue_trend = [
            {"period": p, "revenue": v.get("revenue_cr")}
            for p, v in sorted(fin_periods.items())
            if isinstance(v, dict) and v.get("revenue_cr") is not None
        ]

        financials = {
            "ratios": ratio_section,
            "all_periods_ratios": all_periods_ratios,
            "financial_score": case_result.get("financial_score"),
            "revenue_trend": revenue_trend,
            "key_metrics": flat_metrics,
            "latest_period": latest_fin_period,
        }

    financials["gst_turnover_trend"] = gst_trend

    # ════════════════════════════════════════════════════════════
    # 3. CREDIT RISK PROFILE
    # ════════════════════════════════════════════════════════════
    credit_risk = {
        "bureau": {
            "credit_score": bureau_p.get("credit_score"),
            "score_band": bureau_p.get("score_band"),
            "score_description": bureau_p.get("score_description"),
            "total_exposure_cr": bureau_p.get("total_exposure_cr"),
            "total_lenders": bureau_p.get("total_lenders"),
            "dpd_status": bureau_p.get("dpd_status"),
            "max_dpd_12m": bureau_p.get("max_dpd_last_12m"),
            "worst_status_12m": bureau_p.get("worst_status_12m"),
            "wilful_defaulter": bureau_p.get("wilful_defaulter"),
            "enquiries_last_6m": bureau_p.get("enquiries_last_6m"),
        },
        "rating": {
            "agency": rating_p.get("rating_agency"),
            "long_term": rating_p.get("long_term_rating"),
            "short_term": rating_p.get("short_term_rating"),
            "outlook": rating_p.get("outlook"),
            "last_action": rating_p.get("last_action"),
            "key_drivers": rating_p.get("key_rating_drivers", []),
            "upgrade_trigger": _safe_get(rating_p, "rating_sensitivity", "upgrade"),
            "downgrade_trigger": _safe_get(rating_p, "rating_sensitivity", "downgrade"),
        },
        "crilc": {
            "aggregate_exposure_cr": crilc_p.get("aggregate_exposure_cr"),
            "fund_based_cr": crilc_p.get("fund_based_cr"),
            "non_fund_cr": crilc_p.get("non_fund_based_cr"),
            "sma_status": crilc_p.get("sma_status"),
            "restructured": crilc_p.get("restructured"),
        },
        "charges": {
            "total": charges_payload.get("total_charges", 0),
            "open": charges_payload.get("open_charges", 0),
            "satisfied": charges_payload.get("satisfied_charges", 0),
            "details": charges_payload.get("charges", []),
        },
    }

    # If case was run, add policy scores
    if case_result:
        credit_risk["policy"] = {
            "composite_score": case_result.get("composite_score"),
            "risk_grade": case_result.get("risk_grade"),
            "recommendation": case_result.get("recommendation"),
            "financial_score": case_result.get("financial_score"),
            "conduct_score": case_result.get("conduct_score"),
            "governance_score": case_result.get("governance_score"),
            "market_score": case_result.get("market_score"),
        }

    # ════════════════════════════════════════════════════════════
    # 4. MARKET INTELLIGENCE
    # ════════════════════════════════════════════════════════════
    market_intel = _build_market_intelligence(overview, case_result, market_p, rating_p)

    # ════════════════════════════════════════════════════════════
    # 5. COMPLIANCE & DOCUMENT STATUS
    # ════════════════════════════════════════════════════════════
    compliance = {
        "mca_filing": mca_p.get("compliance_status", {}),
        "gst_compliance": gst_p.get("compliance", {}) or {
            "filing_status": gst_p.get("filing_status"),
            "pending_returns": gst_p.get("pending_returns"),
            "last_return_filed": gst_p.get("last_return_filed"),
        },
        "epfo_status": epfo_p.get("compliance_status"),
        "itr_filing": {
            "assessment_year": itr_p.get("assessment_year"),
            "status": itr_p.get("filing_status"),
            "outstanding_demand": itr_p.get("outstanding_demand_cr"),
        },
    }

    # Document completeness from doc store
    try:
        docs = doc_store.list_company_documents(entity_id)
        compliance["documents"] = docs
    except Exception:
        compliance["documents"] = {"status": "no_documents"}

    # ════════════════════════════════════════════════════════════
    # 6. SELL-SIDE PERSPECTIVE
    # ════════════════════════════════════════════════════════════
    sell_side = _build_sell_perspective(
        entity_id, overview, financials, credit_risk, market_intel, case_result)

    # ════════════════════════════════════════════════════════════
    # 7. RED FLAGS & WATCH ITEMS
    # ════════════════════════════════════════════════════════════
    red_flags = _identify_red_flags(
        bureau_p, rating_p, market_intel, gst_p, epfo_p, itr_p, mca_p,
        case_result)

    # ════════════════════════════════════════════════════════════
    # 8. EXECUTIVE SUMMARY
    # ════════════════════════════════════════════════════════════
    summary = _build_executive_summary(
        overview, credit_risk, market_intel, sell_side, red_flags, case_result)

    return {
        "entity_id": entity_id,
        "generated_at": date.today().isoformat(),
        "overview": overview,
        "financials": financials,
        "credit_risk": credit_risk,
        "market_intelligence": market_intel,
        "compliance": compliance,
        "sell_perspective": sell_side,
        "red_flags": red_flags,
        "executive_summary": summary,
        # ── Additional 360° blocks from pipeline fact pack ──
        "banking_exposure": _extract_banking_exposure(case_result),
        "etb_conduct": _extract_etb_conduct(case_result),
        "collateral": _extract_collateral(case_result),
    }


def _build_sell_perspective(entity_id, overview, financials, credit_risk,
                            market_intel, case_result) -> dict:
    """
    Build sell-side analysis — deal attractiveness, pricing guidance,
    cross-sell opportunities, risk-adjusted returns.
    """
    perspective = {
        "deal_attractiveness": "medium",
        "pricing_guidance": {},
        "cross_sell_opportunities": [],
        "risk_reward_assessment": "",
        "relationship_value": "",
        "wallet_share_potential": {},
    }

    fact_pack = _fact_pack(case_result)
    facility_pricing = fact_pack.get("facility_pricing") or {}
    exposure_list = [item for item in fact_pack.get("existing_exposure", []) if isinstance(item, dict)]
    requested_amount = _safe_number(
        (case_result or {}).get("requested_amount_cr")
        or _safe_get(fact_pack, "facility_details", "amount_requested_cr")
    )
    total_sanctioned = round(sum(_safe_number(item.get("sanctioned_cr")) for item in exposure_list), 1)
    total_outstanding = round(sum(_safe_number(item.get("outstanding_cr")) for item in exposure_list), 1)
    facility_count = len(exposure_list)
    explicit_lenders = {
        str(item.get("lender_name")).strip()
        for item in exposure_list
        if item.get("lender_name")
    }
    lender_count = len(explicit_lenders) if explicit_lenders else facility_count

    latest_metrics = financials.get("key_metrics", {}) or {}
    revenue_cr = _safe_number(latest_metrics.get("revenue_cr"))
    employee_count = _safe_number(overview.get("employee_count"))
    sector_text = str(overview.get("industrial_class") or "").lower()

    # Determine deal attractiveness from risk grade
    grade = case_result.get("risk_grade", "C") if case_result else "C"
    score = case_result.get("composite_score", 50) if case_result else 50

    if grade == "A":
        perspective["deal_attractiveness"] = "high"
        base_spread = 100  # bps over repo
        perspective["risk_reward_assessment"] = (
            "Excellent risk-reward profile. Low probability of default with strong financials. "
            "Pricing can be competitive to win/retain the relationship."
        )
    elif grade == "B":
        perspective["deal_attractiveness"] = "medium-high"
        base_spread = 175
        perspective["risk_reward_assessment"] = (
            "Good risk-reward with manageable conditions. Standard pricing with covenants. "
            "Potential for relationship deepening with performance."
        )
    elif grade == "C":
        perspective["deal_attractiveness"] = "medium"
        base_spread = 275
        perspective["risk_reward_assessment"] = (
            "Moderate risk-reward. Higher pricing needed to compensate for risk. "
            "Requires strong collateral and financial covenants."
        )
    elif grade == "D":
        perspective["deal_attractiveness"] = "low"
        base_spread = 450
        perspective["risk_reward_assessment"] = (
            "Weak risk-reward. Only proceed if strong collateral + promoter backing. "
            "Premium pricing required with quarterly monitoring."
        )
    else:
        perspective["deal_attractiveness"] = "not_recommended"
        base_spread = 0
        perspective["risk_reward_assessment"] = "Not recommended for lending."

    # Pricing guidance uses the case proposal when available, with policy guidance alongside it.
    repo_rate = 6.50  # current RBI repo (illustrative)
    quoted_rate_pct = _parse_percent(facility_pricing.get("interest_rate"))
    quoted_processing_fee_pct = _parse_percent(facility_pricing.get("processing_fee"))
    perspective["pricing_guidance"] = {
        "repo_rate_pct": repo_rate,
        "base_spread_bps": base_spread,
        "suggested_rate_pct": round(repo_rate + base_spread / 100, 2),
        "current_case_rate_pct": quoted_rate_pct,
        "current_case_rate_text": facility_pricing.get("interest_rate"),
        "processing_fee_pct": quoted_processing_fee_pct if quoted_processing_fee_pct is not None else (0.50 if grade in ("A", "B") else 1.00),
        "processing_fee_text": facility_pricing.get("processing_fee"),
        "commitment_fee_bps": 25 if grade in ("A", "B") else 50,
        "commitment_charge_text": facility_pricing.get("commitment_charge"),
        "penal_interest_text": facility_pricing.get("penal_interest"),
    }
    if quoted_rate_pct is not None:
        perspective["pricing_guidance"]["pricing_gap_bps"] = round(
            (perspective["pricing_guidance"]["suggested_rate_pct"] - quoted_rate_pct) * 100,
            0,
        )

    # Cross-sell opportunities
    cross_sell = []
    base_wallet = max(requested_amount, total_outstanding, total_sanctioned * 0.4)
    if requested_amount or total_sanctioned:
        cross_sell.append({
            "product": "Cash Management Services",
            "potential_cr": round(max(base_wallet * 0.08, 25.0), 1),
            "rationale": "Collections, payment rails, and escrow operating flows can deepen the primary relationship.",
        })
    if employee_count >= 2000:
        cross_sell.append({
            "product": "Salary Accounts (CASA)",
            "potential_cr": round(min(max(employee_count / 10000 * 5, 5), 30), 1),
            "rationale": f"Large employee base (~{int(employee_count):,}) supports payroll banking and retail cross-sell.",
        })
    if any(token in sector_text for token in ("technology", "it", "software")):
        cross_sell.append({
            "product": "FX & Treasury Solutions",
            "potential_cr": round(max(requested_amount * 0.06, 20.0), 1),
            "rationale": "Global delivery and cross-border client receipts support hedging and treasury products.",
        })
    if requested_amount or total_outstanding:
        cross_sell.append({
            "product": "Trade / Supply Chain Solutions",
            "potential_cr": round(max(requested_amount * 0.05, 15.0), 1),
            "rationale": "Vendor financing, collections, and supply-chain programs can expand wallet share beyond the lead facility.",
        })
    if not cross_sell:
        cross_sell.append({
        "product": "Cash Management Services",
        "potential_cr": round(max(requested_amount * 0.05, 10.0), 1),
        "rationale": "Base fee-income opportunity on transaction banking."
        })
    perspective["cross_sell_opportunities"] = cross_sell

    # Relationship value
    if total_sanctioned >= 2000 or requested_amount >= 500 or employee_count >= 50000 or revenue_cr >= 100000:
        perspective["relationship_value"] = "Strategic large-corporate relationship with treasury, fee, and board-level wallet potential"
    elif total_sanctioned >= 500 or requested_amount >= 100 or employee_count >= 5000:
        perspective["relationship_value"] = "Core mid-corporate relationship with cross-sell and operating-account deepening potential"
    else:
        perspective["relationship_value"] = "Emerging relationship requiring focused wallet build-up through operating flows"

    # Wallet share should come from case exposure data before any public proxy.
    incremental_wallet = min(total_sanctioned * 0.08, requested_amount * 0.5) if total_sanctioned and requested_amount else 0
    target_wallet = round(requested_amount + incremental_wallet, 1) if requested_amount else round(total_sanctioned * 0.15, 1)
    avg_wallet = round(total_sanctioned / lender_count, 1) if lender_count else 0
    fee_income_lakhs = round(
        target_wallet * (perspective["pricing_guidance"]["processing_fee_pct"] or 0) * 100 / 100,
        1,
    )
    perspective["wallet_share_potential"] = {
        "total_banking_exposure_cr": total_sanctioned,
        "current_outstanding_cr": total_outstanding,
        "lender_count": lender_count,
        "avg_per_lender_cr": avg_wallet,
        "target_wallet_cr": target_wallet,
        "potential_fee_income_lakhs": fee_income_lakhs,
    }

    top_strength = next(
        (item.get("detail") for item in fact_pack.get("credit_strengths", []) if isinstance(item, dict) and item.get("detail")),
        None,
    )
    top_risk = next(
        (item.get("detail") for item in fact_pack.get("key_risks", []) if isinstance(item, dict) and item.get("detail")),
        None,
    )
    stance = market_intel.get("summary", {}).get("stance") or market_intel.get("sentiment", {}).get("overall")
    pricing_note = perspective["pricing_guidance"].get("current_case_rate_text")
    perspective["risk_reward_assessment"] = (
        f"{perspective['deal_attractiveness'].replace('-', ' ').title()} risk-reward profile. "
        f"Market stance: {stance or 'not assessed'}. "
        f"{top_strength + '. ' if top_strength else ''}"
        f"{'Key watch item: ' + top_risk + '. ' if top_risk else ''}"
        f"{'Current proposal pricing: ' + pricing_note + '. ' if pricing_note else ''}"
        f"Target wallet: ₹{target_wallet:,.1f} Cr."
    )

    return perspective


def _identify_red_flags(bureau_p, rating_p, market_intel, gst_p, epfo_p,
                        itr_p, mca_p, case_result) -> list:
    """Identify red flags and watch items across all data sources."""
    flags = []
    fact_pack = _fact_pack(case_result)

    # Public-record stress flags
    max_dpd = bureau_p.get("max_dpd_last_12m") or 0
    if max_dpd > 30:
        flags.append({
            "severity": "high",
            "category": "credit",
            "flag": f"DPD > 30 days in last 12 months (max: {max_dpd}d)",
            "source": "public_records",
        })
    enquiries_last_6m = bureau_p.get("enquiries_last_6m") or 0
    if enquiries_last_6m > 6:
        flags.append({
            "severity": "medium",
            "category": "credit",
            "flag": f"High enquiry count: {enquiries_last_6m} in 6 months (funding stress signal)",
            "source": "public_records",
        })
    if bureau_p.get("dpd_status") in ("SMA-1", "SMA-2"):
        flags.append({
            "severity": "high",
            "category": "credit",
            "flag": f"SMA status: {bureau_p['dpd_status']} — early stress indicator",
            "source": "public_records",
        })

    # Rating red flags
    outlook = rating_p.get("outlook", "")
    if "Negative" in outlook or "Watch" in outlook:
        flags.append({
            "severity": "high",
            "category": "rating",
            "flag": f"Rating on {outlook} — potential downgrade risk",
            "source": "ratings",
        })
    # Check for recent downgrade
    history = rating_p.get("history", [])
    if history and history[0].get("action") in ("Downgraded", "Watch Negative"):
        flags.append({
            "severity": "medium",
            "category": "rating",
            "flag": f"Recent rating action: {history[0]['action']} on {history[0].get('date') or history[0].get('rating_date')}",
            "source": "ratings",
        })

    # Case-level exceptions and market/watch signals
    if case_result:
        flags.extend(_aggregate_validation_flags(case_result.get("exceptions", [])))

    for risk in fact_pack.get("key_risks", []):
        if not isinstance(risk, dict):
            continue
        severity = str(risk.get("severity") or "medium").lower()
        if severity not in ("high", "critical"):
            continue
        category = str(risk.get("category") or "risk").lower()
        if category == "validation":
            continue
        flags.append({
            "severity": severity,
            "category": category,
            "flag": risk.get("detail"),
            "source": "case_fact_pack",
        })

    for signal in market_intel.get("signals", []):
        if not isinstance(signal, dict):
            continue
        severity = str(signal.get("severity") or "low").lower()
        sentiment = str(signal.get("sentiment") or "").lower()
        if sentiment != "negative" or severity not in ("medium", "high", "critical"):
            continue
        flags.append({
            "severity": severity,
            "category": signal.get("type") or "market",
            "flag": signal.get("headline"),
            "source": signal.get("source") or "market_signals",
            "detail": signal.get("details"),
        })

    # GST red flags
    pending = gst_p.get("pending_returns")
    if pending is None:
        pending = gst_p.get("compliance", {}).get("pending_returns", 0)
    if pending and pending > 0:
        flags.append({
            "severity": "medium",
            "category": "compliance",
            "flag": f"{pending} GST returns pending — compliance concern",
            "source": "gst",
        })
    gst3b_pct = gst_p.get("compliance", {}).get("gstr3b_filed_on_time_pct")
    if gst3b_pct and gst3b_pct < 80:
        flags.append({
            "severity": "medium",
            "category": "compliance",
            "flag": f"GST-3B on-time filing only {gst3b_pct}% — poor compliance",
            "source": "gst",
        })

    # EPFO red flags
    pending_challan = epfo_p.get("pending_challan") or 0
    if pending_challan > 0:
        flags.append({
            "severity": "medium",
            "category": "compliance",
            "flag": f"EPFO: {pending_challan} months challan pending",
            "source": "epfo",
        })

    # ITR red flags
    outstanding_demand = itr_p.get("outstanding_demand_cr") or 0
    if outstanding_demand > 0:
        flags.append({
            "severity": "medium",
            "category": "tax",
            "flag": f"Outstanding IT demand: ₹{outstanding_demand} Cr",
            "source": "income_tax",
        })
    if "belated" in str(itr_p.get("filing_status", "")).lower():
        flags.append({
            "severity": "low",
            "category": "compliance",
            "flag": "ITR filed after due date (belated)",
            "source": "income_tax",
        })

    # MCA compliance
    charges_open = mca_p.get("compliance_status", {}).get("charges_open") or 0
    if charges_open and charges_open > 3:
        flags.append({
            "severity": "low",
            "category": "leverage",
            "flag": f"{charges_open} open charges registered — multi-bank lending",
            "source": "mca",
        })

    if case_result and case_result.get("financial_score", 100) < 50:
        flags.append({
            "severity": "high",
            "category": "financial",
            "flag": f"Low financial score: {case_result['financial_score']}",
            "source": "policy_engine",
        })

    deduped: list[dict] = []
    seen = set()
    for flag in flags:
        signature = (
            str(flag.get("severity") or "").lower(),
            str(flag.get("category") or "").lower(),
            str(flag.get("flag") or "").strip().lower(),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(flag)

    return sorted(deduped, key=lambda f: (_severity_rank(f.get("severity")), f.get("category") or ""))


def _build_executive_summary(overview, credit_risk, market_intel,
                             sell_side, red_flags, case_result) -> dict:
    """Build executive summary combining all sections."""
    high_flags = [f for f in red_flags if f["severity"] in ("critical", "high")]
    fact_pack = _fact_pack(case_result)
    strengths = [item for item in fact_pack.get("credit_strengths", []) if isinstance(item, dict)]
    key_strength = strengths[0].get("detail") if strengths else None
    market_summary = market_intel.get("summary", {}) or {}

    summary = {
        "company": overview.get("company_name", "Unknown"),
        "sector": overview.get("industrial_class", "Unknown"),
        "deal_attractiveness": sell_side.get("deal_attractiveness"),
        "suggested_rate": sell_side.get("pricing_guidance", {}).get("suggested_rate_pct"),
        "red_flag_count": len(red_flags),
        "high_severity_flags": len(high_flags),
        "cross_sell_count": len(sell_side.get("cross_sell_opportunities", [])),
    }

    if case_result:
        summary["risk_grade"] = case_result.get("risk_grade")
        summary["composite_score"] = case_result.get("composite_score")
        summary["recommendation"] = case_result.get("recommendation")

    # Generate narrative summary
    grade = summary.get("risk_grade", "N/A")
    attractiveness = sell_side.get("deal_attractiveness", "unknown")
    rating_lt = credit_risk.get("rating", {}).get("long_term", "NR")
    company_descriptor = (
        "listed company"
        if str(overview.get("listing_status") or "").strip()
        else (str(overview.get("company_class") or "").lower() + " company").strip()
    )
    watch_items = market_summary.get("watch_items", 0)
    requested_amount = _safe_number((case_result or {}).get("requested_amount_cr"))
    facility_type = str((case_result or {}).get("facility_type") or "facility").replace("_", " ")

    summary["narrative"] = (
        f"{overview.get('company_name')} is a {company_descriptor} incorporated in "
        f"{overview.get('registered_state', 'India')}, operating in {overview.get('industrial_class', 'N/A')}. "
        f"The current proposal is ₹{requested_amount:,.1f} Cr of {facility_type} with case recommendation "
        f"{str(summary.get('recommendation') or 'under review').upper()} and risk grade {grade}. "
        f"External rating stands at {rating_lt}; open charges are {credit_risk.get('charges', {}).get('open', 'N/A')}. "
        f"Market stance is {str(market_summary.get('stance') or 'not assessed').lower()} "
        f"with {watch_items} watch item(s). "
        f"{key_strength + '. ' if key_strength else ''}"
        f"{str(len(high_flags)) + ' high-severity red flag(s) remain open. ' if high_flags else ''}"
        f"Sell-side attractiveness is {attractiveness}, with guided pricing around {summary.get('suggested_rate', 'N/A')}% p.a."
    )

    return summary


def _extract_banking_exposure(case_result: dict) -> dict:
    """Extract banking & debt exposure from pipeline fact pack."""
    if not case_result:
        return {}
    fp = _fact_pack(case_result)
    exposure_list = fp.get("existing_exposure", [])
    if isinstance(exposure_list, dict):
        exposure_list = exposure_list.get("existing_limits", [])
    fin_sum = fp.get("financial_summary", {})
    facility = fp.get("facility_details", {})
    latest_period, latest_metrics = _latest_financial_period(fin_sum)
    ratio_analysis = fp.get("ratio_analysis", {})
    latest_ratios = ratio_analysis.get(latest_period, {}) if latest_period else {}
    total_existing = sum(e.get("sanctioned_cr", 0) for e in exposure_list) if exposure_list else 0
    total_debt = _safe_number(latest_metrics.get("total_debt_cr") or latest_metrics.get("total_debt"))
    net_worth = _safe_number(
        latest_metrics.get("net_worth_cr")
        or latest_metrics.get("net_worth")
        or latest_metrics.get("total_equity_cr")
    )
    debt_equity = _safe_number(_safe_get(latest_ratios, "debt_to_equity", "value", default=None), default=None)
    if debt_equity is None and net_worth:
        debt_equity = round(total_debt / net_worth, 2)
    return {
        "existing_limits": exposure_list,
        "total_existing_cr": total_existing,
        "proposed_facility": facility,
        "total_debt_cr": total_debt,
        "net_worth_cr": net_worth,
        "debt_equity": debt_equity or 0,
    }


def _extract_etb_conduct(case_result: dict) -> dict:
    """Extract ETB conduct & behavioral data from pipeline fact pack."""
    if not case_result:
        return {}
    fp = case_result.get("fact_pack", {})
    return fp.get("conduct_analysis", {})


def _extract_collateral(case_result: dict) -> dict:
    """Extract collateral & security data from pipeline fact pack."""
    if not case_result:
        return {}
    fp = case_result.get("fact_pack", {})
    return fp.get("collateral_analysis", {})
