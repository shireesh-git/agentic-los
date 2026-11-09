"""Fix list Round 5 (E1–E9): demo registry data, mandatory checks at initiation, the verdict in plain words,
early-warning actions, the Copilot record cleaned for people, and incomplete fields explained."""

import pytest

from src.data import demo_registry
from src.flow import checks as chk
from src.flow import copilot as cp
from src.flow import risk as rk


# ── E5: demo registry files stand in for the APIs that are not connected ────────────────────────────

def test_demo_file_gives_connector_envelopes_with_list_checks_folded_into_the_bureau():
    ext = demo_registry.external_data("INFY001")
    bureau, mca = ext["bureau_data"], ext["mca_data"]
    assert bureau["provenance"]["via"] == "demo_file" and bureau["source_status"] == "success"
    assert mca["payload"]["status"] == "Active" and "Demo MCA" in mca["provenance"]["provider"]
    p = bureau["payload"]
    assert p["wilful_defaulter"] is False and p["fraud_flag"] is False and p["rbi_defaulter_list"] is False
    assert "(demo)" in p["_field_sources"]["fraud_flag"]
    # a new prospect is found by CIN; it has the list checks only
    dixon = demo_registry.external_data(None, "L32101UP1993PLC066581")
    assert set(dixon) == {"bureau_data"} and "dpd_status" not in dixon["bureau_data"]["payload"]
    assert demo_registry.external_data("NOSUCH01") == {}


@pytest.fixture(scope="module")
def companies():
    from src.application.container import build_container
    return build_container().state.companies


@pytest.mark.parametrize("eid, expect", [
    ("INFY001", {"pass"}),                                       # all clear
    ("MFL001", {"pass", "fail"}),                                # suits filed above 25% of exposure
    ("IHCL001", {"pass", "not_verified"}),                       # no bureau report on file
])
def test_precheck_runs_the_six_data_checks_at_initiation(companies, eid, expect):
    res = chk.precheck(companies[eid], demo_enabled=True)
    assert {i["code"] for i in res["items"]} == set(chk.DATA_CHECKS) and res["demo"]
    assert {i["status"] for i in res["items"]} == expect
    for i in res["items"]:
        assert i["label"] and not i["label"].startswith("HR_") and i["evidence"]
    if eid == "MFL001":
        suit = next(i for i in res["items"] if i["code"] == "HR_SUIT_FILED")
        assert suit["status"] == "fail" and "%" in suit["detail"] and "demo" in suit["source"].lower()


def test_precheck_without_demo_data_leaves_the_checks_not_verified(companies):
    res = chk.precheck({**companies["INFY001"], "external_data": {}}, demo_enabled=False)
    assert {i["status"] for i in res["items"]} == {"not_verified"} and not res["demo"]


# ── E2: the verdict in plain words, credit quality toned apart from open checks ────────────────────

def _risk(rec, grade="A", score=88.6, tone="warn", ratios=()):
    return {"recommendation": rec, "label": rk.REC[rec][0], "tone": tone, "rating": grade, "score": score,
            "ratios": list(ratios)}


def _checks(*statuses, note=None):
    items = [{"code": f"HR_X{i}", "label": f"Check {i}", "status": s, "evidence": "e"} for i, s in enumerate(statuses)]
    return chk.view({"items": items}, {"HR_X0": note} if note else None)


def test_refer_only_for_missing_checks_says_so_and_names_the_authority():
    v = rk.verdict(_risk("refer"), _checks("not_verified", "pass"), "Vikram Shah (Sanctioning Authority)")
    assert v["label"] == "Refer: checks outstanding" and v["credit_tone"] == "good" and v["tone"] == "warn"
    assert "strong (A, score 88.6/100)" in v["text"] and "check 0" in v["text"]
    assert "Vikram Shah (Sanctioning Authority)" in v["text"] and "higher authority" not in v["text"]


def test_addressed_checks_turn_the_refer_green():
    note = {"kind": "verified", "note": "CIBIL CMR seen", "by": "Rahul", "role": "Underwriting"}
    v = rk.verdict(_risk("refer"), _checks("not_verified", "pass", note=note), "SA")
    assert v["label"] == "Refer: checks addressed" and v["tone"] == "good"


