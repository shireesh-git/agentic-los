"""M7 CAM Composer: the 12-section banker CAM composed from the structured outputs, with provenance."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from src.application.case_service import build_case_result
from src.data.company_catalog import seed_company_store
from src.engines.cam_composer import SECTIONS, render_final_cam_markdown
from src.engines.data_provenance import CLASS_LABELS

CASE = "ABCE001"
TITLES = ["Executive Summary & Credit Proposal", "Borrower, Group & Promoter Profile",
          "Business Profile & Purpose of Finance", "Industry, Business & Management Assessment",
          "Banking, Credit History & External Rating", "Key Credit Risks & Mitigants",
          "Conduct, Compliance & Due Diligence", "Financial Performance & Repayment Capacity",
          "Financial Outlook & Resilience Assessment", "Credit Facilities & Structure", "Security, Collateral & Covenants",
          "Sanction Terms, Conditions & Recommendation"]


def full_case(company):
    from src.engines.cam_fact_builder import build_cam_fact_pack
    from src.engines.cam_llm_renderer import render_cam_template_only
    fp = build_cam_fact_pack(copy.deepcopy(company))
    narrative = {"fact_pack": fp, "cam_text": render_cam_template_only(fp), "narrative_mode": "template"}
    return build_case_result(CASE, company, {"results": {"narrative": narrative}}, [])


@pytest.fixture(scope="module")
def case():
    return full_case(seed_company_store()[CASE])


def by_id(final):
    return {s["id"]: s for s in final["sections"]}


def rows(section, title):
    return next(t for t in section["tables"] if t["title"].startswith(title))["rows"]


def test_twelve_banker_sections(case):
    final = case["final_cam"]
    assert final["available"] and [s["title"].split(". ", 1)[1] for s in final["sections"]] == TITLES
    assert [s[1] for s in SECTIONS] == TITLES


def test_executive_summary_is_built_around_the_credit_proposal(case):
    exe = by_id(case["final_cam"])["executive_summary"]
    assert [b["heading"] for b in exe["blocks"]] == ["Credit proposal", "Key concerns", "Credit rationale"]
    facts = {f["label"]: f["value"] for f in exe["facts"]}
    assert facts["Facility requested"] == "Working capital of ₹250.00 Cr" and facts["Recommended amount"] == "₹185.00 Cr"
    assert facts["Existing exposure with the bank"] == "Nil (new-to-bank)" and facts["Tenor"] == "12 months"
    assert facts["Primary repayment source"] == "Operating cash flow — inadequate"
    text = " ".join(s["text"] for s in exe["statements"])
    assert "recommended in a modified form: ₹185.00 Cr against ₹250.00 Cr requested" in text
    assert "requires the deviation route" in text and "DSCR is 1.19x in the base case" in text
    assert "interest-coverage test" in text
    assert len(rows(exe, "Key concerns")) == 5


def test_m1_to_m6_appear_in_the_final_cam(case):
    s = by_id(case["final_cam"])
    assert len(rows(s["key_risks"], "Risk and mitigant matrix")) == 12      # M1 (+ M2, M3, M6)
    assert len(rows(s["compliance_intelligence"], "Due diligence register")) == 7   # M2
    assert len(rows(s["key_risks"], "Credit challenges")) == 7       # M3
    assert any("Repayment capacity moved from STRONG" in x["text"] for x in s["financials_repayment"]["statements"])  # M4
    stress = rows(s["projections_stress"], "Scenario analysis")         # M5
    assert stress[2][1:] == ["1.19x", "1.03x", "0.77x", "≥ 1.2"] and stress[-1][1:4] == ["High", "High", "Critical"]
    sizing = rows(s["facility_structure"], "How the amount was sized")  # M6
    assert any("(binding)" in r[0] for r in sizing)
    final = s["final_recommendation"]
    assert len(rows(final, "Conditions precedent")) == 7 and len(rows(final, "Conditions subsequent")) == 5
    assert len(rows(final, "Mitigants")) == 3


def test_every_item_has_a_known_provenance(case):
    for section in case["final_cam"]["sections"]:
        for item in section["statements"] + section["facts"] + section["tables"]:
            assert item["provenance"] in CLASS_LABELS, (section["id"], item)


def test_demo_data_and_gaps_are_labelled_not_presented_as_evidence(case):
    s = by_id(case["final_cam"])
    assert all(f["provenance"] == "synthetic_demo" for f in s["borrower_group"]["facts"][:7])   # demo borrower record
    news = [x for x in s["industry_risk"]["statements"] if x["text"].startswith("Adverse or market news")][0]
    assert news["provenance"] == "unavailable" and "not available" in news["text"]
    signals = next(t for t in s["industry_risk"]["tables"] if t["title"] == "Market signals")
    assert signals["provenance"] == "synthetic_demo" and "not verified" in signals["note"]
    md = render_final_cam_markdown(case["final_cam"])
    assert "wins NHAI highway project" not in md and "[Demo]" in md and "[N/A]" in md


def test_ratios_are_quoted_from_the_engines(case):
    ratios = rows(by_id(case["final_cam"])["financials_repayment"], "Key ratios")
    dscr = next(r for r in ratios if r[0] == "DSCR")
    assert dscr[1:3] == ["1.67x", "1.19x"] and dscr[-1] == "≥ 1.2"
    assert next(r for r in ratios if r[0] == "Revenue growth")[1:3] == ["10.0%", "18.2%"]
    growth = rows(by_id(case["final_cam"])["financials_repayment"], "Growth")
    assert next(r for r in growth if r[0] == "Revenue growth")[-1] == "18.2%"


def test_analytical_sections_remain_for_drill_down(case):
    s = by_id(case["final_cam"])
    fin = [d["analytical_section"] for d in s["financials_repayment"]["drill_down"]]
    assert "financial_analysis" in fin and all(d["text"].startswith("## ") for d in s["financials_repayment"]["drill_down"])
    assert case["cam_text"] and case["fact_pack"] and case["observations"]       # detail kept in the case


def test_markdown_html_and_pdf(case):
    from src.rendering import generate_cam_pdf, markdown_to_html
    md = render_final_cam_markdown(case["final_cam"])
    assert sum(line.startswith("## ") for line in md.splitlines()) == 12
    assert "*Basis of information:" in md and "### Credit rationale" in md
    for phrase in ("agent", "The AI", "model believes", "M6", "M5 ", "Investigation Agent", "INV-ABCE001"):
        assert phrase not in md, phrase
    assert "<h2" in markdown_to_html(md, "ABC")
    assert generate_cam_pdf(md, "ABC")[:4] == b"%PDF"


def test_risk_matrix_links_due_diligence_challenge_and_mitigant(case):
    matrix = rows(by_id(case["final_cam"])["key_risks"], "Risk and mitigant matrix")
    wc = next(r for r in matrix if r[0] == "Working Capital Deterioration")
    assert wc[2] == "HIGH" and "Receivables grew 52.1%" in wc[1]
    assert wc[3].startswith("Receivable deterioration") and "(open)" in wc[3]
    assert "Requested amount reflects a slower cycle" in wc[4]
    assert wc[5].startswith("Drawing power to exclude receivables older than 90 days")
    assert wc[6] == "Open — subject to conditions"
    liquidity = next(r for r in matrix if r[0] == "Liquidity Stress")
    assert liquidity[5] == "—" and liquidity[6] == "Open"


def test_journey_and_decision_trail(case):
    final = case["final_cam"]
    journey = {s["id"]: s for s in final["journey"]}
    assert list(journey) == ["credit_assessment", "risk_identification", "due_diligence", "credit_challenge", "repayment",
                             "resilience", "reassessment", "decision", "cam"]
    assert journey["due_diligence"] == {"id": "due_diligence", "label": "Due Diligence", "status": "attention",
                                        "summary": "7 item(s), 7 open"}
    assert journey["resilience"]["summary"] == "Constrained in severe downside"
    trail = final["decision_trail"]
    assert trail["changed"] and trail["outcome"].startswith("The proposal was modified")
    steps = {s["id"]: s["text"] for s in trail["steps"]}
    assert steps["proposal"].startswith("Working capital of ₹250.00 Cr requested")
    assert "DSCR 1.19x base, 1.03x downside, 0.77x severe downside" in steps["resilience"]
    assert steps["decision"].startswith("Reduced / modified: ₹185.00 Cr against ₹250.00 Cr")
    assert final["headline"]["resilience_status"] == "FAILS SEVERE"


def test_missing_outputs_are_not_marked_complete():
    from src.engines.cam_composer import compose_final_cam
    case = full_case(seed_company_store()[CASE])
    for key in ("repayment_analysis", "stress_test", "reassessment", "investigations"):
        case.pop(key)
    final = compose_final_cam(case)
    journey = {s["id"]: s for s in final["journey"]}
    for sid in ("due_diligence", "repayment", "resilience", "reassessment", "decision"):
        assert journey[sid]["status"] == "unavailable" and journey[sid]["summary"] == "Not available"
    assert final["decision_trail"]["outcome"] == "Not available"
    assert len(final["sections"]) == 12
    assert "Not available" in render_final_cam_markdown(final)


def test_supported_case_composes_too():
    healthy = copy.deepcopy(seed_company_store()[CASE])
    healthy["financials"].pop("FY2026")
    final = full_case(healthy)["final_cam"]
    assert final["available"] and final["headline"]["recommended_cr"] == 250.0
    assert final["decision_trail"]["outcome"] == ("Credit assessment confirmed following due diligence and "
                                                  "resilience assessment.")


# ─── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(case):
    from src.api.app import create_app
    from src.application.container import build_container

    container = build_container()
    stored = {k: v for k, v in copy.deepcopy(case).items() if k != "final_cam"}    # back-filled on read
    stored["run_id"] = "fc-run-1"
    container.state.cases[CASE] = stored
    container.persistence.save_case_run(stored)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(CASE, None)
    container.persistence.delete_company(CASE)


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, text):
        self.text = text

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        assert "do NOT change the recommendation" in system_prompt
        return json.dumps({"interpretation": self.text})


def test_api_final_cam_and_renditions(client):
    http, container = client
    body = http.get(f"/api/cases/{CASE}/final-cam").json()
    assert body["final_cam"]["available"] and len(body["final_cam"]["sections"]) == 12
    assert container.persistence.get_case_run("fc-run-1")["final_cam"]["available"]
    assert http.get(f"/api/cases/{CASE}/final-cam-html").headers["content-type"].startswith("text/html")
    pdf = http.get(f"/api/cases/{CASE}/final-cam-pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert http.get(f"/api/cases/{CASE}/cam-pdf").content[:4] == b"%PDF"            # analyst CAM unchanged
    assert http.post(f"/api/cases/{CASE}/final-cam/interpret", json={}).status_code == 409   # mock provider


def test_ai_interpretation_is_guarded_and_kept_while_content_is_unchanged(client):
    http, container = client
    container.final_cam.llm_factory = lambda: FakeLLM(
        "The facility was reduced from ₹250.00 Cr to ₹185.00 Cr because the reassessment found repayment capacity "
        "stressed and leverage outside policy; the conditions precedent address these gaps.")
    body = http.post(f"/api/cases/{CASE}/final-cam/interpret", json={"section_ids": ["executive_summary"]}).json()
    assert body["results"]["executive_summary"]["status"] == "ok"
    again = http.get(f"/api/cases/{CASE}/final-cam").json()["final_cam"]["sections"][0]
    assert again["ai_interpretation"]["provenance"] == "ai"
    assert "Commentary (AI-assisted)" in http.get(f"/api/cases/{CASE}/final-cam-html").text

    container.final_cam.llm_factory = lambda: FakeLLM("The borrower's DSCR will improve to 2.95x next year as "
                                                      "collections normalise and margins recover strongly.")
    body = http.post(f"/api/cases/{CASE}/final-cam/interpret", json={"section_ids": ["key_risks"]}).json()
    assert body["results"]["key_risks"]["status"] == "rejected" and "2.95" in body["results"]["key_risks"]["reason"]

    # Resolving an investigation changes the risk section; the interpretation tied to old content is dropped.
    container.final_cam.llm_factory = lambda: FakeLLM(
        "Twelve observations remain under review; the investigations and challenges listed must be closed before "
        "the credit committee can rely on the proposal.")
    ok = http.post(f"/api/cases/{CASE}/final-cam/interpret", json={"section_ids": ["key_risks"]}).json()
    assert ok["results"]["key_risks"]["status"] == "ok"
    assert http.get(f"/api/cases/{CASE}/final-cam").json()["final_cam"]["sections"][5]["ai_interpretation"]
    http.patch(f"/api/cases/{CASE}/investigations/INV-{CASE}-LEVERAGE", json={"status": "RESOLVED"})
    risks = http.get(f"/api/cases/{CASE}/final-cam").json()["final_cam"]["sections"][5]
    assert risks["ai_interpretation"] is None
    lev = next(r for r in next(t for t in risks["tables"] if t["title"] == "Risk and mitigant matrix")["rows"]
               if r[0] == "Increasing Leverage Risk")
    assert lev[3] == "Increasing leverage — debt schedule and new borrowings (resolved)" and lev[6] == "Closed"
