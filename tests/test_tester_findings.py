"""Regressions for the tester's findings (UI walkthrough, Oct 2026):

- an existing CAM assessed for another request (the catalogue's ₹1,200 Cr) is not pinned to a ₹30 Cr application;
- an amount accepted from a document keeps the facility's proposed figure in step and makes the CAM re-run;
- a new prospect's accepted financials (net worth, debt) reach the credit engine; EBIT is derived, not zero;
- mandatory documents block Prospect Sourcing until they are on file and reviewed;
- the Disbursement Checker / Final Approver checklists exist from the start and tick and untick;
- a Disbursement Memo that no longer matches the record blocks the maker.
"""

from datetime import date

import pytest

from src.agents.financial_overrides import _statement_from_upload
from src.application.container import build_container
from src.devtools.demo_documents import write_set
from tests.test_los_workflow import _clear_dd, sign
from tests.test_poc_golden_and_e2e import DEC

def _svc():
    return build_container().los


def _app(svc, rm, amount, cam=None, entity="IHCL001"):
    app = svc.create(rm, entity_id=entity, sourcing_decision=DEC, cam=cam,
                     facilities=[{"facility_type": "term_loan", "facility_nature": "fund_based", "amount_cr": amount,
                                  "tenor_months": 36, "purpose": "Renovation"}])
    if cam:
        job = svc.wait_for_preparation(app["application_id"])
        assert job.get("state") == "done", job
    return app["application_id"]


def test_a_workspace_cam_for_another_request_is_regenerated_for_this_one():
    svc = _svc()
    svc.cases.run("IHCL001")                                       # the catalogue request: ₹1,200 Cr
    rm = svc.sign_in("u_rm1", "ps_maker")
    aid = _app(svc, rm, 30, cam={"mode": "workspace"})
    a = svc._require(aid)
    assert a["cam_source"]["mode"] == "generate" and "₹1,200.00 Cr" in a["cam_source"]["reason"]
    ca = a["credit_assessment"]
    assert (ca["requested_cr"], a["amount_cr"]) == (30.0, 30.0)


def _restore_documents(svc, entity_id):
    """Other tests may move a borrower's files in the shared test storage: put the repository's set back."""
    import shutil
    from pathlib import Path
    target = svc._entity_dir(entity_id)
    shutil.copytree(Path(__file__).resolve().parents[1] / "storage" / "documents" / entity_id, target, dirs_exist_ok=True)


def test_an_amount_accepted_from_a_document_moves_the_proposal_and_reruns_the_cam():
    svc = _svc()
    _restore_documents(svc, "IHCL001")                    # the request letter (₹1,200 Cr) must be on file
    svc.cases.run("IHCL001")
    rm = svc.sign_in("u_rm1", "ps_maker")
    aid = _app(svc, rm, 30, cam={"mode": "workspace"})
    field = next(f for f in svc.sourcing(aid, rm)["prefill"]["fields"] if f["id"] == "amount_cr")
    assert field["value"] == 1200 and field["status"] == "conflict"          # the request letter says ₹1,200 Cr
    svc.apply_prefill(aid, rm, [{"field_id": "amount_cr"}])
    a = svc._require(aid)
    assert a["amount_cr"] == 1200 and a["facilities"][0]["proposed_cr"] == 1200
    assert "₹30.00 Cr" in svc.get(aid)["assessment_stale"]               # flagged until the agents re-assess
    _clear_dd(svc, aid, rm)
    svc.act(aid, rm, "submit", comment="Sourcing complete")
    svc.prepare_application(aid, rm, wait=True)                          # the IP Note: same RM
    svc.wait_for_preparation(aid)
    a = svc._require(aid)
    assert a["credit_assessment"]["requested_cr"] == 1200 and not svc.get(aid)["assessment_stale"]


