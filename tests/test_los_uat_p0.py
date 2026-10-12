"""UAT-P0 fixes verified end to end:
1. due-diligence comments persist across a server reload;
2. re-running a check invalidates its approved Compliance VP exception;
3. a mandatory check returning 'unavailable' is controlled (Compliance VP approval required);
4. prospect-sourcing validation (decision + applicable remarks mandatory, Customer ID
   validated against the available core-banking results).
"""

from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.services.document_store import DocumentStore

NOW = datetime(2026, 10, 8, 12, 0, 0)
DEC = {"decision": "Refer for in-principle", "mandatory_remarks": "Test — refer to in-principle"}


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "los.sqlite3"


def make_svc(db_path):
    docs_root = db_path.parent / "docs"
    return LosService(LosStore(db_path), load_workflow, seed_company_store(), clock=lambda: NOW,
                      documents_root=docs_root, doc_store=DocumentStore(docs_root))


def sign(svc, user, role):
    return svc.sign_in(user, role)


def _create(svc, entity="MFL001"):
    return svc.create(sign(svc, "u_rm1", "ps_maker"), entity_id=entity, sourcing_decision=DEC)


# ─── 1. Comments persist ────────────────────────────────────────────────────

def test_dd_comments_survive_a_reload(db_path):
    svc = make_svc(db_path)
    app_id = _create(svc)["application_id"]
    rm = sign(svc, "u_rm1", "ps_maker")
    svc.record_check(app_id, rm, "kyc", "clear", "POI verified")
    svc.comment_check(app_id, rm, "kyc", "First remark — POI and POA cross-checked")
    svc.comment_check(app_id, rm, "mca", "Awaiting the charge register")
    # Simulate a server reload: a brand-new service instance over the same database.
    svc2 = make_svc(db_path)
    d = svc2.due_diligence(app_id, sign(svc2, "u_rm1", "ps_maker"))
    kyc = next(c for c in d["checks"] if c["id"] == "kyc")
    mca = next(c for c in d["checks"] if c["id"] == "mca")
    assert [c["text"] for c in kyc["comments"]] == ["First remark — POI and POA cross-checked"]
    assert [c["text"] for c in mca["comments"]] == ["Awaiting the charge register"]
    # The audit trail also carries the comment event.
    assert any(e["action"] == "dd_comment" for e in svc2.get(app_id, sign(svc2, "u_rm1", "ps_maker"))["events"])


# ─── 2. Exceptions are invalidated when the check is re-run ─────────────────

def test_rerunning_a_check_invalidates_its_vp_exception(db_path):
    svc = make_svc(db_path)
    app_id = _create(svc, "IHCL001")["application_id"]
    rm = sign(svc, "u_rm1", "ps_maker")
    compvp = sign(svc, "u_compvp", "compliance_vp")
    # IHCL's name screening is a mandatory PEP match; the Compliance VP releases it.
    svc.run_due_diligence(app_id, rm)
    svc.exception_check(app_id, compvp, "name_screening", "Close associate — verified, low risk")
    pep = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "name_screening")
    assert pep["status"] == "matched" and pep["exception"]
    # Re-screening invalidates the exception: the new result must be reviewed again.
    svc.trigger_check(app_id, rm, "name_screening")
    pep = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "name_screening")
    assert pep["exception"] is None and pep["status"] == "matched"
    assert pep["exception_history"][0]["invalidated_by"] == "Ananya Rao"
    assert "re-triggered" in pep["exception_history"][0]["reason"]
    # The block is back until the VP approves a fresh exception.
    from src.los import verification as dd
    assert any(c["id"] == "name_screening" for c in dd.blocking(svc.store.get(app_id)["due_diligence"]["checks"]))
    svc.exception_check(app_id, compvp, "name_screening", "Re-screened against the updated list")
    pep = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "name_screening")
    assert pep["exception"]
    assert not any(c["id"] == "name_screening"
                   for c in dd.blocking(svc.store.get(app_id)["due_diligence"]["checks"]))

    # The same invalidation applies when a manual check is re-recorded.
    svc.record_check(app_id, rm, "crilc", "matched", "Large-credit match found")
    svc.exception_check(app_id, compvp, "crilc", "Match explained — group internal facility")
    svc.record_check(app_id, rm, "crilc", "clear", "Re-verified with the borrower's confirmations")
    crilc = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "crilc")
    assert crilc["exception"] is None and len(crilc["exception_history"]) == 1


def test_exception_rejected_for_clear_or_pending_checks(db_path):
    svc = make_svc(db_path)
    app_id = _create(svc)["application_id"]
    compvp = sign(svc, "u_compvp", "compliance_vp")
    rm = sign(svc, "u_rm1", "ps_maker")
    with pytest.raises(ForbiddenError, match="Compliance VP"):
        svc.exception_check(app_id, rm, "mca", "no")
    with pytest.raises(ConflictError, match="applies to a matched, failed or unavailable check"):
        svc.exception_check(app_id, compvp, "mca", "pending check — no exception")
    with pytest.raises(InvalidRequestError, match="reason"):
        svc.exception_check(app_id, compvp, "mca", "  ")


