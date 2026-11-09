"""The new-prospect journey (src/flow/acquire): data acquisition agents, API first and documents where an
API is not connected, verified across sources, then the CAM — for Dixon Technologies (India) Limited.

Live APIs are replaced by canned responses (tests never call the network); the documents are the demo
pack from test-documents/dixon_technologies plus audited statements in the Schedule III layout built here
from Dixon's published standalone figures (₹ lakh)."""

import importlib.util
import json
from pathlib import Path

import pytest

from src.application.container import build_container
from src.application.errors import InvalidRequestError
from src.flow.acquire import readers
from src.flow.acquire.agents import Acquisition, classify_news, verify
from src.flow.acquire.connectors import name_score
from src.flow.acquire.polite import NetworkError, Response

ROOT = Path(__file__).resolve().parents[1]
NAME = "Dixon Technologies (India) Limited"
CIN = "L32101UP1993PLC066581"

BS = [  # label, note, FY2026, FY2025 (₹ lakh) — standalone balance sheet, FY2025-26 annual report p.312
    ("ASSETS", None, None, None), ("Non-current assets", None, None, None),
    ("Property, plant and equipment", "7", "56,895", "57,372"), ("Capital work-in-progress", "8", "36,670", "17,418"),
    ("Other intangible assets", "9", "993", "1,044"), ("Right -of-use assets", "10", "21,737", "25,798"),
    ("Investments", "11", "1,90,688", "1,08,605"), ("Loans", "12", "1,495", "24,182"),
    ("Other financial assets", "13", "1,924", "2,288"), ("Other non-current assets", "14", "812", "918"),
    ("", None, "3,11,214", "2,37,625"), ("Current assets", None, None, None),
    ("Inventories", "15", "47,634", "38,418"), ("Trade receivables", "16", "55,515", "60,763"),
    ("Cash and cash equivalents", "17", "2,163", "3,753"),
    ("Bank balances other than cash and cash equivalents", "18", "36", "151"), ("Loans", "12", "2,938", "4"),
    ("Other financial assets", "13", "2,403", "1,310"), ("Current tax assets (net)", "19", "2,110", "870"),
    ("Other current assets", "14", "6,869", "5,147"), ("", None, "1,19,668", "1,10,416"),
    ("TOTAL ASSETS", None, "4,30,882", "3,48,041"), ("EQUITY AND LIABILITIES", None, None, None),
    ("Equity share capital", "20", "1,216", "1,205"), ("Other equity", "21", "3,22,685", "2,17,072"),
    ("TOTAL EQUITY", None, "3,23,901", "2,18,277"), ("Non-Current Liabilities", None, None, None),
    ("Borrowings", "22", "-", "2,700"), ("Lease liabilities", "23", "7,541", "11,546"),
    ("Provisions", "24", "184", "487"), ("Deferred tax liabilities (net)", "25", "9,066", "8,665"),
    ("Other non current liabilities", "26", "2,973", "1,483"), ("Current Liabilities", None, None, None),
    ("Borrowings", "27", "17,220", "14,966"), ("Lease liabilities", "23", "979", "1,042"),
    ("Total outstanding dues of micro and small enterprises", "28", "4,092", "2,954"),
    ("Total outstanding dues to creditors other than micro and small enterprises", "28", "58,372", "73,801"),
    ("Other financial liabilities", "29", "3,777", "5,227"), ("Other current liabilities", "26", "2,518", "6,382"),
    ("Provisions", "24", "259", "511"), ("TOTAL LIABILITIES", None, "1,06,981", "1,29,764"),
    ("TOTAL EQUITY AND LIABILITIES", None, "4,30,882", "3,48,041")]
