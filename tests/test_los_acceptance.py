"""R8 — sanction-letter acceptance: signed copy, version match, validity, review."""
from datetime import datetime, timedelta

import pytest

from src.application.errors import ConflictError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 7, 9, 9, 0, 0)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def sanctioned(svc, amount=100.0):
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "acceptance test"})
    svc._replay_to(a["application_id"], "pos_maker", NOW, NOW)
    return svc.store.get(a["application_id"])


def facs(a):
    return [{"facility_id": f["facility_id"], "execution_status": "executed",
             "agreement_date": NOW.date().isoformat()}
            for f in (a.get("facilities") or [a.get("facility") or {}])]


def test_acceptance_requires_the_signed_copy(tmp_path):
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    a = sanctioned(svc)
    sid = a["application_id"]
    posm = svc._system_session("pos_maker", a.get("assignee_id"), wf)
    svc.generate_letter(sid, posm, "sanction_letter")
    # consent without the signed copy is refused
    with pytest.raises(ConflictError, match="signed copy"):
        svc.record_consent(sid, posm, acknowledged_by="Customer (demo)",
                           consent_date=NOW.date().isoformat(), facilities=facs(svc.store.get(sid)))
    # and without the letter at all
    b = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 60.0, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "WC (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle", "mandatory_remarks": "x"})
    svc._replay_to(b["application_id"], "pos_maker", NOW, NOW)
    a2 = svc.store.get(b["application_id"])
    a2["letters"] = {}
    svc.store.save(a2)
    posm2 = svc._system_session("pos_maker", a2.get("assignee_id"), wf)
    with pytest.raises(ConflictError, match="Sanction Letter"):
        svc.record_consent(sid2 := b["application_id"], posm2, acknowledged_by="C",
                           consent_date=NOW.date().isoformat(), facilities=facs(a2))


def test_acceptance_records_version_and_method(tmp_path):
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    a = sanctioned(svc)
    sid = a["application_id"]
    posm = svc._system_session("pos_maker", a.get("assignee_id"), wf)
    svc.generate_letter(sid, posm, "sanction_letter")
    svc.upload_signed_letter(sid, posm, "sanction_letter", "signed-copy.pdf", b"%PDF-1.4 demo")
    v = svc.record_consent(sid, posm, acknowledged_by="Customer director (demo)",
                           consent_date=NOW.date().isoformat(), facilities=facs(svc.store.get(sid)),
                           raw_meta={"method": "signed copy (scanned)"})
    consent = svc.store.get(sid)["consent"]
    assert consent["acceptance"]["letter_version"] == 1
    assert consent["acceptance"]["method"] == "signed copy (scanned)"
    assert consent["acceptance"]["date"] == NOW.date().isoformat()


def test_consent_after_the_letter_validity_is_rejected(tmp_path):
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    a = sanctioned(svc)
    sid = a["application_id"]
    posm = svc._system_session("pos_maker", a.get("assignee_id"), wf)
    svc.generate_letter(sid, posm, "sanction_letter")
    a = svc.store.get(sid)
    # push the letter's validity into the past
    versions = a["letters"]["sanction_letter"]
    versions[-1]["valid_until"] = (NOW - timedelta(days=1)).date().isoformat()
    svc.store.save(a)
    posm = svc._system_session("pos_maker", a.get("assignee_id"), wf)
    svc.upload_signed_letter(sid, posm, "sanction_letter", "signed.pdf", b"%PDF-1.4 demo")
    with pytest.raises(InvalidRequestError, match="validity"):
        svc.record_consent(sid, posm, acknowledged_by="Customer (demo)",
                           consent_date=(NOW + timedelta(days=1)).date().isoformat(),
                           facilities=facs(svc.store.get(sid)))


def test_rejected_signed_copy_blocks_until_reupload(tmp_path):
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    a = sanctioned(svc)
    sid = a["application_id"]
    posm = svc._system_session("pos_maker", a.get("assignee_id"), wf)
    svc.generate_letter(sid, posm, "sanction_letter")
    svc.upload_signed_letter(sid, posm, "sanction_letter", "blurry.pdf", b"%PDF-1.4 demo")
    svc.review_signed_letter(sid, posm, "sanction_letter", "rejected", "Illegible signature (demo)")
    with pytest.raises(ConflictError, match="rejected"):
        svc.record_consent(sid, posm, acknowledged_by="Customer (demo)",
                           consent_date=NOW.date().isoformat(), facilities=facs(svc.store.get(sid)))
    # re-upload clears the block
    svc.upload_signed_letter(sid, posm, "sanction_letter", "signed-2.pdf", b"%PDF-1.4 demo v2")
    v = svc.record_consent(sid, posm, acknowledged_by="Customer (demo)",
                           consent_date=NOW.date().isoformat(), facilities=facs(svc.store.get(sid)))
    assert v is not None


def test_signed_copy_must_match_the_current_letter_version(tmp_path):
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    a = sanctioned(svc)
    sid = a["application_id"]
    posm = svc._system_session("pos_maker", a.get("assignee_id"), wf)
    svc.generate_letter(sid, posm, "sanction_letter")          # v1
    svc.upload_signed_letter(sid, posm, "sanction_letter", "v1-signed.pdf", b"%PDF-1.4 v1")
    # a fresh issue (v2) makes the old signed copy outdated
    svc.generate_letter(sid, posm, "sanction_letter")          # v2
    a = svc.store.get(sid)
    sc = a["letters"]["sanction_letter_signed"]
    assert sc["letter_version"] == 1
    with pytest.raises(InvalidRequestError, match="version"):
        svc.record_consent(sid, posm, acknowledged_by="Customer (demo)",
                           consent_date=NOW.date().isoformat(), facilities=facs(a))