# ─── 3. Unavailable mandatory checks are controlled ─────────────────────────

def test_unavailable_mandatory_check_requires_vp_approval(db_path):
    from src.los import verification as dd
    svc = make_svc(db_path)
    app_id = _create(svc)["application_id"]
    rm = sign(svc, "u_rm1", "ps_maker")
    compvp = sign(svc, "u_compvp", "compliance_vp")
    # CRIF returns 'unavailable' in the demo (provider not connected). The client has designated
    # bureau coverage as mandatory for this borrower, so the control must engage.
    app = svc.store.get(app_id)
    next(c for c in app["due_diligence"]["checks"] if c["id"] == "crif")["mandatory"] = True
    svc.store.save(app)
    svc.trigger_check(app_id, rm, "crif")
    crif = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "crif")
    assert crif["status"] == "unavailable"
    # It blocks progression — never silently treated as clear.
    blocked = dd.blocking(svc.store.get(app_id)["due_diligence"]["checks"])
    assert any(c["id"] == "crif" for c in blocked)
    with pytest.raises(InvalidRequestError, match="mandatory due-diligence"):
        svc.act(app_id, rm, "submit")
    # The Compliance VP approval (with a reason) is the release.
    svc.exception_check(app_id, compvp, "crif", "CIBIL coverage accepted for this grade — CRIF not required")
    assert not any(c["id"] == "crif" for c in dd.blocking(svc.store.get(app_id)["due_diligence"]["checks"]))
    # A non-VP cannot release it.
    svc.trigger_check(app_id, rm, "crif")                      # re-run invalidates the approval
    with pytest.raises(ForbiddenError, match="Compliance VP"):
        svc.exception_check(app_id, rm, "crif", "cannot approve")


def test_unavailable_non_mandatory_checks_stay_non_blocking(db_path):
    from src.los import verification as dd
    svc = make_svc(db_path)
    app_id = _create(svc)["application_id"]
    rm = sign(svc, "u_rm1", "ps_maker")
    svc.trigger_check(app_id, rm, "crif")                      # mandatory=False by default
    assert not any(c["id"] == "crif" for c in dd.blocking(svc.store.get(app_id)["due_diligence"]["checks"]))


# ─── 4. Prospect sourcing validation ────────────────────────────────────────

def test_sourcing_decision_and_remarks_are_mandatory(db_path):
    svc = make_svc(db_path)
    rm = sign(svc, "u_rm1", "ps_maker")
    with pytest.raises(InvalidRequestError, match="sourcing decision is required"):
        svc.create(rm, entity_id="ABCE001")
    with pytest.raises(InvalidRequestError, match="Sourcing decision must be one of"):
        svc.create(rm, entity_id="ABCE001", sourcing_decision={"decision": "Hold"})
    with pytest.raises(InvalidRequestError, match="Mandatory remarks are required"):
        svc.create(rm, entity_id="ABCE001", sourcing_decision={"decision": "Refer for in-principle"})
    with pytest.raises(InvalidRequestError, match="conditional remarks"):
        svc.create(rm, entity_id="ABCE001",
                   sourcing_decision={"decision": "Defer", "mandatory_remarks": "cashflow watch"})
    app = svc.create(rm, entity_id="ABCE001",
                     sourcing_decision={"decision": "Defer", "mandatory_remarks": "cashflow watch",
                                        "conditional_remarks": "revisit after the Q3 close"})
    assert app["sourcing_decision"]["decision"] == "Defer"
    assert app["sourcing_decision"]["conditional_remarks"] == "revisit after the Q3 close"


def test_customer_id_is_validated_against_the_core_banking_results(db_path):
    svc = make_svc(db_path)
    rm = sign(svc, "u_rm1", "ps_maker")
    # IHCL001 is on the core-banking book (ETB): its CIF is the only selectable result.
    with pytest.raises(InvalidRequestError, match="not among the available core-banking"):
        svc.create(rm, entity_id="IHCL001", sourcing_decision=DEC, customer_id_selection="CIF-99999")
    app = svc.create(rm, entity_id="IHCL001", sourcing_decision=DEC, customer_id_selection="CIF-IHCL001")
    assert app["sourcing_decision"]["customer_id_selection"] == "CIF-IHCL001"
    # MFL001 is new-to-bank: no Customer ID exists, so any existing-CIF selection is rejected.
    with pytest.raises(InvalidRequestError, match="new-to-bank"):
        svc.create(rm, entity_id="MFL001", sourcing_decision=DEC, customer_id_selection="CIF-MFL001")
    app2 = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC)
    assert app2["sourcing_decision"]["customer_id_selection"] is None
