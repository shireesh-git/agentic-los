"""Sprint 3: the document intake agent, new prospects sourced from documents, and the
preparation agent's parallel lanes."""

import threading
import time
from datetime import datetime

import fitz
import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.core.llm_provider import BaseLLMProvider
from src.data.company_catalog import seed_company_store
from src.los import intake
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.services.document_store import DocumentStore

NOW = datetime(2026, 10, 8, 12, 0, 0)
ZETA_ID = ("Legal Name: Zeta Foods Private Limited CIN: U15400MH2015PTC123456 PAN: AAACZ1234Q "
           "Incorporated: 12-Mar-2015 Registered Office: Plot 7, MIDC Andheri East, Mumbai 400093")
ZETA_REQUEST = ("Facility Requested: working_capital\nCase Type: NTB\nAmount Requested: Rs 45 Cr\n"
                "Tenor: 12 months\nPurpose: Working capital for the Pune plant")


def _pdf(path, *pages, scanned=False):
    """A PDF with text pages; ``scanned`` pages carry the text only as an image (no text layer)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for text in pages:
        if scanned:
            src = fitz.open()
            p = src.new_page()
            p.insert_text((40, 60), text[:90], fontsize=9)
            pix = p.get_pixmap(dpi=72)
            page = doc.new_page()
            page.insert_image(page.rect, pixmap=pix)
        else:
            page = doc.new_page()
            page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=9)
    doc.save(path)
    doc.close()


def _f(prefill, fid):
    return next(f for f in prefill["fields"] if f["id"] == fid)


class VisionLLM(BaseLLMProvider):
    """Transcribes any image to a fixed text; extracts nothing. Counts concurrent calls."""
    name, supports_vision = "fake-vision", True

    def __init__(self, transcript):
        self.transcript, self.calls, self.peak, self._now = transcript, 0, 0, 0
        self._lock = threading.Lock()

    def generate(self, prompt, system_prompt="", temperature=None, max_tokens=None, images=None):
        with self._lock:
            self.calls += 1
            self._now += 1
            self.peak = max(self.peak, self._now)
        time.sleep(0.05)
        with self._lock:
            self._now -= 1
        if images:
            return '{"text": "%s"}' % self.transcript
        return '{"fields": []}'

    def test_connection(self):
        return {"status": "ok"}


# ── the intake agent ─────────────────────────────────────────────────────────

def test_intake_reads_documents_in_parallel_and_corroborates(tmp_path):
    root = tmp_path / "docs"
    _pdf(root / "request" / "request_letter.pdf", ZETA_REQUEST)
    _pdf(root / "kyc" / "incorporation.pdf", "Certificate", ZETA_ID)
    _pdf(root / "kyc" / "pan_card.pdf", "PAN: AAACZ1234Q CIN: U15400MH2015PTC123456")
    p = intake.run_intake(root, {})
    assert p["intake"]["documents"] == 3 and p["intake"]["max_concurrency"] >= 2
    cin = _f(p, "cin")
    assert cin["value"] == "U15400MH2015PTC123456" and cin["status"] == "corroborated"
    assert {s["document"] for s in cin["sources"]} == {"kyc/incorporation.pdf", "kyc/pan_card.pdf"}
    assert _f(p, "legal_name")["sources"][0]["page"] == 2                       # cited to the page
    assert _f(p, "amount_cr")["value"] == 45.0 and _f(p, "facility_type")["value"] == "working_capital"
    assert _f(p, "revenue_cr")["status"] == "not_found"                         # never invented


def test_proposals_carry_document_evidence_and_conflicts_are_flagged(tmp_path):
    root = tmp_path / "docs"
    _pdf(root / "request" / "a.pdf", "Amount Requested: Rs 45 Cr")
    _pdf(root / "request" / "b.pdf", "Amount Requested: Rs 60 Cr")
    props = {p["field_id"]: p for p in intake.proposals_from_prefill(intake.run_intake(root, {}))}
    amount = props["sourcing.proposal.amount_cr"]
    assert amount["source"] == "document" and amount["evidence"]["page"] == 1 and amount["evidence"]["document"]
    assert amount["issues"] and "disagree" in amount["issues"][0]
    assert props["sourcing.borrower.pan"]["provenance"] == "unavailable"


def test_scanned_pages_need_a_vision_model(tmp_path):
    root = tmp_path / "docs"
    _pdf(root / "kyc" / "scan.pdf", "scan one", "scan two", scanned=True)
    p = intake.run_intake(root, {})
    assert p["intake"]["scanned_pages"] == 2 and p["intake"]["vision_pages"] == 0
    assert p["intake"]["unread_pages"] and "vision model" in p["intake"]["note"]
    llm = VisionLLM(ZETA_ID)
    p = intake.run_intake(root, {}, llm)
    assert p["intake"]["vision_pages"] == 2 and not p["intake"]["unread_pages"]
    assert _f(p, "pan")["value"] == "AAACZ1234Q" and _f(p, "pan")["sources"][0]["document"] == "kyc/scan.pdf"
    assert llm.peak >= 2                                                       # pages transcribed in parallel


def test_ai_fallback_keeps_only_values_found_verbatim(tmp_path):
    root = tmp_path / "docs"
    _pdf(root / "request" / "letter.pdf", "Our company GSTIN is 27AAACZ1234Q1Z5 for Maharashtra. Facility Requested: term_loan")

    class Extractor(VisionLLM):
        def generate(self, prompt, system_prompt="", temperature=None, max_tokens=None, images=None):
            return ('{"fields": [{"id": "gstin", "value": "27AAACZ1234Q1Z5", "document": "request/letter.pdf", "page": 1},'
                    ' {"id": "pan", "value": "AAACZ9999Z", "document": "request/letter.pdf", "page": 1}]}')

    p = intake.run_intake(root, {}, Extractor(""))
    assert _f(p, "gstin")["value"] == "27AAACZ1234Q1Z5" and _f(p, "gstin")["method"] == "ai"
    assert _f(p, "pan")["status"] == "not_found"                               # not on the page: rejected
    assert p["ai"]["used"] is True


# ── new prospect from documents ──────────────────────────────────────────────

@pytest.fixture()
def svc(tmp_path):
    root = tmp_path / "documents"
    root.mkdir()
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         documents_root=root, doc_store=DocumentStore(root))
    service.seed_demo()
    return service


@pytest.fixture()
def rm(svc):
    return svc.sign_in("u_rm1", "ps_maker")


def _stage(svc, rm, tmp_path):
    a, b = tmp_path / "in" / "request_letter.pdf", tmp_path / "in" / "incorporation.pdf"
    _pdf(a, ZETA_REQUEST)
    _pdf(b, ZETA_ID)
    sid = svc.stage_document(rm, "request", a.name, a.read_bytes())["staging_id"]
    return svc.stage_document(rm, "kyc", b.name, b.read_bytes(), staging_id=sid)["staging_id"]


DECISION = {"decision": "Refer for in-principle", "mandatory_remarks": "New prospect sourced from its documents."}


def _create(svc, rm, sid, **identity):
    ident = {"company_name": "Zeta Foods Private Limited", "cin": "U15400MH2015PTC123456", "pan": "AAACZ1234Q",
             "date_of_incorporation": "2015-03-12", "sector": "manufacturing", **identity}
    return svc.create_prospect(rm, staging_id=sid, identity=ident, sourcing_decision=DECISION,
                               facilities=[{"facility_type": "working_capital", "amount_cr": 45, "tenor_months": 12,
                                            "purpose": "Working capital"}], prepare=False)


def test_read_staged_proposes_identity_facility_and_checks_duplicates(svc, rm, tmp_path):
    sid = _stage(svc, rm, tmp_path)
    out = svc.read_staged(rm, sid)
    assert out["identity"]["legal_name"]["value"] == "Zeta Foods Private Limited"
    assert out["identity"]["pan"]["source"]["document"] == "kyc/incorporation.pdf"
    assert out["facility"]["amount_cr"]["value"] == 45.0 and out["matches"] == []
    with pytest.raises(ForbiddenError):
        svc.read_staged(svc.sign_in("u_ra1", "risk_analyst"), sid)


def test_create_prospect_registers_the_borrower_without_invented_identifiers(svc, rm, tmp_path):
    sid = _stage(svc, rm, tmp_path)
    app = _create(svc, rm, sid, cin=None, date_of_incorporation=None)
    eid = app["entity_id"]
    b = svc.companies[eid]["borrower"]
    assert eid.startswith("ZETA") and b.pan == "AAACZ1234Q"
    assert b.cin is None and b.date_of_incorporation is None and b.registered_address is None
    assert svc.companies[eid]["financials"] == {}                          # no statements until real ones
    assert app["step_id"] == "ps_maker" and app["events"][0]["action"] == "prospect_sourced"
    assert {d["document"] for d in svc._documents_on_file(eid)} == {"request/request_letter.pdf",
                                                                    "kyc/incorporation.pdf"}
    assert not svc._staging_dir(sid).exists()                             # staging is cleared


def test_duplicates_are_refused_or_need_confirmation(svc, rm, tmp_path):
    ihcl = svc.companies["IHCL001"]["borrower"]
    sid = _stage(svc, rm, tmp_path)
    with pytest.raises(ConflictError, match="already on record as IHCL001"):
        _create(svc, rm, sid, pan=ihcl.pan, cin=None)
    with pytest.raises(ConflictError, match="same name"):
        _create(svc, rm, sid, company_name=ihcl.company_name, pan=None, cin=None)
    app = svc.create_prospect(rm, staging_id=sid, identity={"company_name": ihcl.company_name, "sector": "hospitality"},
                              facilities=[{"facility_type": "term_loan", "amount_cr": 10}],
                              sourcing_decision=DECISION, confirm_not_duplicate=True, prepare=False)
    assert app["entity_id"] != "IHCL001"
    with pytest.raises(InvalidRequestError, match="PAN"):
        _create(svc, rm, _stage(svc, rm, tmp_path), pan="NOTAPAN")


def test_preparation_agent_runs_lanes_in_parallel_and_populates_sourcing(svc, rm, tmp_path):
    sid = _stage(svc, rm, tmp_path)
    app_id = _create(svc, rm, sid)["application_id"]
    svc.prepare_application(app_id, rm, wait=True)
    job = svc.wait_for_preparation(app_id)
    assert job["state"] == "done", job.get("error")
    assert {lane["lane"] for lane in job["lanes"]} == {"identity", "checks", "intake"}
    assert job["summary"]["max_concurrency"] >= 3                         # lanes and checks side by side
    s = svc.sourcing(app_id, rm)
    assert s["prefill"]["summary"]["found"] >= 8 and s["fields"]["total"] == 21
    assert s["fields"]["populated"] >= 8 and s["fields"]["confirmed"] == 0
    dd = svc.due_diligence(app_id, rm)
    assert all(c["status"] != "pending" for c in dd["checks"] if c["mode"] == "api")
    app = svc.get(app_id)
    assert app["events"][0]["action"] == "application_prepared"
    assert app["fields"]["sourcing.borrower.pan"]["proposal"]["evidence"]["document"] == "kyc/incorporation.pdf"


def test_accepting_the_prefill_is_recorded_in_the_field_store(svc, rm, tmp_path):
    sid = _stage(svc, rm, tmp_path)
    app_id = _create(svc, rm, sid)["application_id"]
    svc.run_prefill(app_id, rm)
    svc.apply_prefill(app_id, rm, [{"field_id": "pan"},
                                   {"field_id": "amount_cr", "value": "50", "reason": "Revised request by phone"}])
    s = svc.sourcing(app_id, rm)
    assert s["fields"]["confirmed"] == 1 and s["fields"]["overridden"] == 1
    assert s["fields"]["accepted_unchanged_pct"] == 50.0
    fields = svc.get(app_id)["fields"]
    assert fields["sourcing.proposal.amount_cr"]["value"] == "50"
    assert svc.get(app_id)["facility"]["amount_cr"] == 50.0


def test_run_all_checks_runs_in_parallel_with_one_event_each(svc, rm):
    app = next(a for a in svc.list() if a["entity_id"] == "IHCL001")
    rm1 = svc.sign_in(app["assignee_id"], "ps_maker")
    pending = [c["id"] for c in svc.due_diligence(app["application_id"], rm1)["checks"]
               if c["mode"] == "api" and c["status"] != "clear"]
    svc.run_due_diligence(app["application_id"], rm1)
    events = [e for e in svc.get(app["application_id"])["events"] if e["action"] == "dd_trigger"]
    assert len(events) >= len(pending) and pending
