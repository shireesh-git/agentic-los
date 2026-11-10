"""Fix list round 7 (new-to-bank prospects Transport Corporation of India, KPI Green Energy, H.G. Infra): the statement
and rating readers on real annual reports, the notes reader's clean-opinion wording, the CAM intake agent's
financial-highlights table, an ingested CAM measured on the audited statements, and the RM's explanation of a
verification difference."""

import pytest

from src.application.container import build_container
from src.engines import notes_reader as nr
from src.flow import cam_intake
from src.flow.acquire import readers

E = "INFY001"


# ── readers ──────────────────────────────────────────────────────────────────

def test_units_in_million_and_abbreviations_are_recognised():
    assert readers._unit("All amounts in ₹ million unless otherwise stated") == ("million", readers._unit("million")[1])
    assert readers._unit("(₹ in Mn)")[0] == "million"
    assert readers._unit("(Rs. in lacs)")[0] == "lakh"
    assert readers._unit("(₹ in Cr)")[0] == "crore"


def test_a_care_rationale_is_read_from_its_facility_table():
    page = ("Press Release H.G. Infra Engineering Limited September 03, 2026 Ratings Facilities/Instruments "
            "Amount (₹ crore) Rating1 Rating Action Long-term bank facilities 40.00 CARE AA; Negative Revised "
            "Short-term bank facilities 100.00 CARE A1+ Reaffirmed")
    p = readers.read_rating(None, [page])["payload"]
    assert p["rating_agency"] == "CARE" and p["long_term_rating"] == "CARE AA (Negative)"
    assert p["short_term_rating"].replace(" ", "") == "CAREA1+" and p["total_rated_cr"] == 140.0


# ── notes to accounts ────────────────────────────────────────────────────────

def test_a_negated_adverse_remark_is_a_clean_opinion_and_curly_apostrophes_are_found():
    pages = ["Board's report. The emphasis of matter does not constitute a qualification, reservation, adverse remark "
             "or disclaimer of opinion.",
             "INDEPENDENT AUDITOR’S REPORT To the Members. Opinion. In our opinion the standalone financial statements "
             "give a true and fair view."]
    s = nr.locate(pages)
    assert s["auditor"] and s["auditor"][0] == 1                     # curly apostrophe
    r = nr.read_by_rules(pages, s)
    assert r["opinion"] != "adverse"
    assert not any(f["topic"] == "audit_opinion" and f["severity"] == "high" for f in r["findings"])


# ── CAM intake: financial highlights table ───────────────────────────────────

def test_the_latest_actual_year_is_read_from_a_cell_per_line_table():
    cells = ["5. FINANCIAL PERFORMANCE", "Particulars (Rs Cr)", "FY2024", "FY2025", "FY2026",
             "Revenue from operations", "5,121.74", "6,051.88", "5,666.68", "EBITDA", "834.57", "965.94", "762.41",
             "Profit after tax", "545.49", "577.12", "389.14"]
    t = cam_intake.read_financial_table([cells])
    assert t["revenue_cr"]["value"] == 5666.68 and t["ebitda_cr"]["value"] == 762.41
    assert t["pat_cr"]["value"] == 389.14 and t["revenue_cr"]["year"] == "FY2026"


def test_projected_columns_are_skipped_units_scaled_and_short_rows_not_guessed():
    t = cam_intake.read_financial_table([["Financial Highlights (Rs in lakh)", "Particulars  FY24  FY25  FY26 (P)",
                                          "Net Sales 10,050 12,000 14,000", "PAT (500) 620 700", "Total debt 300"]])
    assert t["revenue_cr"] == {**t["revenue_cr"], "value": 120.0, "year": "FY2025"}
    assert t["pat_cr"]["value"] == 6.2
    assert "total_debt_cr" not in t                                   # one cell for three years: not read


# ── the flow ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def svc():
    flow = build_container().flow
    flow.reset({"user": {"id": "test"}}, E)
    yield flow
    flow.reset({"user": {"id": "test"}}, E)


def _cam_pdf(revenue: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 800),
                        "CREDIT APPRAISAL MEMORANDUM\nInfosys Limited\nInternal Rating: AA-\n\nFinancial Highlights\n"
                        f"Particulars (Rs Cr)\nFY2024\nFY2025\nRevenue from operations\n146,767.00\n{revenue}\n\n"
                        "Recommendation\nSanction recommended.", fontsize=10)
    return doc.tobytes()


def test_an_ingested_cam_is_checked_and_completed_from_the_audited_statements(svc):
    rm = svc.sign_in("f_rm")
    svc.reset(rm, E)
    case = svc.create(rm, entity_id=E)
    svc.upload_cam(case["case_id"], rm, "bank_cam.pdf", _cam_pdf("150,000.00"))
    pts = {p["id"]: p for g in svc.view(case["case_id"], rm)["groups"] for p in g["points"]}
    assert pts["revenue_cr"]["value"] == 150000.0 and "audited FY2025" in (pts["revenue_cr"]["flag"] or "")
    # not stated in the CAM → from the audited statements on record, with the formula
    assert pts["pat_cr"]["source"]["kind"] == "record" and pts["pat_cr"]["value"] is not None
    assert pts["current_ratio"]["source"]["label"].startswith("Ratio engine · Audited statements · FY2025")
    svc.reset(rm, E)


def test_the_rm_explains_a_verification_difference_and_it_stops_blocking(svc):
    rm = svc.sign_in("f_rm")
    svc.reset(rm, E)
    cid = svc.create(rm, entity_id=E)["case_id"]
    case = svc._require(cid)
    case["is_prospect"] = True
    case["acquisition"] = {"sources": {}, "verification": [
        {"id": "gst_vs_revenue", "label": "GST turnover vs reported revenue", "status": "fail", "detail": "38% apart"}]}
    svc._save(case)
    assert any("Data verification failed" in b for b in svc.blockers(svc._require(cid)))
    with pytest.raises(Exception):
        svc.explain_verification(cid, rm, "gst_vs_revenue", "  ")
    svc.explain_verification(cid, rm, "gst_vs_revenue", "Sale of power is GST-exempt")
    case = svc._require(cid)
    assert not any("Data verification failed" in b for b in svc.blockers(case))
    assert case["verification_notes"]["gst_vs_revenue"]["note"] == "Sale of power is GST-exempt"
    svc.reset(rm, E)
