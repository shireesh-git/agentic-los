"""CAM data integrity: no template / assumed value is presented as borrower evidence.

Regression tests for: one EBITDA-margin source, evidence-based hard rules (KYC, MCA status), bureau status
mapping, the defaulted-sector override, template end use / ESG / industry figures, and the provenance of
curated market signals and demo external data.
"""

import copy
import dataclasses

import pytest

from src.data.company_catalog import seed_company_store
from src.engines.cam_fact_builder import build_cam_fact_pack, classify_bureau_status
from src.engines.data_provenance import NOT_AVAILABLE
from src.engines.policy_engine import RiskScore, tier1_hard_rules, tier3_recommendation
from src.engines.ratio_engine import as_pct, compute_all_ratios


@pytest.fixture(scope="module")
def store():
    return seed_company_store()


@pytest.fixture(scope="module")
def abce_fp(store):
    return build_cam_fact_pack(copy.deepcopy(store["ABCE001"]))


@pytest.fixture(scope="module")
def apol_fp(store):
    return build_cam_fact_pack(copy.deepcopy(store["APOL001"]))


# ─── One EBITDA margin, everywhere ───────────────────────────────────────────

def test_ebitda_margin_has_one_source_and_one_rounding(store, abce_fp):
    """ABCE001 FY2026: 268 / 2080 = 12.88%. Previously the ratio engine said 13.0% and the CAM 12.9%."""
    from src.application.case_service import build_case_result
    from src.engines.cam_llm_renderer import render_cam_template_only

    ratios = {r.ratio_name: r.value for r in compute_all_ratios(store["ABCE001"]["financials"]["FY2026"])}
    assert ratios["ebitda_margin"] == 0.1288                       # fractions kept to 4 decimals
    assert as_pct(ratios["ebitda_margin"]) == 12.9
    assert abce_fp["financial_summary"]["periods"]["FY2026"]["ebitda_margin_pct"] == 12.9
    assert abce_fp["ratio_analysis"]["FY2026"]["ebitda_margin"]["value"] == 0.1288

    narrative = {"fact_pack": abce_fp, "cam_text": render_cam_template_only(abce_fp), "narrative_mode": "template"}
    case = build_case_result("ABCE001", copy.deepcopy(store["ABCE001"]), {"results": {"narrative": narrative}}, [])
    base = next(s for s in case["stress_test"]["scenarios"] if s["scenario"] == "base")
    assert base["stressed_metrics"]["ebitda_margin_pct"] == 12.9
    sections = {s["id"]: s for s in case["final_cam"]["sections"]}
    tables = {t["title"]: t for t in sections["financials_repayment"]["tables"]}
    assert next(r for r in tables["Key financials"]["rows"] if r[0] == "EBITDA margin")[-1] == "12.9%"
    assert next(r for r in tables["Key ratios"]["rows"] if r[0] == "EBITDA margin")[2] == "12.9%"


# ─── Evidence-based hard rules ───────────────────────────────────────────────

def _rules(store, eid="APOL001", **kwargs):
    c = store[eid]
    return {d.rule_code: d for d in tier1_hard_rules(c["borrower"], c["facility"], [], {}, **kwargs)}


def test_kyc_is_never_passed_without_evidence(store):
    assert _rules(store)["HR_KYC_COMPLETE"].result == "not_verified"                  # no inventory
    missing = {"has_kyc": False, "kyc_files": [], "source": "storage/documents/X"}
    assert _rules(store, document_inventory=missing)["HR_KYC_COMPLETE"].result == "fail"
    declared = {"has_kyc": True, "kyc_files": [], "source": "synthetic demo fixture (declared documents, not files)"}
    assert _rules(store, document_inventory=declared)["HR_KYC_COMPLETE"].result == "not_verified"
    on_file = {"has_kyc": True, "kyc_files": ["pan_card.pdf"], "source": "storage/documents/X"}
    kyc = _rules(store, document_inventory=on_file)["HR_KYC_COMPLETE"]
    assert kyc.result == "pass" and "pan_card.pdf" in kyc.details


