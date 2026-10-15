"""S8: the CAM as an input to the LOS journey.

    workspace  a CAM already generated in the CAM workspace is pinned at creation and fills the
               IP fields at once (no second credit run at the IP Note)
    document   the bank's own CAM (PDF) is read by the CAM intake agent: narratives, terms,
               security, ratings and figures with section / page evidence; identity and facility
               come from the intake agent, which reads the CAM with the other documents
    generate   no CAM yet: the preparation agent generates it in a parallel lane and pins it
"""

from pathlib import Path

import pytest

from src.devtools.demo_documents import CAM_DOCUMENTS, GOLDEN, write_pdf, write_set
from src.los import cam_intake, intake
from tests.test_poc_golden_and_e2e import DEC, _holder

CAM_REL = "cam/credit_appraisal_memo.pdf"
FAC = {"facility_type": "term_loan", "facility_nature": "fund_based", "amount_cr": 100, "tenor_months": 60,
       "purpose": "Hospital expansion"}


@pytest.fixture
def svc():
    from src.application.container import build_container
    return build_container().los


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("cam_demo")
    write_set(root, include_cam=True)
    return root


def _stage(svc, rm, root: Path, rels, sid=None):
    for rel in rels:
        category, name = rel.split("/")
        sid = svc.stage_document(rm, category, name, (root / rel).read_bytes(), sid)["staging_id"]
    return sid


def _cam_pdf(path: Path, replace: dict) -> Path:
    pages = list(CAM_DOCUMENTS[CAM_REL]["pages"])
    for a, b in replace.items():
        pages = [p.replace(a, b) for p in pages]
    write_pdf(path, pages)
    return path


# ── the CAM intake agent ─────────────────────────────────────────────────────

def test_the_cam_intake_agent_reads_the_bank_cam(demo):
    r = cam_intake.read_cams(demo)
    assert set(GOLDEN["cam"]["sections"]) <= set(r["sections"]), set(GOLDEN["cam"]["sections"]) - set(r["sections"])
    wrong = {k: (r["labels"].get(k, {}).get("value"), v) for k, v in GOLDEN["cam"]["labels"].items()
             if r["labels"].get(k, {}).get("value") != v}
    assert not wrong, wrong
    risks = r["sections"]["key_risks"]
    assert risks["page"] == 3 and risks["text"].startswith("- Raw-material price volatility")
    props = cam_intake.proposals(r)
    assert all(p["evidence"]["document"] == CAM_REL and p["evidence"]["page"] >= 1 for p in props)
    assert {f"narrative.background.{k}" for k in cam_intake.NARRATIVE_KEYS} <= {p["field_id"] for p in props}


def test_the_cam_feeds_identity_and_facility_through_the_intake_agent(demo, tmp_path):
    (tmp_path / "cam").mkdir()
    (tmp_path / CAM_REL).write_bytes((demo / CAM_REL).read_bytes())
    got = {f["id"]: f["value"] for f in intake.run_intake(tmp_path, {})["fields"]}
    wrong = {k: (got.get(k), v) for k, v in GOLDEN["cam"]["sourcing"].items() if got.get(k) != v}
    assert not wrong, wrong                                   # incl. the PAN a scanned PAN card could not give


def test_an_unknown_heading_is_mapped_only_if_it_exists(tmp_path):
    class Llm:
        supports_structured, model_id = True, "fake"

        def generate_structured(self, prompt, schema, **kw):
            return {"map": [{"heading": "Promoter Track Record", "key": "corporate_governance"},
                            {"heading": "Invented Heading", "key": "industry_outlook"}]}

    pdf = tmp_path / "cam" / "x.pdf"
    write_pdf(pdf, ["Promoter Track Record\nThe promoters have run food businesses for 20 years.\n"
                    "Key Risks\n- Input costs."])
    r = cam_intake.read_cams(tmp_path, Llm())
    assert r["sections"]["corporate_governance"]["text"].startswith("The promoters")
    assert "industry_outlook" not in r["sections"] and r["ai"]["used"]


# ── start from a CAM ────────────────────────────────────────────────────────

