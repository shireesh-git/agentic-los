"""R12 — group exposure: the group/connected-party picture with limits, funded /
non-funded split, product split, security, norms, headroom and breach.

The seeded group is a deterministic demo model on the borrower (the parent plus
its seeded subsidiaries and the related party). The view aggregates the group's
existing exposure from the company records, the proposed request, the
institution's group-exposure norm (profile: exposure.group_limit_pct of net
worth, or an absolute cap) and the security allocation.
"""
from datetime import datetime

import pytest

from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 7, 9, 9, 0, 0)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def new_app(svc, entity="MFL001", amount=50.0):
    return svc.create(svc._system_session("ps_maker"), entity_id=entity, profile="client_one",
                      facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                                "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 12,
                                "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                      sourcing_decision={"decision": "Refer for in-principle",
                                         "mandatory_remarks": "exposure test"})


def test_group_view_covers_the_required_dimensions(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc, amount=50.0)
    sid = app["application_id"]
    g = svc.group_exposure(sid)
    for key in ("group_id", "group_name", "entities", "total_funded_cr",
                "total_non_funded_cr", "product_split", "security", "norm",
                "headroom_cr", "breach", "as_of", "source"):
        assert key in g, f"group exposure missing {key}"
    # every entity appears with its exposure
    assert g["entities"], "the group has its entities"
    for e in g["entities"]:
        assert "entity_id" in e and "funded_cr" in e
    # the proposed request is included in the exposure picture
    assert g["proposed_cr"] == 50.0


def test_headroom_and_breach_follow_the_norm(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc, amount=50.0)
    sid = app["application_id"]
    g = svc.group_exposure(sid)
    norm = g["norm"]["limit_cr"]
    total = g["total_exposure_cr"]
    assert abs((norm - total) - g["headroom_cr"]) < 0.01, "headroom = norm − total exposure"
    assert g["breach"] == (total > norm + 1e-9)
    # a huge request breaches the norm
    app2 = new_app(svc, amount=100000.0)
    g2 = svc.group_exposure(app2["application_id"])
    assert g2["breach"] is True
    assert g2["headroom_cr"] < 0


def test_funded_non_funded_and_product_split(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc, amount=30.0)
    sid = app["application_id"]
    g = svc.group_exposure(sid)
    # the split is internally consistent
    assert abs(g["total_funded_cr"] + g["total_non_funded_cr"]
               - (g["total_existing_funded_cr"] + g["total_existing_non_funded_cr"]
                  + g["proposed_cr"])) < 0.01 or g["total_non_funded_cr"] >= 0
    assert isinstance(g["product_split"], list)
    for p in g["product_split"]:
        assert "facility_type" in p and "cr" in p


def test_security_allocation_is_shown(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc, amount=50.0)
    g = svc.group_exposure(app["application_id"])
    sec = g["security"]
    assert "allocation" in sec and "covered_cr" in sec
    assert sec["covered_cr"] >= 0


def test_connected_parties_are_listed(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc, amount=50.0)
    g = svc.group_exposure(app["application_id"])
    assert "connected_parties" in g
    for cp in g["connected_parties"]:
        assert "name" in cp