def test_company_active_needs_an_mca_status(store):
    assert _rules(store)["HR_COMPANY_ACTIVE"].result == "not_verified"
    assert _rules(store, mca_status="Unknown")["HR_COMPANY_ACTIVE"].result == "not_verified"
    assert _rules(store, mca_status="Active")["HR_COMPANY_ACTIVE"].result == "pass"
    assert _rules(store, mca_status="Strike Off")["HR_COMPANY_ACTIVE"].result == "fail"


def test_unverified_rule_blocks_approval(store):
    rules = list(_rules(store, mca_status="Active").values())           # KYC not verified
    strong = RiskScore(85, 85, 85, 85, 85, "A")
    rec = tier3_recommendation(rules, strong, [], store["APOL001"]["facility"], 2.0)
    assert rec.recommendation.value == "refer" and "HR_KYC_COMPLETE" in rec.rationale
    assert any(c.startswith("Evidence to be obtained and verified before sanction") for c in rec.conditions)


def test_unverified_rule_reaches_the_policy_observation(abce_fp):
    from src.engines.observation_engine import detect_observations
    fp = copy.deepcopy(abce_fp)
    fp["policy_decisions"]["tier1_hard_rules"] = [{"rule": "HR_KYC_COMPLETE", "result": "not_verified",
                                                    "description": "KYC", "details": "no inventory"}]
    obs = next(o for o in detect_observations(fp, "X") if o["trigger"]["rule_id"] == "POLICY_DEVIATION")
    assert obs["trigger"]["observed"]["unverified_hard_rules"] == ["HR_KYC_COMPLETE"]
    assert "not verified" in obs["summary"]


# ─── Bureau status ───────────────────────────────────────────────────────────

def test_bureau_standard_means_no_overdues(abce_fp):
    assert classify_bureau_status("Standard") == "clean" and classify_bureau_status("NIL") == "clean"
    assert classify_bureau_status("SMA-1") == "overdue"
    assert classify_bureau_status("SMA-2") == "adverse" and classify_bureau_status("Substandard") == "adverse"
    cc = abce_fp["compliance_checks"]
    item = next(i for i in cc["items"] if i["check"].startswith("Credit Bureau — Repayment"))
    assert item["status"] == "No Overdues (Standard)" and cc["bureau_clean"] is True
    assert not any(i["status"] == "Overdue Reported" for i in cc["items"])


def test_no_assumed_compliance_statuses(apol_fp):
    statuses = {i["check"]: i["status"] for i in apol_fp["compliance_checks"]["items"]}
    assert statuses["Wilful Defaulter (bureau flag)"] == "Not verified"                # no bureau payload
    assert "Clear" not in statuses.values() and "Compliant" not in statuses.values()
    assert apol_fp["compliance_checks"]["annual_return_filed"] is None


# ─── Template borrower data removed ──────────────────────────────────────────

def test_no_template_end_use_esg_or_industry_figures(apol_fp):
    pricing = apol_fp["facility_pricing"]
    assert pricing["end_use_details"] == [] and pricing["end_use_note"] == NOT_AVAILABLE
    esg = apol_fp["esg_regulatory"]
    assert esg["environmental"]["compliance_status"] is None and esg["regulatory"]["rbi_compliance"] is None
    assert esg["governance"]["board_composition"] is None and esg["regulatory"]["itr_filing"] is None
    ia = apol_fp["industry_analysis"]
    assert ia["revenue_segments"] == [] and ia["geographic_mix"] == [] and ia["swot"] == {}
    assert ia["business_description"] == "" and "revenue_cr" not in str(ia.get("sector_reference_segments"))


def test_template_cam_does_not_invent_values(apol_fp):
    from src.engines.cam_llm_renderer import render_cam_template_only
    text = render_cam_template_only(apol_fp)
    for phrase in ("Raw Material Purchase", "Machinery & Equipment", "Not listed", "board_composition: Adequate",
                   "significant contributor to the country's GDP"):
        assert phrase not in text, phrase
    assert NOT_AVAILABLE in text


