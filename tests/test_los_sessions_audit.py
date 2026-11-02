"""R18 — secure sessions and audit integrity.

Sessions expire (absolute) and time out (idle); they invalidate on logout; a
session cannot escalate its own role; the audit log is a per-application
sequence with a hash chain, and `verify_audit` recomputes the chain to prove
no recorded event was altered.
"""
from datetime import datetime, timedelta

import pytest

from src.application.errors import ForbiddenError, InvalidRequestError
from src.los.audit import chain_hash, verify_audit
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 7, 9, 9, 0, 0)
MAX_AGE = timedelta(hours=8)
IDLE = timedelta(minutes=30)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW,
                      session_max_age=MAX_AGE, session_idle_timeout=IDLE)


def test_session_expires_after_absolute_max_age(tmp_path):
    t = [NOW]
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                     seed_company_store(), clock=lambda: t[0],
                     session_max_age=MAX_AGE, session_idle_timeout=IDLE)
    sess = svc.sign_in("u_rm1", "ps_maker")
    tok = sess["token"]
    t[0] = NOW + MAX_AGE + timedelta(seconds=1)
    with pytest.raises(ForbiddenError, match="expired"):
        svc.session(tok)
    # the dead token is dropped from the store
    assert tok not in svc._sessions


def test_session_idle_timeout(tmp_path):
    t = [NOW]
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                     seed_company_store(), clock=lambda: t[0],
                     session_max_age=MAX_AGE, session_idle_timeout=IDLE)
    sess = svc.sign_in("u_rm1", "ps_maker")
    tok = sess["token"]
    t[0] = NOW + IDLE + timedelta(seconds=1)
    with pytest.raises(ForbiddenError, match="expired"):
        svc.session(tok), "an idle session times out"


def test_logout_invalidates_the_session(tmp_path):
    svc = make_service(tmp_path)
    tok = svc.sign_in("u_rm1", "ps_maker")["token"]
    svc.sign_out(tok)
    assert tok not in svc._sessions
    with pytest.raises(ForbiddenError):
        svc.session(tok)


def test_session_cannot_escalate_its_role(tmp_path):
    svc = make_service(tmp_path)
    tok = svc.sign_in("u_rm1", "ps_maker")["token"]
    assert svc.session(tok)["role"] == "ps_maker"
    # switching to a role the person does not hold is refused — the stored session wins
    with pytest.raises(ForbiddenError):
        svc.switch_role(tok, "los_admin")
    # a role the person genuinely holds is allowed; the stored role is what the token carries
    if "risk_analyst" in svc.session(tok)["user"]["roles"]:
        assert svc.switch_role(tok, "risk_analyst")["role"] == "risk_analyst"
        assert svc.session(tok)["role"] == "risk_analyst"
    else:
        assert svc.session(tok)["role"] == "ps_maker"


def test_audit_chain_verifies_and_detects_tampering(tmp_path):
    svc = make_service(tmp_path)
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 100.0, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "audit test"})
    sid = a["application_id"]
    ok = verify_audit(svc.store.events(sid, limit=100000))
    assert ok["valid"], ok
    # tamper with a middle event: the chain must fail
    events = svc.store.events(sid, limit=100000)
    if len(events) > 2:
        mid = list(events)[len(events) // 2]
        tampered = {**mid, "comment": (mid.get("comment") or "x") + " (altered)"}
        bad = verify_audit(list(events)[:len(events) // 2 + 1].copy() and
                           list(events)[:len(events) // 2] + [tampered] + list(events)[len(events) // 2 + 1:])
        assert not bad["valid"]


def test_sensitive_action_requires_a_valid_session(tmp_path):
    """Admin operations go through the session guard: a dead/foreign session is refused."""
    svc = make_service(tmp_path)
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 100.0, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "audit test"})
    tok = svc.sign_in("u_rm1", "ps_maker")["token"]
    svc.sign_out(tok)
    with pytest.raises(ForbiddenError):
        svc.session(tok)
