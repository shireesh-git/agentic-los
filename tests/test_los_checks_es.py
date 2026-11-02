"""R5 — conditional due-diligence checks and E&S exceptions.

The institution's profile decides which of the due-diligence checks actually apply to
an application (constitution, entity type, product, sector, grade, amount, facility
nature), how long a recorded result stays valid, and whether the excluded-activity
(E&S) screen admits an exception decided by a configured authority. Client One's
behaviour is unchanged: no applicability conditions, no validity lapses, and an
excluded activity is a hard block.
"""
from datetime import datetime, timedelta

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los import esms as es
from src.los import verification as dd
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "checks & E&S test"}


def make_service(tmp_path, profile="dfi"):
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                     clock=lambda: NOW)
    from src.los import profiles
    profiles.set_active_profile(profile)
    return svc


def dd_app(svc, session, entity_id="KAVG001", facility=None, profile="dfi", **kw):
    return svc.create(session, entity_id=entity_id, profile=profile,
                      facility=facility or {"facility_type": "term_loan", "facility_nature": "fund_based",
                                            "proposal_type": "Fresh", "amount_cr": 100.0,
                                            "tenor_months": 24, "interest_rate": 11.5,
                                            "purpose": "Term loan (demo)"},
                      sourcing_decision=SOURCING, **kw)


def ps_session(svc):
    wf = svc.wf_for_profile("dfi")
    return svc._system_session("ps_maker", None, wf)


def _stage_docs(svc, sid):
    """The stage's mandatory documents on file and reviewed (demo history)."""
    import src.los.docreg as dreg
    app = svc.store.get(sid)
    v = NOW.isoformat(timespec="seconds")
    for d in app["documents"]:
        if d["mandatory_stage"] == "PS" and not d["versions"]:
            dreg.register_upload(app["documents"], name=d["name"], category="kyc", scope=d["scope"],
                                 file_name="demo.pdf", by_name="Demo seed", at=v)
            d.update(status="reviewed", reviewer="Demo seed", reviewed_at=v)
    svc.store.save(app)


# ── 1. applicability conditions ─────────────────────────────────────────────


def test_applicability_conditions_select_the_effective_checks(tmp_path):
    svc = make_service(tmp_path)
    a = dd_app(svc, ps_session(svc))                      # ₹100 Cr fund-based term loan
    dd_view = svc.due_diligence(a["application_id"], ps_session(svc))
    by_id = {x["id"]: x for x in dd_view["applicability"]}
    # the DFI's conditions: GSTIN only for fund-based tickets…
    assert by_id["gstin"]["applies"] is True
    # …EDD runs on energy and infrastructure tickets…
    assert by_id["edd"]["applies"] is True
    # …and the Central Fraud Registry run is reserved for large tickets
    assert by_id["cfr"]["applies"] is False
    assert "200" in (by_id["cfr"]["reason"] or "")
    for other in ("mca", "name_screening", "mlra"):
        assert by_id[other]["applies"] is True, other
    # a large ticket brings the CFP run in
    big = dd_app(svc, ps_session(svc), facility={"facility_type": "term_loan", "facility_nature": "fund_based",
                                                 "proposal_type": "Fresh", "amount_cr": 600.0,
                                                 "tenor_months": 24, "interest_rate": 11.5,
                                                 "purpose": "Term loan (demo)"})
    dd_view = svc.due_diligence(big["application_id"], ps_session(svc))
    assert {x["id"]: x["applies"] for x in dd_view["applicability"]}["cfr"] is True
    # a non-fund-based ticket drops the GSTIN check
    ntb = dd_app(svc, ps_session(svc), facility={"facility_type": "term_loan", "facility_nature": "non_fund_based",
                                                 "proposal_type": "Fresh", "amount_cr": 100.0,
                                                 "tenor_months": 24, "interest_rate": 11.5,
                                                 "purpose": "Bank guarantee (demo)"})
    dd_view = svc.due_diligence(ntb["application_id"], ps_session(svc))
    assert {x["id"]: x["applies"] for x in dd_view["applicability"]}["gstin"] is False


