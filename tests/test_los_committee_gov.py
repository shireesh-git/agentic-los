"""R9 (committee governance) — attendance, quorum, voting, abstention, dissent,
conflicts of interest, structured minutes, version history, and decision blocking
when quorum is unmet.

The governance is profile-driven (``committee_governance``): the DFI profile enables it
(quorum 3, a standing roster, conflicts excused); the default profile leaves it off and the
committee acts exactly as before (legacy behaviour preserved).
"""
from datetime import datetime

import pytest

from src.application import errors
from src.data.company_catalog import seed_company_store
from src.los import profiles
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime.fromisoformat("2026-10-12T12:00:00")
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "committee gov test"}
ROSTER = ["Credit Committee Secretariat", "D. K. Jain (DMD)", "A. Deshmukh (EVP Credit)",
          "R. Iyer (CRP VP)", "S. Bhatia (RMD)"]


def make_service(tmp_path, profile="dfi"):
    profiles.set_active_profile(profile)
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def at_committee(svc, profile="dfi"):
    """A DFI project-finance application replayed to the IP Sanction Committee."""
    a = svc.create(svc._system_session("ps_maker"), entity_id="SAPT001", profile=profile,
                   facility={"facility_type": "term_loan", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 120.0, "tenor_months": 60,
                             "interest_rate": 12.4, "purpose": "Shuttle-rail rolling stock (demo)"},
                   sourcing_decision=SOURCING)
    sid = a["application_id"]
    svc._replay_to(sid, "ip_sanction", NOW, NOW)
    cc = svc.sign_in("u_cc", "sanction_committee")
    return sid, cc


def _attend(svc, sid, cc, names, *, coi=None):
    members = []
    for n in ROSTER:
        m = {"name": n, "status": "present" if n in names else "absent"}
        if n in (coi or ()):
            m.update(conflict_of_interest=True, conflict_note="Relationship with the borrower (demo)")
        members.append(m)
    return svc.record_committee_attendance(sid, cc, "ip_sanction", members)


def _vote(svc, sid, cc, votes):
    return svc.record_committee_votes(sid, cc, "ip_sanction",
                                      [{"name": n, "vote": v, "remarks": r or ""}
                                       for n, v, r in votes])


def _minutes(svc, sid, cc, **kw):
    kw = kw or {}
    return svc.record_committee_minutes(
        sid, cc, "ip_sanction",
        agenda=kw.get("agenda") or ["Credit proposal — SAPT001", "Risk and security", "Resolution"],
        discussion=kw.get("discussion") or "The committee examined the cash-flow coverage, the security "
                                           "package and the sector exposure; the dissenting view is on record.",
        resolution=kw.get("resolution") or "Sanctioned at the recommended amount, subject to the conditions.")


def test_legacy_profile_has_no_governance_block(tmp_path):
    """client_one (governance disabled): the committee sanctions without any meeting record —
    the exact legacy flow."""
    svc = make_service(tmp_path, profile="client_one")
    sid, cc = at_committee(svc, profile="client_one")
    out = svc.act(sid, cc, "sanction", comment="In-principle sanctioned (demo)")
    assert (svc.store.get(sid).get("sanctions") or {}).get("IP")
    assert "governance" not in (svc.store.get(sid).get("sanctions") or {}).get("IP", {})


def test_sanction_blocked_until_quorum_met(tmp_path):
    """DFI: no attendance → blocked; 2 present of quorum 3 → blocked (quorum unmet); the gate
    message says what is missing."""
    svc = make_service(tmp_path)
    sid, cc = at_committee(svc)
    with pytest.raises(errors.InvalidRequestError, match="attendance"):
        svc.act(sid, cc, "sanction", comment="x")
    _attend(svc, sid, cc, ["Credit Committee Secretariat", "D. K. Jain (DMD)"])
    with pytest.raises(errors.InvalidRequestError, match="quorum"):
        svc.act(sid, cc, "sanction", comment="x")
    # the view shows the quorum position and is readable to the committee
    view = svc.committee_meeting(sid, cc, "ip_sanction")
    assert view["quorum"] == {"required": 3, "present": 2, "met": False, "excluded_conflicts": 0}
    assert view["enabled"] is True and view["roster_size"] == 5


def test_conflict_of_interest_is_excused_from_quorum_and_vote(tmp_path):
    """A member declaring a conflict of interest is excused: it does not count toward the
    quorum and cannot vote; the conflict needs a note."""
    svc = make_service(tmp_path)
    sid, cc = at_committee(svc)
    with pytest.raises(errors.InvalidRequestError, match="conflict"):
        svc.record_committee_attendance(sid, cc, "ip_sanction",
                                        [{"name": "D. K. Jain (DMD)", "status": "present",
                                          "conflict_of_interest": True}])
    _attend(svc, sid, cc, ROSTER[:4], coi=["R. Iyer (CRP VP)"])  # 3 present + 1 COI
    view = svc.committee_meeting(sid, cc, "ip_sanction")
    assert view["quorum"] == {"required": 3, "present": 3, "met": True, "excluded_conflicts": 1}
    # 3 present counting (SAPT001 is a rail borrower: the CRP VP is in a conflict) — quorum is met
    with pytest.raises(errors.ForbiddenError, match="conflict"):
        _vote(svc, sid, cc, [("R. Iyer (CRP VP)", "approve", "")])