def test_a_workspace_cam_is_pinned_and_fills_the_ip_fields_at_creation(svc):
    from tests.test_los_workflow import _clear_dd

    case, _ = svc.cases.run("APOL001")                           # generated earlier in the CAM workspace
    opts = svc.cam_options("APOL001")
    assert opts["workspace"]["run_id"] == case["run_id"] and opts["workspace"]["facility"]["amount_cr"]
    rm = svc.sign_in("u_rm1", "ps_maker")
    fac = opts["workspace"]["facility"]
    app = svc.create(rm, entity_id="APOL001", sourcing_decision=DEC, cam={"mode": "workspace"},
                     facilities=[{**FAC, "facility_type": fac["facility_type"], "amount_cr": fac["amount_cr"],
                                  "tenor_months": fac["tenor_months"]}])
    app_id = app["application_id"]
    assert app["credit_assessment"]["run_id"] == case["run_id"] and app["cam_source"]["mode"] == "workspace"
    domains = {r["domain"] for r in app["fields"].values() if r["status"] != "unavailable"}
    assert {"cma", "narrative", "rating", "securities"} <= domains, domains        # IP fields already at PS
    assert svc.wait_for_preparation(app_id)["state"] == "done"                    # PS agents started at once
    _clear_dd(svc, app_id, rm)
    svc.act(app_id, rm, "submit", comment="Sourcing complete")
    svc.prepare_application(app_id, _holder(svc, app_id), wait=True)              # IP Note: no second CAM run
    job = svc.wait_for_preparation(app_id)
    assert job["state"] == "done" and job["summary"]["credit_case_ran"] is False
    assert svc.get(app_id)["credit_assessment"]["run_id"] == case["run_id"]
    events = [e["action"] for e in svc.store.events(app_id)]
    assert "cam_attached" in events


def test_generate_the_cam_when_there_is_none(svc):
    rm = svc.sign_in("u_rm1", "ps_maker")
    assert svc.cam_options("MRF001")["workspace"] is None
    app = svc.create(rm, entity_id="MRF001", sourcing_decision=DEC, facilities=[FAC], cam={"mode": "generate"})
    job = svc.wait_for_preparation(app["application_id"])
    assert job["state"] == "done", job.get("error")
    assert "credit_case" in [x["lane"] for x in job["lanes"]]
    after = svc.get(app["application_id"])
    assert after["credit_assessment"]["run_id"] == job["summary"]["cam_generated"]
    assert after["credit_assessment"]["requested_cr"] == 100                       # the application's request
    assert any(r["domain"] == "cma" and r["status"] == "proposed" for r in after["fields"].values())


def test_a_new_prospect_from_its_documents_and_the_bank_cam(svc, demo):
    rm = svc.sign_in("u_rm1", "ps_maker")
    sid = _stage(svc, rm, demo, ["request/request_letter.pdf", "kyc/certificate_of_incorporation.pdf",
                                 "kyc/pan_card_scan.pdf", "financials/audited_financials_fy2025.pdf", CAM_REL])
    read = svc.read_staged(rm, sid)
    assert read["cam"]["summary"]["narratives"] == 7 and read["identity"]["pan"]["value"] == "AAACZ1234Q"
    amount = read["facility"]["amount_cr"]
    assert amount["status"] == "corroborated"                                     # the request letter and the CAM agree
    app = svc.create_prospect(rm, staging_id=sid, sourcing_decision=DEC, cam={"mode": "document"}, prepare=False,
                              # a distinct identity: the end-to-end journey registers Zeta Foods itself
                              identity={"company_name": "Zeta Snacks CAM Test Private Limited", "pan": "AAACZ9999Q",
                                        "sector": "manufacturing"},
                              facilities=[{"facility_type": "working_capital", "amount_cr": 45, "tenor_months": 12,
                                           "purpose": "Working capital for the Pune plant expansion"}])
    fields = svc.get(app["application_id"])["fields"]
    risks = fields["narrative.background.key_risks"]
    assert risks["proposal"]["resolver"] == "cam_document" and risks["proposal"]["evidence"]["page"] == 3
    assert fields["cam.profile.banking_arrangement"]["value"] == "Sole"
    assert app["proposal"]["background"]["key_risks"].startswith("- Raw-material")          # materialised
    # the IP Note preparation keeps the CAM's text over the engine's deterministic draft
    case, _ = svc.cases.run(app["entity_id"])
    svc._record_assessment(app["application_id"], case, {"id": "u_rm1", "role": "ps_maker"})
    svc.populate_fields(app["application_id"], force=True)
    after = svc.get(app["application_id"])["fields"]["narrative.background.key_risks"]
    assert after["value"] == risks["value"] and after["proposal"]["resolver"] == "cam_document"
    cam = svc.mis()["agents"]["cam"]
    assert cam["applications"]["document"] >= 1 and cam["populated"] >= 20


