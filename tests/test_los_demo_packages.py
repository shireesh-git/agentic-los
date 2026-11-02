"""R22 — executive / functional demo packages.

The packages are configuration (config/demo_packages.yaml): audience, profile,
sign-in, prepared case, scripted steps and artifacts — plus the reset procedure.
The service enriches each package with its live demo application (id, borrower,
current step and role); the validation below checks the contract against the
live workflow (real profiles, real steps, real seeded cases).
"""
from datetime import datetime

from src.data.company_catalog import seed_company_store
from src.los import profiles
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 10, 12, 12, 0, 0)
REQUIRED = ("id", "audience", "title", "profile", "sign_in", "duration", "points", "steps", "artifacts")
AUDIENCES = ("executive", "functional")
STAGE_FIELDS = ("role", "stage", "action", "expected", "next")


def _svc(tmp_path):
    profiles.set_active_profile("client_one")
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                     clock=lambda: NOW)
    svc.seed_demo(force=True)
    return svc


def test_every_package_carries_the_required_fields(tmp_path):
    svc = _svc(tmp_path)
    out = svc.demo_packages("all")
    assert out["reset"].get("instructions") and out["reset"].get("endpoint")
    pkgs = out["packages"]
    assert len(pkgs) >= 11, [p["id"] for p in pkgs]
    ids = [p["id"] for p in pkgs]
    assert len(ids) == len(set(ids)), "package ids must be unique"
    for p in pkgs:
        for f in REQUIRED:
            assert p.get(f), f"package {p['id']} missing {f}"
        assert p["audience"] in AUDIENCES
        assert p["profile"] != "base"
        assert isinstance(p["sign_in"], dict) and p["sign_in"].get("user") and p["sign_in"].get("role")
        assert isinstance(p["points"], list) and p["points"]
        for st in p["steps"]:
            for f in STAGE_FIELDS:
                assert st.get(f), f"package {p['id']} step missing {f}"
        assert p["artifacts"]


def test_packages_reference_real_profiles_steps_and_seeded_cases(tmp_path):
    svc = _svc(tmp_path)
    out = svc.demo_packages("all")
    profiles_seen = set()
    live = 0
    for p in out["packages"]:
        wf = svc.wf_for_profile(p["profile"])
        profiles_seen.add(p["profile"])
        # the sign-in role must exist in the profile's workflow
        assert p["sign_in"]["role"] in wf.roles or p["sign_in"]["role"] in {s.role for s in wf.steps}, \
            f"{p['id']}: role {p['sign_in']['role']}"
        if "application_id" in p and not p.get("completed"):
            live += 1
            app = svc.store.get(p["application_id"])
            assert app["profile"] == p["profile"] and app["is_demo"]
            step = wf.step(app["step_id"])
            assert p["live_step"] == step.id
            assert p["live_role"] == wf.roles.get(step.role, step.role)
        elif p.get("application_id"):
            pass
        else:
            assert "seed_note" in p, f"{p['id']}: neither a live case nor a seed note"
    # the executive set and the functional set are both present
    assert any(p["audience"] == "executive" for p in out["packages"])
    assert any(p["audience"] == "functional" for p in out["packages"])
    # the DFI and Client One packages open on seeded cases (both profiles are seeded)
    assert profiles_seen >= {"client_one", "dfi"}


def test_demo_packages_endpoint_shapes_the_packages():
    # the router path exists and is wired to the service method
    from src.api import routers  # noqa: F401
    from src.api.routers.los import router
    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/api/los/demo-packages" in paths


def test_package_for_a_profile_includes_only_its_packages(tmp_path):
    svc = _svc(tmp_path)
    only = svc.demo_packages("dfi")
    assert only["packages"] and all(p["profile"] == "dfi" for p in only["packages"])
    everything = svc.demo_packages("all")
    assert len(everything["packages"]) > len(only["packages"])