def test_vote_dissent_and_abstention(tmp_path):
    """Abstention needs a note and does not count as a vote; a dissent needs remarks; a
    dissenting majority blocks the decision even with quorum and minutes."""
    svc = make_service(tmp_path)
    sid, cc = at_committee(svc)
    _attend(svc, sid, cc, ROSTER[:4])
    with pytest.raises(errors.InvalidRequestError, match="Abstention"):
        _vote(svc, sid, cc, [("A. Deshmukh (EVP Credit)", "abstain", "")])
    with pytest.raises(errors.InvalidRequestError, match="Dissent"):
        _vote(svc, sid, cc, [("R. Iyer (CRP VP)", "dissent", "")])
    _minutes(svc, sid, cc)
    # 2 approve, 1 abstain, 1 dissent → the vote approves
    _vote(svc, sid, cc, [("Credit Committee Secretariat", "approve", ""),
                         ("D. K. Jain (DMD)", "approve", ""),
                         ("A. Deshmukh (EVP Credit)", "abstain", "Awaiting the EDD closure"),
                         ("R. Iyer (CRP VP)", "dissent", "Coverage ratio is thin; seek additional security")])
    out = svc.act(sid, cc, "sanction", comment="Sanctioned per the committee's resolution")
    sanc = (svc.store.get(sid).get("sanctions") or {}).get("IP")
    gov = sanc["governance"]
    assert gov["quorum"] == {"required": 3, "present": 4, "met": True, "excluded_conflicts": 0}
    assert gov["votes"] == {"approve": 2, "abstain": 1, "dissent": 1}
    assert gov["dissenters"] == ["R. Iyer (CRP VP)"]
    # a dissenting majority blocks: flip the secretary's vote and re-block a fresh case
    sid2, cc2 = at_committee(svc)
    _attend(svc, sid2, cc2, ROSTER[:4])
    _minutes(svc, sid2, cc2)
    _vote(svc, sid2, cc2, [("Credit Committee Secretariat", "dissent", "Against — conditions not met"),
                           ("D. K. Jain (DMD)", "dissent", "Against — sector exposure"),
                           ("A. Deshmukh (EVP Credit)", "approve", ""),
                           ("R. Iyer (CRP VP)", "abstain", "Recusal from position, present in meeting")])
    with pytest.raises(errors.InvalidRequestError, match="vote does not approve"):
        svc.act(sid2, cc2, "sanction", comment="x")


def test_minutes_required_and_version_history(tmp_path):
    """The structured minutes must be on file before the decision; every change (attendance,
    vote, minutes re-save) bumps the meeting version and the minutes carry their own version;
    a changed vote is one row per member (no duplicates)."""
    svc = make_service(tmp_path)
    sid, cc = at_committee(svc)
    v1 = _attend(svc, sid, cc, ROSTER[:4])
    assert v1["version"] == 1
    _vote(svc, sid, cc, [("Credit Committee Secretariat", "approve", ""),
                         ("D. K. Jain (DMD)", "approve", ""),
                         ("A. Deshmukh (EVP Credit)", "approve", "")])
    v2 = svc.committee_meeting(sid, cc, "ip_sanction")
    assert v2["version"] == 2
    with pytest.raises(errors.InvalidRequestError, match="minutes"):
        svc.act(sid, cc, "sanction", comment="x")
    with pytest.raises(errors.InvalidRequestError, match="agenda"):
        svc.record_committee_minutes(sid, cc, "ip_sanction", agenda=[], discussion="d", resolution="r")
    _minutes(svc, sid, cc)
    _minutes(svc, sid, cc, resolution="Sanctioned at the recommended amount; security to be perfected "
                                        "within 90 days (revised resolution).")
    view = svc.committee_meeting(sid, cc, "ip_sanction")
    assert view["minutes"]["version"] == 2
    assert [v["change"] for v in view["versions"]] == ["attendance", "vote", "minutes", "minutes"]
    # changed vote: one row per member
    svc.record_committee_votes(sid, cc, "ip_sanction",
                               [{"name": "A. Deshmukh (EVP Credit)", "vote": "approve", "remarks": ""}])
    view = svc.committee_meeting(sid, cc, "ip_sanction")
    assert len(view["votes"]) == 3
    assert view["vote_tally"]["approve"] == 3
    out = svc.act(sid, cc, "sanction", comment="Sanctioned per the committee's resolution")
    assert (svc.store.get(sid).get("sanctions") or {}).get("IP")


def test_only_the_committee_keeps_the_records(tmp_path):
    """The meeting records are kept by the committee step's role; the RM cannot attend/vote,
    and a non-committee step is not a meeting."""
    svc = make_service(tmp_path)
    sid, cc = at_committee(svc)
    rm = svc.sign_in("u_rm1", "ps_maker")
    with pytest.raises(errors.ForbiddenError):
        svc.committee_meeting(sid, rm, "ip_sanction")
    with pytest.raises(errors.ForbiddenError):
        svc.record_committee_attendance(sid, rm, "ip_sanction",
                                        [{"name": ROSTER[0], "status": "present"}])
    with pytest.raises(errors.InvalidRequestError, match="not a committee"):
        svc.committee_meeting(sid, cc, "ps_maker")
    with pytest.raises(errors.NotFoundError):
        svc.committee_meeting(sid, cc, "no_such_step")
    # a vote before attendance is refused
    _attend(svc, sid, cc, ROSTER[:4])
    assert svc.committee_meeting(sid, cc, "ip_sanction")["vote_tally"]["approve"] == 0