def test_a_cam_that_disagrees_is_flagged_not_trusted(svc, demo, tmp_path):
    rm = svc.sign_in("u_rm1", "ps_maker")
    bad = _cam_pdf(tmp_path / "bad.pdf", {"Proposed Limit: Rs 45 Cr": "Proposed Limit: Rs 50 Cr"})
    sid = _stage(svc, rm, demo, ["request/request_letter.pdf"])
    sid = svc.stage_document(rm, "cam", "credit_appraisal_memo.pdf", bad.read_bytes(), sid)["staging_id"]
    read = svc.read_staged(rm, sid)
    amount = read["facility"]["amount_cr"]
    assert amount["status"] == "conflict" and {a["value"] for a in amount["alternatives"]} & {"45", "50"}

    # an existing borrower: the CAM's revenue against the audited statements on record
    company = svc.companies["APOL001"]
    audited = max((fs for fs in company["financials"].values() if fs.source == "audited"), key=lambda fs: fs.period)
    rev = audited.line_items["revenue_operating"]
    b = company["borrower"]
    wrong = _cam_pdf(tmp_path / "apollo.pdf", {"Revenue from Operations 312.40": f"Revenue from Operations {rev * 1.2:.2f}",
                                               "AAACZ1234Q": b.pan, "U15400MH2015PTC123456": b.cin,
                                               "Zeta Foods Private Limited": b.company_name})
    sid = svc.stage_document(rm, "cam", "apollo_cam.pdf", wrong.read_bytes())["staging_id"]
    svc.read_staged(rm, sid)
    app = svc.create(rm, entity_id="APOL001", sourcing_decision=DEC, facilities=[FAC],
                     cam={"mode": "document", "staging_id": sid})
    rec = app["fields"]["cam.financials.revenue_cr"]
    assert rec["proposal"]["issues"] and "audited statements show" in rec["proposal"]["issues"][0]
    queue = svc.assessment(app["application_id"], rm)["verify"]["queue"]
    assert not any(i["field_id"] == "cam.financials.revenue_cr" and i.get("preticked") for i in queue)
    assert any(d.startswith("cam/") for d in [doc for x in app["documents"] for doc in
                                               [v.get("file_name") for v in x.get("versions") or []] if doc])


def test_a_cam_start_needs_a_valid_option(svc):
    from src.application.errors import ConflictError, InvalidRequestError

    rm = svc.sign_in("u_rm1", "ps_maker")
    with pytest.raises(InvalidRequestError):
        svc.create(rm, entity_id="MRF001", sourcing_decision=DEC, facilities=[FAC], cam={"mode": "telepathy"})
    with pytest.raises(ConflictError):                     # no CAM in the workspace for this borrower
        svc.create(rm, entity_id="INFY001", sourcing_decision=DEC, facilities=[FAC], cam={"mode": "workspace"})


def test_another_companys_cam_is_refused_before_anything_is_created(svc, demo):
    from src.application.errors import ConflictError

    rm = svc.sign_in("u_rm1", "ps_maker")
    sid = _stage(svc, rm, demo, [CAM_REL])                       # Zeta Foods' CAM ...
    svc.read_staged(rm, sid)
    before = len(svc.store.list())
    with pytest.raises(ConflictError, match="another company"):   # ... offered for Apollo
        svc.create(rm, entity_id="APOL001", sourcing_decision=DEC, facilities=[FAC],
                   cam={"mode": "document", "staging_id": sid})
    assert len(svc.store.list()) == before
