"""The governed due-diligence module (Client One GAP-P0-05/06): the fifteen checks,
their statuses, the blocking rule and the deterministic demo execution of the API checks."""

from src.data.company_catalog import seed_company_store
from src.los import verification as dd

COMPANIES = seed_company_store()


def _check(id_, **over):
    c = dd.initial_checks()[next(i for i, x in enumerate(dd.CHECKS) if x["id"] == id_)]
    c.update(over)
    return c


# ─── Catalog and lifecycle states ────────────────────────────────────────────

def test_the_fifteen_checks_start_pending():
    checks = dd.initial_checks()
    assert len(checks) == 15
    assert {c["id"] for c in checks} == {
        "mca", "cibil", "crif", "crilc", "litigation", "ews", "cfr", "ceib",
        "gstin", "lei", "edd", "udin", "kyc", "name_screening", "mlra"}
    assert all(c["status"] == "pending" and c["history"] == [] and c["exception"] is None for c in checks)
    assert sum(1 for c in checks if c["mode"] == "api") == 8 and sum(1 for c in checks if c["mode"] == "manual") == 7
    mandatory = {c["id"] for c in checks if c["mandatory"]}
    assert mandatory == {"mca", "crilc", "kyc", "name_screening", "mlra"}


def test_summary_counts_every_state():
    checks = [
        _check("mca", status="clear"), _check("crilc", status="pending"),
        _check("kyc", status="matched"), _check("name_screening", status="failed", exception={"reason": "ok"}),
        _check("cibil", status="unavailable"),
    ]
    s = dd.summary(checks)
    assert (s["clear"], s["pending"], s["matched"], s["failed"], s["unavailable"], s["exceptions"]) == (1, 1, 1, 1, 1, 1)
    assert s["blocking"] == 2                                              # crilc pending + kyc matched


# ─── The blocking rule ───────────────────────────────────────────────────────

def test_blocking_covers_only_mandatory_pending_failed_or_unresolved_matches():
    checks = [
        _check("mca", status="pending"),                                          # blocks
        _check("crilc", status="failed"),                                         # blocks
        _check("kyc", status="matched"),                                          # blocks
        _check("name_screening", status="matched", exception={"by_name": "VP", "reason": "ok"}),   # released
        _check("mlra", status="clear"),
        _check("cibil", status="unavailable"),                                    # operational — never blocks
        _check("gstin", status="failed"),                                         # not mandatory — never blocks
    ]
    assert {c["id"] for c in dd.blocking(checks)} == {"mca", "crilc", "kyc"}


# ─── Deterministic demo execution of the API checks ─────────────────────────

def test_api_checks_run_deterministically_against_the_in_app_record():
    ihcl = COMPANIES["IHCL001"]
    mca = dd.run_api_check("mca", ihcl)
    assert mca["status"] == "clear" and "demo" in mca["source"] and "CIN" in mca["detail"]
    # N. Chandrasekaran is on the demo PEP reference list (close associate, low risk).
    screening = dd.run_api_check("name_screening", ihcl)
    assert screening["status"] == "matched" and "PEP" in screening["detail"]
    clean = dd.run_api_check("name_screening", COMPANIES["MFL001"])
    assert clean["status"] == "clear"
    # Not-connected providers yield 'unavailable' — an operational state, never a negative result.
    assert dd.run_api_check("crif", ihcl)["status"] == "unavailable"
    assert dd.run_api_check("lei", ihcl)["status"] == "unavailable"
    no_cin = {"borrower": type("B", (), {"entity_id": "X", "cin": None, "pan": None})()}
    assert dd.run_api_check("mca", no_cin)["status"] == "failed"
    assert dd.run_api_check("gstin", no_cin)["status"] == "failed"
    try:
        dd.run_api_check("kyc", ihcl)
        assert False, "manual checks are not triggerable"
    except ValueError:
        pass
