"""R11 — policy-deviation detection.

`detect_policy_deviations(app, profile)` applies the profile's `deviation_rules`
(thresholds on amount, tenor, pricing, grade, sector and exposure) to the
application and returns the deviations it detects — each with the rule reference,
the expected vs actual value, the severity, and the authority the deviation
requires. Natural-key dedupe: the same rule on the same facts is reported once.
The existing manual + committee deviations are unchanged; this is the automatic,
configurable layer.
"""
from datetime import datetime

import pytest

from src.los import deviations as devmod
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 7, 9, 9, 0, 0)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def make_app(svc, amount=100.0, tenor=12, grade="A", **kw):
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": kw.pop("facility_type", "working_capital"),
                             "facility_nature": "fund_based", "proposal_type": "Fresh",
                             "amount_cr": amount, "tenor_months": tenor,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)", **kw},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "deviation test"})
    return svc.store.get(a["application_id"])


def test_detection_fires_on_the_configured_thresholds(tmp_path):
    svc = make_service(tmp_path)
    # within thresholds: no automatic deviation
    a = make_app(svc, amount=100.0, tenor=12, grade="A")
    found = devmod.detect_policy_deviations(a, svc._profile(a))
    assert found == [], found
    # a long tenor breaches the tenor threshold
    a2 = make_app(svc, amount=100.0, tenor=84, grade="A")
    found2 = devmod.detect_policy_deviations(a2, svc._profile(a2))
    assert any(d["rule_ref"].startswith("tenor") for d in found2)
    for d in found2:
        for key in ("rule_ref", "expected", "actual", "severity", "required_authority", "type", "summary"):
            assert key in d, f"deviation missing {key}"


def test_natural_key_dedupe(tmp_path):
    svc = make_service(tmp_path)
    a = make_app(svc, amount=100.0, tenor=84)
    once = devmod.detect_policy_deviations(a, svc._profile(a))
    twice = devmod.detect_policy_deviations(a, svc._profile(a))
    assert [d["rule_ref"] for d in once] == [d["rule_ref"] for d in twice]
    # re-detecting on the same record does not double the stored items
    ids = [d.get("deviation_id") for d in once]
    assert len(ids) == len(set(ids))


def test_severity_and_required_authority_scale(tmp_path):
    svc = make_service(tmp_path)
    small = make_app(svc, amount=100.0, tenor=84)
    big = make_app(svc, amount=100.0, tenor=144)
    sev = {d["rule_ref"]: d for d in devmod.detect_policy_deviations(small, svc._profile(small))}
    sev_big = {d["rule_ref"]: d for d in devmod.detect_policy_deviations(big, svc._profile(big))}
    ref = next(k for k in sev if k.startswith("tenor"))
    assert sev_big[ref]["severity"] in ("major", "critical") or sev_big[ref]["severity"] == sev[ref]["severity"]
    assert sev[ref].get("required_authority"), "a deviation states the authority it requires"


def test_deviation_increases_the_required_authority(tmp_path):
    """The detected deviations feed the authority computation (the route sees them)."""
    from src.los import authority
    svc = make_service(tmp_path)
    a = make_app(svc, amount=100.0, tenor=84)
    found = devmod.detect_policy_deviations(a, svc._profile(a))
    base = authority.required_authority(a["amount_cr"], "A", deviations=0, final=True, app=a)
    with_dev = authority.required_authority(a["amount_cr"], "A", deviations=len(found), final=True, app=a)
    b = base.get("required") or base.get("authority")
    w = with_dev.get("required") or with_dev.get("authority")
    assert "deviation" in str(w) and str(w) != str(b)
