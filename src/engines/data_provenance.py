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


def classify_fact_pack(fact_pack: dict, company_data: dict) -> dict:
    """{fact-pack key: {"class", "label", "note"}} for every section of the fact pack."""
    demo = (company_data.get("catalog_source") == "demo_catalog"
            or company_data.get("data_provider") == "synthetic_demo")
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
            # In-code curated headlines (no feed, no URL): kept for testing, never shown as verified news.
            cls = "unavailable" if _empty(value) else "synthetic_demo"
            note = "" if cls == "unavailable" else "curated in-code signals, not from a verified news feed"
        elif key == "external_intelligence":
            cls = "unavailable" if _empty(value) else ("synthetic_demo" if demo else "external")
            note = "demo fixture bureau / GST / MCA data" if demo else "public-record payloads (bureau, GST, MCA)"
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
