"""LOS Phase 4: Prospect Sourcing document prefill (source page + confidence) and the IP Note."""

import json
from datetime import datetime

import fitz
import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.ip_note import build_ip_note, prescreen, render_html, summarise
from src.los.service import LosService, load_workflow
from src.los.sourcing import build_prefill, master_values, read_documents
from src.los.store import LosStore
from src.services.document_store import DocumentStore

NOW = datetime(2026, 10, 8, 12, 0, 0)


def _pdf(path, *pages):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((40, 60), text, fontsize=9)
    doc.save(path)
    doc.close()


@pytest.fixture()
def docs_root(tmp_path):
    root = tmp_path / "documents"
    d = root / "IHCL001"
    _pdf(d / "request" / "request_note.pdf",
         "The Indian Hotels Company Limited\nFacility Requested: term_loan\nCase Type: ETB\n"
         "Amount Requested: Rs 1,200 Cr\nTenor: 84 months\nPurpose: Renovation of Taj Palace Delhi\n"
         "Latest Financial Snapshot (FY2025): Revenue Rs 6,854 Cr, EBITDA Rs 2,952 Cr, PAT Rs 1,461 Cr, Debt Rs 5,000 Cr.")
    _pdf(d / "kyc" / "pan_card.pdf", "Cover page", "PAN: AAACT5678H\nLegal Name: The Indian Hotels Company Limited\n"
                                                   "CIN: L74999MH1902PLC000183\nIncorporated: 01-Oct-1902")
    _pdf(d / "kyc" / "board_resolution_borrowing.pdf",
         "The Board authorizes N. Chandrasekaran to execute all credit documents for the proposed term_loan.\n"
         "Requested limit under review: Rs 1,250 Cr.")
    _pdf(d / "exchange" / "quarterly_results_q3.pdf", "Revenue from Operations 1,782.04 1,500.00")
    _pdf(d / "collateral" / "valuation_report.pdf",
         "Total collateral market value assessed at Rs 2,800 Cr with aggregate forced-sale value of Rs 1,960 Cr.")
    return root


@pytest.fixture()
def ihcl():
    return seed_company_store()["IHCL001"]


def _f(prefill, fid):
    return next(f for f in prefill["fields"] if f["id"] == fid)


# ─── Extraction ─────────────────────────────────────────────────────────────

def test_prefill_cites_document_and_page_and_scores_confidence(docs_root, ihcl):
    p = build_prefill(read_documents(docs_root / "IHCL001"), master_values(ihcl, {"facility": {}}))
    pan = _f(p, "pan")
    assert pan["value"] == "AAACT5678H" and pan["sources"][0] == {**pan["sources"][0], "document": "kyc/pan_card.pdf",
                                                                    "page": 2}
    assert pan["status"] == "matches_record" and pan["band"] == "high"                 # agrees with the borrower master
    assert _f(p, "date_of_incorporation")["value"] == "1902-10-01"
    sig = _f(p, "authorised_signatory")
    assert (sig["value"], sig["status"], sig["band"]) == ("N. Chandrasekaran", "single_source", "medium")
    assert _f(p, "gstin")["status"] == "not_found" and _f(p, "gstin")["confidence"] == 0


def test_documents_that_disagree_are_a_conflict(docs_root, ihcl):
    p = build_prefill(read_documents(docs_root / "IHCL001"), master_values(ihcl, {"facility": {}}))
    amt = _f(p, "amount_cr")                                   # request note 1,200 vs board resolution 1,250
    assert amt["status"] == "conflict" and amt["band"] == "low"
    assert {a["value"] for a in amt["alternatives"]} == {"1,250"}
    assert p["summary"]["conflicts"] >= 1


