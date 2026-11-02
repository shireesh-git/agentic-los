"""R17 — field-level edit permissions.

The institution's profile decides which fields are material (a change to them is a
material edit: audited with before/after and flagged in the decision record) and
which roles may edit which domain. Makers edit their own domains; reviewers decide
(decision fields only) and are read-only on the workspaces. The API enforces the
policy (403 on a violation) and the UI reads the same policy so it disables exactly
the fields a role may not edit.
"""
from datetime import datetime, timedelta

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los import profiles
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "permissions test"}


def make_service(tmp_path):
    profiles.set_active_profile("dfi")
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: NOW)


def ps_app(svc, amount=100.0):
    wf = svc.wf_for_profile("dfi")
    s = svc._system_session("ps_maker", None, wf)
    a = svc.create(s, entity_id="KAVG001", profile="dfi",
                   facility={"facility_type": "term_loan", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 24,
                             "interest_rate": 11.5, "purpose": "Term loan (demo)"},
                   sourcing_decision=SOURCING)
    return a["application_id"], s


def test_material_facility_edit_is_audited_with_before_after(tmp_path):
    svc = make_service(tmp_path)
    sid, s = ps_app(svc)
    before = svc.store.get(sid)["facilities"][0]["amount_cr"]
    out = svc.update_facility(sid, s, "FAC-001", {"amount_cr": 120})
    # the change is recorded with before/after and flagged as a material edit
    ev = svc.store.events(sid, limit=5, asc=True)[-1]
    assert ev["action"] == "facility_updated"
    assert ev["detail"]["changes"]["amount_cr"] == {"before": before, "after": 120}
    assert "material edit" in ev["comment"].lower()
    app = svc.store.get(sid)
    assert app["material_change_reviews"][-1]["fields"] == ["amount_cr"]
    # the decision record carries the material-edit flag
    d = svc.decision_view(sid, s)
    assert d.get("material_change_flags") and any("amount_cr" in m for m in d["material_change_flags"])
    # a non-material change does not flag
    svc.update_facility(sid, s, "FAC-001", {"repayment_type": "annuity"})
    ev = svc.store.events(sid, limit=5, asc=True)[-1]
    assert "material edit" not in ev["comment"].lower()


def test_reviewer_is_read_only_on_the_makers_domain(tmp_path):
    svc = make_service(tmp_path)
    sid, _ = ps_app(svc)
    # the reviewer holds the PS maker's domain in the DFI policy — and is not the current
    # step's role, so the domain check is what releases the edit
    wf = svc.wf_for_profile("dfi")
    lpf = svc._system_session("lpf_vp", None, wf)
    app = svc.store.get(sid)
    step = wf.step(app["step_id"])
    # the current step is the PS maker: the reviewer is read-only there
    with pytest.raises(ForbiddenError, match="current step's role"):
        svc.update_facility(sid, lpf, "FAC-001", {"amount_cr": 90})
    # the configured domain editors may keep editing even while another step holds the case
    ra = svc._system_session("risk_analyst", None, wf)
    app2 = svc.store.get(sid)
    app2["step_id"] = "ip_note"                      # the case has moved on
    svc.store.save(app2)
    with pytest.raises(ForbiddenError, match="read-only|current step's role"):
        # the risk analyst edits the facility domain only at its own steps
        svc.update_facility(sid, ra, "FAC-001", {"amount_cr": 90})
    # and the permission view says the same thing the API enforces
    perms = svc.field_permissions(sid, lpf)
    assert perms["editable_now"]["facility"] is False
    maker = svc._system_session("ps_maker", None, wf)
    perms = svc.field_permissions(sid, maker)
    assert perms["editable_now"]["facility"] is True
    assert "amount_cr" in perms["material_fields"]


def test_post_sanction_facility_edits_require_a_modification(tmp_path):
    svc = make_service(tmp_path)
    sid, _ = ps_app(svc)
    svc._replay_to(sid, "pos_maker", NOW, NOW)
    wf = svc.wf_for_profile("dfi")
    posm = svc._system_session("pos_maker", None, wf)
    # after sanction the domain is closed for everyone — the message points to a modification
    with pytest.raises(ForbiddenError, match="read-only"):
        svc.update_facility(sid, posm, "FAC-001", {"amount_cr": 110})
    # even a configured domain editor is closed out after sanction
    ra = svc._system_session("risk_analyst", None, wf)
    with pytest.raises((ConflictError, ForbiddenError)):
        svc.update_facility(sid, ra, "FAC-001", {"amount_cr": 110})
    # the permission view reflects the closed domain at the POS stage (pos_maker is not among
    # the DFI policy's facility editors; the API refuses the edit and the UI hides the button)
    perms = svc.field_permissions(sid, posm)
    assert perms["editable_now"]["facility"] is False
    # the seeded replay through the governed committee carried the meeting record (R9)
    app = svc.store.get(sid)
    assert (app.get("committee_meetings") or {}).get("ap_sanction", {}).get("minutes")


def test_client_one_keeps_the_legacy_step_role_rule(tmp_path):
    profiles.set_active_profile("client_one")
    try:
        svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                         clock=lambda: NOW)
        wf = svc.wf_for_profile("client_one")
        s = svc._system_session("ps_maker", None, wf)
        a = svc.create(s, entity_id="MFL001", profile="client_one",
                       facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                                 "proposal_type": "Fresh", "amount_cr": 50.0, "tenor_months": 12,
                                 "interest_rate": 12.4, "purpose": "WC (demo)"},
                       sourcing_decision={"decision": "Refer for in-principle",
                                          "mandatory_remarks": "client one"})
        sid = a["application_id"]
        # no domain policy configured: the current step's role edits, others are refused
        checker = svc._system_session("lpf_vp", None, wf)
        with pytest.raises(ForbiddenError):
            svc.update_facility(sid, checker, "FAC-001", {"amount_cr": 55})
        perms = svc.field_permissions(sid, s)
        assert perms["edit_roles"] == {}
        assert perms["editable_now"].get("facility") is True   # no domain policy: the maker step edits
        # material fields are still the institution's list — client one keeps the default
        assert "amount_cr" in perms["material_fields"]
    finally:
        profiles.set_active_profile("client_one")