def test_waived_check_does_not_block_but_a_real_match_does(tmp_path):
    svc = make_service(tmp_path)
    a = dd_app(svc, ps_session(svc))
    sid = a["application_id"]
    s = ps_session(svc)
    # run the API checks — the waived CFP/EDD runs are not in the effective set
    # a pending mandatory check still blocks the PS submit
    dd_view = svc.due_diligence(sid, s)
    assert any("CRILC" in b for b in dd_view["blocking"])
    with pytest.raises(InvalidRequestError, match="due-diligence"):
        svc.act(sid, s, "submit", comment="PS complete (demo)")
    # run the API checks and record the manual ones; the stage documents go on file
    svc.run_due_diligence(sid, s)
    app = svc.store.get(sid)
    for c in app["due_diligence"]["checks"]:
        if c["mode"] == "manual":
            svc.record_check(sid, s, c["id"], "clear", "Recorded (demo)")
    _stage_docs(svc, sid)
    svc.act(sid, s, "submit", comment="PS complete (demo)")


def test_waived_mandatory_check_does_not_block(tmp_path):
    svc = make_service(tmp_path)
    a = dd_app(svc, ps_session(svc), entity_id="MFL001")     # manufacturing ticket
    sid = a["application_id"]
    s = ps_session(svc)
    svc.run_due_diligence(sid, s)
    app = svc.store.get(sid)
    for c in app["due_diligence"]["checks"]:
        if c["mode"] == "manual":
            svc.record_check(sid, s, c["id"], "clear", "Recorded (demo)")
    dd_view = svc.due_diligence(sid, s)
    by_id = {x["id"]: x for x in dd_view["applicability"]}
    # the energy/infrastructure EDD run does not apply to this manufacturing ticket —
    # it is left pending on purpose
    assert by_id["edd"]["applies"] is False
    app = svc.store.get(sid)
    for c in app["due_diligence"]["checks"]:
        if c["id"] == "edd":
            c.update(status="pending", detail=None)
    svc.store.save(app)
    dd_view = svc.due_diligence(sid, s)
    assert not any("Enhanced" in b or "EDD" in b for b in dd_view["blocking"])
    assert not dd_view["blocking"]
    _stage_docs(svc, sid)
    svc.act(sid, s, "submit", comment="PS complete (demo)")


# ── 2. per-check validity ───────────────────────────────────────────────────


def test_result_validity_lapses_and_rerun_clears(tmp_path):
    svc = make_service(tmp_path)
    a = dd_app(svc, ps_session(svc))
    sid = a["application_id"]
    s = ps_session(svc)
    # a registry result recorded at the walk's clock (64 days before this test's clock —
    # inside the DFI's 90-day name-screening validity, the MCA result is within 180)
    walk_at = NOW - timedelta(days=64)
    svc._replay_to(sid, "ps_maker", walk_at, walk_at)      # no-op target: seeds nothing
    app = svc.store.get(sid)
    svc._seed_due_diligence(sid, walk_at)
    app = svc.store.get(sid)
    for c in app["due_diligence"]["checks"]:
        if c["id"] not in ("name_screening", "mca") and c["mode"] == "manual":
            c.update(status="clear", detail="Recorded (demo)", last_triggered=NOW.isoformat(timespec="seconds"))
    svc.store.save(app)
    dd_view = svc.due_diligence(sid, s)
    exp = {x["id"]: x for x in dd_view["applicability"]}
    assert exp["name_screening"]["expires_at"] == (walk_at + timedelta(days=90)).date().isoformat()
    assert exp["mca"]["expired"] is False and exp["name_screening"]["expired"] is False
    # age the name-screening result past its 90-day validity
    app = svc.store.get(sid)
    for c in app["due_diligence"]["checks"]:
        if c["id"] == "name_screening":
            c["last_triggered"] = (NOW - timedelta(days=91)).isoformat(timespec="seconds")
    svc.store.save(app)
    dd_view = svc.due_diligence(sid, s)
    assert any("name screening" in b.lower() for b in dd_view["blocking"])
    # the re-run refreshes it
    svc.trigger_check(sid, s, "name_screening")
    dd_view = svc.due_diligence(sid, s)
    assert not any("name screening" in b.lower() for b in dd_view["blocking"])


# ── 3. E&S exceptions: request, decision, expiry, decline ───────────────────


def _dfi_project(svc, tmp_path, at=NOW):
    s = svc._system_session("ps_maker", None, svc.wf_for_profile("dfi"))
    a = svc.create(s, entity_id="KAVG001", profile="dfi",
                   facility={"facility_type": "project_finance", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 250.0, "tenor_months": 96,
                             "interest_rate": 12.0, "purpose": "Solar EPC project (demo)"},
                   sourcing_decision=SOURCING)
    svc._replay_to(a["application_id"], "ap_es_maker", at, at)
    return svc.store.get(a["application_id"])


