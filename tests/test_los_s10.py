"""S10: the carry-forward agent (R-P3) and the field gaps found in the reference field list (F-1 … F-10)."""

import copy

import pytest

from src.agentic.critic import check_evidence
from src.application.errors import ForbiddenError, InvalidRequestError
from src.los import carry_forward as cf
from src.los import esms as es
from src.los import prefill
from src.los.fields.registry import FieldRegistry
from tests.test_los_post_sanction import _abce_to, _holder, abce_case, svc  # noqa: F401 (fixtures)


@pytest.fixture(scope="module")
def registry():
    return FieldRegistry.load()


def _to_dis_maker(svc, app_id):
    """Place an application at the Disbursement Maker with sanctioned pricing, repayment, fees and a security."""
    raw = svc._require(app_id)
    f = raw["facilities"][0]
    f["pricing"].update(benchmark="MCLR", interest_rate=9.4, spread=1.0, reset_frequency="annual", penal_rate=2.0)
    f["repayment"].update(repayment_type="annuity", repayment_frequency="quarterly", moratorium_months=6)
    raw["pricing"]["fees"] = [{"fee_id": "APF-01", "facility_id": f["facility_id"], "nature": "Processing fee",
                               "type": "one-time", "scope": "facility", "amount_cr": None, "pct": 0.5, "total_cr": 0.75}]
    raw["securities"] = [{"security_id": "SEC-001", "type": "land_building", "description": "Factory land and building",
                          "facility_ids": [f["facility_id"]], "proposed_value_cr": 210.0, "valuation_date": "2026-09-01"}]
    raw.update(step_id="dis_maker", stage_id="DIS", assignee_id="u_dism", status="IN_PROGRESS")
    svc.store.save(raw)
    return svc.sign_in("u_dism", "dis_maker")


# ── R-P3: the carry-forward agent ────────────────────────────────────────────

def test_the_carry_forward_agent_proposes_the_disbursement_record_with_evidence(registry):
    app = {"facilities": [{"facility_id": "FAC-001", "facility_nature": "fund_based", "tenor_months": 60,
                           "pricing": {"benchmark": "MCLR", "interest_rate": 9.4, "spread": 1.0},
                           "repayment": {"repayment_frequency": "quarterly", "moratorium_months": 6}}],
           "pricing": {"fees": [{"fee_id": "APF-01", "facility_id": "FAC-001", "nature": "Processing fee", "total_cr": 0.5}]},
           "securities": [{"security_id": "SEC-001", "type": "stock", "facility_ids": ["FAC-001"], "proposed_value_cr": 80}]}
    ctx = {"app": app, "registry": registry, "fact_pack": {"facility_pricing": {"penal_interest": "2% p.a. above"}}}
    props = {p["field_id"]: p for fn in cf.RESOLVERS.values() for p in fn(ctx)}
    assert props["dis_carry.interest.rate"]["value"] == 9.4 and props["dis_carry.interest.penal_rate"]["value"] == 2.0
    assert props["dis_carry.repayment.instalment_frequency"]["value"] == "quarterly"
    assert props["dis_carry.fee.processing_fac_001.gross_cr"]["target"][2]["find"] == {"nature": "processing", "facility_id": "FAC-001"}
    assert props["dis_carry.security.sec_001.valuation_cr"]["value"] == 80
    for p in props.values():
        assert p["domain"] in registry.domains and (p["provenance"] == "unavailable" or check_evidence(p) == [])
    bare = copy.deepcopy(app)
    bare["facilities"][0]["repayment"] = {}
    gap = {p["field_id"]: p for p in cf.resolve_repayment({**ctx, "app": bare})}
    assert gap["dis_carry.repayment.instalment_frequency"]["provenance"] == "unavailable"   # never invented