def test_interim_filings_do_not_feed_annual_figures(docs_root, ihcl):
    p = build_prefill(read_documents(docs_root / "IHCL001"), master_values(ihcl, {}))
    rev = _f(p, "revenue_cr")
    assert rev["value"] == 6854.0 and all("quarterly" not in s["document"] for s in rev["sources"])
    assert rev["status"] == "matches_record"                   # the audited FY2025 revenue in the borrower master


class FakeLLM:
    name, model = "fake", "fake-llm"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=1000):
        return json.dumps(self.reply)


def test_ai_fallback_is_accepted_only_when_the_value_is_in_the_cited_page(docs_root, ihcl):
    reply = {"fields": [
        {"id": "gstin", "value": "27AAACT5678H1Z5", "document": "kyc/pan_card.pdf", "page": 2},      # not in the page
        {"id": "registered_address", "value": "Taj Palace Delhi", "document": "request/request_note.pdf", "page": 1}]}
    p = build_prefill(read_documents(docs_root / "IHCL001"), {}, llm_factory=lambda: FakeLLM(reply))
    assert p["ai"]["status"] == "ok" and _f(p, "gstin")["status"] == "not_found"
    addr = _f(p, "registered_address")
    assert addr["method"] == "ai" and addr["sources"][0]["page"] == 1 and addr["note"].startswith("AI-proposed")


def test_ai_fallback_is_skipped_with_the_mock_provider(docs_root):
    class Mock:
        name = "mock"
    p = build_prefill(read_documents(docs_root / "IHCL001"), {}, llm_factory=Mock)
    assert p["ai"]["used"] is False and "mock" in p["ai"]["status"]


# ─── Service: upload, prefill, accept ───────────────────────────────────────

@pytest.fixture()
def svc(tmp_path, docs_root):
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         documents_root=docs_root, doc_store=DocumentStore(docs_root))
    service.seed_demo()
    return service


def _draft(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "IHCL001")
    return app["application_id"], svc.sign_in(app["assignee_id"], "ps_maker")


def test_prefill_then_accept_updates_the_facility_with_an_audit_trail(svc):
    app_id, rm = _draft(svc)
    out = svc.run_prefill(app_id, rm)
    assert out["can_edit"] and out["prefill"]["summary"]["found"] >= 12 and len(out["documents"]) == 5
    out = svc.apply_prefill(app_id, rm, [{"field_id": "tenor_months"}, {"field_id": "pan"},
                                         {"field_id": "amount_cr", "value": "1,200", "reason": "Request note governs"}])
    app = svc.get(app_id)
    assert app["facility"]["tenor_months"] == 84 and app["amount_cr"] == 1200.0
    amt = next(f for f in out["prefill"]["fields"] if f["id"] == "amount_cr")["accepted"]
    assert amt["edited"] is False and amt["source"]["document"] == "request/request_note.pdf"   # chose a cited value
    assert [e["action"] for e in app["events"][:2]] == ["prefill_apply", "document_prefill"]
    assert app["sourcing"]["accepted"] == 3


def test_editing_a_value_needs_a_reason_and_a_valid_number(svc):
    app_id, rm = _draft(svc)
    svc.run_prefill(app_id, rm)
    with pytest.raises(InvalidRequestError, match="needs a reason"):
        svc.apply_prefill(app_id, rm, [{"field_id": "tenor_months", "value": "96"}])
    with pytest.raises(InvalidRequestError, match="must be a number"):
        svc.apply_prefill(app_id, rm, [{"field_id": "tenor_months", "value": "ten", "reason": "x"}])
    with pytest.raises(InvalidRequestError, match="no value"):
        svc.apply_prefill(app_id, rm, [{"field_id": "gstin"}])
    out = svc.apply_prefill(app_id, rm, [{"field_id": "tenor_months", "value": "96", "reason": "RM call with CFO"}])
    acc = next(f for f in out["prefill"]["fields"] if f["id"] == "tenor_months")["accepted"]
    assert acc["edited"] and acc["proposed"] == "84" and svc.get(app_id)["facility"]["tenor_months"] == 96