PL = [("Revenue from operations", "30", "3,93,048", "5,40,090"), ("Other income", "31", "80,198", "6,647"),
      ("Total income (1+2)", None, "4,73,246", "5,46,737"), ("Cost of materials consumed", "32", "3,29,476", "4,58,911"),
      ("Changes in inventories of finished goods and work-in-progress", "33", "(5,012)", "820"),
      ("Employee benefits expense", "34", "24,028", "26,442"), ("Finance costs", "35", "5,427", "5,303"),
      ("Depreciation and amortisation expense", "36", "6,989", "7,065"), ("Other expenses", "37", "23,521", "29,258"),
      ("Total expenses (4)", None, "3,84,429", "5,27,799"),
      ("Profit before exceptional items and tax (3-4)", None, "88,817", "18,938"),
      ("Exceptional items", "38", "-", "48,950"), ("Profit before tax (5+6)", None, "88,817", "67,888"),
      ("Tax expense (8)", "39", "12,873", "11,298"), ("Profit for the year (7-8)", None, "75,944", "56,590")]
CF = [("Net cash generated from/ (used in) operating activities", None, "(10,357)", "27,859"),
      ("Capital expenditure on property, plant and equipment and intangible assets", None, "(30,683)", "(19,036)"),
      ("Net cash generated from/(used in) investing activities", None, "(4,300)", "(38,200)")]


def statements_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle
    ss = getSampleStyleSheet()
    cell = ss["BodyText"].clone("cell", fontSize=8, leading=9.5)

    def table(rows):
        t = Table([["Particulars", "Note No.", "As at 31st March, 2026", "As at 31st March, 2025"],
                   *[[Paragraph(a, cell), b or "", c or "", d or ""] for a, b, c, d in rows]],
                  colWidths=[90 * mm, 16 * mm, 34 * mm, 34 * mm])
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (2, 0), (-1, -1), "RIGHT")]))
        return t
    flow = [Paragraph(f"{NAME.upper()}", ss["Title"]), Paragraph(f"CIN: {CIN}", ss["Normal"]),
            Paragraph("Audited financial statements 2025-26", ss["Normal"]), PageBreak(),
            Paragraph("STANDALONE BALANCE SHEET AS AT 31ST MARCH, 2026 (` / Lakhs)", ss["Heading2"]), table(BS),
            PageBreak(), Paragraph("STANDALONE STATEMENT OF PROFIT AND LOSS FOR THE YEAR ENDED 31ST MARCH, 2026 "
                                   "(` / Lakhs)", ss["Heading2"]), table(PL), PageBreak(),
            Paragraph("STANDALONE STATEMENT OF CASH FLOWS FOR THE YEAR ENDED 31ST MARCH, 2026 (` / Lakhs)",
                      ss["Heading2"]),
            Paragraph("A. Cash flow from operating activities", ss["Normal"]), table(CF),
            Paragraph("B. Cash flow from investing activities", ss["Normal"])]
    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(path), pagesize=A4).build(flow)
    return path