def test_a_prospects_accepted_financials_reach_the_credit_engine(tmp_path):
    svc = _svc()
    root = tmp_path / "docs"
    write_set(root)
    rm = svc.sign_in("u_rm1", "ps_maker")
    sid = None
    for rel in ("request/request_letter.pdf", "kyc/certificate_of_incorporation.pdf",
                "financials/audited_financials_fy2025.pdf"):
        sid = svc.stage_document(rm, rel.split("/")[0], rel.split("/")[1], (root / rel).read_bytes(), sid)["staging_id"]
    read = svc.read_staged(rm, sid)
    app = svc.create_prospect(rm, staging_id=sid, sourcing_decision=DEC, cam={"mode": "generate"},
                              identity={"company_name": "Zeta Foods Findings Private Limited", "pan": "AAACZ7777Q",
                                        "sector": "manufacturing", "cin": "U15400MH2015PTC777777"},
                              confirm_not_duplicate=True,
                              facilities=[{"facility_type": "working_capital", "amount_cr": 45, "tenor_months": 12,
                                           "purpose": "Working capital"}])
    aid = app["application_id"]
    svc.wait_for_preparation(aid)
    fields = svc.sourcing(aid, rm)["prefill"]["fields"]
    svc.apply_prefill(aid, rm, [{"field_id": f["id"]} for f in fields
                                if f["value"] is not None and f["id"].endswith("_cr") and f["id"] != "amount_cr"])
    assert "net worth" in svc.get(aid)["assessment_stale"]
    _clear_dd(svc, aid, rm)
    svc.act(aid, rm, "submit", comment="Sourcing complete")
    svc.prepare_application(aid, rm, wait=True)
    svc.wait_for_preparation(aid)
    case = svc._app_case(svc._require(aid))[0]
    fy = case["fact_pack"]["financial_summary"]["periods"]["FY2025"]
    assert (fy["net_worth_cr"], fy["total_debt_cr"]) == (118.0, 96.0)
    assert case["reassessment"]["facility_recommendation"]["recommended_cr"] > 0


def test_ebit_is_derived_for_a_statement_read_from_an_upload():
    fs = _statement_from_upload("X", "FY2025", date(2025, 3, 31), "rm_upload_audited", None,
                                {"revenue_operating": 312.4, "ebitda": 41.2, "pat": 16.8, "pbt": 22.5, "finance_cost": 8.9})
    assert fs.line_items["ebit"] == 31.4 and fs.line_items["depreciation"] == 9.8


def test_mandatory_documents_block_prospect_sourcing_until_reviewed():
    svc = _svc()
    rm = svc.sign_in("u_rm1", "ps_maker")
    aid = _app(svc, rm, 100, entity="APOL001")
    svc.run_due_diligence(aid, rm)
    compvp = sign(svc, "u_compvp", "compliance_vp")
    for c in svc.due_diligence(aid, rm)["checks"]:
        if c["mode"] == "manual" and c["status"] == "pending":
            svc.record_check(aid, rm, c["id"], "clear", "Verified (test)")
    for c in svc.due_diligence(aid, rm)["checks"]:
        if c["status"] in ("matched", "failed") and not c.get("exception"):
            svc.exception_check(aid, compvp, c["id"], "Exception (test)")
    blocked = [b for b in svc.get(aid)["blockers"] if b["where"] == "documents"]
    assert blocked and "Mandatory documents" in blocked[0]["message"]
    with pytest.raises(Exception, match="Mandatory documents"):
        svc.act(aid, rm, "submit", comment="Sourcing complete")
    svc._seed_stage_docs(aid, "PS", svc.now())
    svc.act(aid, rm, "submit", comment="Sourcing complete")
    assert svc.get(aid)["step"]["id"] == "ip_note"


def test_disbursement_review_checklists_exist_from_the_start():
    from src.los import disops as do
    view = do.disops_view({"disops": {}})
    assert len(view["checker_review"]) == len(do.CHECKER_REVIEW_ITEMS)
    assert len(view["final_review"]) == len(do.FINAL_REVIEW_ITEMS)
    assert not any(i["done"] for i in view["checker_review"])