def test_the_disbursement_maker_confirms_the_carried_record_and_a_rerun_keeps_their_entries(svc):
    app_id = _abce_to(svc, "ap_note")
    maker = _to_dis_maker(svc, app_id)
    svc.prepare_application(app_id, maker, wait=True)
    job = svc.wait_for_preparation(app_id)
    assert job["state"] == "done", job.get("error")
    assert job["summary"]["carry_forward"]["filled"] >= 10
    d = svc.get(app_id, maker)["disops"]
    assert (d["interest_terms"]["rate"], d["interest_terms"]["benchmark"]) == (9.4, "MCLR")
    assert d["repayment_final"]["instalment_frequency"] == "quarterly" and d["repayment_final"]["moratorium_months"] == 6
    assert d["fees"][0]["fee_id"] == "FEE-01" and d["fees"][0]["gross_cr"] == 0.75
    assert d["security_refs"][0]["security_id"] == "SEC-001" and d["security_refs"][0]["valuation_cr"] == 210.0
    # the maker saves the interest terms with a different reset: recorded, and a re-run keeps it
    svc.update_disops(app_id, maker, "interest_terms", {**{k: v for k, v in d["interest_terms"].items() if v is not None},
                                                         "reset_frequency": "half_yearly"})
    fields = svc._require(app_id)["fields"]
    assert fields["dis_carry.interest.rate"]["status"] == "confirmed"
    assert fields["dis_carry.interest.reset_frequency"]["status"] == "overridden"
    svc.prepare_application(app_id, maker, wait=True)
    svc.wait_for_preparation(app_id)
    assert svc.get(app_id, maker)["disops"]["interest_terms"]["reset_frequency"] == "half_yearly"
    # the fee row the maker saves is found again by its natural key, not duplicated
    svc.update_disops(app_id, maker, "fees", {"rows": [{**d["fees"][0], "received_cr": 0.75}]})
    svc.prepare_application(app_id, maker, wait=True)
    svc.wait_for_preparation(app_id)
    assert len(svc.get(app_id, maker)["disops"]["fees"]) == 1


# ── F-1 / F-2: the bank's AP narratives and decision notes ───────────────────

def test_the_bank_narratives_are_drafted_from_real_sources_only(abce_case, registry):
    case = copy.deepcopy(abce_case)
    case["fact_pack"]["crilc_exposure"] = {"fund_based_facilities": [
        {"facility_type": "Term loan", "classification": "Standard", "sma_flag": "None", "dpd": 0}]}
    case["fact_pack"]["market_signals"] = [{"headline": "Order book at a record high", "source": "ET", "date": "2026-05-01"}]
    app = {"facilities": [], "sanctions": {"IP": {"by_name": "Credit Committee", "at": "2026-09-01T10:00:00",
                                                  "sanctioned_cr": 50.0, "minutes": "Escrow of receivables"}},
           "stage_id": "AP"}
    ctx = {"case": case, "fact_pack": case["fact_pack"], "registry": registry, "app": app, "run_id": "r",
           "entity_history": [{"application_id": "LOS-2025-00011", "status": "DROPPED", "reason": "Prospect not pursued",
                               "deferrals": []}],
           "authority": {"amount_cr": 50.0, "risk_grade": "B", "deviations": 2, "required": "Credit Sanction Committee"}}
    n = {p["field_id"].rsplit(".", 1)[1]: p for p in prefill.resolve_bank_narratives(ctx)}
    assert "all Standard with no SMA flag" in n["asset_quality_status"]["value"]
    assert "Order book at a record high (ET, 2026-05-01)" in n["market_enquiries"]["value"]
    assert "LOS-2025-00011: dropped — Prospect not pursued" in n["past_proposals"]["value"]
    assert "Credit Sanction Committee" in n["committee_reason"]["value"] and "Escrow" in n["committee_directions"]["value"]
    for key in ("promoter_pledge", "corporate_actions", "unhedged_exposure"):
        assert n[key]["provenance"] == "unavailable", key                      # no source: left for a person
    d = {p["field_id"].rsplit(".", 1)[1]: p for p in prefill.resolve_decision_notes(ctx)}
    assert d["policy_compliance"]["value"].startswith("Policy engine hard rules:")
    assert "Escrow" in d["ip_observations"]["value"] and d["previous_relaxations"]["value"].startswith("Fresh proposal")