def test_failed_check_is_a_decline_with_reasons():
    v = rk.verdict(_risk("decline", grade="D", score=45.8, tone="bad",
                         ratios=[{"label": "DSCR", "status": "bad"}]), _checks("fail"), "SA")
    assert v["label"] == "Decline" and v["credit_tone"] == "bad"
    assert "check 0" in v["text"] and "DSCR outside policy" in v["text"] and "justification" in v["text"]


def test_approve_says_checks_are_clear():
    v = rk.verdict(_risk("approve", tone="good"), _checks("pass", "pass"), "SA")
    assert v["tone"] == "good" and "mandatory checks are clear" in v["text"]


# ── E3: each early-warning flag carries an action ──────────────────────────────────────────────────

def test_every_early_warning_indicator_has_a_plain_action():
    from src.engines import quality_engine
    import inspect
    src = inspect.getsource(quality_engine.ews_indicators) + inspect.getsource(quality_engine._forensic)
    ids = set(__import__("re").findall(r'add\("([a-z_]+)"', src))
    assert ids and ids <= set(rk.EWS_ACTION), ids - set(rk.EWS_ACTION)
    assert all(kind in ("send_back", "none") for _, kind in rk.EWS_ACTION.values())


# ── E6 / E9: the record is cleaned before the model reads it ───────────────────────────────────────

def test_clean_formats_figures_dates_and_rule_codes_and_drops_empties():
    out = cp.clean({"revenue_cr": 153670.0, "pat_cr": 26073.37, "small_cr": 12.5, "dscr": 28.1123,
                    "value_date": "2026-11-09", "at": "2026-11-09T10:22:54", "edited_by": None, "x": "null",
                    "rationale": "Referred: HR_WILFUL_DEFAULTER, HR_SUIT_FILED", "flag": False, "code": "HR_X",
                    "list": [None, "", {"a": None}]})
    assert out == {"revenue_cr": "₹1,53,670 Cr", "pat_cr": "₹26,073 Cr", "small_cr": "₹12.5 Cr", "dscr": "28.11",
                   "value_date": "9 Nov 2026", "at": "9 Nov 2026, 10:22",
                   "rationale": "Referred: wilful defaulter check, suits filed check", "flag": "no"}
    assert cp.indian(123456789) == "12,34,56,789" and cp.crore(400.0) == "₹400 Cr"


# ── E5 service: checks at initiation, and a note recorded against an open one ─────────────────────

@pytest.fixture(scope="module")
def svc():
    from src.application.container import build_container
    flow = build_container().flow
    flow.reset({"user": {"id": "test"}}, "IHCL001")
    yield flow
    flow.reset({"user": {"id": "test"}}, "IHCL001")


def test_initiation_raises_the_open_check_to_the_rm_who_can_record_against_it(svc):
    from src.application.errors import ForbiddenError, InvalidRequestError

    rm, cro = svc.sign_in("f_rm"), svc.sign_in("f_cro")
    case = svc.create(rm, entity_id="IHCL001")
    cid = case["case_id"]
    v = svc.view(cid, rm)
    assert v["checks"]["basis"] == "initiation" and v["checks"]["open"] == 1 and v["checks"]["can_note"]
    open_ = v["checks"]["not_verified"][0]
    assert open_["label"] == "Bureau status" and "bureau report" in open_["evidence"].lower()
    warn = next(m for m in v["chat"] if m["text"].startswith("Mandatory checks:"))
    assert warn["kind"] == "warn" and "Not verified: Bureau status" in warn["text"] and "demo data" in warn["text"]
    with pytest.raises(InvalidRequestError):
        svc.check_note(cid, open_["code"], {"kind": "verified", "note": "short"}, rm)
    with pytest.raises(InvalidRequestError):
        svc.check_note(cid, "HR_WILFUL_DEFAULTER", {"kind": "verified", "note": "already clear, nothing to add"}, rm)
    with pytest.raises(ForbiddenError):
        svc.check_note(cid, open_["code"], {"kind": "verified", "note": "CIBIL CMR dated 1-Nov-2026 seen"}, cro)
    v = svc.check_note(cid, open_["code"], {"kind": "verified", "note": "CIBIL CMR dated 1-Nov-2026: Standard"}, rm)
    noted = next(i for i in v["checks"]["items"] if i["code"] == open_["code"])
    assert v["checks"]["open"] == 0 and noted["note"]["by"] == "Ananya Rao" and not noted["open"]
    rec = svc._record(svc.store.get(cid))
    assert any(c["recorded"] and c["recorded"].startswith("verified by Ananya Rao") for c in rec["mandatory_checks"])