def test_only_the_sourcing_maker_can_prefill(svc):
    app_id, _ = _draft(svc)
    with pytest.raises(ForbiddenError):
        svc.run_prefill(app_id, svc.sign_in("u_cvp", "crp_vp"))
    apol = next(a for a in svc.list() if a["entity_id"] == "APOL001")
    with pytest.raises(ConflictError, match="Prospect"):
        svc.run_prefill(apol["application_id"], svc.sign_in("u_rm1", "ps_maker"))


def test_upload_is_pdf_only_and_never_overwrites(svc, docs_root):
    app_id, rm = _draft(svc)
    with pytest.raises(InvalidRequestError, match="Only PDF"):
        svc.upload_document(app_id, rm, "kyc", "gst.pdf", b"not a pdf")
    existing = (docs_root / "IHCL001" / "kyc" / "pan_card.pdf").read_bytes()
    out = svc.upload_document(app_id, rm, "kyc", "pan_card.pdf", existing)              # a new version, never an overwrite
    assert (docs_root / "IHCL001" / "kyc" / "pan_card.pdf").read_bytes() == existing
    assert (docs_root / "IHCL001" / "kyc" / "pan_card-2.pdf").exists()                   # versioned side-by-side
    assert "kyc/pan_card-2.pdf" in [d["document"] for d in out["documents"]]
    _pdf(docs_root.parent / "gst_reg.pdf", "GSTIN: 27AAACT5678H1Z5")
    out = svc.upload_document(app_id, rm, "kyc", "../gst reg.pdf", (docs_root.parent / "gst_reg.pdf").read_bytes())
    assert "kyc/gst_reg.pdf" in [d["document"] for d in out["documents"]]
    gstin = next(f for f in svc.run_prefill(app_id, rm)["prefill"]["fields"] if f["id"] == "gstin")
    assert gstin["value"] == "27AAACT5678H1Z5" and gstin["sources"][0]["document"] == "kyc/gst_reg.pdf"


# ─── IP Note ────────────────────────────────────────────────────────────────

def _to_ip_note(svc):
    from tests.test_los_workflow import _clear_dd
    app_id, rm = _draft(svc)
    _clear_dd(svc, app_id, rm)                                # the governed workspace gates the submission
    svc.run_prefill(app_id, rm)
    svc.apply_prefill(app_id, rm, [{"field_id": "pan"}, {"field_id": "collateral_mv_cr"},
                                   {"field_id": "collateral_fsv_cr"}])
    svc.act(app_id, rm, "submit")                             # ps_maker → IP Note (the RM holds it)
    app = svc.get(app_id)
    assert app["step"]["id"] == "ip_note"
    return app_id, svc.sign_in(app["assignee_id"], app["step"]["role"])


def test_ip_note_uses_accepted_values_and_prescreens_against_policy(svc):
    app_id, maker = _to_ip_note(svc)
    preview = svc.ip_note(app_id, maker)
    assert preview["preview"] and preview["can_generate"]
    note = svc.generate_ip_note(app_id, maker)["note"]
    pan = next(f for f in note["borrower"] if f["label"] == "PAN")
    assert pan["source"].startswith("kyc/pan_card.pdf p.2") and pan["provenance"] == "source"
    sec = {f["label"]: f["value"] for f in note["security"]}
    assert sec["FSV cover on proposed amount"] == "1.63x"                   # 1,960 / 1,200
    checks = {c["metric"]: c for c in note["prescreen"]["checks"]}
    assert checks["current_ratio"]["result"] == "breach" and checks["debt_to_ebitda"]["result"] == "pass"
    assert note["prescreen"]["outcome"].startswith("1 policy exception") and note["ai_status"] == "not requested"
    assert svc.get(app_id)["events"][0]["action"] == "ip_note" and svc.get(app_id)["ip_note"]["outcome"]