def _screen_excluded(svc, sid):
    app = svc.store.get(sid)
    wf = svc.wf_for_profile(app["profile"])
    s = svc._system_session(wf.step(app["step_id"]).role, app.get("assignee_id"), wf)
    svc.update_esms(sid, s, {"screening_date": NOW.date().isoformat(),
                             "checklist": [{"id": "es_hazardous", "answer": "Yes",
                                            "remarks": "Ozone-depleting inputs in demo scope"}]})
    return s


def test_esms_exception_approved_releases_the_block(tmp_path):
    svc = make_service(tmp_path)
    app = _dfi_project(svc, tmp_path)
    sid = app["application_id"]
    s = _screen_excluded(svc, sid)
    # the excluded activity blocks the ES maker's submit
    esms = svc.store.get(sid)["esms"]
    assert es.esms_gate(esms, None, NOW) is not None
    # the institution's configured E&S authority (the DMD) decides — nobody else
    other = svc._system_session("crp_vp", None, svc.wf_for_profile("dfi"))
    svc.request_esms_exception(sid, s, "Hazardous inputs are contained and licensed (demo)")
    with pytest.raises(ForbiddenError, match="DMD"):
        svc.decide_esms_exception(sid, other, "approved", "Not your decision (demo)")
    dmd = svc._system_session("dmd", None, svc.wf_for_profile("dfi"))
    svc.decide_esms_exception(sid, dmd, "approved", "Controls verified; release for 180 days (demo)")
    app = svc.store.get(sid)
    exc = app["esms"]["exception"]
    assert exc["status"] == "approved" and exc["decided_by"]
    assert exc["expires_at"] == (NOW + timedelta(days=180)).isoformat(timespec="seconds")
    # the gate is released while the exception holds
    assert es.esms_gate(app["esms"], exc, NOW) is None
    events = [e["action"] for e in svc.store.events(sid, limit=200, asc=True)]
    assert "esms_exception_requested" in events and "esms_exception_approved" in events


def test_esms_exception_declined_or_lapsed_keeps_the_block(tmp_path):
    svc = make_service(tmp_path)
    app = _dfi_project(svc, tmp_path)
    sid = app["application_id"]
    s = _screen_excluded(svc, sid)
    svc.request_esms_exception(sid, s, "Request to be decided (demo)")
    dmd = svc._system_session("dmd", None, svc.wf_for_profile("dfi"))
    svc.decide_esms_exception(sid, dmd, "declined", "Excluded activity stands (demo)")
    app = svc.store.get(sid)
    msg = es.esms_gate(app["esms"], app["esms"]["exception"], NOW)
    assert msg and "declined" in msg
    # a lapsed approval blocks again
    app = svc.store.get(sid)
    app["esms"]["exception"].update(status="approved",
                                     expires_at=(NOW - timedelta(days=1)).isoformat(timespec="seconds"))
    svc.store.save(app)
    app = svc.store.get(sid)
    msg = es.esms_gate(app["esms"], app["esms"]["exception"], NOW)
    assert msg and "lapsed" in msg
    # a pending request blocks until the authority decides
    app["esms"]["exception"] = {"status": "pending", "at": NOW.isoformat(timespec="seconds")}
    assert es.esms_gate(app["esms"], app["esms"]["exception"], NOW) is not None


def test_client_one_excluded_activity_is_a_hard_block(tmp_path):
    from src.los import profiles
    profiles.set_active_profile("client_one")
    try:
        svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                         clock=lambda: NOW)
        s = svc._system_session("ps_maker", None, svc.wf_for_profile("client_one"))
        a = svc.create(s, entity_id="KAVG001", profile="client_one",
                       facility={"facility_type": "project_finance", "facility_nature": "fund_based",
                                 "proposal_type": "Fresh", "amount_cr": 250.0, "tenor_months": 96,
                                 "interest_rate": 12.0, "purpose": "Solar project (demo)"},
                       sourcing_decision=SOURCING)
        svc._replay_to(a["application_id"], "ap_es_maker", NOW, NOW)
        sid = a["application_id"]
        app = svc.store.get(sid)
        wf = svc.wf_for_profile("client_one")
        es_s = svc._system_session(wf.step(app["step_id"]).role, app.get("assignee_id"), wf)
        svc.update_esms(sid, es_s, {"screening_date": NOW.date().isoformat(),
                                    "checklist": [{"id": "es_hazardous", "answer": "Yes",
                                                   "remarks": "Excluded input (demo)"}]})
        with pytest.raises(ConflictError, match="does not allow exceptions"):
            svc.request_esms_exception(sid, es_s, "Should be refused (demo)")
        app = svc.store.get(sid)
        assert es.esms_gate(app["esms"], None, NOW) is not None
    finally:
        profiles.set_active_profile("client_one")