def test_decision_notes_are_saved_against_the_agent_draft(svc):
    app_id = _abce_to(svc, "ap_note")
    rm = _holder(svc, app_id)
    svc.populate_fields(app_id, force=True)
    view = svc.decision_view(app_id, rm)
    note = next(x for x in view["notes"] if x["key"] == "policy_compliance")
    assert note["text"] and note["status"] == "proposed"
    svc.save_decision_note(app_id, rm, "policy_compliance", note["text"])                  # unchanged → confirmed
    svc.save_decision_note(app_id, rm, "other_matters", "Approval for a 6-month moratorium")
    notes = {x["key"]: x for x in svc.decision_view(app_id, rm)["notes"]}
    assert notes["policy_compliance"]["status"] == "confirmed" and notes["other_matters"]["text"].startswith("Approval")
    with pytest.raises(InvalidRequestError):
        svc.save_decision_note(app_id, rm, "unknown", "x")


# ── F-3: the bank's ESMS list ────────────────────────────────────────────────

def test_the_excluded_activities_are_the_banks_annex_and_a_yes_blocks():
    assert [i for i, _ in es.ES_CHECKLIST] == ["es_basel_waste", "es_illegal", "es_wmd", "es_hazardous", "es_forced_labour"]
    screen = {"screening_date": "2026-10-01", "category": "B",
              "checklist": [{"id": i, "label": label, "answer": "No"} for i, label in es.ES_CHECKLIST]}
    assert es.esms_gate(screen) is None
    screen["checklist"][2]["answer"] = "Yes"
    assert "excluded activity" in es.esms_gate(screen)


# ── F-4, F-5, F-6, F-9 ───────────────────────────────────────────────────────

def test_unit_visits_sourcing_details_facility_fields_and_security_remarks(svc):
    app_id = _abce_to(svc, "ap_note")
    rm = _holder(svc, app_id)
    with pytest.raises(InvalidRequestError, match="visiting official"):
        svc.save_unit_visit(app_id, rm, {"date_of_visit": "2026-10-05", "observation": "Satisfactory"})
    with pytest.raises(InvalidRequestError, match="remarks are required"):
        svc.save_unit_visit(app_id, rm, {"date_of_visit": "2026-10-05", "observation": "Unsatisfactory",
                                         "officials": [{"name": "Ananya Rao", "designation": "RM"}]})
    svc.save_unit_visit(app_id, rm, {"date_of_visit": "2026-10-05", "observation": "Satisfactory", "place": "Pune",
                                     "address_visited": "Registered office",
                                     "officials": [{"name": "Ananya Rao", "designation": "RM"}]})
    view = svc.get(app_id, rm)
    assert view["unit_visits"][0]["visit_id"] == "UV-01" and view["unit_visits"][0]["entity_name"] == view["borrower_name"]
    # sourcing details were defaulted from the creating session
    assert view["sourcing_details"]["source"] == "Sourced by RM" and view["sourcing_details"]["owner_primary"]
    with pytest.raises(ForbiddenError):
        svc.save_sourcing_details(app_id, rm, {"sol_id": "001"})                       # kept at PS / IP only
    # facility fields: secured is derived from the securities record
    assert view["facilities"][0]["secured"] is False
    # security remarks drafted by the agent, saved against the drafts
    svc.populate_fields(app_id, force=True)
    notes = svc.get(app_id, rm)["security_notes"]
    assert notes.get("change_since_last_sanction", "").startswith("Fresh proposal")
    svc.save_security_notes(app_id, rm, {"security_trustee": "No — the bank holds the security directly"})
    assert svc.get(app_id, rm)["security_notes"]["security_trustee"].startswith("No")
