"""R10 — conditions & covenants: owners, due dates, testing, waivers with authority,
indicators, and the closed-loop breach → test → cure."""
from datetime import datetime, timedelta

import pytest

from src.application.errors import InvalidRequestError
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
                                      "mandatory_remarks": "conditions test"})
    svc._replay_to(a["application_id"], "pos_maker", NOW, NOW)
    return svc.store.get(a["application_id"])


def test_satisfy_defer_waive_with_owner_and_frequency(tmp_path):
    svc = make_service(tmp_path)
    a = sanctioned(svc)
    sid = a["application_id"]
    conds = a.get("conditions") or []
    assert conds, "the sanctioned case carries conditions"
    posm = svc._system_session("pos_maker", a.get("assignee_id"))
    # satisfy one with evidence, setting the owner and frequency
    c1 = conds[0]
    svc.update_conditions(sid, posm, [{"id": c1["id"], "status": "satisfied",
                                       "evidence": "Certificate received (demo)",
                                       "owner": "POS team (demo)", "frequency": "once"}])
    a = svc.store.get(sid)
    c1 = next(c for c in a["conditions"] if c["id"] == c1["id"])
    assert c1["status"] == "satisfied" and c1.get("owner") == "POS team (demo)"
    # defer another with a new due date
    c2 = next((c for c in a["conditions"] if c["status"] == "open"), conds[1])
    svc.update_conditions(sid, posm, [{"id": c2["id"], "status": "deferred",
                                       "due": (NOW + timedelta(days=30)).date().isoformat(),
                                       "note": "Awaiting board note (demo)"}])
    a = svc.store.get(sid)
    c2 = next(c for c in a["conditions"] if c["id"] == c2["id"])
    assert c2["status"] == "deferred"
    assert c2["due"] == (NOW + timedelta(days=30)).date().isoformat()


def test_waiver_carries_authority_and_expiry(tmp_path):
    svc = make_service(tmp_path)
    a = sanctioned(svc)
    sid = a["application_id"]
    conds = [c for c in a["conditions"] or [] if c["status"] == "open"]
    assert conds
    posm = svc._system_session("pos_maker", a.get("assignee_id"))
    c = conds[0]
    svc.update_conditions(sid, posm, [{"id": c["id"], "status": "waived",
                                       "note": "Not achievable this period (demo)",
                                       "waiver": {"authority": "DMD (demo)"}}])
    a = svc.store.get(sid)
    c = next(x for x in a["conditions"] if x["id"] == c["id"])
    w = c.get("waiver")
    assert w, "the waiver is recorded"
    assert w["authority"] == "DMD (demo)"
    assert w.get("expires_at"), "the waiver has an expiry (profile max period)"
    # the expiry respects the profile maximum (180 days from the decision)
    from datetime import date
    exp = date.fromisoformat(w["expires_at"])
    assert timedelta(0) < (exp - NOW.date()) <= timedelta(days=180)


def test_indicators_reflect_the_state(tmp_path):
    svc = make_service(tmp_path)
    a = sanctioned(svc)
    sid = a["application_id"]
    ind = svc.condition_indicators(sid)
    for key in ("open", "overdue", "breached", "waived", "pending_approval", "as_of"):
        assert key in ind
    # right after sanction, the PC-type conditions are open (the seed satisfied them)
    a = svc.store.get(sid)
    open_now = sum(1 for c in a["conditions"] if c["status"] == "open")
    assert ind["open"] == open_now


def test_covenant_breach_test_cure_loop(tmp_path):
    svc = make_service(tmp_path)
    a = sanctioned(svc)
    sid = a["application_id"]
    covs = [c for c in a["conditions"] or [] if c["type"] in ("FC", "NC", "CS", "PD")]
    assert covs, "the sanctioned case carries covenants"
    posm = svc._system_session("pos_maker", a.get("assignee_id"))
    cov = covs[0]
    # a failing test breaches the covenant
    svc.record_covenant(sid, posm, cov["id"], "test", result="fail",
                        remarks="Below the stipulated level (demo)")
    a = svc.store.get(sid)
    c = next(x for x in a["conditions"] if x["id"] == cov["id"])
    assert c["status"] == "non_compliant"
    ind = svc.condition_indicators(sid)
    assert ind["breached"] >= 1
    # a passing test cures it
    svc.record_covenant(sid, posm, cov["id"], "test", result="pass",
                        remarks="Recovered (demo)")
    a = svc.store.get(sid)
    c = next(x for x in a["conditions"] if x["id"] == cov["id"])
    assert c["status"] == "satisfied"
    mon = c.get("monitoring") or {}
    assert mon.get("compliance") == "cured" or mon.get("cure")
    ind = svc.condition_indicators(sid)
    assert ind["covenants"]["cured"] >= 1


def test_defer_requires_a_future_date(tmp_path):
    svc = make_service(tmp_path)
    a = sanctioned(svc)
    sid = a["application_id"]
    conds = [c for c in a["conditions"] or [] if c["status"] == "open"]
    posm = svc._system_session("pos_maker", a.get("assignee_id"))
    with pytest.raises(InvalidRequestError, match="after today"):
        svc.update_conditions(sid, posm, [{"id": conds[0]["id"], "status": "deferred",
                                           "due": (NOW - timedelta(days=1)).date().isoformat(),
                                           "note": "x"}])
    with pytest.raises(InvalidRequestError, match="reason"):
        svc.update_conditions(sid, posm, [{"id": conds[0]["id"], "status": "waived"}])