def test_ip_note_step_cannot_be_submitted_without_the_note(svc):
    app_id, maker = _to_ip_note(svc)
    with pytest.raises(InvalidRequestError, match="Generate the IP Note"):
        svc.act(app_id, maker, "submit")
    svc.generate_ip_note(app_id, maker, with_ai=False)
    assert svc.act(app_id, maker, "submit")["step"]["id"] == "ip_note_review"


def test_seeded_applications_past_the_ip_note_carry_one(svc):
    apol = next(a for a in svc.list() if a["entity_id"] == "APOL001")
    assert svc.get(apol["application_id"])["ip_note"]["seeded"] is True
    assert svc.ip_note(apol["application_id"])["generated"] is True


def test_ai_summary_is_number_guarded(ihcl):
    app = {"application_id": "X", "borrower_name": "IHCL", "facility": {}, "amount_cr": 1200.0}
    note = build_ip_note(app, ihcl, now=NOW)
    good = "The proposal for the borrower is supported by audited FY2025 revenue of 6,854 and a pre-screen within most thresholds."
    assert summarise(note, FakeLLM({"summary": good}))["provenance"] == "ai"
    with pytest.raises(ValueError, match="figures not in the note"):
        summarise(note, FakeLLM({"summary": good.replace("6,854", "7,412")}))
    assert "In-Principle Note" in render_html(note) and "CAM Report" not in render_html(note)


def test_prescreen_marks_missing_inputs_not_available():
    rows = prescreen(None, {"min_dscr": 1.2})
    assert all(r["result"] == "not_available" and r["provenance"] == "unavailable" for r in rows)


def test_api_sourcing_and_ip_note_endpoints(tmp_path):
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container
    container = build_container()
    container.los.seed_demo(force=True)
    http = TestClient(create_app(container))
    token = http.post("/api/los/session", json={"user_id": "u_rm1", "role": "ps_maker"}).json()["token"]
    h = {"X-LOS-Session": token}
    ihcl = next(a for a in http.get("/api/los/applications?q=IHCL", headers=h).json()["applications"])
    base = f"/api/los/applications/{ihcl['application_id']}"
    # The demo PDFs are not part of the repository: drop two of them into the container's documents
    # root for the duration of the test and clean them up afterwards.
    root = container.los.documents_root / "IHCL001"
    (root / "request").mkdir(parents=True, exist_ok=True)
    (root / "kyc").mkdir(parents=True, exist_ok=True)
    _pdf(root / "request" / "request_note.pdf",
         "The Indian Hotels Company Limited\nFacility Requested: term_loan\nCase Type: ETB\n"
         "Amount Requested: Rs 1,200 Cr\nTenor: 84 months\nPurpose: Renovation of Taj Palace Delhi")
    _pdf(root / "kyc" / "pan_card.pdf", "PAN: AAACT5678H\nLegal Name: The Indian Hotels Company Limited\n"
                                       "CIN: L74999MH1902PLC000183\nIncorporated: 01-Oct-1902")
    try:
        assert http.get(base + "/sourcing", headers=h).json()["can_edit"] is True
        r = http.post(base + "/prefill", headers=h)
        assert r.status_code == 200 and r.json()["prefill"]["summary"]["found"] > 0
        found = next(f["id"] for f in r.json()["prefill"]["fields"] if f["status"] in ("found", "conflict"))
        r = http.post(base + "/prefill/apply", headers=h, json={"items": [{"field_id": found}]})
        assert r.status_code == 200 and r.json()["accepted_count"] == 1
        r = http.post(base + "/documents", headers=h, data={"category": "kyc"},
                      files={"file": ("note.txt", b"hello", "text/plain")})
        assert r.status_code == 400
        assert http.get(base + "/ip-note", headers=h).json()["preview"] is True
        assert "In-Principle Note" in http.get(base + "/ip-note.html", headers=h).text
    finally:
        import shutil
        shutil.rmtree(container.los.documents_root / "IHCL001", ignore_errors=True)
