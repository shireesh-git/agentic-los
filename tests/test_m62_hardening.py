"""M6.2: seven-agent hardening — extraction, PEP, financial-analysis authority, validation documents,
overrides integrity, narrative boundary, provenance and no fabricated external intelligence."""

import copy
import json

import pytest

from src.data.company_catalog import seed_company_store
from src.engines.cam_fact_builder import build_cam_fact_pack

CASE = "ABCE001"


@pytest.fixture(scope="module")
def company():
    return seed_company_store()[CASE]


# ─── Data ingestion ──────────────────────────────────────────────────────────

def test_one_failing_extractor_does_not_abort_the_case(tmp_path):
    from src.services.document_extractor import _cached_extract

    def broken(_path):
        raise ValueError("openpyxl does not support .pdf file format")

    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-1.4")
    out = _cached_extract(broken, f)
    assert "broken" in out["error"] and out["source_file"].endswith("x.pdf")


def test_pdf_unaudited_results_are_not_sent_to_the_excel_reader(tmp_path, monkeypatch):
    from src.services import document_extractor as de

    (tmp_path / "E1" / "financials").mkdir(parents=True)
    (tmp_path / "E1" / "financials" / "unaudited_results_fy2026.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(de, "extract_provisional_financials", lambda p: pytest.fail("Excel reader called for a PDF"))
    monkeypatch.setattr(de, "extract_financials_from_pdf", lambda p: {"data": {"revenue": [100.0]}})
    monkeypatch.setattr(de, "find_best_document",
                        lambda d, c, role: (tmp_path / "E1" / "financials" / "unaudited_results_fy2026.pdf")
                        if role == "provisional_financials" else None)
    out = de.extract_all_documents("E1", tmp_path)
    assert out["provisional"] == {}
    assert out["unaudited_results"]["data"] == {"revenue": [100.0]}
    assert "not used to override" in out["unaudited_results"]["status"]


def test_document_inventory_from_disk_and_demo_declaration(tmp_path, monkeypatch, company):
    from src.agents import ingestion_agent

    monkeypatch.setattr(ingestion_agent, "DOCUMENTS_ROOT", tmp_path)
    (tmp_path / "E2" / "kyc").mkdir(parents=True)
    (tmp_path / "E2" / "kyc" / "pan_card.pdf").write_bytes(b"x")
    inv = ingestion_agent.DataIngestionAgent._document_inventory("E2", {})
    assert inv["has_kyc"] and not inv["has_board_resolution"] and not inv["has_collateral_docs"]
    demo = ingestion_agent.DataIngestionAgent._document_inventory("NOFILES", company)
    assert demo["has_kyc"] and "synthetic demo" in demo["source"]


# ─── Overrides integrity ─────────────────────────────────────────────────────

def test_wrong_year_and_inconsistent_overrides_are_skipped(company):
    from src.agents.financial_overrides import apply_uploaded_financial_overrides

    cd = copy.deepcopy(company)
    original = copy.deepcopy(cd["financials"]["FY2026"].line_items)
    wrong_year = {"selected_documents": {"audited_financials": "annual_report_fy2024.pdf"},
                  "financials": {"audited": {"revenue": [999.0]}}}
    apply_uploaded_financial_overrides(cd, wrong_year)
    assert cd["financials"]["FY2026"].line_items == original

    noisy = {"selected_documents": {"audited_financials": "audited_financial_statements.pdf"},
             "financials": {"audited": {"ebitda": [9999.0]}}}         # would break EBITDA reconciliation
    apply_uploaded_financial_overrides(cd, noisy)
    assert cd["financials"]["FY2026"].line_items == original


# ─── PEP / validation ────────────────────────────────────────────────────────

def test_pep_message_reports_real_hits(company):
    from src.agents.screening_agent import PEPScreeningAgent
    from src.models.canonical_model import DirectorPromoter

    cd = copy.deepcopy(company)
    cd["directors"].append(DirectorPromoter(din="00012345", name="Sample", designation="Director", entity_id=CASE))
    messages = []
    PEPScreeningAgent().run({"company_data": cd, "_on_progress": lambda e: messages.append(e["message"])})
    assert any("1 hit(s)" in m for m in messages)


def test_ntb_document_checks_use_the_inventory(company):
    from src.engines.validation_engine import run_all_validations

    def codes(inventory):
        return {e.exception_code for e in run_all_validations(
            company["borrower"], company["financials"], document_inventory=inventory)}

    assert "POL_MISSING_KYC" in codes({"has_kyc": False, "has_board_resolution": True, "has_collateral_docs": True})
    assert not {c for c in codes(None) if c.startswith("POL_MISSING") and c != "POL_MISSING_3YR_AUDITED"}


# ─── Financial analysis authority / narrative boundary ───────────────────────

def test_growth_metrics_are_deterministic(company):
    from src.engines.ratio_engine import compute_growth_metrics
    g = compute_growth_metrics(company["financials"])
    fy26 = g["by_period"]["FY2026"]
    assert (fy26["revenue_yoy_pct"], fy26["receivables_yoy_pct"], fy26["ocf_yoy_pct"]) == (18.2, 52.1, -76.3)
    assert fy26["ocf_to_pat"] == 0.51 and g["revenue_cagr_pct"] == 12.8


def test_fact_pack_uses_financial_analysis_output(company):
    from src.engines.ratio_engine import compute_growth_metrics, compute_multi_period_ratios

    ratios = compute_multi_period_ratios(company["financials"])
    ratios["FY2026"][0].value = 123.45            # marker: proves the given ratios are used, not recomputed
    growth = compute_growth_metrics(company["financials"])
    fp = build_cam_fact_pack(copy.deepcopy(company),
                             financial_analysis={"multi_period_ratios": ratios, "growth_metrics": growth})
    assert fp["ratio_analysis"]["FY2026"][ratios["FY2026"][0].ratio_name]["value"] == 123.45
    assert fp["financial_summary"]["growth_by_period"] == growth["by_period"]


# ─── Mock data integrity ─────────────────────────────────────────────────────

def test_no_fabricated_news_or_default_social_profile(company):
    fp = build_cam_fact_pack(copy.deepcopy(company))
    assert fp["web_crawl_news"]["available"] is False and fp["web_crawl_news"]["articles"] == []
    assert fp["social_media_analysis"] == {} and fp["social_media_cam_summary"] == ""
    text = json.dumps(fp, default=str)
    assert "wins NHAI highway project" not in text and "receives rating upgrade" not in text
    prov = fp["data_provenance"]
    assert prov["web_crawl_news"]["class"] == "unavailable" and prov["social_media_analysis"]["class"] == "unavailable"
    assert prov["financial_summary"]["class"] == "synthetic_demo"          # demo borrower
    assert prov["ratio_analysis"]["class"] == "calculated"


def test_demo_social_profile_is_labelled_synthetic():
    company = seed_company_store()["IHCL001"]
    fp = build_cam_fact_pack(copy.deepcopy(company))
    assert fp["social_media_analysis"]["data_provenance"].startswith("synthetic_demo")
    assert fp["data_provenance"]["social_media_analysis"]["class"] == "synthetic_demo"


def test_prompts_carry_provenance_and_ask_for_no_calculation(company):
    from src.devtools.agent_harness import _prompts_asking_to_compute
    from src.engines.cam_llm_renderer import CAM_SECTIONS, SYSTEM_PROMPT, _section_prompt

    fp = build_cam_fact_pack(copy.deepcopy(company))
    section = next(s for s in CAM_SECTIONS if s["id"] == "financial_analysis")
    prompt, data_json = _section_prompt(section, fp)
    data = json.loads(data_json)
    assert set(data["ratio_analysis"]) == {"values_by_period", "formulas"}     # formulas sent once
    assert "_provenance" in data and "growth_by_period" in data["financial_summary"]
    assert "DATA PROVENANCE" in SYSTEM_PROMPT
    assert _prompts_asking_to_compute() == []