def test_a_memo_that_no_longer_matches_the_record_blocks_the_maker():
    from src.los import disops as do
    app = {"disops": {"cif": {"cif_no": "C1"}, "memo": None}}
    app["disops"]["memo"] = {"content_hash": do.memo_hash(app["disops"]), "reviewed": True}
    assert "regenerate" not in (do.maker_gate(app) or "")
    app["disops"]["beneficiaries"] = [{"name": "X"}]                  # the record changes after review
    assert "regenerate" in do.maker_gate(app)
    assert do.disops_view(app)["memo_stale"] is True


# ── the Compliance VP exception, requested from the step (user feedback, 17 Oct 2026) ─────────────────

def _matched_name_screening(svc, rm, aid):
    svc.run_due_diligence(aid, rm)
    app = svc._require(aid)
    c = next(c for c in app["due_diligence"]["checks"] if c["id"] == "name_screening")
    c.update(status="matched", detail="1 PEP hit on the demo reference list (test)")
    svc.store.save(app)
    return c


def test_the_rm_requests_an_exception_and_the_compliance_vp_sees_and_decides_it():
    svc = _svc()
    rm = svc.sign_in("u_rm1", "ps_maker")
    aid = _app(svc, rm, 100, entity="INFY001")
    _matched_name_screening(svc, rm, aid)
    copilot = {a["id"]: a for a in svc.copilot(aid, rm)["actions"]}
    assert "dd_exception" in copilot and not copilot["dd_exception"].get("tool")   # re-running cannot clear a hit
    with pytest.raises(Exception, match="why an exception"):
        svc.request_exception(aid, rm, "name_screening", " ")
    svc.request_exception(aid, rm, "name_screening", "Namesake: different DOB and nationality")
    msgs = [b["message"] for b in svc.get(aid, rm)["blockers"]]
    assert any("Waiting for the Compliance VP" in m for m in msgs)
    assert not any("Resolve the outstanding" in m and "Name screening" in m for m in msgs)
    cvp = sign(svc, "u_compvp", "compliance_vp")
    assert aid in [a["application_id"] for a in svc.list(cvp, mine=True)]           # in the Compliance VP's queue
    svc.decline_exception(aid, cvp, "name_screening", "Need the PEP list extract")
    c = next(c for c in svc._require(aid)["due_diligence"]["checks"] if c["id"] == "name_screening")
    assert c["exception_request"]["status"] == "declined" and aid not in [a["application_id"] for a in svc.list(cvp, mine=True)]
    svc.request_exception(aid, rm, "name_screening", "Extract attached: namesake")
    svc.exception_check(aid, cvp, "name_screening", "Namesake confirmed")
    c = next(c for c in svc._require(aid)["due_diligence"]["checks"] if c["id"] == "name_screening")
    assert c["exception_request"]["status"] == "approved" and c["exception"]
    assert not any("Name screening" in b["message"] for b in svc.get(aid, rm)["blockers"])


def test_a_copilot_task_says_whether_it_resolved_anything():
    svc = _svc()
    rm = svc.sign_in("u_rm1", "ps_maker")
    aid = _app(svc, rm, 100, entity="INFY001")
    out = svc.copilot_run(aid, rm, "run_due_diligence")
    assert out["outcome"] in ("resolved", "partial", "unchanged") and "still_open" in out
    assert out["message"].startswith("Run the pending API due-diligence checks: ")
    assert "Checks run" in out["detail"]


def test_the_los_page_script_parses():
    """A syntax error in los.js blanks the whole LOS page (it happened with an unescaped apostrophe)."""
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    script = Path(__file__).resolve().parents[1] / "src" / "ui" / "static" / "js" / "los" / "los.js"
    r = subprocess.run([node, "-e", "new Function(require('fs').readFileSync(process.argv[1], 'utf8'))", str(script)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