@pytest.fixture(scope="module")
def docs(tmp_path_factory) -> dict:
    spec = importlib.util.spec_from_file_location("dixon_prepare", ROOT / "test-documents/dixon_technologies/prepare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.make_demo(tmp_path_factory.mktemp("dixon"))
    return {"mca": out / "mca/mca_master_data.pdf", "kyc": out / "kyc/kyc_pack.pdf",
            "bureau": out / "bureau/commercial_bureau_report.pdf",
            "bank_statements": out / "banking/bank_statement_apr_sep_2026.pdf",
            "gst": out / "gst/gst_returns_fy2025_26.pdf",
            "financials": statements_pdf(out / "financials/audited_financial_statements_fy2026.pdf")}


class FakeClient:
    """Canned GLEIF and GDELT answers; any other call fails like an unreachable host."""
    calls: list = []

    def get(self, url, params=None, cache_hours=24, accept=""):
        if "gleif" in url:
            body = {"data": [{"id": "335800D7XO7AVXXJ8575", "attributes": {
                "lei": "335800D7XO7AVXXJ8575", "entity": {"legalName": {"name": "DIXON TECHNOLOGIES (INDIA) LIMITED"},
                                                          "registeredAs": CIN, "jurisdiction": "IN", "status": "ACTIVE",
                                                          "legalAddress": {"addressLines": ["B-14&15 PHASE- II"],
                                                                           "city": "NOIDA", "region": "IN-UP",
                                                                           "postalCode": "201305"}},
                "registration": {"status": "ISSUED", "nextRenewalDate": "2027-12-12T00:00:00Z"}}}]}
        elif "gdelt" in url:
            body = {"articles": [
                {"title": "Dixon Technologies Q2 revenue rises on mobile phone demand", "url": "https://example.com/a",
                 "domain": "example.com", "seendate": "20261020T101500Z"},
                {"title": "Dixon Technologies shares fall after tax raid at Noida plant", "url": "https://example.com/b",
                 "domain": "example.org", "seendate": "20260915T090000Z"}]}
        else:
            raise NetworkError("unreachable in tests")
        return Response(url=url, status=200, content=json.dumps(body).encode(), content_type="application/json",
                        from_cache=False, fetched_at=1.0)


class FakeSanctions:
    def screen(self, names, threshold=0.9):
        return {"lists": [{"list": "OFAC SDN", "entries": 19555}, {"list": "UN consolidated", "entries": 1007}],
                "screened": [{**n, "matches": [], "status": "clear"} for n in names], "matches": 0}


@pytest.fixture(scope="module")
def svc():
    flow = build_container().flow
    flow.acquirer.client = FakeClient()
    flow.acquirer.sanctions = FakeSanctions()
    return flow


def _upload(svc, cid, rm, sid, path: Path):
    svc.upload_source(cid, rm, sid, path.name, path.read_bytes())
    return svc.wait_for_acquisition(cid)


# ── readers ──────────────────────────────────────────────────────────────────

def test_the_statement_reader_finds_the_standalone_statements_and_reconciles_both_years(docs):
    r = readers.read_financial_statements(docs["financials"])
    assert r["unit"] == "lakh" and r["basis"] == "standalone" and r["identity"]["cin"] == CIN
    fy26, fy25 = r["statements"]
    assert (fy26["period"], fy25["period"]) == ("FY2026", "FY2025")
    i = fy26["items"]
    assert i["revenue_operating"] == pytest.approx(3930.48) and i["pat"] == pytest.approx(759.44)
    assert i["total_equity"] == pytest.approx(3239.01) and i["total_assets"] == pytest.approx(4308.82)
    assert i["current_liabilities"] == pytest.approx(872.17) and i["short_term_debt"] == pytest.approx(172.20)
    assert i["raw_material_cost"] == pytest.approx(3244.64)               # materials + change in inventories
    assert i["ocf"] == pytest.approx(-103.57) and i["capex"] == pytest.approx(-306.83)
    assert fy25["items"]["exceptional_items"] == pytest.approx(489.5)
    assert all(c["ok"] for s in r["statements"] for c in s["checks"])


def test_demo_documents_read_into_the_same_record_an_api_returns(docs):
    b = readers.read_source_document("bureau", docs["bureau"])
    assert b["provenance"]["via"] == "document" and b["source_status"] == "success"
    assert b["payload"]["total_exposure_cr"] == pytest.approx(2415.0) and b["payload"]["total_lenders"] == 6
    m = readers.read_source_document("mca", docs["mca"])
    assert m["payload"]["cin"] == CIN and len(m["payload"]["directors"]) == 8
    g = readers.read_source_document("gst", docs["gst"])
    assert g["payload"]["aggregate_turnover_fy2026_cr"] == pytest.approx(3862.4) and len(g["payload"]["returns"]) == 12


def test_news_is_screened_by_keywords_when_ai_is_not_configured():
    flags = classify_news(["Dixon reports record quarter", "ED raid at Dixon plant over fraud probe"], NAME)
    assert [f["adverse"] for f in flags] == [False, True]
    assert name_score("DIXON TECHNOLOGIES (INDIA) LIMITED", "Dixon Technologies (India) Ltd") == 1.0


def test_an_inactive_api_falls_back_to_the_document(tmp_path):
    cfg = {"sources": [{"id": "mca", "agent": "identity", "label": "MCA", "mode": "api", "connector": "probe42",
                        "requires_key": "PROBE42_TEST_KEY_NOT_SET", "upload": {"category": "mca", "ask": "MCA data"}}],
           "requirements": {"always": ["mca"]}}
    acq = Acquisition(cfg, FakeClient(), tmp_path, sanctions=FakeSanctions())
    mode, why = acq.mode(cfg["sources"][0])
    assert mode == "inactive" and "PROBE42_TEST_KEY_NOT_SET" in why


# ── the journey ──────────────────────────────────────────────────────────────

def test_dixon_prospect_api_first_then_documents_then_the_cam(svc, docs):
    rm = svc.sign_in("f_rm")
    case = svc.create(rm, prospect={"company_name": NAME, "cin": CIN, "sector": "manufacturing"},
                      facility={"product": "working_capital", "amount_cr": 250, "tenor_months": 12,
                                "purpose": "Fund-based working capital (cash credit) for component inventory"})
    cid = case["case_id"]
    case = svc.wait_for_acquisition(cid)
    src = case["acquisition"]["sources"]
    # live APIs answered; inactive ones wait for documents
    assert src["lei"]["status"] == "fetched" and "335800D7XO7AVXXJ8575" in src["lei"]["summary"]
    assert src["sanctions"]["status"] == "fetched" and src["adverse_media"]["status"] == "fetched"
    assert src["mca"]["status"] == "awaiting_upload" and src["mca"]["mode"] == "inactive"
    assert "PROBE42_API_KEY" in src["mca"]["mode_reason"]
    assert {s for s, v in src.items() if v["status"] == "awaiting_upload"} == \
        {"mca", "financials", "bureau", "bank_statements", "gst", "kyc", "rating"}
    # the regulatory-list checks come from the demo file while their feeds are not connected (E5)
    assert src["registries"]["status"] == "fetched" and src["registries"]["demo"]
    assert src["registries"]["summary"].startswith("Demo data · Not on the wilful-defaulter")
    v = svc.view(cid, rm)
    assert v["acquisition"]["counts"]["fetched"] == 4 and not v["can_generate"]
    assert v["ask"]["kind"] == "source_doc" and v["ask"]["ref"] == "mca"
    with pytest.raises(InvalidRequestError, match="MCA"):
        svc.generate_cam(cid, rm)

    # documents, in the order Copilot asks for them
    case = _upload(svc, cid, rm, "mca", docs["mca"])
    assert case["acquisition"]["sources"]["mca"]["status"] == "read"
    screened = case["acquisition"]["records"]["sanctions"]["payload"]["screened"]
    assert len(screened) == 9                                    # the company and its eight directors
    assert svc.view(cid, rm)["ask"]["ref"] == "financials"
    case = _upload(svc, cid, rm, "financials", docs["financials"])
    assert [s["period"] for s in case["acquisition"]["statements"]] == ["FY2026", "FY2025"]
    assert svc.view(cid, rm)["ask"]["ref"] == "kyc"
    case = _upload(svc, cid, rm, "kyc", docs["kyc"])
    v = svc.view(cid, rm)
    assert v["can_generate"]                                     # the CAM's minimum is in
    assert v["ask"]["kind"] == "source_doc" and v["ask"]["ref"] == "bureau" and "Skip for now" in v["ask"]["quick"]
    assert any("Required data sources pending" in b for b in svc.blockers(case))
    for sid in ("bureau", "bank_statements", "gst"):
        case = _upload(svc, cid, rm, sid, docs[sid])
        assert case["acquisition"]["sources"][sid]["status"] == "read", case["acquisition"]["sources"][sid]
    v = svc.view(cid, rm)
    assert v["ask"]["ref"] == "rating"                           # recommended: it can be skipped
    svc.chat(cid, rm, "Skip for now")
    v = svc.view(cid, rm)
    assert v["ask"]["kind"] == "generate"

    # what the verification agent concluded
    checks = {c["id"]: c for c in svc._require(cid)["acquisition"]["verification"]}
    assert checks["cin"]["status"] == "pass" and checks["pan"]["status"] == "pass"
    assert checks["reconcile"]["status"] == "pass" and checks["gst_vs_revenue"]["status"] == "pass"
    assert checks["earnings_quality"]["status"] == "warn"        # other income is 90% of FY2026 PBT
    assert checks["bureau_vs_bs"]["status"] == "warn"            # inter-company loans are not in the bureau
    assert checks["bank_vs_revenue"]["status"] == "warn"         # H1 FY2027 credits run ahead of FY2026 revenue
    assert checks["bureau_conduct"]["status"] == "pass" and checks["sanctions"]["status"] == "pass"
    assert checks["adverse_media"]["status"] == "warn"           # the canned 'tax raid' headline

    # the borrower record the CAM engine reads
    company = svc.companies[case["entity_id"]]
    b = company["borrower"]
    assert b.cin == CIN and b.pan == "AAACD3641D" and str(b.date_of_incorporation) == "1993-01-15"
    assert len(company["directors"]) == 8 and sorted(company["financials"]) == ["FY2025", "FY2026"]
    assert company["external_data"]["bureau_data"]["payload"]["total_exposure_cr"] == pytest.approx(2415.0)
    assert company["external_data"]["bureau_data"]["payload"]["fraud_flag"] is False     # list checks folded in
    assert not [i for i in svc._require(cid)["checks"]["items"] if i["status"] != "pass"]  # all six clear
    assert company["collateral"][0].market_value_cr == pytest.approx(476.34 + 555.15)
    assert sum(1 for s in company["market_signals"] if s.signal_type == "news") == 1

    # generate the CAM from the chat
    svc.chat(cid, rm, "Yes, generate")
    case = svc.wait_for_cam(cid, timeout=300)
    assert case["cam"]["state"] == "ready", case["cam"]
    v = svc.view(cid, rm)
    rev = next(p for g in v["groups"] for p in g["points"] if p["id"] == "revenue_cr")
    assert rev["value"] == pytest.approx(3930.48)
    assert not any("Required data sources pending" in b for b in svc.blockers(svc._require(cid)))
    assert svc.source_record(cid, "financials")["statements"][0]["items"]["pat"] == pytest.approx(759.44)
    html = svc.audit_pack(cid, rm)
    assert "Data acquisition (new prospect)" in html and "Fetched via API" in html and "Read from document" in html


def test_a_document_for_another_company_is_rejected(svc, docs, tmp_path):
    rm = svc.sign_in("f_rm")
    case = svc.create(rm, prospect={"company_name": "Zenith Circuits Private Limited", "sector": "manufacturing"},
                      facility={"product": "term_loan", "amount_cr": 40, "tenor_months": 60})
    cid = case["case_id"]
    svc.wait_for_acquisition(cid)
    case = _upload(svc, cid, rm, "kyc", docs["kyc"])
    k = case["acquisition"]["sources"]["kyc"]
    assert k["status"] == "rejected" and "DIXON" in k["error"]
    assert svc.view(cid, rm)["ask"]["ref"] in ("mca", "kyc")


def test_verification_flags_a_cin_mismatch():
    ctx = {"cin": CIN}
    recs = {"mca": {"payload": {"cin": "U99999MH2000PTC123456"}}}
    out = {c["id"]: c for c in verify(ctx, {}, recs, [])}
    assert out["cin"]["status"] == "fail"