def test_curated_signals_and_demo_external_data_are_not_verified_evidence(apol_fp, abce_fp):
    assert apol_fp["data_provenance"]["market_signals"]["class"] == "synthetic_demo"
    assert abce_fp["data_provenance"]["market_signals"]["class"] == "synthetic_demo"
    assert abce_fp["data_provenance"]["external_intelligence"]["class"] == "synthetic_demo"
    assert abce_fp["data_provenance"]["web_crawl_news"]["class"] == "unavailable"


# ─── Sector: a default guess never overrides curated master data ────────────

def test_defaulted_sector_does_not_override_curated_sector(store):
    from src.application.company_service import merge_overlay_company_data, restore_curated_sector
    from src.models.canonical_model import Sector
    from src.services.probe_service import _infer_sector_from_text

    assert _infer_sector_from_text(None) == (Sector.MANUFACTURING, "default")
    assert _infer_sector_from_text("Hospital services") == (Sector.HEALTHCARE, "industry_text")

    seed = store["APOL001"]
    guessed = dataclasses.replace(seed["borrower"], sector=Sector.MANUFACTURING, subsector="manufacturing")
    merged = merge_overlay_company_data(seed, {"borrower": guessed, "sector_basis": "default"})
    assert merged["borrower"].sector == Sector.HEALTHCARE and merged["borrower"].subsector == "Hospitals & Health Services"

    stored = {"borrower": guessed}                                     # saved before sector_basis existed
    assert restore_curated_sector(seed, stored) is True
    assert stored["borrower"].sector == Sector.HEALTHCARE and stored["sector_basis"] == "reference_catalog"
    assert restore_curated_sector(seed, stored) is False                # idempotent

    matched = {"borrower": guessed, "sector_basis": "industry_text"}    # a real match is respected
    assert restore_curated_sector(seed, matched) is False


def test_apol001_benchmarks_against_healthcare(apol_fp):
    assert apol_fp["case_summary"]["sector"] == "healthcare"
    assert apol_fp["benchmark_summary"]["sector"] in ("healthcare", "hospitals_healthcare")


def test_bureau_rules_need_the_bureau_field(store):
    """A missing bureau report, or a report without the field, is not verified — never a default pass."""
    bureau_rules = ("HR_WILFUL_DEFAULTER", "HR_BUREAU_STATUS", "HR_FRAUD_REGISTRY", "HR_RBI_DEFAULTER", "HR_SUIT_FILED")
    none = _rules(store)
    assert all(none[code].result == "not_verified" for code in bureau_rules)

    report = {"payload": {"wilful_defaulter": False, "dpd_status": "Standard", "suit_filed_amount_cr": 0.0,
                          "total_exposure_cr": 100.0}}
    c = store["APOL001"]
    partial = {d.rule_code: d.result for d in tier1_hard_rules(c["borrower"], c["facility"], [], report)}
    assert partial["HR_WILFUL_DEFAULTER"] == partial["HR_BUREAU_STATUS"] == partial["HR_SUIT_FILED"] == "pass"
    assert partial["HR_FRAUD_REGISTRY"] == partial["HR_RBI_DEFAULTER"] == "not_verified"     # fields not stated

    adverse = {"payload": {**report["payload"], "dpd_status": "SMA-2", "suit_filed_amount_cr": 40.0,
                           "fraud_flag": True, "rbi_defaulter_list": False}}
    bad = {d.rule_code: d.result for d in tier1_hard_rules(c["borrower"], c["facility"], [], adverse)}
    assert bad["HR_BUREAU_STATUS"] == bad["HR_SUIT_FILED"] == bad["HR_FRAUD_REGISTRY"] == "fail"
    assert bad["HR_RBI_DEFAULTER"] == "pass"
