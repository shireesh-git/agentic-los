"""
Data provenance for the CAM fact pack.

Every fact-pack section is classed so that the narrative, the final CAM and a
reviewer can tell borrower facts from calculations, rules, demo data and gaps:

  source          borrower / source data (statements, documents, the borrower record)
  external        external verified data (public-record payloads fetched from a verified provider)
  calculated      deterministic calculation by an engine (ratios, growth, coverage, stress)
  derived         rule-based analysis (validations, policy, strengths/risks, M1–M6)
  synthetic_demo  intentional synthetic demo data — not verified external evidence
  template        reference or template text (sector descriptions, pricing grid)
  unavailable     not available from any verified source
"""

from __future__ import annotations

# The wording used wherever evidence for a fact is absent.
NOT_AVAILABLE = "Not available from submitted information"
NOT_VERIFIED = "Not verified"

CLASS_LABELS = {
    "source": "Borrower / source data",
    "external": "External verified data",
    "calculated": "Deterministic calculation",
    "derived": "Rule-based analysis",
    "synthetic_demo": "Synthetic demo data (not verified)",
    "template": "Reference / template text",
    "unavailable": "Not available",
    "ai": "AI interpretation",
}

# Sections whose class does not depend on the borrower.
_STATIC = {
    "meta": "derived", "case_summary": "source", "facility_details": "source", "facility_pricing": "template",
    "ratio_analysis": "calculated", "benchmark_summary": "calculated", "drawing_power": "calculated",
    "debt_capacity": "calculated", "earnings_quality": "calculated", "revenue_truth": "calculated",
    "ews_indicators": "derived",
    "cash_flow_repayment": "calculated", "financial_projections": "calculated", "policy_thresholds": "template",
    "validation_exceptions": "derived", "policy_decisions": "derived", "approving_authority": "derived",
    "credit_strengths": "derived", "key_risks": "derived", "compliance_checks": "derived",
    "industry_analysis": "template", "esg_regulatory": "derived", "data_sources": "derived",
    "quarterly_performance": "calculated", "pep_screening": "derived", "corporate_hierarchy": "source",
    "document_extraction": "source", "document_verification": "source", "downloaded_annual_reports": "source",
}

# Sections that come from the borrower record; synthetic for a demo borrower.
_BORROWER_RECORD = {"borrower_profile", "group_profile", "management_profile", "existing_exposure",
                    "financial_summary", "collateral_analysis", "conduct_analysis", "covenant_history",
                    "infra_metrics", "sector_kpis", "site_visit_data", "valuation_report_data",
                    "bank_statement_analysis", "charges_data", "financial_data_strategy"}

_NOTES = {
    "pep_screening": "screened against an in-code reference list, not an external screening service",
    "industry_analysis": "in-code sector description",
    "facility_pricing": "in-code pricing grid",
    "policy_thresholds": "bank policy limits from config/rules.yaml",
    "drawing_power": "receivable ageing not available: all trade receivables counted",
}


def _empty(value) -> bool:
    if value in (None, "", [], {}):
        return True
    if isinstance(value, dict):
        if value.get("available") is False:
            return True
        return all(_empty(v) for v in value.values())
    return False


# The bank's own records about the borrower: demo stand-ins while no core-banking / LMS / DMS system is connected
# (config data_sources.yaml → demo_data.enabled), whatever the borrower (round 9: never shown as source data).
_BANK_INTERNAL = {"existing_exposure", "conduct_analysis", "covenant_history", "collateral_analysis",
                  "core_banking", "core_banking_analysis", "charges_data", "site_visit_data", "valuation_report_data",
                  "bank_statement_analysis"}


def _demo_external(company_data: dict) -> bool:
    """Whether the bureau / MCA / GST payloads came from a demo registry file, not a live API."""
    ext = company_data.get("external_data") or {}
    return any(isinstance(v, dict) and (v.get("demo") or (v.get("provenance") or {}).get("demo")
                                        or (v.get("provenance") or {}).get("via") == "demo_file")
               for k, v in ext.items() if k in ("bureau_data", "mca_data", "gst_data"))


def _bank_demo() -> bool:
    try:
        from src.core.config_manager import config
        return bool(config.get("data_sources", "demo_data", "enabled", default=False))
    except Exception:
        return True


def classify_fact_pack(fact_pack: dict, company_data: dict) -> dict:
    """{fact-pack key: {"class", "label", "note"}} for every section of the fact pack."""
    demo = (company_data.get("catalog_source") == "demo_catalog"
            or company_data.get("data_provider") == "synthetic_demo")
    bank_demo = _bank_demo()
    out = {}
    for key, value in fact_pack.items():
        if key == "data_provenance":
            continue
        note = _NOTES.get(key, "")
        if key in ("social_media_analysis", "social_media_cam_summary"):
            cls = "unavailable" if _empty(value) else "synthetic_demo"
            note = "no verified social-media source" if cls == "unavailable" else "in-code demo profile, not verified"
        elif key == "web_crawl_news":
            verified = isinstance(value, dict) and value.get("verified") and value.get("articles")
            cls = "source" if verified else "unavailable"
            note = "verified news feed" if verified else "no verified news source connected"
        elif key == "crilc_exposure":
            cls = "unavailable" if _empty(value) else "synthetic_demo"
            note = "" if cls == "unavailable" else "generated CRILC demo data, not an RBI CRILC extract"
        elif key in ("core_banking", "core_banking_analysis"):
            cls = "unavailable" if _empty(value) else ("synthetic_demo" if demo or company_data.get("etb_overlay")
                                                       else "source")
        elif key == "market_signals":
            # headlines from the live news feed (GDELT) are external; curated ones are demo, never verified news
            live = isinstance(value, list) and value and all(
                (s.get("source") if isinstance(s, dict) else getattr(s, "source_name", "")) in ("GDELT", "rating_agency")
                for s in value)
            cls = "unavailable" if _empty(value) else ("external" if live else "synthetic_demo")
            note = ("" if cls == "unavailable" else "live news feed (GDELT), screened for adverse items" if live
                    else "curated demo signals, not from a verified news feed")
        elif key == "external_intelligence":
            dem = demo or _demo_external(company_data)
            cls = "unavailable" if _empty(value) else ("synthetic_demo" if dem else "external")
            note = ("demo registry file standing in for the bureau / MCA / GST APIs" if dem
                    else "public-record payloads (bureau, GST, MCA)")
        elif key in _BANK_INTERNAL and bank_demo:
            cls = "unavailable" if _empty(value) else "synthetic_demo"
            note = "" if cls == "unavailable" else "the bank's own records: demo data, no core-banking system connected"
        elif key == "etb_behavioral_analytics":
            cls = "unavailable" if _empty(value) else "source"
        elif key in _BORROWER_RECORD:
            cls = "unavailable" if _empty(value) else ("synthetic_demo" if demo else "source")
            if key == "financial_summary" and cls == "source":
                note = "statements as reported; growth and margins calculated"
        else:
            cls = _STATIC.get(key, "derived")
            if cls == "source" and demo:
                cls = "synthetic_demo"
        out[key] = {"class": cls, "label": CLASS_LABELS[cls], "note": note}
    return out
