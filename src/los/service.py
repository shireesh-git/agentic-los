"""
LOS service — applications moving through the corporate credit workflow.

An application is the LOS workitem for one borrower and one credit proposal. It
references the borrower record and credit case of the CAM platform by entity_id;
the credit analysis itself stays with the existing engine (CaseService etc.).

All changes go through ``act`` / ``reassign`` / ``escalate``: the workflow decides
the transition, the acting user must hold the step's role, and every change is
written with an audit event. Sign-in is a demo picker (no passwords).
"""

from __future__ import annotations

import json
import logging
import os
import dataclasses
import hashlib
import secrets
import shutil
import re
import threading
import yaml as _yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from src.application.errors import (
    ConflictError, ForbiddenError, InvalidRequestError, NotFoundError, OperationFailedError,
)
from src.los.committee import (BRIEF_SECTIONS, DEVIATION_TYPES, build_committee_pack, committee_deviations,
                               manual_deviations)
from src.los.post_sanction import (
    CS_DUE_DAYS, CONDITION_STATUSES, CONDITION_STEPS, MANUAL_ITEMS, build_comparison, build_conditions, build_deviations,
    build_disbursement, condition_state, condition_summary, covenant_monitor, covenant_summary,
    record_covenant_cure, record_covenant_test,
)
from src.los import (authority, cma as cma_mod, copilot as cp, disops as do, docreg as dreg, esms as es,
                     ewp as ewp_mod, facilities as facmod, party_evidence as pev, pricing as pricing_mod,
                     projects as prj, proposal as prop_mod, ratings as rat, securities as sec, snapshot as snap)
from src.los import rules as rules_mod
from src.los import letters as lt
from src.los import config_version as cfgver
from src.los import routing as rt_routing
from src.los import profiles
from src.los import products as prodmod
from src.los import verification as dd
from src.los.mis import build_mis
from src.los.ip_note import build_ip_note, render_html, summarise
from src.los.sourcing import FIELDS as PREFILL_FIELDS, master_values
from src.los.risk_maker import RISK_MAKER_STEPS, build_risk_maker_view
from src.los.fields import model as fieldmodel
from src.agentic.critic import CriticAgent
from src.agentic.graph import AgentGraph, Node
from src.los import intake
from src.los import cam_intake, carry_forward, later_intake, prefill, reconcile
from src.los import terms as terms_mod
from src.models.canonical_model import Sector
from src.los.fields.metrics import agent_metrics
from src.los.fields.population import run_population
from src.los.fields.registry import FieldRegistry
from src.los.fields.resolvers import risk_maker_proposals
from src.los.workflow import (
    STATUS_APPROVED, STATUS_DRAFT, STATUS_IN_PROGRESS, STATUS_REJECTED, STATUS_WITHDRAWN, STATUS_DROPPED, TERMINAL,
    Workflow, WorkflowError, can_act, sla_state, transition,
)
import src.los.workflow as wfmod

DEMO_NOTE = "Demo data: fictitious users and seeded applications for demonstration."
log = logging.getLogger(__name__)
_AGENTS = 7          # credit-intelligence pipeline agents (progress estimate)
# Steps that decide on the Risk Maker's work: they get the review & committee pack.
COMMITTEE_STEPS = ("ip_risk_review", "ip_post_rating_vp", "ip_evp", "ip_sanction", "ap_risk_review", "ap_post_rating",
                   "ap_rating_vp", "ap_evp", "ap_recommend", "ap_es_review", "ap_es_recommend", "ap_dmd", "ap_sanction")
# The decisions shown in the remarks history (G-W5), in the bank's wording; a step's own label wins.
ACTION_WORDS = {"create": "Created", "submit": "Submitted", "approve": "Approved", "return": "Rework",
                "reject": "Rejected", "sanction": "Sanctioned", "allocate": "Allocated", "drop": "Dropped",
                "withdraw": "Withdrawn", "defer": "Deferred", "reactivate": "Reactivated",
                "propose_modification": "Modification proposed", "recommend_modification": "Recommended for modification",
                "dd_exception": "Compliance approval (exception)", "escalate": "Escalated", "reassign": "Reassigned"}
# The Environmental & Social (ESMS) process before the committee (G-W2)
ES_MAKER_STEP, ES_PREP_STEP = "ap_es_maker", "ap_es_prep"
_SECTIONS = 21       # analytical CAM sections written by the narrative agent
SOURCING_STEPS = ("ps_maker",)          # where documents are uploaded and the prefill is reviewed
PREP_STEPS = ("ps_maker", "ip_note", "ap_note", "ip_risk_maker", "ap_risk_maker", ES_MAKER_STEP,
              "pos_maker", "dis_maker")                                    # the preparation agent runs here
UPLOAD_STEPS = ("ps_maker", "ip_note", "ap_note", "pos_maker", "dis_maker")   # documents can be added at any maker stage
IP_NOTE_STEP = "ip_note"
# Steps where the due-diligence workspace may be worked, and where unresolved
# mandatory checks hard-stop a submission (GAP-P0-05/06 mandatory controls).
DD_STEPS = ("ps_maker", "ip_note", "ip_risk_maker", "ap_risk_maker")
DD_GATE_STEPS = ("ps_maker", "ip_risk_maker", "ap_risk_maker")

# Separate downloadable demo outputs (UAT-P1-7): the annexures are labelled demo templates —
# the client's exact annexure text is confirmation-required, so no content is fabricated.
OUTPUT_ANNEXURES = {
    "annexure_I": ("I", "List of documents and information"),
    "annexure_III": ("III", "Financial covenants"),
    "annexure_IV": ("IV", "Security and collateral"),
    "annexure_VI": ("VI", "Account and limit details"),
    "annexure_IX": ("IX", "Pricing and fees"),
    "annexure_XI": ("XI", "Drawdown and disbursement conditions"),
    "annexure_XIII": ("XIII", "KYC and party identification"),
    "annexure_XIV": ("XIV", "Compliance declarations"),
}
# The only committees that record a sanction (the Recommendations Committee records a recommendation).
SANCTION_STEPS = ("ip_sanction", "ap_sanction")
LETTER_ROLES = {"term_sheet": ("ps_maker",), "sanction_letter": ("pos_maker",)}   # who issues each document
SOURCING_DECISIONS = ("Refer for in-principle", "Request further information", "Defer", "Decline")
EXECUTION_STATUSES = ("executed", "partial", "not_executed")
UPLOAD_CATEGORIES = ("request", "kyc", "financials", "ratings", "collateral", "gst", "banking", "bureau", "legal",
                     "exchange", "misc", cam_intake.CAM_CATEGORY)
CAM_MODES = ("workspace", "document", "generate")
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Demo applications seeded on first start:
# (borrower, target step, flag, days since creation, days idle in the target step, note)
DEMO_SEED = [
    ("ABCE001", "ip_risk_maker", None, 9, 2, "Working-capital proposal at Risk Maker — run the credit assessment."),
    ("IHCL001", "ps_maker", "draft", 1, 1, "Prospect created; sourcing details in progress."),
    ("APOL001", "ip_sanction", None, 21, 9, "Awaiting IP Sanction Committee (SLA breached)."),
    ("MFL001", "ip_risk_maker", "returned", 14, 1, "Returned by Risk Review for rework."),
    ("MRF001", "ap_risk_maker", None, 30, 6, "Application Processing — credit reassessment (SLA breached)."),
    ("INFY001", "pos_maker", None, 38, 1, "Sanctioned; post-sanction documentation."),
    ("PNCR001", "dis_maker", "escalated", 45, 3, "Disbursement set-up; escalated for tranche timing."),
]
DEMO_EXIT_ENTITY = "PNCR002"

_demo_packages_cache: tuple[float, dict] = (0.0, {})


def _demo_packages() -> dict:
    """The bank-focused demo packages (config/demo_packages.yaml, R22), cached with hot reload."""
    global _demo_packages_cache
    base = os.getenv("CAM_CONFIG_DIR", "").strip() or str(Path(__file__).resolve().parents[2] / "config")
    path = Path(base) / "demo_packages.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _demo_packages_cache[0] >= mtime:
        return _demo_packages_cache[1]
    with open(path, "r", encoding="utf-8") as fh:
        data = _yaml.safe_load(fh) or {}
    _demo_packages_cache = (mtime, data)
    return data


_demo_scenarios_cache: tuple[float, dict] = (0.0, {})


def _demo_scenarios() -> dict:
    """The guided demo scenarios (config/demo_scenarios.yaml), cached with hot reload."""
    global _demo_scenarios_cache
    base = os.getenv("CAM_CONFIG_DIR", "").strip() or str(Path(__file__).resolve().parents[2] / "config")
    path = Path(base) / "demo_scenarios.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _demo_scenarios_cache[0] >= mtime:
        return _demo_scenarios_cache[1]
    with open(path, "r", encoding="utf-8") as fh:
        data = _yaml.safe_load(fh) or {}
    _demo_scenarios_cache = (mtime, data)
    return data


class LosService:
    def __init__(self, store, workflow_loader: Callable[[], Workflow], companies: dict,
                 clock: Callable[[], datetime] = datetime.now, cases=None, final_cam=None,
                 documents_root: Optional[Path] = None, doc_store=None, llm_factory: Optional[Callable] = None,
                 company_registrar: Optional[Callable] = None,
                 session_max_age: Optional[timedelta] = None,
                 session_idle_timeout: Optional[timedelta] = None):
        self.store = store
        self._workflow_loader = workflow_loader
        self._workflow: Optional[Workflow] = None
        self.companies = companies          # entity_id → company record (AppState.companies)
        self.clock = clock
        self.cases = cases                  # CaseService: runs the credit-intelligence pipeline
        self.final_cam = final_cam          # FinalCamService: re-syncs M1–M7 for a case
        self._sessions: dict[str, dict] = {}
        # R18: session security — absolute expiry and idle timeout (None = the profile default)
        self.session_max_age = session_max_age
        self.session_idle_timeout = session_idle_timeout
        self._jobs: dict[str, dict] = {}    # application_id → running / last credit-assessment job
        self._jobs_lock = threading.Lock()
        self.documents_root = Path(documents_root) if documents_root else None   # storage/documents/{entity}/...
        self.doc_store = doc_store          # DocumentStore: writes uploads into the borrower's folders
        self.llm_factory = llm_factory      # optional AI fallback / IP Note summary
        self._field_registry: Optional[FieldRegistry] = None
        self._wf_cache: dict[str, Workflow] = {}
        self._app_locks: dict[str, threading.Lock] = {}
        self._app_locks_guard = threading.Lock()
        self._prep_jobs: dict[str, dict] = {}   # application_id → stage-preparation job (agent lanes)
        self.company_registrar = company_registrar   # registers a new prospect borrower (CompanyService)

    @property
    def wf(self) -> Workflow:
        """The workflow of the active institution profile (sign-in, directory, new work).
        Application-scoped code uses ``_wf(app)`` instead, so an application always runs
        on the workflow of the profile it was created in."""
        if self._workflow is None:
            self._workflow = self._workflow_loader()
        return self._workflow

    def wf_for_profile(self, profile_id: Optional[str] = None) -> Workflow:
        """The journey of one institution profile (cached per profile id)."""
        pid = profile_id or profiles.active_profile_id()
        if pid not in self._wf_cache:
            self._wf_cache[pid] = load_workflow(pid)
        return self._wf_cache[pid]

    def _wf(self, app: Optional[dict]) -> Workflow:
        """The workflow an application runs under: the profile stored against it."""
        return self.wf_for_profile((app or {}).get("profile"))

    def invalidate_workflow_cache(self, profile_id: Optional[str] = None) -> None:
        """Drop cached journeys after the on-disk workflow / profile configuration changes."""
        if profile_id:
            self._wf_cache.pop(profile_id, None)
        else:
            self._wf_cache.clear()

    def now(self) -> datetime:
        return self.clock().replace(microsecond=0)

    # ── institution profile (resolved per application) ─────────────────────
    def _profile(self, app: Optional[dict] = None) -> dict:
        """The application's institution profile (the active one for new work)."""
        return profiles.get_profile(app=app)

    def _check_catalog(self, app: Optional[dict] = None) -> list[dict]:
        return prodmod.checks(self._profile(app), (app or {}).get("product"))

    def _doc_checklist(self, app: Optional[dict] = None) -> dict:
        return prodmod.documents(self._profile(app), (app or {}).get("product"),
                                 [profiles.primary_product(app)] or [None])

    def _exc_authority(self, app: Optional[dict] = None) -> dict:
        return profiles.exception_authority(self._profile(app))

    def profiles_view(self) -> dict:
        return profiles.profiles_view()

    def profile_detail(self, profile_id: str, full: bool = False) -> dict:
        try:
            return profiles.profile_summary(profile_id, full=full)
        except profiles.ProfileError as e:
            raise NotFoundError(str(e))

    def set_active_profile(self, session: dict, profile_id: str) -> dict:
        """Switch the institution for new work (journey, modules, checks, documents, authority, outputs).
        Administrator-only (the base skeleton profile is not selectable). Existing applications keep
        the profile recorded against them."""
        self._require_admin(session)
        try:
            profiles.set_active_profile(profile_id)
        except profiles.ProfileError as e:
            raise InvalidRequestError(str(e))
        self._workflow = None                      # the new journey applies to new work
        self._wf_cache.clear()
        self._admin_event(session, "active_profile_changed", f"Institution profile set to '{profile_id}'",
                          {"profile_id": profile_id})
        return profiles.profiles_view()

    # ── administration (administrator only) ──────────────────────────────────

    def _require_admin(self, session: Optional[dict]) -> dict:
        if not session or session.get("role") != "los_admin":
            raise ForbiddenError("Only the System Administrator (los_admin) may manage institution "
                                 "profiles and demo data")
        return session

    def _admin_event(self, session: dict, action: str, comment: str, detail: Optional[dict] = None) -> None:
        self.store.record_event({"application_id": "SYSTEM", "at": self.now().isoformat(timespec="seconds"),
                                 "actor_id": session.get("user", {}).get("id"), "actor_role": session.get("role"),
                                 "action": action, "from_step": None, "to_step": None, "status": None,
                                 "comment": comment, "detail": detail or {}})

    def admin_overview(self, session: dict) -> dict:
        """Read-only administration summary: institution profiles, products, seeded demo
        applications and the guided demo scenarios."""
        self._require_admin(session)
        by_profile: dict[str, dict] = {}
        for a in self.store.list():
            pid = a.get("profile") or "client_one"
            d = by_profile.setdefault(pid, {"applications": 0, "demo_applications": 0, "application_ids": []})
            d["applications"] += 1
            d["demo_applications"] += int(bool(a.get("is_demo")))
            d["application_ids"].append(a["application_id"])
        profs = []
        for p in profiles.profiles_view().get("profiles", []):
            full = profiles.get_profile(p["id"])
            wf = self.wf_for_profile(p["id"])
            appr = profiles.approval(full)
            active_roles = {s.role for s in wf.steps}
            active_roles.update({"los_admin", profiles.exception_authority(full).get("role")})
            active_roles.discard(None)
            profs.append({**p,
                          "selectable": p["id"] != "base",
                          "products": prodmod.profile_products(full),
                          "journey_steps": len(wf.steps),
                          "groups": len(wf.groups),
                          "roles": len(active_roles),
                          "modules": {m: bool(cfg.get("enabled", True)) for m, cfg in profiles.modules(full).items()},
                          "checks": len(profiles.check_catalog(full)),
                          "check_applicability": list(((full.get("checks") or {}).get("applicability") or {}).keys()),
                          "check_validity_days": (full.get("checks") or {}).get("validity_days") or {},
                          "esms_exceptions": profiles.esms_policy(full),
                          "documents": {st: len(items) for st, items in profiles.document_checklist(full).items()},
                          "approval": {"preliminary_bands": len(appr.get("preliminary") or []),
                                        "final_bands": len(appr.get("final") or []),
                                        "preliminary_top": (appr.get("preliminary") or [{}])[-1].get("authority", ""),
                                        "final_top": (appr.get("final") or [{}])[-1].get("authority", "")},
                          "outputs": {k: (profiles.output_template(k, full).get("title")
                                          or profiles.output_template(k, full).get("title_prefix") or "")
                                      for k in ("cam", "ip_note", "committee_pack", "sanction_letter", "term_sheet")},
                          "demo_applications": by_profile.get(p["id"], {}).get("demo_applications", 0)})
        return {"active_profile": profiles.active_profile_id(),
                "default_profile": profiles.default_profile_id(),
                "profiles": profs,
                "products": prodmod.list_products(),
                "applications_by_profile": by_profile,
                "demo_reset_scopes": ["active_profile"],
                "note": "This deployment presents one governed lending configuration. "
                        "Demo-data changes are audit-logged."}

    def admin_switch_profile(self, session: dict, profile_id: str, reseed: bool = False) -> dict:
        """Administrator: make an institution profile the active one, optionally reseeding its demo
        applications. Audited (``active_profile_changed``)."""
        self._require_admin(session)
        profile_id = str(profile_id or "").strip()
        if not profile_id:
            raise InvalidRequestError("Send a profile_id")
        if profile_id == "base":
            raise InvalidRequestError("The base profile is a configuration skeleton and cannot be activated")
        with self._admin_lock:
            try:
                profiles.set_active_profile(profile_id)
            except profiles.ProfileError as e:
                raise InvalidRequestError(str(e))
            self._workflow = None
            self._wf_cache.clear()
            created = 0
            if reseed:
                created = self.seed_profile_apps(profile_id, force=True)
            self._admin_event(session, "active_profile_changed",
                              f"Institution profile set to '{profile_id}'" + ("; demo applications reseeded" if reseed else ""),
                              {"profile_id": profile_id, "reseed": bool(reseed), "demo_applications_created": created})
            return {"active_profile": profiles.active_profile_id(), "reseeded": bool(reseed),
                    "demo_applications_created": created}

    def admin_reset_demo(self, session: dict, scope: str = "active_profile") -> dict:
        """Administrator: controlled demo-data reset — removes the seeded demo applications
        (of the active profile, or of every profile) and reseeds them deterministically.
        User-created applications are never touched. Audited (``demo_reset``)."""
        self._require_admin(session)
        if scope not in ("active_profile", "all_demo"):
            raise InvalidRequestError("scope must be 'active_profile' or 'all_demo'")
        active = profiles.active_profile_id()
        with self._admin_lock:
            removed = 0
            removed_by = {}
            for a in list(self.store.list()):
                if a.get("is_demo") and (scope == "all_demo" or (a.get("profile") or "client_one") == active):
                    self.store.delete(a["application_id"])
                    removed += 1
                    removed_by[a.get("profile") or "client_one"] = removed_by.get(a.get("profile") or "client_one", 0) + 1
            recreated_by = {}

            def _legacy():
                """The legacy Client One walkthrough set (idempotent per entity)."""
                n = self._seed_legacy_once()
                recreated_by["client_one"] = recreated_by.get("client_one", 0) + n

            def _profile(pid):
                """One presentation profile's seeded demos (force: replace, deterministic)."""
                n = self.seed_profile_apps(pid, force=True)
                recreated_by[pid] = recreated_by.get(pid, 0) + n

            if scope == "all_demo":
                # the complete expected demo dataset for EVERY selectable profile,
                # independent of the active profile
                _legacy()
                for p in profiles.profiles_view().get("profiles", []):
                    if p["id"] not in ("base", "client_one"):
                        _profile(p["id"])
            else:
                if active == "client_one":
                    _legacy()
                _profile(active)
            created = sum(recreated_by.values())
            self._admin_event(session, "demo_reset",
                              f"Demo data reset ({scope}): {removed} seeded application(s) removed, {created} recreated",
                              {"scope": scope, "removed": removed, "recreated": created,
                               "active_profile": active,
                               "removed_by_profile": removed_by, "recreated_by_profile": recreated_by})
            return {"scope": scope, "removed": removed, "recreated": created, "active_profile": active,
                    "removed_by_profile": removed_by, "recreated_by_profile": recreated_by}

    def demo_scenarios(self, profile_id: Optional[str] = None) -> dict:
        """The guided demo scenarios (any role; filtered to the institution profile, or every one
        when ``profile_id='all'``). Each scenario is enriched with its live demo application
        (id, borrower, current step and role) and the real next step from the profile's
        workflow — the walkthrough itself uses the normal application APIs only."""
        pid = profile_id or profiles.active_profile_id()
        out = []
        for s in _demo_scenarios().get("scenarios") or []:
            if pid == "all" or s.get("profile") in (None, pid):
                sc = dict(s)
                if (s.get("steps") or [{}])[0].get("action"):
                    sc["current_action"] = s["steps"][0]["action"]
                    sc["expected"] = s["steps"][0].get("expected", "")
                spid = s.get("profile") or (profiles.active_profile_id() if pid == "all" else pid)
                wf = self.wf_for_profile(spid)

                def _next(step_id):
                    idx = [i for i, x in enumerate(wf.steps) if x.id == step_id]
                    if not idx or idx[0] + 1 >= len(wf.steps):
                        return {}
                    nxt = wf.steps[idx[0] + 1]
                    return {"next_step": nxt.id, "next_step_name": nxt.name,
                            "next_role_id": nxt.role, "next_role": wf.roles.get(nxt.role, nxt.role)}

                app = None
                if s.get("application_entity"):
                    app = next((a for a in self.store.list()
                                if a.get("is_demo") and a["entity_id"] == s["application_entity"]
                                and (a.get("profile") or "client_one") == spid), None)
                if app:
                    step = wf.step(app["step_id"])
                    sc.update({"application_id": app["application_id"],
                               "application_borrower": app.get("borrower_name"),
                               "application_profile": app.get("profile") or spid,
                               "live_step": step.id, "live_step_name": step.name,
                               "live_role_id": step.role, "live_role": wf.roles.get(step.role, step.role),
                               "start_role": step.role, "start_step": step.id, **_next(step.id)})
                elif s.get("start_step"):
                    step = wf.step(s["start_step"])
                    sc.update({"start_role": step.role,
                               "live_step": step.id, "live_step_name": step.name,
                               "live_role": wf.roles.get(step.role, step.role), **_next(step.id)})
                out.append(sc)
        return {"active_profile": pid, "scenarios": out}

    _admin_lock = threading.Lock()

    def branding_view(self) -> dict:
        prof = profiles.get_profile()
        return {"branding": profiles.branding(prof), "labels": profiles.labels(prof),
                "profile": {"id": prof["profile"]["id"], "name": prof["profile"]["name"]}}

    def demo_packages(self, profile_id: Optional[str] = None) -> dict:
        """R22: the bank-focused demo packages (executive / functional walkthroughs of the
        22 enhancements). Each package is enriched with its live demo application (id,
        borrower, current step and role) from the profile's workflow — the walkthrough itself
        uses the normal application APIs only. Filtered to the institution profile, or every
        one when ``profile_id='all'``."""
        pid = profile_id or profiles.active_profile_id()
        data = _demo_packages()
        out = []
        for pk in data.get("packages") or []:
            if pid == "all" or pk.get("profile") in (None, pid):
                p2 = dict(pk)
                spid = pk.get("profile") or pid
                wf = self.wf_for_profile(spid)
                app = None
                if pk.get("application_entity"):
                    app = next((a for a in self.store.list()
                                if a.get("is_demo") and a["entity_id"] == pk["application_entity"]
                                and (a.get("profile") or "client_one") == spid), None)
                if app and app.get("step_id"):
                    step = wf.step(app["step_id"])
                    p2.update({"application_id": app["application_id"],
                               "application_borrower": app.get("borrower_name"),
                               "live_step": step.id, "live_step_name": step.name,
                               "live_role": wf.roles.get(step.role, step.role)})
                    if p2.get("sign_in", {}).get("role") == step.role:
                        p2["sign_in"] = {**p2["sign_in"], "user": app.get("assignee_id")
                                         or p2["sign_in"].get("user")}
                elif app:
                    p2.update({"application_id": app["application_id"],
                               "application_borrower": app.get("borrower_name"), "completed": True})
                else:
                    # the seeded case sits at an earlier stage than the package opens on: the
                    # walkthrough plays it forward through its normal steps first
                    at = wf.step(app["step_id"]).name if (app and app.get("step_id")) else "an earlier stage"
                    p2["seed_note"] = (f"This case is live at “{at}” — play the package's steps in order "
                                       "from the live stage, or seed fresh demo applications "
                                       "(Administration → reset demo).")
                out.append(p2)
        return {"reset": data.get("reset") or {}, "packages": out}

    def products_view(self) -> list[dict]:
        return prodmod.list_products()

    def product_detail(self, product_id: str, profile_id: Optional[str] = None) -> dict:
        try:
            return prodmod.resolve_product(product_id, profiles.profile_for_new(profile_id))
        except prodmod.ProductError as e:
            raise NotFoundError(str(e))

    # ── demo sign-in ─────────────────────────────────────────────────────────
    def directory(self) -> dict:
        """Groups, roles and demo users for the sign-in screen and allocation pickers,
        with the institution profile's branding."""
        prof = profiles.get_profile()
        visible_roles = {s.role for s in self.wf.steps}
        visible_roles.update({"los_admin", profiles.exception_authority(prof).get("role")})
        visible_roles.discard(None)
        groups = []
        for group in self.wf.groups:
            roles = [r for r in group.get("roles", []) if r in visible_roles]
            if roles:
                groups.append({**group, "roles": roles})
        users = []
        for user in self.wf.users:
            roles = [r for r in user.get("roles", []) if r in visible_roles]
            if roles:
                users.append({**{k: user[k] for k in ("id", "name", "email", "branch")}, "roles": roles})
        return {"groups": groups, "roles": {r: n for r, n in self.wf.roles.items() if r in visible_roles},
                "users": users,
                "note": DEMO_NOTE, "branding": profiles.branding(prof),
                "profile": {"id": prof["profile"]["id"], "name": prof["profile"]["name"]}}

    def sign_in(self, user_id: str, role: str) -> dict:
        try:
            user = self.wf.user(user_id)
        except WorkflowError as e:
            raise NotFoundError(str(e))
        if role not in user.get("roles", []):
            raise ForbiddenError(f"{user['name']} does not hold the role {role}")
        visible_roles = {s.role for s in self.wf.steps}
        visible_roles.update({"los_admin", profiles.exception_authority().get("role")})
        token = secrets.token_urlsafe(24)
        now = self.now()
        session_user = {k: user[k] for k in ("id", "name", "email", "branch")}
        session_user["roles"] = [r for r in user.get("roles", []) if r in visible_roles]
        session = {"token": token, "user": session_user,
                   "role": role, "role_name": self.wf.roles[role], "group": self.wf.group_of_role(role),
                   "created_at": now, "last_used_at": now}
        self._sessions[token] = session
        return session

    def _session_policy(self) -> tuple:
        """The active session policy: the explicit service values, else the profile defaults."""
        prof = self._default_profile_cfg() if hasattr(self, "_default_profile_cfg") else {}
        sec = (prof.get("session") or {})
        max_age = self.session_max_age
        idle = self.session_idle_timeout
        if max_age is None:
            try:
                max_age = timedelta(hours=float(sec.get("max_hours") or 8))
            except (TypeError, ValueError):
                max_age = timedelta(hours=8)
        if idle is None:
            try:
                idle = timedelta(minutes=float(sec.get("idle_minutes") or 30))
            except (TypeError, ValueError):
                idle = timedelta(minutes=30)
        return max_age, idle

    def _session_expired(self, s: dict) -> bool:
        max_age, idle = self._session_policy()
        now = self.now()
        if now - s.get("created_at", now) > max_age:
            return True
        if now - s.get("last_used_at", now) > idle:
            return True
        return False

    def session(self, token: Optional[str]) -> dict:
        s = self._sessions.get(token or "")
        if not s:
            raise ForbiddenError("Not signed in (demo session expired — sign in again)")
        if self._session_expired(s):
            # the session is dead: drop it so the token cannot be replayed
            self._sessions.pop(token or "", None)
            raise ForbiddenError("Session expired (idle or maximum age) — sign in again")
        s["last_used_at"] = self.now()
        return s

    def switch_role(self, token: str, role: str) -> dict:
        """R18: a session can only move between roles the person genuinely holds — the stored
        session is the source of truth, never a client-supplied role."""
        s = self.session(token)
        if role not in s["user"]["roles"]:
            raise ForbiddenError(f"{s['user']['name']} does not hold the role {role}")
        s.update(role=role, role_name=self.wf.roles[role], group=self.wf.group_of_role(role),
                 last_used_at=self.now())
        return s

    def sign_out(self, token: str) -> None:
        self._sessions.pop(token or "", None)

    # ── idempotency (R15) ──────────────────────────────────────────────────
    def idempotent(self, key: Optional[str], scope: str, application_id: Optional[str], fn):
        """Run ``fn`` under an idempotency key: a repeated successful request returns the original
        result without re-executing; a failed request is not cached, so it may be retried."""
        if not key:
            return fn()
        try:
            at = self.now().isoformat(timespec="seconds")
        except AttributeError:            # a bare LosService built for tests without a clock
            at = datetime.now().isoformat(timespec="seconds")
        state = self.store.idempotency_begin(key, scope, application_id, at)
        if state == "hit":
            r = self.store.idempotency_result(key)
            if r and r.get("status") == "completed":
                return dict(r["result"])
        if state != "new":
            raise ConflictError("A request with this idempotency key is already in flight; "
                                "wait for it to complete or use a new key")
        try:
            result = fn()
        except Exception:
            self.store.idempotency_fail(key, "", at)
            raise
        self.store.idempotency_complete(key, result, at)
        return result

    # ── reads ────────────────────────────────────────────────────────────────
    def _require(self, application_id: str) -> dict:
        app = self.store.get(application_id)
        if not app:
            raise NotFoundError(f"Application {application_id} not found")
        return app

    def _user_name(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        try:
            return self.wf.user(user_id)["name"]
        except WorkflowError:
            return user_id

    def _view(self, app: dict, session: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
        """The application with its current step, SLA, rail and the actions open to this session."""
        now = now or self.now()
        view = dict(app)
        # Older stored applications contain only ``facility``. Expose the new
        # collection shape without requiring a destructive data migration.
        if not view.get("facilities") and view.get("facility"):
            view["facilities"] = [dict(view["facility"], facility_id="FAC-001")]
        view.setdefault("related_parties", [])
        view["assignee_name"] = self._user_name(app.get("assignee_id"))
        if app.get("ip_note"):
            n = app["ip_note"]
            view["ip_note"] = {"generated_at": n.get("generated_at"), "outcome": n["prescreen"]["outcome"],
                               "prepared_by": n.get("prepared_by"), "seeded": bool(n.get("seeded"))}
        if app.get("sourcing"):
            src = app["sourcing"]
            view["sourcing"] = {"prefill_at": (src.get("prefill") or {}).get("generated_at"),
                                "summary": (src.get("prefill") or {}).get("summary"),
                                "accepted": len(src.get("accepted") or {})}
        if app.get("cam"):
            view["cam"] = {"document": app["cam"].get("document"), "summary": app["cam"].get("summary"),
                           "read_at": app["cam"].get("read_at")}
        created = datetime.fromisoformat(app["created_at"])
        view["tat_days"] = round((now - created).total_seconds() / 86400, 1)
        if app.get("step_id"):
            step = self._wf(app).step(app["step_id"])
            view["step"] = {"id": step.id, "name": step.name, "kind": step.kind, "role": step.role,
                            "role_name": self._wf(app).roles[step.role], "stage_id": step.stage_id,
                            "stage_name": step.stage_name, "sla_days": step.sla_days,
                            "allocates_to": step.allocates_to}
            active = app["status"] not in TERMINAL
            deferred = app["status"] == wfmod.STATUS_DEFERRED
            # A deferred application is on hold: its SLA clock is paused (restarted on reactivation).
            view["sla"] = (sla_state(datetime.fromisoformat(app["step_entered_at"]), step, now)
                           if active and not deferred else None)
            holder = app.get("assignee_id") in (None, (session or {}).get("user", {}).get("id"))
            in_role = bool(session and active and can_act(self._wf(app), session["user"]["id"], session["role"], step))
            # the step's actions are offered to the person it is assigned to; others in the role see who holds it
            view["actions"] = list(wfmod.available_actions(self._wf(app), step, app["status"])) if in_role and holder else []
            view["assigned_to_other"] = in_role and not holder
            view["action_labels"] = {a: wfmod.action_label(step, a) for a in view["actions"]
                                     if wfmod.action_label(step, a)}
            view["decision_fields"] = [dict(f, type=wfmod.DECISION_FIELD_TYPES[f["id"]],
                                            label=self._wf(app).decision_field_labels.get(f["id"], f["id"].replace("_", " ").capitalize()))
                                       for f in step.decision_fields]
            view["decision_defaults"] = self._decision_defaults(app, step) if step.decision_fields else {}
            view["remarks_required"] = self._wf(app).remarks_required
            view["deferral"] = (app.get("deferrals") or [None])[-1] if deferred else None
            # R2: a deferral reminder — days until the case must be taken up (negative: overdue)
            if deferred and view["deferral"].get("until"):
                due = datetime.fromisoformat(view["deferral"]["until"]).date()
                view["deferral_days"] = (due - now.date()).days
            view["rework_destinations"] = (wfmod.rework_destinations(self._wf(app), step)
                                           if step.kind in ("checker", "committee", "vp_review") else [])
            view["can_reassign"] = bool(session and active and self._may_reassign(session, step))
        else:
            view["step"], view["sla"], view["actions"], view["can_reassign"] = None, None, [], False
        view["rail"] = self._rail(app)
        # R1: the calculated route (authority → steps & concurrences) and R16: its configuration versions
        view["routing"] = rt_routing.public_route(app.get("routing"))
        view["routing_history"] = [rt_routing.public_route(r) for r in (app.get("routing_history") or [])]
        view["concurrences"] = app.get("concurrences") or []
        view["routing_ack"] = app.get("routing_ack") or None
        view["config_snapshot"] = app.get("config_snapshot") or None
        view["config_migrations"] = app.get("config_migrations") or []
        # Governed workspaces (GAP-P0-01/04/07/08/09, P1-01/02/03/04/05) — summaries for list/get.
        _facs, split = facmod.facilities_view(app)
        view["exposure_split"] = split
        view["securities"] = app.get("securities") or []
        view["security_cover"] = sec.cover_ratio(view["securities"], app.get("amount_cr"))
        view["projects"] = app.get("projects") or []
        view["projects_status"] = prj.project_summary(view["projects"])
        view["esms_status"] = (app.get("esms") or {}).get("status")
        view["esms"] = app.get("esms")
        view["esms_checklist"] = es.ES_CHECKLIST
        view["cma_rows"] = cma_mod.CMA_ROWS
        view["ewps"] = app.get("ewps") or []
        view["related_parties"] = app.get("related_parties") or []
        view["party_evidence_coverage"] = {p["party_id"]: pev.coverage(p) for p in view["related_parties"]}
        view["open_invalidations"] = [i for i in app.get("invalidations", []) if i["status"] == "open"]
        view["decisions"] = app.get("decisions") or []
        view["proposal"] = app.get("proposal")
        view["pricing"] = app.get("pricing")
        view["terms_summary"] = terms_mod.summary(app.get("terms"), app.get("fields"))
        secured_ids = {fid for s in app.get("securities") or [] for fid in s.get("facility_ids") or []}
        view["facilities"] = [dict(f, secured=f["facility_id"] in secured_ids) if isinstance(f, dict) and "facility_id" in f
                              else f for f in view.get("facilities") or []]
        view["unit_visits"] = app.get("unit_visits") or []
        view["unit_visit_observations"] = list(prop_mod.UNIT_VISIT_OBSERVATIONS)
        view["sourcing_details"] = app.get("sourcing_details")
        view["prospect"] = self._prospect_record(app)
        view["sourcing_sources"] = list(prop_mod.SOURCES)
        view["security_notes"] = app.get("security_notes") or {}
        view["security_note_labels"] = prefill.SECURITY_NOTES
        view["narrative_labels"] = {**cam_intake.NARRATIVE_LABELS, "other_material_information": "Other material information",
                                    **prefill.BANK_NARRATIVES}
        view["prefill_coverage"] = prefill.ip_coverage(app) if app.get("stage_id") in ("IP", "AP") else None
        ratings = app.get("ratings") or {}
        view["ratings"] = {k: ratings.get(k) for k in ("external_ratings", "internal_ratings", "group_rating",
                                                       "adverse_events", "crp_notes", "raroc")}
        view["raroc_stale"] = rat.stale_raroc(app)
        view["cma"] = cma_mod.cma_view(app)
        view["cma_reconciliation"] = cma_mod.reconciliation(app)
        view["pricing_gate"] = pricing_mod.pricing_gate(app.get("pricing") or {}, app.get("facilities") or [])
        view["proposal_gate"] = prop_mod.banking_gate((app.get("proposal") or {}).get("banking"))
        view["exposure_gate"] = prop_mod.exposure_gate((app.get("proposal") or {}).get("exposure") or {})
        view["documents_gate"] = dreg.stage_gate(app)
        view["material_changes"] = snap.material_changes(app) if app.get("snapshots") else []
        view["material_change_gate"] = snap.material_change_gate(app) if app.get("snapshots") else None
        view["exception_requests"] = self._pending_exception_requests(app)
        view["assessment_stale"] = (self._case_stale(self._app_case(app)[0] or {}, app)
                                    if self.cases and (app.get("credit_assessment") or {}).get("run_id") else None)
        view["snapshots"] = [s["ref"] for s in sorted(app.get("snapshots") or [], key=lambda s: (s.get("seq", 0), s.get("at") or ""))]
        view["rules_failed"] = [r for r in rules_mod.evaluate(app) if r["status"] == "failed"]
        view["disops"] = do.disops_view(app) if app.get("stage_id") in ("POS", "DIS") or app.get("disops", {}).get("sop") else None
        return view

    def _rail(self, app: dict) -> list[dict]:
        current = self._wf(app).step(app["step_id"]).index if app.get("step_id") else len(self._wf(app).steps)
        done_all = app["status"] == STATUS_APPROVED
        returned = app["status"] == "RETURNED"
        rail = []
        for stage in self._wf(app).stages:
            steps = []
            for s in (x for x in self._wf(app).steps if x.stage_id == stage["id"]):
                state = ("done" if done_all or s.index < current
                         else "current" if s.index == current else "pending")
                if state == "current" and returned:
                    state = "returned"
                if state == "current" and app["status"] == STATUS_REJECTED:
                    state = "rejected"
                steps.append({"id": s.id, "name": s.name, "state": state, "role_name": self._wf(app).roles[s.role]})
            states = {x["state"] for x in steps}
            stage_state = ("done" if states == {"done"} else
                           "current" if states & {"current", "returned", "rejected"} else "pending")
            rail.append({"id": stage["id"], "name": stage["name"], "state": stage_state, "steps": steps})
        return rail

    def _active_profile_apps(self) -> list[dict]:
        """Applications belonging to the one institution configuration shown in the demo."""
        active = profiles.active_profile_id()
        return [a for a in self.store.list()
                if (a.get("profile") or "client_one") == active]

    def list(self, session: Optional[dict] = None, *, status: str = "", stage: str = "", mine: bool = False,
             query: str = "") -> list[dict]:
        now = self.now()
        out = []
        for app in self._active_profile_apps():
            if status and app["status"] != status:
                continue
            if stage and app.get("stage_id") != stage:
                continue
            if mine and session and session["role"] == profiles.exception_authority()["role"]:
                if app["status"] in TERMINAL or not [r for r in self._pending_exception_requests(app)
                                                       if r.get("to_id") in (None, session["user"]["id"])]:
                    continue
            elif mine and session:
                step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
                if not step or app["status"] in TERMINAL or step.role != session["role"]:
                    continue
                if app.get("assignee_id") not in (None, session["user"]["id"]):
                    continue
            if query:
                hay = " ".join(str(app.get(k, "")) for k in ("application_id", "borrower_name", "entity_id")).lower()
                if query.lower() not in hay:
                    continue
            out.append(self._view(app, session, now))
        return out

    @staticmethod
    def _pending_exception_requests(app: dict) -> list[dict]:
        return [{**c["exception_request"], "check_id": c["id"], "name": c["name"], "check_status": c["status"]}
                for c in (app.get("due_diligence") or {}).get("checks") or []
                if (c.get("exception_request") or {}).get("status") == "pending" and not c.get("exception")]

    def get(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        view = self._view(app, session)
        view["events"] = [self._event_view(e) for e in self.store.events(application_id)]
        view["blockers"] = self.blockers(app)            # what stops the step's forward action now
        # Live customer identity & deduplication (the snapshot taken at creation stays in the record).
        view["customer_identity"] = self.borrower_identity(app["entity_id"], exclude_app=application_id)
        view["summary"] = self.summary(app)              # R13 - the document-free case view
        return view

    def summary(self, app=None, application_id=None) -> dict:
        """R13 - a compact, document-free case summary for approvals: the headline terms, the
        position at each stage, the open risks (policy deviations, conditions, covenant breaches,
        open E&S exceptions), the recent decisions, and the pending work on every desk."""
        if app is None:
            app = self._require(application_id)
        wf = self._wf(app)
        facs = app.get("facilities") or [app.get("facility") or {}]
        total = round(sum(float(f.get("amount_cr") or 0) for f in facs), 2)
        try:
            if self._reached_stage(app, "disbursement"):
                stage = "Disbursement"
            elif self._reached_stage(app, "post_sanction"):
                stage = "Post-sanction"
            elif self._reached_stage(app, "sanction"):
                stage = "Sanction"
            elif self._reached_stage(app, "risk_assessment"):
                stage = "Credit assessment"
            elif self._reached_stage(app, "information_gathering"):
                stage = "Information gathering"
            else:
                stage = "Intake"
        except Exception:
            stage = None
        open_risks = []
        for d in app.get("policy_deviation_items") or []:
            if d.get("status") in ("open", "in_progress"):
                open_risks.append({"kind": "policy_deviation", "id": d.get("deviation_id"),
                                   "detail": ((d.get("deviation_type") or "deviation") + " - " + (d.get("summary") or ""))[:140],
                                   "status": d.get("status")})
        for c in app.get("conditions") or []:
            if c.get("status") in ("open", "partially_met", "in_progress"):
                open_risks.append({"kind": "condition_" + str(c.get("type")), "id": c.get("condition_id"),
                                   "detail": (c.get("condition_text") or "")[:140], "status": c.get("status")})
        for c in app.get("covenants") or []:
            latest = (c.get("monitoring") or [{}])[-1]
            if latest.get("status") == "breached" or c.get("status") == "breached":
                open_risks.append({"kind": "covenant_breach", "id": c.get("covenant_id"),
                                   "detail": (c.get("description") or "")[:140], "status": "breached"})
        for e in app.get("exceptions") or []:
            if e.get("status") in ("open", "under_review"):
                open_risks.append({"kind": "es_exception", "id": e.get("exception_id"),
                                   "detail": (e.get("exception_type") or "exception")[:140], "status": e.get("status")})
        for m in app.get("modifications") or []:
            if m.get("status") == "open":
                open_risks.append({"kind": "modification", "id": m.get("modification_id"),
                                   "detail": (m.get("reason") or "")[:140], "status": "open"})
        pending = []
        if app.get("status") not in TERMINAL:
            step = wf.step(app["step_id"])
            if step:
                pending.append({"where": step.name, "role": wf.roles.get(step.role, step.role),
                                "waiting": "decision" if step.kind in ("checker", "committee", "vp_review", "allocation")
                                           else "documentation / action"})
        return {
            "application_id": app.get("application_id"),
            "name": app.get("borrower_name"),
            "status": app.get("status"),
            "stage": stage,
            "profile": app.get("profile") or self.default_profile,
            "product": app.get("product"),
            "total_amount_cr": total,
            "facilities": [{"facility_id": f.get("facility_id"), "facility_type": f.get("facility_type"),
                            "amount_cr": f.get("amount_cr")} for f in facs],
            "current_step": (lambda st: {"id": st.id, "name": st.name,
                                         "role": wf.roles.get(st.role, st.role)} if st else None)(
                wf.step(app["step_id"]) if app.get("step_id") else None),
            "positions": self._decision_positions(app),
            "latest_risk_grade": (app.get("credit_assessment") or {}).get("risk_grade"),
            "deviation_count": len(app.get("policy_deviation_items") or []),
            "open_risks": open_risks,
            "recent_decisions": (app.get("decisions") or [])[-5:],
            "pending": pending,
            "blockers": self.blockers(app) if app.get("status") not in TERMINAL else [],
            "as_of": self.now().isoformat(timespec="seconds"),
        }

    def _decision_positions(self, app: dict) -> dict:
        """The standing position at each governance point: the calculated route's authority,
        the committee decisions of record, the sanction outcome, and the latest credit
        assessment."""
        positions: dict = {}
        route = app.get("routing") or {}
        prelim = (route.get("authority_of_record") or {}).get("preliminary_authority") or route.get("preliminary_authority") or {}
        final = (route.get("authority_of_record") or {}).get("final_authority") or route.get("final_authority") or {}
        if isinstance(prelim, dict) and prelim.get("required"):
            positions["ip_authority"] = {"recommended": prelim.get("required"),
                                         "basis": prelim.get("basis"), "at": prelim.get("at") or route.get("calculated_at")}
        if isinstance(final, dict) and final.get("required"):
            positions["final_authority"] = {"recommended": final.get("required"),
                                            "basis": final.get("basis"), "at": final.get("at") or route.get("calculated_at")}
        for d in app.get("decisions") or []:
            step_id = d.get("at_step")
            if step_id == "ip_sanction" or d.get("stage") == "IP":
                positions["ip_committee"] = {"decision": d.get("decision") or d.get("action"),
                                             "by": d.get("by"), "at": d.get("at")}
            elif step_id == "ap_sanction" or d.get("stage") == "final":
                positions["sanction_committee"] = {"decision": d.get("decision") or d.get("action"),
                                                   "by": d.get("by"), "at": d.get("at")}
        ca = app.get("credit_assessment") or {}
        if ca:
            positions["latest_risk_assessment"] = {"risk_grade": ca.get("risk_grade"),
                                                   "recommended_cr": ca.get("recommended_cr"),
                                                   "at": ca.get("run_at")}
        for stage_id, sanc in (app.get("sanctions") or {}).items():
            key = "sanction" if stage_id == "AP" else "ip_sanction"
            positions[key] = {"decision": "sanctioned",
                              "amount_cr": (sanc or {}).get("sanctioned_cr"),
                              "authority": (sanc or {}).get("authority"),
                              "minutes": (sanc or {}).get("minutes"),
                              "at": (sanc or {}).get("at")}
        return positions

    def borrower_identity(self, entity_id: str, exclude_app: Optional[str] = None) -> dict:
        """Customer identity & deduplication for a borrower: the borrower master, the reference
        identifier table (PAN/CIN/GSTIN), the core-banking book (demo data until real adapters
        land) and the LOS record for duplicate applications (same entity, PAN or CIN)."""
        from src.services.external_systems import reference_identifiers

        if entity_id not in self.companies:
            raise NotFoundError(f"Borrower {entity_id} not found")
        company = self.companies[entity_id]
        borrower = company.get("borrower") or {}
        facility = company.get("facility")
        reference = reference_identifiers(entity_id)
        name = getattr(borrower, "company_name", entity_id)
        pan = getattr(borrower, "pan", None) or reference.get("pan") or None
        cin = getattr(borrower, "cin", None) or reference.get("cin") or None
        gstin = company.get("gstin") or reference.get("gstin") or None
        case_type = getattr(getattr(facility, "case_type", None), "value", None)
        doi = getattr(borrower, "date_of_incorporation", None)
        constitution = getattr(getattr(borrower, "borrower_type", None), "value", None)
        existing = company.get("existing_exposure") or []
        outstanding = round(sum(float(e.outstanding_cr or 0) for e in existing), 2)
        customer_id = f"CIF-{entity_id}" if (case_type == "ETB" or existing) else None
        if customer_id:
            cbs = {"status": "found",
                   "detail": (f"Existing customer on the core-banking book: {len(existing)} facility(ies), "
                              f"outstanding ₹{outstanding:,.2f} Cr") if existing
                   else "Existing customer on the core-banking book (ETB) — accounts in core banking",
                   "source": "Core banking (demo data)"}
        else:
            cbs = {"status": "not_found",
                   "detail": "No customer record on the core-banking book — prospective new-to-bank "
                             "customer; the CIF is allocated at onboarding",
                   "source": "Core banking (demo data)"}
        matches = self._duplicate_applications(entity_id, pan, cin, exclude_app)
        cin_status = "valid" if re.fullmatch(r"[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}", cin or "") else (
            "invalid" if cin else "missing")
        gstin_status = "valid" if re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9]Z[A-Z0-9]", gstin or "") else (
            "invalid" if gstin else "missing")
        customer_id_options = ([{"value": customer_id, "label": f"{customer_id} — existing customer"}]
                               if customer_id else []) + [{"value": "new", "label": "New customer — CIF allocated at onboarding"}]
        return {
            "entity_id": entity_id,
            "name": name,
            "ntb_etb": case_type or "NTB",
            "customer_id": customer_id,
            "customer_id_options": customer_id_options,
            "pan": pan,
            "name_as_per_pan": name if pan else None,
            "cin": cin,
            "cin_status": cin_status,
            "gstin": gstin,
            "gstin_status": gstin_status,
            "date_of_incorporation": doi.isoformat() if doi else None,
            "constitution": constitution,
            "cbs": cbs,
            "los_duplicates": {
                "checked_at": self.now().isoformat(timespec="seconds"),
                "matches": matches,
                "advice": (f"{len(matches)} existing LOS application(s) for this customer — confirm this "
                           f"is not a duplicate before creating.")
                if matches else "No other LOS application on record for this customer (same entity, PAN or CIN).",
            },
        }

    def _duplicate_applications(self, entity_id: str, pan: Optional[str], cin: Optional[str],
                                exclude_app: Optional[str]) -> list[dict]:
        """Potential duplicate LOS applications: same borrower, or the same PAN / CIN on record."""
        out = []
        for app in self.store.list():
            if app["application_id"] == exclude_app:
                continue
            other = (self.companies.get(app["entity_id"]) or {}).get("borrower") or {}
            opan = str(getattr(other, "pan", "") or "").upper()
            ocin = str(getattr(other, "cin", "") or "").upper()
            matched_on = []
            if app["entity_id"] == entity_id:
                matched_on.append("same customer (entity)")
            if pan and opan == str(pan).upper():
                matched_on.append("same PAN")
            if cin and ocin == str(cin).upper():
                matched_on.append("same CIN")
            if not matched_on:
                continue
            step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
            stage = next((s for s in self._wf(app).stages if s["id"] == app.get("stage_id")), None)
            out.append({"application_id": app["application_id"], "borrower_name": app["borrower_name"],
                        "entity_id": app["entity_id"], "stage": stage["name"] if stage else "—",
                        "step": step.name if step else "Complete", "status": app["status"],
                        "amount_cr": app.get("amount_cr"), "updated_at": app.get("updated_at"),
                        "matched_on": matched_on})
        return out

    def _event_view(self, e: dict) -> dict:
        e = dict(e)
        e["actor_name"] = self._user_name(e.get("actor_id")) or "System"
        e["actor_role_name"] = self.wf.roles.get(e.get("actor_role") or "", e.get("actor_role"))
        for k in ("from_step", "to_step"):
            if e.get(k):
                try:
                    e[k + "_name"] = self.wf.step(e[k]).name
                except WorkflowError:
                    e[k + "_name"] = e[k]
        return e

    def audit(self, limit: int = 200) -> list[dict]:
        active = profiles.active_profile_id()
        application_ids = {a["application_id"] for a in self._active_profile_apps()}
        events = []
        for event in self.store.events(limit=max(limit * 5, limit)):
            if event.get("application_id") in application_ids:
                events.append(event)
            elif event.get("application_id") == "SYSTEM":
                detail = event.get("detail") or {}
                event_profile = detail.get("profile_id") or detail.get("active_profile")
                if event_profile in (None, active):
                    events.append(event)
            if len(events) >= limit:
                break
        return [self._event_view(e) for e in events]

    def dashboard(self, session: Optional[dict] = None) -> dict:
        now = self.now()
        profile_apps = self._active_profile_apps()
        apps = [self._view(a, session, now) for a in profile_apps]
        active = [a for a in apps if a["status"] not in TERMINAL]
        month_start = now.replace(day=1, hour=0, minute=0, second=0)
        application_ids = {a["application_id"] for a in profile_apps}
        sanctioned_mtd = {e["application_id"] for e in self.store.events(limit=5000)
                          if e["action"] == "sanction" and datetime.fromisoformat(e["at"]) >= month_start}
        sanctioned_mtd &= application_ids
        stage_counts = {s["id"]: 0 for s in self.wf.stages}
        for a in active:
            stage_counts[a["stage_id"]] = stage_counts.get(a["stage_id"], 0) + 1
        mine = self.list(session, mine=True) if session else []
        return {
            "as_of": now.isoformat(timespec="minutes"),
            "kpis": {
                "total": len(apps), "active": len(active),
                "sla_breached": sum(1 for a in active if (a.get("sla") or {}).get("breached")),
                "sla_escalated": sum(1 for a in active if (a.get("sla") or {}).get("escalated")),
                "sanctioned_mtd": len(sanctioned_mtd),
                "exposure_cr": round(sum(a.get("amount_cr") or 0 for a in active), 2),
                "avg_tat_days": round(sum(a["tat_days"] for a in active) / len(active), 1) if active else 0,
                "pending_committee": sum(1 for a in active if (a.get("step") or {}).get("kind") == "committee"),
                "dd_blocking": sum(1 for a in active
                                   if a.get("due_diligence") and dd.blocking(
                                       [c for c in a["due_diligence"]["checks"]
                                        if dd.check_applies(((profiles.get_profile(app=a).get("checks") or {}).get("applicability") or {}).get(c["id"]) or {}, a)[0]],
                                       now=now,
                                       validity_days={k: int(v) for k, v in ((profiles.get_profile(app=a).get("checks") or {}).get("validity_days") or {}).items()})),
                "dd_rescreen_overdue": sum(1 for a in active if a.get("due_diligence")
                                           and dd.summary(a["due_diligence"]["checks"], now).get("rescreen_overdue")),
                "disbursed": sum(1 for a in apps if a["status"] == STATUS_APPROVED),
                "rejected": sum(1 for a in apps if a["status"] == STATUS_REJECTED),
                "my_queue": len(mine),
            },
            "stages": [{"id": s["id"], "name": s["name"], "count": stage_counts.get(s["id"], 0)} for s in self.wf.stages],
            "screening_alerts": self._screening_alerts(apps, now),
            "note": DEMO_NOTE,
        }

    def _screening_alerts(self, apps: list[dict], now: datetime) -> list[dict]:
        """Expiry reminders and escalations (UAT-P0-2): re-screening overdue / due soon, and
        Compliance VP exceptions expiring or already lapsed, across active applications."""
        alerts = []
        for a in apps:
            if a["status"] in TERMINAL or not a.get("due_diligence"):
                continue
            pol = profiles.check_policy(profiles.get_profile(app=a))
            exc_name = profiles.exception_authority(profiles.get_profile(app=a))["name"]
            rev = dd.screening_review(a["due_diligence"]["checks"], now, pol)
            if not rev["needs_attention"]:
                continue
            items = [f"{r['name']}: {pol['rescreen_days']}-day re-screening due {r['due_at']} ({r['days_left']} days left)"
                     for r in rev["rescreens"] if r["state"] != "current"]
            items += [f"{e['name']}: {exc_name} exception {e['state']} on {e['expires_at']}"
                      for e in rev["exceptions"] if e["state"] != "current"]
            alerts.append({"application_id": a["application_id"], "borrower_name": a.get("borrower_name"),
                           "entity_id": a.get("entity_id"), "overdue": bool(rev["overdue"]), "items": items})
        alerts.sort(key=lambda x: (not x["overdue"], x["entity_id"] or ""))
        return alerts

    # ── writes ───────────────────────────────────────────────────────────────
    def _event(self, app: dict, action: str, *, actor: Optional[dict], from_step=None, to_step=None, comment="",
               detail=None, at: Optional[datetime] = None) -> dict:
        return {"application_id": app["application_id"], "at": (at or self.now()).isoformat(timespec="seconds"),
                "actor_id": (actor or {}).get("id"), "actor_role": (actor or {}).get("role"), "action": action,
                "from_step": from_step, "to_step": to_step, "status": app["status"], "comment": comment or None,
                "detail": detail or {}}

    def _default_assignee(self, role: str, wf: Optional[Workflow] = None) -> Optional[str]:
        """The holder of ``role`` with the fewest active applications (simple load balancing)."""
        users = (wf or self.wf).users_with_role(role)
        if not users:
            return None
        load = {u["id"]: 0 for u in users}
        for app in self.store.list():
            if app["status"] not in TERMINAL and app.get("assignee_id") in load:
                load[app["assignee_id"]] += 1
        return min(users, key=lambda u: (load[u["id"]], u["id"]))["id"]

    def create(self, session: dict, *, entity_id: str, facility: Optional[dict] = None,
               facilities: Optional[list[dict]] = None, related_parties: Optional[list[dict]] = None,
               priority: str = "Normal", prospect_discussion: Optional[dict] = None,
               sourcing_decision: Optional[dict] = None, customer_id_selection: Optional[str] = None,
               at: Optional[datetime] = None, seeded: bool = False, cam: Optional[dict] = None,
               profile: Optional[str] = None, product: Optional[str] = None,
               idempotency_key: Optional[str] = None) -> dict:
        def _create() -> dict:
            return self._create_impl(session, entity_id=entity_id, facility=facility, facilities=facilities,
                                     related_parties=related_parties, priority=priority,
                                     prospect_discussion=prospect_discussion,
                                     sourcing_decision=sourcing_decision,
                                     customer_id_selection=customer_id_selection, at=at, seeded=seeded,
                                     cam=cam, profile=profile, product=product)
        return self.idempotent(idempotency_key, "create", None, _create)

    def _create_impl(self, session: dict, *, entity_id: str, facility: Optional[dict] = None,
               facilities: Optional[list[dict]] = None, related_parties: Optional[list[dict]] = None,
               priority: str = "Normal", prospect_discussion: Optional[dict] = None,
               sourcing_decision: Optional[dict] = None, customer_id_selection: Optional[str] = None,
               at: Optional[datetime] = None, seeded: bool = False, cam: Optional[dict] = None,
               profile: Optional[str] = None, product: Optional[str] = None) -> dict:
        """A new draft at Prospect Sourcing. ``cam`` starts it from a CAM (see ``_attach_cam``):
        {"mode": "workspace", "run_id"?} · {"mode": "document", "staging_id"} · {"mode": "generate"};
        the preparation agent then starts at once. ``profile`` fixes the institution profile the
        application runs under; ``product`` the credit product (explicit, else inferred from the
        facility types when the profile runs a fixed product set). Both persist with the
        application and follow it through its life — switching the active profile never alters it."""
        prof = profiles.profile_for_new(profile)   # validates the id first; 404 unknown / 400 base, before any record exists
        if cam and cam.get("mode") not in CAM_MODES:
            raise InvalidRequestError(f"Unknown CAM option: {cam.get('mode')} (one of {', '.join(CAM_MODES)})")
        prof_wf = self.wf_for_profile(prof["profile"]["id"])   # the new application's journey
        first = prof_wf.first_step
        if not seeded and session["role"] != first.role:
            raise ForbiddenError(f"Only the {prof_wf.roles[first.role]} role can create applications")
        company = self.companies.get(entity_id)
        if not company:
            raise NotFoundError(f"Borrower {entity_id} not found")
        if cam and cam["mode"] == "document":                 # checked before anything is created
            staged = self._staging_dir(str(cam.get("staging_id") or ""))
            if not (staged / cam_intake.CAM_CATEGORY).exists():
                raise InvalidRequestError("Upload the CAM (category CAM) and read it before creating the application")
            self._check_cam_borrower(staged, company)
        borrower, fac = company.get("borrower"), company.get("facility")
        if facility and facilities:
            raise InvalidRequestError("Send either facility or facilities, not both")
        base_facility = _facility_from_company(fac)
        raw_facilities = facilities if facilities else [{**base_facility, **(facility or {})}]
        facilities = facmod.normalise_facilities(raw_facilities, base_facility if facilities else None)
        for f in facilities:
            if base_facility.get("case_type") and not f.get("case_type"):
                f["case_type"] = base_facility["case_type"]
        # the product: explicit, else inferred when the institution profile runs a fixed product set
        prod_obj = None
        if product:
            try:
                prod_obj = prodmod.get_product(product)
            except prodmod.ProductError as e:
                raise NotFoundError(str(e))
            if not prodmod.is_compatible(prod_obj, prof):
                raise InvalidRequestError(f"Product '{prod_obj['product']['name']}' is not available under the "
                                          f"institution profile '{prof['profile']['name']}'")
        elif prof.get("products"):
            ftypes = [f["facility_type"] for f in facilities]
            for pid in prodmod.profile_products(prof):
                cand = prodmod.get_product(pid)
                if prodmod.is_compatible(cand, prof) and \
                        any(ft in (cand["product"].get("facility_types") or []) for ft in ftypes):
                    prod_obj = cand
                    break
            if prod_obj is None:
                ok = sorted({t for pid in prodmod.profile_products(prof)
                             for t in prodmod.get_product(pid)["product"].get("facility_types") or []})
                raise InvalidRequestError("None of the proposed facility types belongs to a product this "
                                          "institution profile runs — select a supported facility type "
                                          f"({', '.join(ok)}) or a matching product")
        product_id = prod_obj["product"]["id"] if prod_obj else None
        if prod_obj is not None:
            prodmod.validate_creation(prod_obj, facilities)
        related_parties = _normalise_related_parties(related_parties or [])
        prospect = _normalise_prospect_discussion(prospect_discussion)
        # Customer identity & deduplication snapshot, stored with the application (GAP: prospect sourcing parity).
        identity = self.borrower_identity(entity_id)
        decision = _normalise_sourcing_decision(sourcing_decision, required=not seeded, customer=identity)
        if customer_id_selection and not decision["customer_id_selection"]:
            selection = str(customer_id_selection).strip()[:50]
            if selection and selection != "new":
                valid = identity.get("customer_id")
                if valid != selection:
                    hint = (f"Available core-banking result: {valid}." if valid
                            else "No customer record on the core-banking book (new-to-bank) — select 'New customer'.")
                    raise InvalidRequestError(
                        f"The selected Customer ID {selection} is not among the available core-banking "
                        f"results for this borrower. {hint}")
                decision["customer_id_selection"] = selection
        primary_facility = dict(facilities[0])
        total_amount = round(sum(row["amount_cr"] for row in facilities), 2)
        at = (at or self.now()).replace(microsecond=0)
        app = {
            "application_id": self.store.next_application_id(at.year),
            "entity_id": entity_id,
            "borrower_name": getattr(borrower, "company_name", entity_id),
            "sector": getattr(getattr(borrower, "sector", None), "value", None),
            "constitution": getattr(getattr(borrower, "borrower_type", None), "value", None),
            # ``facility`` is retained as the primary/legacy facility while all
            # new behavior uses the canonical ``facilities`` collection.
            "facility": primary_facility, "facilities": facilities,
            "related_parties": related_parties, "prospect_discussion": prospect,
            "customer_identity": identity, "sourcing_decision": decision,
            # Governed sub-objects (GAP-P0-01/04/07/08/09, P1-01/02/03/04/05, P0-12)
            "securities": [], "projects": [], "ewps": [],
            "esms": es.initial_esms(app=None),
            "ratings": rat.initial_ratings({"entity_id": entity_id, "borrower_name": getattr(borrower, "company_name", entity_id), "facilities": facilities}, self.companies),
            "cma": cma_mod.initial_cma(),
            "proposal": prop_mod.initial_proposal({"facility": dict(facilities[0])}, company),
            "pricing": pricing_mod.initial_pricing(),
            "terms": terms_mod.initial_terms(),
            "sourcing_details": prop_mod.initial_sourcing_details(session["user"], at.isoformat(timespec="seconds")),
            "documents": dreg.initial_registry(prodmod.documents(prof, product_id,
                                                                 [profiles.primary_product({"facilities": facilities})])),
            "disops": {"sop": do.initial_sop()},
            "snapshots": [], "material_change_reviews": [],
            "due_diligence": {"version": dd.CHECK_VERSION, "initiated_at": at.isoformat(timespec="seconds"),
                              "checks": dd.initial_checks(prodmod.checks(prof, product_id))},
            "amount_cr": total_amount,
            "profile": prof["profile"]["id"],
            "product": product_id,
            "is_demo": seeded,
            "stage_id": first.stage_id, "step_id": first.id, "status": STATUS_DRAFT,
            "assignee_id": session["user"]["id"], "priority": priority, "escalated": False,
            "created_by": session["user"]["id"], "created_at": at.isoformat(timespec="seconds"),
            "updated_at": at.isoformat(timespec="seconds"), "step_entered_at": at.isoformat(timespec="seconds"),
            "seeded_demo": seeded,
        }
        # R16: the exact configuration versions this application runs against (newer configuration
        # applies to new applications only; a running app migrates only via an authorised migration)
        app["config_snapshot"] = cfgver.snapshot_for_app(app, at.isoformat(timespec="seconds"))
        rt_routing.record(app, rt_routing.calculate(app, prof, prof_wf), at.isoformat(timespec="seconds"),
                          note="route calculated at creation")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "create", actor=actor, to_step=first.id, at=at,
                                         detail={"facilities": facilities, "related_parties": related_parties,
                                                 "total_amount_cr": total_amount,
                                                 "customer_identity": identity, "prospect_discussion": prospect,
                                                 "sourcing_decision": decision,
                                                 "route": rt_routing.public_route(app.get("routing"))}))
        if cam:
            reading = None
            if cam["mode"] == "document":
                d = self._staging_dir(str(cam.get("staging_id") or ""))
                reading = self._staged_cam(d)
                self._register_moved(app["application_id"], self._move_staged(d, entity_id), session)
            self._attach_cam(app["application_id"], session, cam, reading)
            self.prepare_application(app["application_id"], session)
            return self._require(app["application_id"])
        return app

    # ── the CAM as an input (S8): a CAM from the workspace, the bank's CAM document, or generate one ──
    def cam_options(self, entity_id: str) -> dict:
        """What a new application for this borrower can start from: the latest CAM generated in the
        CAM workspace (with the facility it assessed), or generating one."""
        company = self.companies.get(entity_id)
        if not company:
            raise NotFoundError(f"Borrower {entity_id} not found")
        case = self.cases.get(entity_id) if self.cases else None
        ws = None
        if case:
            fr = (case.get("reassessment") or {}).get("facility_recommendation") or {}
            fac = company.get("facility")
            ftype = getattr(getattr(fac, "facility_type", None), "value", None)
            ws = {"run_id": case.get("run_id"), "run_at": case.get("run_at"),
                  "decision_label": (case.get("reassessment") or {}).get("decision_label"),
                  "risk_grade": case.get("risk_grade"), "recommendation": case.get("recommendation"),
                  "requested_cr": fr.get("requested_cr"), "recommended_cr": fr.get("recommended_cr"),
                  "facility": {"facility_type": ftype, "amount_cr": getattr(fac, "amount_requested_cr", None),
                               "tenor_months": getattr(fac, "tenor_months", None),
                               "purpose": getattr(fac, "purpose", None)} if fac is not None else None}
        return {"entity_id": entity_id, "workspace": ws, "can_generate": bool(self.cases),
                "modes": list(CAM_MODES)}

    @staticmethod
    def _has_master_financials(company: dict) -> bool:
        """Statements on record other than those the engine extracted from an RM upload (a prospect has none)."""
        return any(not str(getattr(fs, "source", "")).startswith("rm_upload")
                   for fs in (company.get("financials") or {}).values())

    def _case_stale(self, case: dict, app: dict) -> Optional[str]:
        """Why the pinned CAM no longer fits this application, or None.

        The credit case is generated for the *borrower* (the company's facility record and
        its financials), so the fields the LOS adds while the journey plays out (the
        application's own facility, a re-priced request) do not stale it. A re-run is
        earned by a changed *request* (amount/facility type vs what the case assessed) or
        by financials accepted at Prospect Sourcing differing from the case's — a figure
        the case did not carry for that period (e.g. total debt, when the case was
        generated from an earlier statement) never stales it, but a recorded, differing
        value does."""
        other = self._cam_for_other_request(case, app)
        if other:
            return other
        stmt = self._accepted_statement(app)
        if not stmt:
            return None
        periods = (((case.get("fact_pack") or {}).get("financial_summary") or {}).get("periods") or {})
        used = periods.get(stmt["period"]) or {}
        if not used:                                       # the case never carried this period
            return None
        keys = {"revenue_operating": "revenue_cr", "ebitda": "ebitda_cr", "pat": "pat_cr",
                "total_equity": "net_worth_cr", "total_debt": "total_debt_cr"}
        differ = [k for k, v in stmt["items"].items()
                  if used.get(keys[k]) is not None
                  and abs(float(used.get(keys[k]) or 0) - float(v)) > 0.01 * max(abs(float(v)), 1.0)]
        return (f"the financials accepted at Prospect Sourcing ({', '.join(keys[k].replace('_cr', '').replace('_', ' ') for k in differ)}) "
                f"differ from those the CAM was generated with") if differ else None

    @staticmethod
    def _cam_for_other_request(case: dict, app: dict) -> Optional[str]:
        """Why an existing CAM does not assess this application's request (amount or facility), or None."""
        fr = (case.get("reassessment") or {}).get("facility_recommendation") or {}
        assessed = fr.get("requested_cr") or case.get("requested_amount_cr")
        wanted = app.get("amount_cr")
        fac = app.get("facility") or (app.get("facilities") or [{}])[0]
        reasons = []
        if assessed and wanted and abs(float(assessed) - float(wanted)) > 0.005 * max(float(wanted), 1.0):
            reasons.append(f"it assessed ₹{float(assessed):,.2f} Cr, this application requests ₹{float(wanted):,.2f} Cr")
        ctype, atype = case.get("facility_type"), fac.get("facility_type")
        if ctype and atype and str(ctype) != str(atype):
            reasons.append(f"it assessed a {str(ctype).replace('_', ' ')}, this application is a {str(atype).replace('_', ' ')}")
        return ("the CAM in the workspace is for another request: " + "; ".join(reasons)) if reasons else None

    @staticmethod
    def _check_cam_borrower(d: Path, company: dict) -> None:
        """A CAM uploaded for an existing borrower must be about that borrower: a PAN or CIN read from
        it that differs from the borrower's is another company's CAM."""
        saved = d / "intake.json"
        if not saved.exists():
            return
        read = {f["id"]: f.get("value") for f in json.loads(saved.read_text(encoding="utf-8")).get("fields") or []}
        b = company.get("borrower")
        for key, label in (("pan", "PAN"), ("cin", "CIN")):
            mine, theirs = getattr(b, key, None), read.get(key)
            if mine and theirs and str(mine).upper() != str(theirs).upper():
                raise ConflictError(f"The CAM is for another company ({label} {theirs}; "
                                    f"{getattr(b, 'company_name', 'this borrower')} has {mine}) — upload this borrower's CAM")

    @staticmethod
    def _staged_cam(d: Path) -> Optional[dict]:
        """The CAM reading saved when the staged documents were read (else read now, without the LLM)."""
        saved = d / "cam.json"
        if saved.exists():
            return json.loads(saved.read_text(encoding="utf-8"))
        return cam_intake.read_cams(d)

    def _register_moved(self, application_id: str, moved: list[str], session: dict) -> None:
        with self._app_lock(application_id):
            app = self._require(application_id)
            at = self.now().isoformat(timespec="seconds")
            registry = app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app)))
            for doc in moved:
                dreg.register_upload(registry, name=Path(doc).name, category=doc.split("/")[0], scope="application",
                                     file_name=doc, by_name=session["user"]["name"], at=at)
            self.store.save(app, self._event(app, "document_upload", actor={"id": session["user"]["id"],
                                                                             "role": session["role"]},
                                             from_step=app["step_id"], to_step=app["step_id"],
                                             comment=f"{len(moved)} document(s) filed: " + ", ".join(moved)[:300],
                                             detail={"documents": moved}))

    def _attach_cam(self, application_id: str, session: dict, cam: dict, reading: Optional[dict] = None) -> dict:
        """Start the application from a CAM.
        workspace  pin the CAM generated in the CAM workspace (no second run) and populate the IP
                   fields from it at once;
        document   the bank's CAM: its reading (narratives, terms, security, ratings, figures) goes into
                   the field store with section / page evidence; identity and facility come from the
                   intake agent, which reads the CAM with the borrower's other documents;
        generate   the preparation agent generates the CAM (a credit-case lane) and pins it."""
        mode = cam.get("mode")
        actor = {"id": session["user"]["id"], "role": session["role"], "agent": "cam"}
        app = self._require(application_id)
        at = self.now().isoformat(timespec="seconds")
        if mode == "workspace":
            case = self._credit_case(app["entity_id"], cam.get("run_id"))[0]
            if not case:
                raise ConflictError("There is no CAM for this borrower in the CAM workspace — generate one")
            other = self._cam_for_other_request(case, app)
            if other:
                # the CAM in the workspace assessed another proposal (e.g. the catalogue's ₹1,200 Cr) — pinning
                # it would put that amount in the assessment, pricing and decision; generate one for this request
                mode = "generate"
                detail = {"mode": mode, "replaced_run_id": case.get("run_id"), "reason": other}
            else:
                self._record_assessment(application_id, case, actor)
                detail = {"mode": mode, "run_id": case.get("run_id")}
        elif mode == "document":
            if not reading:
                raise InvalidRequestError("Upload the CAM (category CAM) and read it before creating the application")
            detail = {"mode": mode, "document": reading.get("document"), **(reading.get("summary") or {})}
        else:
            detail = {"mode": mode}
        with self._app_lock(application_id):
            app = self._require(application_id)
            app["cam_source"] = {**detail, "at": at, "by": session["user"]["name"]}
            if mode == "document":
                reading = {**reading, "read_at": at}
                app["cam"] = reading
                fields = app.setdefault("fields", {})
                props = cam_intake.resolver(reading, {"company": self.companies.get(app["entity_id"]) or {}})
                merged = fieldmodel.merge(fields, props, self.field_registry, at)
                reconcile.materialise(app, fields, [p["field_id"] for p in props])
                app["field_reviews"] = fieldmodel.legacy_reviews(fields)
                detail["fields"] = merged
            comment = {"workspace": f"Started from the CAM in the CAM workspace (run {detail.get('run_id')})",
                       "document": f"Started from the bank's CAM {detail.get('document')}: "
                                   f"{detail.get('sections', 0)} sections and {detail.get('labels', 0)} values read",
                       "generate": "The CAM will be generated by the preparation agent"
                                   + (f" — {detail['reason']}" if detail.get("reason") else "")}[mode]
            self.store.save(app, self._event(app, "cam_attached", actor=actor, from_step=app["step_id"],
                                             to_step=app["step_id"], comment=comment, detail=detail))
        if mode == "workspace":
            self.populate_fields(application_id, actor, force=True)
        return detail

    def act(self, application_id: str, session: dict, action: str, *, comment: str = "",
            allocate_to: Optional[str] = None, at: Optional[datetime] = None,
            sanctioned_amount_cr: Optional[float] = None,
            significant_changes: Optional[str] = None,
            rework_to: Optional[str] = None, decision_data: Optional[dict] = None,
            deferred_until: Optional[str] = None,
            idempotency_key: Optional[str] = None) -> dict:
        if idempotency_key:
            return self.idempotent(
                idempotency_key, "act", application_id,
                lambda: self._act_impl(application_id, session, action, comment=comment,
                                       allocate_to=allocate_to, at=at,
                                       sanctioned_amount_cr=sanctioned_amount_cr,
                                       significant_changes=significant_changes,
                                       rework_to=rework_to, decision_data=decision_data,
                                       deferred_until=deferred_until))
        return self._act_impl(application_id, session, action, comment=comment, allocate_to=allocate_to,
                              at=at, sanctioned_amount_cr=sanctioned_amount_cr,
                              significant_changes=significant_changes, rework_to=rework_to,
                              decision_data=decision_data, deferred_until=deferred_until)

    def _act_impl(self, application_id: str, session: dict, action: str, *, comment: str = "",
                  allocate_to: Optional[str] = None, at: Optional[datetime] = None,
                  sanctioned_amount_cr: Optional[float] = None,
                  significant_changes: Optional[str] = None,
                  rework_to: Optional[str] = None, decision_data: Optional[dict] = None,
                  deferred_until: Optional[str] = None) -> dict:
        app = self._require(application_id)
        if not app.get("step_id"):
            raise ConflictError("This application is complete")
        step = self._wf(app).step(app["step_id"])
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step ({step.name}) belongs to the {self._wf(app).roles[step.role]} role")
        if app.get("assignee_id") and app["assignee_id"] != session["user"]["id"]:
            raise ForbiddenError(f"Assigned to {self._user_name(app['assignee_id'])}; reassign it first")
        try:
            out = transition(self._wf(app), step, action, comment=comment, allocate_to=allocate_to,
                             current_status=app["status"], rework_to=rework_to)
        except WorkflowError as e:
            raise InvalidRequestError(str(e))
        if action == "defer":
            try:
                until = datetime.fromisoformat(str(deferred_until or "")).date()
            except ValueError:
                raise InvalidRequestError("Deferring needs the date to take the application up again (YYYY-MM-DD)")
            if until <= self.now().date():
                raise InvalidRequestError("The deferred-until date must be in the future")
            if not (comment or "").strip():
                raise InvalidRequestError("Deferring the application needs a reason (what is being awaited)")
            # the institution's maximum deferral period (profile: deferral.max_days)
            max_days = int(((self._profile(app).get("deferral") or {}).get("max_days") or 0))
            if max_days and (until - self.now().date()).days > max_days:
                raise InvalidRequestError(
                    f"The deferral exceeds the institution's maximum period of {max_days} days "
                    f"(until {str(deferred_until)[:10]}) — take the case up earlier or reject it")
        if step.id == "pos_checker" and not (comment or "").strip():
            raise InvalidRequestError("Post-Sanction Checker remarks are mandatory for every decision at this step")
        stuck = self._gates(app, step, action)
        if stuck:
            raise InvalidRequestError(stuck[0][0])
        # The decision record the step asks for (G-04 / G-W6): e.g. the material-information date.
        decision = self._decision_fields(app, step, action, decision_data, significant_changes)
        at = (at or self.now()).replace(microsecond=0)
        # Disbursement VP Review: the read-only gate records its endorsement / rework decision,
        # including any significant changes observed (GAP-P0-16).
        if step.id == "dis_vp_review":
            app.setdefault("disbursement", {}).setdefault("vp_reviews", []).append(
                {"action": action, "by": session["user"]["id"], "by_name": session["user"]["name"],
                 "at": at.isoformat(timespec="seconds"), "remarks": comment or None,
                 "significant_changes": (significant_changes or "").strip() or None})
        sanction = self._sanction_record(app, step, session, action, comment, sanctioned_amount_cr, at)
        app["status"] = out.status
        # Alternate workflow decisions (Client One): record the governed decision itself.
        if action in ("propose_modification", "recommend_modification"):
            mods = app.setdefault("modifications", [])
            mods.append({"modification_id": f"MOD-{len(mods) + 1:03d}",
                         "type": "proposed" if action == "propose_modification" else "recommended",
                         "by": session["user"]["id"], "by_name": session["user"]["name"],
                         "at": at.isoformat(timespec="seconds"), "at_step": step.id,
                         "reason": (comment or "").strip(), "status": "open"})
            app.setdefault("deviations", []).append({
                "type": "modification_request", "at": at.isoformat(timespec="seconds"),
                "by_name": session["user"]["name"], "detail": f"{step.name}: {mods[-1]['reason'][:300]}",
                "authority": self._wf(app).roles.get(step.role, step.role)})
        elif action == "defer":
            app.setdefault("deferrals", []).append({
                "at": at.isoformat(timespec="seconds"), "by": session["user"]["id"], "by_name": session["user"]["name"],
                "at_step": step.id, "reason": (comment or "").strip(), "until": str(deferred_until)[:10],
                "reactivated_at": None, "reactivated_by": None})
        elif action == "reactivate":
            last = (app.get("deferrals") or [{}])[-1]
            if not (comment or "").strip():
                raise InvalidRequestError("Reactivating needs a reason (what has changed since the deferral)")
            overdue_days = max(0, (self.now().date() - datetime.fromisoformat(str(last.get("until") or at.date().isoformat())).date()).days)                 if last.get("until") else 0
            last.update(reactivated_at=at.isoformat(timespec="seconds"), reactivated_by=session["user"]["name"],
                        reactivation_remarks=(comment or "").strip(),
                        reactivated_overdue_days=overdue_days or None)
            app["step_entered_at"] = at.isoformat(timespec="seconds")      # the SLA restarts on reactivation
        elif action in ("withdraw", "drop"):
            app["terminated"] = {"type": "withdrawn" if action == "withdraw" else "dropped",
                                 "at": at.isoformat(timespec="seconds"), "by_name": session["user"]["name"],
                                 "at_step": step.id, "reason": (comment or "").strip()}
            app.setdefault("deviations", []).append({
                "type": "withdrawal" if action == "withdraw" else "drop",
                "at": at.isoformat(timespec="seconds"), "by_name": session["user"]["name"],
                "detail": (comment or "")[:300], "authority": self._wf(app).roles.get(step.role, step.role)})
        # A committee that sent the case back for re-consideration: the Risk Maker holds the case
        # until it re-recommends (re_recommend), so the return is recorded, not an auto-advance.
        if action == "return" and step.kind == "committee" and rework_to is None:
            app["committee_returned"] = {"at": at.isoformat(timespec="seconds"),
                                         "by": session["user"]["id"], "by_name": session["user"]["name"],
                                         "by_role": self._wf(app).roles.get(step.role, step.role),
                                         "reason": (comment or "").strip()[:300]}
            self.store.save(app, self._event(app, "committee_return",
                                             actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=step.id, to_step=step.id, comment=(comment or "")[:300]))
            return self.get(application_id, session)
        if out.step_id and out.step_id != step.id:
            target_step = self._route_skip(app, out.step_id)
            if target_step != out.step_id:
                out = dataclasses.replace(out, step_id=target_step,
                                          message=out.message + f" · route: skipped {out.step_id}")
            nxt = self._wf(app).step(target_step)
            assignee = (out.assign_user
                        or (self._last_worker(application_id, nxt.id) if action == "return" else None)
                        # the next step in the same role stays with the person who did this one (the RM who sourced
                        # the prospect writes its IP Note), unless they no longer hold the role
                        or (session["user"]["id"] if nxt.role == step.role and nxt.role in session["user"]["roles"] else None)
                        or self._last_worker(application_id, nxt.id)
                        # a later step in a role already worked on this application (the RM's AP Note after
                        # their IP Note) goes back to the same person
                        or self._last_in_role(application_id, nxt.role)
                        or self._default_assignee(nxt.role, self._wf(app)))
            app.update(step_id=nxt.id, stage_id=nxt.stage_id, step_entered_at=at.isoformat(timespec="seconds"),
                       assignee_id=assignee)
            app.pop("demo_note", None)          # the seed note describes the step it was seeded at
        elif out.step_id is None:
            app.update(step_id=None, assignee_id=None)
        elif action == "reject":                # rejected: stays on the step, no assignee
            app["assignee_id"] = None
        # defer / reactivate stay on the step with the same assignee (the case is on hold, not handed over)
        if action in ("approve", "sanction", "submit") and app.get("escalated"):
            app["escalated"] = False
        if sanction:
            app.setdefault("sanctions", {})[step.stage_id] = sanction
        self._after_action(app, step, action, session, at, comment)
        if sanction and step.id in SANCTION_STEPS:
            # Refresh the approval package so it also binds the conditions just built (GAP-P0-11).
            snap.record_snapshot(app, "IP" if step.id == "ip_sanction" else "sanction",
                                 at.isoformat(timespec="seconds"), session["user"]["name"])
        app["updated_at"] = at.isoformat(timespec="seconds")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        route = app.get("routing") or {}
        # R3: the append-only decision record — every governed decision is recorded with what
        # it was decided under (authority + route version) and what it stands on
        dec = self._decision_record(app, step, session, action, at, comment, decision, route)
        if dec:
            app.setdefault("decisions", []).append(dec)
        self.store.save(app, self._event(app, action, actor=actor, from_step=step.id, to_step=app.get("step_id"),
                                         comment=comment, at=at,
                                         detail={"message": out.message, "allocated_to": allocate_to,
                                                 **({"sanction": sanction} if sanction else {}),
                                                 **({"deferred_until": str(deferred_until)[:10]} if action == "defer" else {}),
                                                 **decision}))
        return self.get(application_id, session)

    _FORWARD = ("submit", "approve", "sanction")

    def _decision_fields(self, app: dict, step, action: str, data: Optional[dict], significant_changes: Optional[str]) -> dict:
        """The step's decision fields for this decision (G-04), validated; required ones only on a
        forward decision (a return or drop is explained by its remarks)."""
        data = dict(data or {})
        if significant_changes and "significant_changes" not in data:
            data["significant_changes"] = significant_changes              # the earlier API parameter
        out = {}
        for f in step.decision_fields:
            raw = str(data.get(f["id"]) or "").strip()
            label = self._wf(app).decision_field_labels.get(f["id"], f["id"].replace("_", " ").capitalize())
            if not raw:
                if f.get("required") and action in self._FORWARD:
                    word = wfmod.action_label(step, action) or action
                    raise InvalidRequestError(f"{label} is required to {word.lower()} at {step.name}")
                continue
            if wfmod.DECISION_FIELD_TYPES[f["id"]] == "date":
                try:
                    raw = datetime.fromisoformat(raw).date().isoformat()
                except ValueError:
                    raise InvalidRequestError(f"{label} must be a date (YYYY-MM-DD)")
            out[f["id"]] = raw[:2000]
        return out

    def _sanction_record(self, app: dict, step, session: dict, action: str, comment: str,
                         amount: Optional[float], at: datetime) -> Optional[dict]:
        """The sanction committee's sanction: amount (default: the reassessed recommendation) and minutes.
        Sanctioning a different amount than recommended needs minutes explaining why.
        Other committees (e.g. the Recommendations Committee) record a recommendation, not a sanction."""
        if action != "sanction" or step.id not in SANCTION_STEPS:
            return None
        ca = app.get("credit_assessment") or {}
        recommended = ca.get("recommended_cr")
        default = recommended if recommended not in (None, 0) else app.get("amount_cr")
        amount = default if amount in (None, "") else float(amount)
        if amount is None or amount <= 0:
            raise InvalidRequestError("Sanctioned amount must be greater than zero")
        if amount > (app.get("amount_cr") or amount):
            raise InvalidRequestError("Sanctioned amount cannot exceed the requested amount")
        differs = recommended not in (None, 0) and abs(amount - recommended) > 1e-6
        if (differs or ca.get("decision") == "NOT_SUPPORTED") and not (comment or "").strip():
            raise InvalidRequestError("Minutes are required when the sanction differs from the reassessed recommendation")
        # Facility-wise sanction allocation + approval authority (GAP-P0-04 / P0-11).
        facmod.apply_sanction(app.get("facilities") or [], amount, at.isoformat(timespec="seconds"), session["user"]["name"])
        auth = authority.required_authority(amount, ca.get("risk_grade"),
                                            deviations=len(committee_deviations((self._app_case(app) or (None,))[0]) or [])
                                            + len(manual_deviations(app)),
                                            final=step.id == "ap_sanction",
                                            app=app, product=profiles.primary_product(app))
        # The decision binds the exact versions reviewed — the approval snapshot (GAP-P0-11).
        snap.record_snapshot(app, "IP" if step.id == "ip_sanction" else "sanction", at.isoformat(timespec="seconds"),
                             session["user"]["name"])
        return {"stage": step.stage_id, "step": step.id, "sanctioned_cr": round(amount, 2),
                "authority": auth,
                "facility": dict(app.get("facility") or {}),
                "facilities": [dict(row) for row in app.get("facilities") or [app.get("facility") or {}]],
                "recommended_cr": recommended, "requested_cr": app.get("amount_cr"),
                "reassessed_decision": ca.get("decision_label"), "deviates_from_recommendation": bool(
                    differs or ca.get("decision") == "NOT_SUPPORTED"),
                "minutes": comment or None, "by": session["user"]["id"], "by_name": session["user"]["name"],
                "at": at.isoformat(timespec="seconds"),
                **({"governance": gov} if (gov := self._cg_summary(app, step.id)) else {})}

    def _gates(self, app: dict, step, action: str) -> list[tuple[str, str]]:
        """What stops ``action`` at ``step`` now, in the order the bank's gates apply: (message, where to fix
        it — a page section). ``act`` refuses with the first; the application view lists them all, so the
        step holder sees every blocker before pressing the button."""
        out: list[tuple[str, str]] = []
        add = lambda msg, where: msg and out.append((msg, where))
        checks = (app.get("due_diligence") or {}).get("checks") or []
        # R5: the profile's applicability conditions and validity clock — the effective
        # check set for every gate (a waived check never blocks; a stale result re-blocks)
        _prof = self._profile(app)
        _app5 = (_prof.get("checks") or {}).get("applicability") or {}
        _val5 = {k: int(v) for k, v in ((_prof.get("checks") or {}).get("validity_days") or {}).items()}
        eff = [c for c in checks if dd.check_applies(_app5.get(c["id"]) or {}, app)[0]]
        if action == "submit" and step.id == IP_NOTE_STEP and app.get("ip_note"):
            # G-10: the IP proposal goes for review only with blocking checks resolved and its documents in place
            stuck = dd.blocking(eff, now=self.now(), validity_days=_val5)
            if stuck:
                add("Resolve the blocking due-diligence check(s) before submitting the IP Note: "
                    + "; ".join(f"{c['name']} ({c['status']})" for c in stuck[:4]), "checks")
            add(dreg.stage_gate(app), "documents")
        # Mandatory gates (due diligence, consent)
        waiting = {r["check_id"]: r for r in self._pending_exception_requests(app)}
        if action == "submit" and step.id in DD_GATE_STEPS and app.get("due_diligence") and waiting:
            who = {r.get("to_name") for r in waiting.values()} - {None}
            exc_name = self._exc_authority(app)["name"]
            add(f"Waiting for {', '.join(sorted(who)) if who else 'a ' + exc_name} ({exc_name}) to decide the exception on: "
                + "; ".join(f"{r['name']} (requested {r['at'][:10]})" for r in waiting.values()), "checks")
        if action == "submit" and step.id in DD_GATE_STEPS and app.get("due_diligence"):
            stuck = [c for c in dd.blocking(eff, now=self.now(), validity_days=_val5) if c["id"] not in waiting]
            if stuck:
                names = "; ".join(f"{c['name']} ({c['status']})" for c in stuck[:4])
                add("Resolve the outstanding mandatory due-diligence check(s) before "
                    f"submitting: {names}" + (f" (+{len(stuck) - 4} more)" if len(stuck) > 4 else ""), "checks")
        # the stage's mandatory documents, present and reviewed, at the step that answers for them
        cma_on = prodmod.module_enabled(self._profile(app), app.get("product"), "cma")
        if action == "submit" and step.id == "ps_maker":
            gate = dreg.stage_gate(app)
            if gate:                       # documents on file the agent has not linked yet: say how
                import copy
                trial = copy.deepcopy(app)
                if self._link_documents(trial, self.now().isoformat(timespec="seconds")):
                    gate = gate.replace("for this stage:", "for this stage (the borrower's documents on file can be "
                                        "linked — click “Prepare with agents”, then review each in Documents):", 1)
            add(gate, "documents")
        if action == "submit" and step.id == "ap_note":
            add(dreg.stage_gate(app, skip={dreg.CMA_DOC} if cma_on else set()), "documents")       # the CMA is the Risk Maker's
        if action == "submit" and step.id == "ap_risk_maker" and cma_on:
            dreg.link_workspace(app, self.now().isoformat(timespec="seconds"))     # the CMA, once recorded
            add(dreg.stage_gate(app, only={dreg.CMA_DOC}), "documents")
        if action == "submit" and step.id == "ip_note" and not app.get("ip_note"):
            add("Generate the IP Note before submitting it for review", "task")
        if action == "submit" and step.id == "pos_maker":
            # in order: the sanction letter is issued, the customer accepts it, the facilities are executed
            letter = next((d for d in app.get("documents") or [] if d["name"].startswith("Sanction letter")), None)
            if not letter or not letter.get("versions"):
                add("Generate and issue the Sanction Letter before post-sanction progression", "letters")
            consent = app.get("consent")
            if not consent:
                add("Record the customer's sanction consent and facility execution before submitting", "task")
            else:
                stuck = [f["facility_id"] for f in consent.get("facilities", [])
                         if f.get("execution_status") not in ("executed", "partial")]
                if stuck:
                    add("Every facility must be executed or partially executed before submitting: " + ", ".join(stuck), "task")
        if action == "submit" and step.id == "ap_note" and (app.get("terms") or {}).get("conditions"):
            # G-F2: the T&C go to sanction authored — every agent draft confirmed, edited or removed.
            add(terms_mod.submit_gate(app.get("terms"), app.get("fields")), "terms")
        if action == "submit" and step.id in RISK_MAKER_STEPS and self.cases and not app.get("credit_assessment"):
            add("Run the credit assessment before submitting the Risk Maker step", "assessment")
        if action == "submit" and step.id in RISK_MAKER_STEPS and (app.get("credit_assessment") or {}).get("run_id"):
            stale = self._case_stale(self._app_case(app)[0] or {}, app)
            if stale:
                add("Re-run the credit assessment: " + stale.replace("the CAM in the workspace", "the assessment"),
                    "assessment")
        if action == "submit" and step.id in ("ap_risk_maker",):
            # the CMA in the governed workspace; benchmark and spread for fund-based facilities (RUL-07);
            # an ESMS screen in progress (or any project) complete (RUL-06) — per the profile's modules
            if cma_on and not any(s.get("rows") for s in (app.get("cma") or {}).get("subjects") or []):
                add("Record the CMA (financial analysis) in the CMA workspace before submitting", "cma")
            add(pricing_mod.pricing_gate(app.get("pricing") or {}, app.get("facilities") or []), "pricing")
            esms = app.get("esms") or {}
            if prodmod.module_enabled(self._profile(app), app.get("product"), "esms") and \
                    (any(i.get("answer") for i in esms.get("checklist", [])) or bool(app.get("projects"))):
                add(es.esms_gate(esms, self._esms_exception(app, esms), self.now()), "projects")
        if action == "submit" and step.id == ES_MAKER_STEP:
            # G-W2: the CRP ES Maker records the E&S risk categorisation the ES preparation works from
            if (app.get("esms") or {}).get("category") not in es.ES_CATEGORIES:
                add("Record the E&S risk category (A, B or C) in Projects & ESMS — the agent's proposed "
                    "category is there to confirm", "projects")
        if action == "submit" and step.id == ES_PREP_STEP:
            add(es.esms_gate(app.get("esms") or {}, self._esms_exception(app, app.get("esms") or {}), self.now()), "projects")
            if not any(v.get("kind") in ("esms_approval_note", "esms_note")
                       for d in app.get("documents") or [] for v in d.get("versions") or []):
                add("Generate the ESMS Approval Note (Documents → generated outputs) before submitting for ES review",
                    "documents")
        if action == "submit" and step.id == "dis_maker":
            add(do.maker_gate(app), "disops")
            add(dreg.stage_gate(app), "documents")
        if action == "approve" and step.id in ("dis_checker", "dis_approver"):
            add(self.dis_review_gate(app), "disops")
        if action == "submit" and step.id in ("pos_maker", "dis_maker") and app.get("snapshots"):
            add(snap.material_change_gate(app), "approvals")
        if action == "submit" and step.id == "pos_maker" and app.get("conditions") and \
                not condition_summary(app["conditions"], self.now().date().isoformat())["cps_cleared"]:
            today = self.now().date().isoformat()
            open_ids = [c["id"] for c in app["conditions"] if c["type"] in ("PC", "CP", "CPS")
                        and condition_state(c, today) in ("open", "non_compliant", "overdue")]
            add("Every condition precedent must be satisfied, deferred or waived before submitting"
                + (" — still open: " + ", ".join(open_ids[:8]) if open_ids else ""), "task")
        if action == "submit" and step.id == "dis_maker":
            dis = self._disbursement(app)
            if not dis["pending_tranche"]:
                add("Record the disbursement tranche before submitting", "task")
            else:
                missing = [i["label"] for i in dis["checklist"] if not i["done"]]
                if missing:
                    add("Disbursement checklist incomplete: " + "; ".join(missing[:3])
                        + (f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""), "task")
        # R1: the calculated authority gates the committee decisions (concurrences + reapproval)
        # — enforced by the institution profile (routing.enforce_concurrences); profiles that
        # leave it off (e.g. the legacy demo) keep their original sanction flow
        if action in ("sanction",) and step.id in SANCTION_STEPS                 and bool(((profiles.get_profile(app=app).get("routing")) or {}).get("enforce_concurrences")):
            add(rt_routing.gate_message(app, step.id, action), "decision")
        # R9: committee governance — attendance, quorum, minutes and the vote (profile-enabled)
        for msg in self._cg_blockers(app, step, action):
            add(msg, "decision")
        return out


    # ── R19 notifications ──────────────────────────────────────────────────
    def notifications_for(self, application_id: str) -> list[dict]:
        """The current notifications for the case (derived + recorded), with acks."""
        from src.los import notifications as ntf
        with self._app_lock(application_id):
            app = self._require(application_id)
            ntf.merge(self, app)
            self.store.save(app)
            return list(app.get("notifications") or [])

    def acknowledge_notification(self, application_id: str, session: dict, notification_id: str,
                                 note: str = "") -> dict:
        """Acknowledge a notification (the user has seen it; the case state is unchanged)."""
        with self._app_lock(application_id):
            app = self._require(application_id)
            nts = app.get("notifications") or []
            n = next((x for x in nts if x.get("id") == notification_id), None)
            if not n:
                from src.application.errors import NotFoundError
                raise NotFoundError(f"Notification {notification_id} not found on this case")
            n.update(acknowledged_by=session["user"]["name"], acknowledged_at=self.now().isoformat(timespec="seconds"),
                     acknowledgement_note=(note or "").strip() or None)
            self.store.save(app, self._event(app, "notification_acknowledged",
                                             actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=app.get("step_id"), to_step=app.get("step_id"),
                                             detail={"notification": n.get("id"), "kind": n.get("kind")}))
            return {"application_id": application_id,
                    "notifications": list(app.get("notifications") or [])}

    # ── R9 committee governance ────────────────────────────────────────────
    def re_recommend(self, application_id: str, session: dict) -> dict:
        """R9: the Risk Maker re-submits a revised recommendation to a committee that sent the case
        back for re-consideration — the route is recalculated on the current facts and the revised
        recommendation is recorded as a fresh audit entry (the committee then decides on it)."""
        app = self._require(application_id)
        wf = self._wf(app)
        step = wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in RISK_MAKER_STEPS or app["status"] in TERMINAL:
            raise ConflictError("A revised recommendation is submitted at the Risk Maker step")
        if not can_act(wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"Only the {wf.roles[step.role]} role can re-recommend")
        if not app.get("committee_returned"):
            raise ConflictError("The committee has not sent this case back for re-consideration")
        if self._jobs.get(application_id, {}).get("state") not in (None, "done", "failed"):
            raise ConflictError("Wait for the running assessment to finish before re-recommending")
        with self._app_lock(application_id):
            app = self._require(application_id)
            self._recompute_routing(app, {"id": session["user"]["id"], "role": session["role"],
                                          "agent": "risk_maker"},
                                    "route recalculated for the revised recommendation")
            app["committee_returned"] = None
            ca = app.get("credit_assessment") or {}
            self.store.save(app, self._event(app, "re_recommendation",
                                             actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=app.get("step_id"), to_step=app.get("step_id"),
                                             detail={"recommended_cr": ca.get("recommended_cr"),
                                                     "risk_grade": ca.get("risk_grade")},
                                             comment="Revised recommendation re-submitted to the committee"))
        return self.get(application_id, session)

    # ── R9 committee governance: attendance, quorum, votes, dissent, minutes ─────────────
    @staticmethod
    def _cg_policy(app: Optional[dict]) -> dict:
        """The institution's committee-governance policy (profile ``committee_governance``)."""
        return dict(profiles.get_profile(app=app).get("committee_governance") or {})

    def _cg_step(self, app: dict, step_id: str):
        """The committee step the meeting is about (must exist and be a committee step)."""
        wf = self._wf(app)
        try:
            step = wf.step(step_id)
        except Exception:
            raise NotFoundError(f"Unknown step {step_id}")
        if step.kind != "committee":
            raise InvalidRequestError(f"{step.name} is not a committee step")
        return step

    def _cg_may(self, app: dict, step, session: dict) -> None:
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(
                f"Committee records are kept by the {self._wf(app).roles[step.role]} (the {step.name} step)")

    def _cg_record(self, app: dict, step_id: str) -> dict:
        recs = app.setdefault("committee_meetings", {})
        return recs.setdefault(step_id, {"version": 0, "members": [], "votes": [], "minutes": None,
                                         "versions": []})

    @staticmethod
    def _cg_present_quorum(policy: dict, members: list) -> tuple:
        """(present, required, met, excluded_conflicts) — a conflict of interest excuses the member."""
        present = [m for m in members if m.get("status") == "present"]
        excluded = len([m for m in present if m.get("conflict_of_interest")
                        and policy.get("conflicts_exclude_from_quorum", True)])
        counted = len(present) - excluded
        required = int(policy.get("quorum") or 0)
        return counted, required, (counted >= required) if required else bool(counted), excluded

    def committee_meeting(self, application_id: str, session: dict, step_id: str) -> dict:
        """R9: the committee's meeting record for this step — roster, attendance (with conflicts
        of interest), the vote (approve / abstain / dissent), the structured minutes, the quorum
        position and the version history."""
        app = self._require(application_id)
        step = self._cg_step(app, step_id)
        self._cg_may(app, step, session)
        policy = self._cg_policy(app)
        rec = self._cg_record(app, step_id)
        roster = policy.get("members") or []
        members = {}
        for r in roster:
            key = str(r.get("user_id") or r.get("name"))
            members[key] = {"user_id": r.get("user_id"), "name": r.get("name"), "status": "absent",
                            "conflict_of_interest": False}
        for m in rec.get("members") or []:
            key = str(m.get("user_id") or m.get("name"))
            merged = dict(members.get(key) or {"name": m.get("name")})
            merged.update({k: v for k, v in m.items() if v is not None})
            members[key] = merged
        votes = rec.get("votes") or []
        tally = {"approve": sum(1 for v in votes if v.get("vote") == "approve"),
                 "abstain": sum(1 for v in votes if v.get("vote") == "abstain"),
                 "dissent": sum(1 for v in votes if v.get("vote") == "dissent")}
        present, required, met, excluded = self._cg_present_quorum(policy, list(members.values()))
        voting = tally["approve"] + tally["dissent"]
        need = policy.get("majority") or "simple"
        if voting:
            vote_met = (tally["approve"] * 3 >= voting * 2) if need == "two_thirds" else (tally["approve"] > tally["dissent"])
        else:
            vote_met = None          # no vote recorded yet
        return {"step_id": step_id, "step_name": step.name, "enabled": bool(policy.get("enabled")),
                "roster": list(members.values()), "roster_size": len(roster),
                "quorum": {"required": required, "present": present, "met": met,
                           "excluded_conflicts": excluded},
                "votes": votes, "vote_tally": tally, "vote_approves": vote_met, "majority": need,
                "minutes": rec.get("minutes"), "version": rec.get("version"),
                "versions": rec.get("versions") or []}

    def _cg_bump(self, app: dict, rec: dict, session: dict, what: str, detail: dict) -> None:
        rec["version"] = int(rec.get("version") or 0) + 1
        rec.setdefault("versions", []).append(
            {"version": rec["version"], "change": what, "by": session["user"]["id"],
             "by_name": session["user"]["name"], "at": self.now().isoformat(timespec="seconds"),
             "detail": detail})

    def record_committee_attendance(self, application_id: str, session: dict, step_id: str,
                                    members: list) -> dict:
        """R9: mark the roster's attendance (present / absent / excused) with conflict-of-interest
        declarations. A conflict excuses the member from the vote and (by policy) the quorum."""
        app = self._require(application_id)
        step = self._cg_step(app, step_id)
        self._cg_may(app, step, session)
        if not isinstance(members, list) or not members:
            raise InvalidRequestError("Attendance is a list of member records")
        with self._app_lock(application_id):
            app = self._require(application_id)
            rec = self._cg_record(app, step_id)
            roster = {str(r.get("user_id") or r.get("name"))
                      for r in (self._cg_policy(app).get("members") or [])}
            at = self.now().isoformat(timespec="seconds")
            out = []
            for m in members:
                name = str(m.get("name") or m.get("user_id") or "").strip()
                if not name:
                    raise InvalidRequestError("Each attendance record needs a name (or user_id)")
                key = str(m.get("user_id") or name)
                status = m.get("status") or "present"
                if status not in ("present", "absent", "excused"):
                    raise InvalidRequestError("Attendance status is present, absent or excused")
                coi = bool(m.get("conflict_of_interest"))
                if coi and not str(m.get("conflict_note") or "").strip():
                    raise InvalidRequestError("A conflict of interest needs a note (what the connection is)")
                row = {"user_id": m.get("user_id"), "name": name, "status": status,
                       "conflict_of_interest": coi,
                       "conflict_note": (str(m.get("conflict_note") or "").strip() or None) if coi else None,
                       "declared_at": at, "by": session["user"]["id"]}
                if roster and key not in roster and not m.get("user_id"):
                    row["ad_hoc"] = True      # a member outside the standing roster (e.g. a delegate)
                rec["members"] = [r for r in rec.get("members") or []
                                  if str(r.get("user_id") or r.get("name")) != key]
                rec["members"].append(row)
                out.append(row)
            self._cg_bump(app, rec, session, "attendance",
                          {"present": sum(1 for r in out if r["status"] == "present")})
            self.store.save(app, self._event(app, "committee_attendance",
                                             actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=step.id, to_step=step.id,
                                             detail={"step_id": step_id, "members": out},
                                             comment="Committee attendance recorded"))
        return self.committee_meeting(application_id, session, step_id)

    def record_committee_votes(self, application_id: str, session: dict, step_id: str,
                               votes: list) -> dict:
        """R9: the vote — approve / abstain / dissent, per member. Only present members who are
        not in a conflict of interest may vote; a dissent needs remarks (by policy). A member may
        change a vote (one vote per member, kept with its history in the version log)."""
        app = self._require(application_id)
        step = self._cg_step(app, step_id)
        self._cg_may(app, step, session)
        policy = self._cg_policy(app)
        if not isinstance(votes, list) or not votes:
            raise InvalidRequestError("The vote is a list of member votes")
        with self._app_lock(application_id):
            app = self._require(application_id)
            rec = self._cg_record(app, step_id)
            present = {str(m.get("user_id") or m.get("name")): m for m in rec.get("members") or []
                       if m.get("status") == "present"}
            if not present:
                raise ConflictError("Record the committee's attendance before taking the vote")
            out = []
            for v in votes:
                name = str(v.get("name") or v.get("user_id") or "").strip()
                key = str(v.get("user_id") or name)
                if key not in present:
                    raise InvalidRequestError(f"{name or key} is not present — only present members vote")
                if present[key].get("conflict_of_interest"):
                    raise ForbiddenError(f"{name} has declared a conflict of interest and is excused from the vote")
                vote = v.get("vote")
                if vote not in ("approve", "abstain", "dissent"):
                    raise InvalidRequestError("A vote is approve, abstain or dissent")
                remarks = str(v.get("remarks") or "").strip()
                if vote == "dissent" and policy.get("dissent_requires_remarks", True) and not remarks:
                    raise InvalidRequestError(f"Dissent needs remarks ({name}: the position and why)")
                if vote == "abstain" and not remarks:
                    raise InvalidRequestError(f"Abstention needs a note ({name}: what is being held back)")
                rec["votes"] = [x for x in rec.get("votes") or []
                                if str(x.get("user_id") or x.get("name")) != key]
                row = {"user_id": v.get("user_id"), "name": name, "vote": vote,
                       "remarks": remarks or None, "at": self.now().isoformat(timespec="seconds"),
                       "by": session["user"]["id"]}
                rec["votes"].append(row)
                out.append(row)
            tally = {k: sum(1 for r in out if r["vote"] == k) for k in ("approve", "abstain", "dissent")}
            self._cg_bump(app, rec, session, "vote", tally)
            self.store.save(app, self._event(app, "committee_vote",
                                             actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=step.id, to_step=step.id,
                                             detail={"step_id": step_id, "tally": tally},
                                             comment=f"Committee vote: {tally['approve']} approve, "
                                                     f"{tally['abstain']} abstain, {tally['dissent']} dissent"))
        return self.committee_meeting(application_id, session, step_id)

    def record_committee_minutes(self, application_id: str, session: dict, step_id: str, *,
                                 agenda: list, discussion: str, resolution: str) -> dict:
        """R9: the structured minutes — the agenda, the discussion and the resolution. Re-saving
        produces a new minutes version (the history is kept)."""
        app = self._require(application_id)
        step = self._cg_step(app, step_id)
        self._cg_may(app, step, session)
        agenda = [str(a).strip() for a in (agenda or []) if str(a).strip()]
        discussion = str(discussion or "").strip()
        resolution = str(resolution or "").strip()
        if not agenda:
            raise InvalidRequestError("The minutes need the agenda")
        if not discussion:
            raise InvalidRequestError("The minutes need the discussion")
        if not resolution:
            raise InvalidRequestError("The minutes need the resolution")
        with self._app_lock(application_id):
            app = self._require(application_id)
            rec = self._cg_record(app, step_id)
            prev = rec.get("minutes") or {}
            rec["minutes"] = {"version": int(prev.get("version") or 0) + 1, "agenda": agenda,
                              "discussion": discussion, "resolution": resolution,
                              "recorded_by": session["user"]["id"],
                              "recorded_by_name": session["user"]["name"],
                              "at": self.now().isoformat(timespec="seconds")}
            self._cg_bump(app, rec, session, "minutes", {"minutes_version": rec["minutes"]["version"]})
            self.store.save(app, self._event(app, "committee_minutes",
                                             actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=step.id, to_step=step.id,
                                             detail={"step_id": step_id,
                                                     "minutes_version": rec["minutes"]["version"],
                                                     "resolution": resolution[:400]},
                                             comment="Committee minutes recorded"))
        return self.committee_meeting(application_id, session, step_id)

    def _cg_blockers(self, app: dict, step, action: str) -> list:
        """R9: what (if anything) stops a forward committee decision under the governance policy."""
        policy = self._cg_policy(app)
        if not policy.get("enabled") or step.kind != "committee" or action not in ("sanction", "approve"):
            return []
        rec = (app.get("committee_meetings") or {}).get(step.id) or {}
        if not rec.get("members"):
            return ["Committee governance: record the committee's attendance before deciding"]
        present, required, met, excluded = self._cg_present_quorum(policy, rec.get("members") or [])
        if not met:
            extra = f" ({excluded} excused on conflict of interest)" if excluded else ""
            return [f"Committee governance: quorum is not met — {present} of the required {required} "
                    f"present members{extra}"]
        if not rec.get("minutes"):
            return ["Committee governance: the structured minutes (agenda, discussion, resolution) "
                    "must be on file before the decision"]
        tally = {"approve": 0, "abstain": 0, "dissent": 0}
        for v in rec.get("votes") or []:
            tally[v.get("vote")] = tally.get(v.get("vote"), 0) + 1
        voting = tally["approve"] + tally["dissent"]
        if not voting:
            return ["Committee governance: the committee's vote is not recorded"]
        need = policy.get("majority") or "simple"
        ok = (tally["approve"] * 3 >= voting * 2) if need == "two_thirds" else (tally["approve"] > tally["dissent"])
        if not ok:
            return [f"Committee governance: the vote does not approve the decision "
                    f"({tally['approve']} approve / {tally['dissent']} dissent / {tally['abstain']} abstain)"]
        return []

    def _cg_summary(self, app: dict, step_id: str) -> Optional[dict]:
        """The governance position attached to a committee decision (for the sanction record)."""
        policy = self._cg_policy(app)
        if not policy.get("enabled"):
            return None
        rec = (app.get("committee_meetings") or {}).get(step_id) or {}
        if not rec:
            return None
        present, required, met, excluded = self._cg_present_quorum(policy, rec.get("members") or [])
        tally = {"approve": 0, "abstain": 0, "dissent": 0}
        for v in rec.get("votes") or []:
            tally[v.get("vote")] = tally.get(v.get("vote"), 0) + 1
        return {"quorum": {"required": required, "present": present, "met": met,
                           "excluded_conflicts": excluded},
                "votes": tally,
                "minutes_version": (rec.get("minutes") or {}).get("version"),
                "dissenters": [v.get("name") for v in rec.get("votes") or [] if v.get("vote") == "dissent"],
                "meeting_version": rec.get("version")}

    def _seed_committee_meeting(self, application_id: str, session: dict, step_id: str, at: datetime) -> None:
        """R9: the governed meeting behind a seeded committee decision — every roster member
        present, the minutes on file, a fully approving vote (the seeded history is a replay;
        live decisions are always gated). Idempotent per step."""
        app = self._require(application_id)
        if (app.get("committee_meetings") or {}).get(step_id):
            return
        policy = self._profile(app)
        roster = (policy.get("committee_governance") or {}).get("members") or []
        members = [{"name": r.get("name"), "user_id": r.get("user_id"), "status": "present"} for r in roster]
        self.record_committee_attendance(application_id, session, step_id, members)
        self.record_committee_minutes(application_id, session, step_id,
                                      agenda=["Credit proposal — seeded demo history", "Risk and security",
                                              "Resolution"],
                                      discussion="The committee examined the recommendation, the risk grade and "
                                                "the security package (seeded demo history).",
                                      resolution="Sanctioned as recommended (seeded demo history).")
        votes = [{"name": r.get("name"), "user_id": r.get("user_id"), "vote": "approve", "remarks": ""}
                 for r in roster]
        self.record_committee_votes(application_id, session, step_id, votes)

    # ── R1 authority-driven routing: the route controls the actual journey ─────────────────────
    def _route_skip(self, app: dict, step_id: str) -> str:
        """When the calculated route excludes a step (e.g. the ES process for a DFI term loan),
        follow the route: advance past the excluded step. Committee steps are never skipped —
        a decision always happens at its authority."""
        route = app.get("routing") or {}
        excluded = {e["step"]: e.get("basis") for e in route.get("excluded") or []}
        if not excluded or step_id not in excluded:
            return step_id
        wf = self._wf(app)
        cur = wf.step(step_id)
        hops = 0
        while cur.id in excluded and cur.kind != "committee" and hops < 8:
            nxt = wf.next_step(cur)
            if not nxt:
                break
            self.store.save(app, self._event(app, "step_skipped", actor={"id": None, "role": "route"},
                                             from_step=cur.id, to_step=nxt.id, at=self.now(),
                                             comment=f"Step not applicable per the calculated route: {cur.name}",
                                             detail={"basis": excluded[cur.id]}))
            cur = nxt
            hops += 1
        return cur.id

    def _recompute_routing(self, app: dict, actor: dict, note: str) -> None:
        """Recalculate the route after a material input (amount, risk grade, deviations, E&S
        category). A non-material change keeps the route and the completed approvals; a change
        that moves the required authority flags the route for reapproval at the next sanction.

        The authority follows the *recorded* assessment, not the request: once the credit
        reassessment has recorded a recommended amount / risk grade, the route is computed
        from them (a later route change stays flagged for reapproval at the next sanction)."""
        try:
            p = profiles.get_profile(app=app)
            probe = app
            old = app.get("routing") or {}
            if old.get("note") == "route calculated at creation":
                ca = app.get("credit_assessment") or {}
                rec_amount = ca.get("recommended_cr")
                rec_grade = (ca.get("risk_grade") or (app.get("ratings") or {}).get("risk_grade"))
                if rec_amount or rec_grade:
                    probe = dict(app)
                    if rec_amount:
                        probe["amount_cr"] = float(rec_amount)
                    if rec_grade:
                        probe["credit_assessment"] = {**ca, "risk_grade": rec_grade}
            # R11: fold the automatic policy deviations (from the profile rules) into the
            # count the route's authority is computed from — the route sees them.
            new = rt_routing.calculate(probe, p, self._wf(app))
            new["history"] = list(app.get("events") or [])        # approvals of record for this case
            material = bool(old) and rt_routing.authority_moved(old, new)
            rt_routing.record(app, new, self.now().isoformat(timespec="seconds"), note=note)
            if old and (material or sorted(x["step"] for x in new.get("excluded", []))
                        != sorted(x["step"] for x in old.get("excluded", []))):
                self.store.save(app, self._event(app, "route_changed", actor=actor,
                                                 from_step=app.get("step_id"), to_step=app.get("step_id"),
                                                 at=self.now(),
                                                 detail={"material": material,
                                                         "note": note,
                                                         "route": rt_routing.public_route(app.get("routing"))}))
        except Exception:
            logging.getLogger("los.routing").exception("route recalculation failed for %s",
                                                       app.get("application_id"))

    # R1: the concurrences the calculated authority requires at a sanction step
    @staticmethod
    def _concurrences_needed(app: dict, step_id: str) -> list:
        route = app.get("routing") or {}
        if step_id == "ip_sanction":
            return route.get("preliminary_concurrences") or []
        if step_id == "ap_sanction":
            return route.get("final_concurrences") or []
        return []

    def blockers(self, app: dict, step=None) -> list[dict]:
        """The blockers of the step's forward action (submit / approve), for the view."""
        step = step or (self._wf(app).step(app["step_id"]) if app.get("step_id") else None)
        if not step or app.get("status") in TERMINAL:
            return []
        action = {"maker": "submit", "checker": "approve", "vp_review": "submit"}.get(step.kind)
        if not action:
            return []
        try:
            return [{"message": m, "where": w} for m, w in self._gates(app, step, action)]
        except Exception:                                    # a view never fails on a gate it cannot evaluate
            log.exception("Gate evaluation failed for %s", app.get("application_id"))
            return []

    def _after_action(self, app: dict, step, action: str, session: dict, at: datetime, comment: str = "") -> None:
        """What a decision records beyond the move: recommendations, assessment snapshots, conditions, approvals, tranches."""
        stamp = {"by": session["user"]["id"], "by_name": session["user"]["name"], "at": at.isoformat(timespec="seconds")}
        if action == "sanction" and step.id == "ap_recommend":
            app.setdefault("recommendations", {})[step.stage_id] = {
                "by": session["user"]["id"], "by_name": session["user"]["name"],
                "at": at.isoformat(timespec="seconds"), "remarks": (comment or None)}
        if action == "submit" and step.id in RISK_MAKER_STEPS and app.get("credit_assessment"):
            app.setdefault("assessments", {})[step.stage_id] = dict(app["credit_assessment"])
        if action == "sanction" and step.id == "ap_sanction":
            terms = app.get("terms") or {}
            if any(not r.get("removed") for r in terms.get("conditions") or []):
                # G-F2: the conditions tracked after sanction are the T&C authored and approved at AP.
                due = (at + timedelta(days=CS_DUE_DAYS)).date().isoformat()
                app["conditions"] = terms_mod.to_conditions(terms, due)
                terms.update(status="sanctioned", locked_at=at.isoformat(timespec="seconds"),
                             locked_by=session["user"]["name"])
            else:
                case, _ = self._app_case(app)
                app["conditions"] = build_conditions(case, at)
        if step.id == "pos_checker" and action == "approve":
            for c in app.get("conditions") or []:
                if c["status"] in ("deferred", "waived") and not (c.get("approval") or {}).get("by"):
                    c["approval"] = dict(stamp)
            app["pos_approved"] = dict(stamp)
            # The checker's approval reviews the post-sanction mandatory documents (RUL-10).
            for d in app.get("documents") or []:
                if d.get("mandatory_stage") == "POS" and d.get("versions") and d["status"] == "uploaded":
                    d.update(status="reviewed", reviewer=stamp["by_name"], reviewed_at=stamp["at"])
        if step.id == "dis_checker" and action == "approve":
            for d in app.get("documents") or []:
                if d.get("mandatory_stage") == "DIS" and d.get("versions") and d["status"] == "uploaded":
                    d.update(status="reviewed", reviewer=stamp["by_name"], reviewed_at=stamp["at"])
        tranche = next((t for t in (app.get("disbursement") or {}).get("tranches") or []
                        if t["status"] in ("requested", "verified")), None)
        if tranche and step.id in ("dis_checker", "dis_vp_review", "dis_approver"):
            if action == "approve":
                # Final approval is an *authorisation to release* — payment execution and
                # reconciliation happen in core banking (Exit semantics, GAP-P0-16).
                tranche["status"] = "verified" if step.id == "dis_checker" else "approved"
                tranche["verified" if step.id == "dis_checker" else "approved"] = dict(stamp)
            elif action == "return":            # checker or VP rework: the tranche goes back to the maker
                tranche["status"] = "requested"
            elif action == "reject":
                tranche["status"] = "rejected"

    def _last_worker(self, application_id: str, step_id: str) -> Optional[str]:
        """Who last completed ``step_id`` on this application (returned work goes back to them)."""
        for e in self.store.events(application_id):
            if e.get("from_step") == step_id and e["action"] in ("submit", "allocate") and e.get("actor_id"):
                return e["actor_id"]
        return None

    def _last_in_role(self, application_id: str, role: str) -> Optional[str]:
        """Who last completed a step of ``role`` on this application, if they still hold the role."""
        app = self.store.get(application_id)
        for e in self.store.events(application_id):
            st = e.get("from_step")
            if not st or e["action"] not in ("submit", "allocate") or not e.get("actor_id"):
                continue
            try:
                if self._wf(app).step(st).role != role:
                    continue
            except Exception:
                continue
            user = next((u for u in self._wf(app).users_with_role(role) if u["id"] == e["actor_id"]), None)
            if user:
                return user["id"]
        return None

    def _may_reassign(self, session: dict, step) -> bool:
        if session["role"] == "los_admin":
            return True
        return step.role in session["user"]["roles"] or session["role"] in ("crp_evp", "crp_vp", "lpf_vp")

    def reassign(self, application_id: str, session: dict, user_id: str, comment: str = "") -> dict:
        app = self._require(application_id)
        if not app.get("step_id") or app["status"] in TERMINAL:
            raise ConflictError("Only an active application can be reassigned")
        step = self._wf(app).step(app["step_id"])
        if not self._may_reassign(session, step):
            raise ForbiddenError("Your role cannot reassign this step")
        try:
            user = self._wf(app).user(user_id)
        except WorkflowError as e:
            raise InvalidRequestError(str(e))
        if step.role not in user.get("roles", []):
            raise InvalidRequestError(f"{user['name']} does not hold the {self._wf(app).roles[step.role]} role")
        before = app.get("assignee_id")
        app.update(assignee_id=user_id, updated_at=self.now().isoformat(timespec="seconds"))
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "reassign", actor=actor, from_step=step.id, to_step=step.id,
                                         comment=comment, detail={"from": before, "to": user_id}))
        return self.get(application_id, session)

    def escalate(self, application_id: str, session: dict, comment: str) -> dict:
        app = self._require(application_id)
        if app["status"] in TERMINAL:
            raise ConflictError("A completed application cannot be escalated")
        if not (comment or "").strip():
            raise InvalidRequestError("A comment is required to escalate")
        app.update(escalated=True, updated_at=self.now().isoformat(timespec="seconds"))
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "escalate", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment=comment))
        return self.get(application_id, session)

    # ── credit assessment (Risk Maker) ───────────────────────────────────────
    def _credit_case(self, entity_id: str, run_id: Optional[str] = None) -> tuple[Optional[dict], Optional[dict]]:
        """The borrower's credit case and composed CAM (re-synced): the given run when it is
        not the latest (an application stays on the run it was assessed with), else the latest."""
        if not self.cases or not self.cases.get(entity_id):
            return None, None
        latest = self.cases.get(entity_id)
        if run_id and run_id != latest.get("run_id") and hasattr(self.cases, "get_run"):
            try:
                case = self.cases.get_run(entity_id, run_id)
                final = self.final_cam.get(entity_id, run_id)["final_cam"] if self.final_cam else None
                return case, final
            except NotFoundError:
                log.warning("Pinned run %s for %s is gone; using the latest run", run_id, entity_id)
        final = self.final_cam.get(entity_id)["final_cam"] if self.final_cam else None
        return latest, final

    def _app_case(self, app: dict) -> tuple[Optional[dict], Optional[dict]]:
        """The credit case pinned to this application (the run its assessment recorded).
        Another application re-running the borrower does not change what this one shows."""
        return self._credit_case(app["entity_id"], (app.get("credit_assessment") or {}).get("run_id"))

    def _pin_info(self, app: dict, case: Optional[dict]) -> dict:
        latest = self.cases.get(app["entity_id"]) if self.cases else None
        pinned = (app.get("credit_assessment") or {}).get("run_id")
        return {"pinned_run_id": pinned, "shown_run_id": (case or {}).get("run_id"),
                "latest_run_id": (latest or {}).get("run_id"),
                "newer_run_available": bool(pinned and latest and latest.get("run_id") != pinned)}

    # ── Populate → Verify → Lock: fields filled by agents, verified by people ─────

    @property
    def field_registry(self) -> FieldRegistry:
        if self._field_registry is None:
            self._field_registry = FieldRegistry.load()
        return self._field_registry

    def _app_lock(self, application_id: str) -> threading.Lock:
        """One writer per application for agent proposals and verification (single-writer merge)."""
        with self._app_locks_guard:
            return self._app_locks.setdefault(application_id, threading.Lock())

    def _reviews_of(self, app: dict) -> dict:
        """Decided fields in the earlier field_reviews shape (applications from before the field store keep theirs)."""
        return fieldmodel.legacy_reviews(app["fields"]) if app.get("fields") else (app.get("field_reviews") or {})

    def _populate(self, app: dict, case: Optional[dict], final: Optional[dict], at: str) -> Optional[dict]:
        """Run the population graph for the application's pinned case and merge the proposals
        into ``app["fields"]`` (the caller holds the application lock and saves)."""
        if not case:
            return None
        registry = self.field_registry
        view = build_risk_maker_view(case, final, self._view_context(app))
        run_id = case.get("run_id")
        # One parallel graph: the Risk Maker view and one reconciliation agent per workspace domain.
        rctx = {"case": case, "fact_pack": case.get("fact_pack") or {}, "company": self.companies.get(app["entity_id"]) or {},
                "app": app, "registry": registry, "today": self.now().date().isoformat(), "run_id": run_id,
                "prefill_values": self._prefill_values(app), "entity_history": self._entity_history(app),
                "authority": authority.required_authority(
                    app.get("amount_cr"), (app.get("credit_assessment") or {}).get("risk_grade") or case.get("risk_grade"),
                    deviations=len(committee_deviations(case)) + len(manual_deviations(app)),
                    final=app.get("stage_id") not in ("PS", "IP"),
                    app=app, product=profiles.primary_product(app))}
        resolvers = {**({cam_intake.RESOLVER: lambda ctx: cam_intake.resolver(app.get("cam"), rctx)}
                        if app.get("cam") else {}),
                     "risk_maker": lambda ctx: risk_maker_proposals(view, registry, run_id),
                     **{f"reconcile_{name}": (lambda ctx, fn=fn: fn(rctx)) for name, fn in reconcile.RESOLVERS.items()},
                     **{f"prefill_{name}": (lambda ctx, fn=fn: fn(rctx)) for name, fn in prefill.RESOLVERS.items()}}
        result = run_population(resolvers, registry)
        fields = app.setdefault("fields", {})
        summary = fieldmodel.merge(fields, result["proposals"], registry, at)
        workspaces = reconcile.materialise(app, fields)              # the values into the governed workspaces
        workspaces["raroc"] = self._auto_raroc(app, case, at)
        app["fields_meta"] = {"run_id": run_id, "at": at, "resolvers": list(resolvers),
                              "duration_ms": result["duration_ms"], "max_concurrency": result["max_concurrency"],
                              "failed": result["failed"], "registry_version": registry.version, "workspaces": workspaces}
        app["field_reviews"] = fieldmodel.legacy_reviews(fields)
        return {**summary, "proposals": len(result["proposals"]), "run_id": run_id, "workspaces": workspaces,
                "duration_ms": result["duration_ms"], "max_concurrency": result["max_concurrency"],
                "failed": result["failed"]}

    def _entity_history(self, app: dict) -> list[dict]:
        """The borrower's other applications in the LOS (for the past-proposals and relaxations narratives)."""
        out = []
        for other in self.store.list():
            if other["entity_id"] != app["entity_id"] or other["application_id"] == app["application_id"]:
                continue
            out.append({"application_id": other["application_id"], "status": other["status"],
                        "reason": (other.get("terminated") or {}).get("reason"), "deferrals": other.get("deferrals") or []})
        return out

    @staticmethod
    def _prefill_values(app: dict) -> dict:
        """Values read from the documents (accepted by the RM, else proposed) for reconciliation."""
        src = app.get("sourcing") or {}
        accepted = src.get("accepted") or {}
        out = {}
        for f in (src.get("prefill") or {}).get("fields") or []:
            if f.get("value") is None and f["id"] not in accepted:
                continue
            first = (f.get("sources") or [{}])[0]
            value = accepted[f["id"]]["value"] if f["id"] in accepted else f["value"]
            out[f["id"]] = {"value": value, "document": first.get("document"), "page": first.get("page")}
        return out

    def populate_fields(self, application_id: str, actor: Optional[dict] = None, *, force: bool = False) -> Optional[dict]:
        """Populate the application's fields from its pinned credit case and record it.
        Without ``force`` it only runs when the fields are missing or from another run."""
        with self._app_lock(application_id):
            app = self._require(application_id)
            case, final = self._app_case(app)
            if not case:
                return None
            if not force and app.get("fields") and (app.get("fields_meta") or {}).get("run_id") == case.get("run_id"):
                return None
            at = self.now().isoformat(timespec="seconds")
            summary = self._populate(app, case, final, at)
            app["updated_at"] = at
            self.store.save(app, self._event(app, "fields_populated", actor=actor or {"id": None, "role": "agent"},
                                             from_step=app.get("step_id"), to_step=app.get("step_id"),
                                             comment=(f"{summary['new']} new, {summary['updated']} updated, "
                                                      f"{summary['conflicts']} conflict(s) from run {summary['run_id']}"),
                                             detail=summary))
            return summary

    # agent fields whose value a person may already have recorded in another slot of the application
    _RELATED_ENTRIES = {"esms_screening.proposed_category": (("esms", "category"), "The ESMS screening category")}

    def _verify_stats(self, app: dict, step) -> dict:
        registry, fields = self.field_registry, app.get("fields") or {}
        step_id = step.id if step else None
        queue = fieldmodel.queue(fields, registry, step_id)
        for item in queue:              # an agent proposal next to what a person already recorded elsewhere
            path = self._RELATED_ENTRIES.get(item["field_id"])
            if not path:
                continue
            node = app
            for k in path[0]:
                node = node.get(k) if isinstance(node, dict) else None
            proposed = (item.get("proposal") or {}).get("value")
            if node not in (None, "") and str(node) != str(proposed):
                item["why"] = (f"{path[1]} is {node}; the agent proposes {proposed} — confirm, or change it "
                               f"to match")
                item["person_entry"] = node
        return {"queue": queue,
                "stats": fieldmodel.stats(fields, registry),
                "step_stats": fieldmodel.stats(fields, registry, registry.domains_verified_at(step_id)),
                "meta": app.get("fields_meta"), "pretick_confidence": registry.pretick_confidence}

    def _may_verify(self, app: dict, session: Optional[dict]) -> bool:
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        return bool(session and step and app["status"] not in TERMINAL
                    and self.field_registry.domains_verified_at(step.id)
                    and can_act(self._wf(app), session["user"]["id"], session["role"], step)
                    and app.get("assignee_id") in (None, session["user"]["id"]))

    def assessment(self, application_id: str, session: Optional[dict] = None) -> dict:
        """The Risk Maker workspace: job status, the tabs built from the application's pinned
        credit case, and the verify queue for the current step."""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        can_run = bool(session and step and step.id in RISK_MAKER_STEPS and app["status"] not in TERMINAL
                       and can_act(self._wf(app), session["user"]["id"], session["role"], step)
                       and app.get("assignee_id") in (None, session["user"]["id"]))
        with self._jobs_lock:
            job = dict(self._jobs[application_id]) if application_id in self._jobs else None
        if job:
            job.pop("thread", None)
            job["lanes"] = [dict(lane) for lane in job.get("lanes") or []]
        running = bool(job and job["state"] == "running")
        case, final = self._app_case(app) if not running else (None, None)
        if case and not running and self.populate_fields(application_id):
            app = self._require(application_id)          # first view of this run: populated just now
        view = (build_risk_maker_view(case, final, self._view_context(app)) if case else
                {"available": False, "reason": "No credit assessment has been run for this borrower yet."})
        review_summary = self._apply_reviews(view, self._reviews_of(app))
        return {"application_id": application_id, "entity_id": app["entity_id"], "can_run": can_run,
                "can_review": can_run and bool(view.get("available")),
                "at_risk_maker": bool(step and step.id in RISK_MAKER_STEPS), "job": job,
                "recorded": app.get("credit_assessment"), "review_summary": review_summary, "view": view,
                "pin": self._pin_info(app, case), "verify": self._verify_stats(app, step),
                "can_verify": self._may_verify(app, session),
                "prep": self._prep_job(application_id), "can_prepare": self._may_prepare(app, session)}

    def _prep_job(self, application_id: str) -> Optional[dict]:
        with self._jobs_lock:
            prep = dict(self._prep_jobs[application_id]) if application_id in self._prep_jobs else None
        if prep:
            prep.pop("thread", None)
            prep["lanes"] = [dict(lane) for lane in prep.get("lanes") or []]
        return prep

    def _may_prepare(self, app: dict, session: Optional[dict]) -> bool:
        try:
            self._maker_at(app, session, PREP_STEPS, "Preparing the application") if session else None
            return bool(session)
        except (ConflictError, ForbiddenError):
            return False

    def _view_context(self, app: dict) -> dict:
        others = [a["application_id"] for a in self.store.list()
                  if a["entity_id"] == app["entity_id"] and a["application_id"] != app["application_id"]]
        return {"relationship_manager": self._user_name(app.get("created_by")), "other_applications": others}

    @staticmethod
    def _apply_reviews(view: dict, reviews: dict) -> dict:
        """Attach each stored review to its field; a review whose original value has changed is stale."""
        counts = {"fields": 0, "confirmed": 0, "overridden": 0, "stale": 0, "pending": 0}
        if not view.get("available"):
            return counts
        for tab in view["tabs"]:
            tab_counts = {"fields": 0, "reviewed": 0}
            for sec in tab["sections"]:
                for f in sec.get("fields") or []:
                    counts["fields"] += 1
                    tab_counts["fields"] += 1
                    review = reviews.get(f["id"])
                    if review:
                        review = dict(review, stale=review.get("original") != f["value"])
                        f["review"] = review
                        if review["stale"]:
                            counts["stale"] += 1
                        else:
                            counts[review["status"]] += 1
                            tab_counts["reviewed"] += 1
                    else:
                        counts["pending"] += 1
            tab["review_counts"] = tab_counts
        return counts

    def _apply_field_actions(self, application_id: str, session: dict, decisions: list[dict], *,
                             event: str, known: Optional[set] = None) -> tuple[dict, list[dict]]:
        """Apply people's decisions to fields under the application lock (single writer):
        populate from the pinned case first, so a decision is always against the latest proposal."""
        registry = self.field_registry
        with self._app_lock(application_id):
            app = self._require(application_id)
            step = self._wf(app).step(app["step_id"])
            case, final = self._app_case(app)
            at = self.now().isoformat(timespec="seconds")
            populated = self._populate(app, case, final, at)
            fields = app.setdefault("fields", {})
            by = {"id": session["user"]["id"], "name": session["user"]["name"]}
            done = []
            for d in decisions:
                fid = d.get("field_id")
                rec = fields.get(fid)
                if rec is None or (known is not None and fid not in known):
                    raise InvalidRequestError(f"Unknown field {fid}")
                if not registry.verifiable_at(fid, step.id):
                    raise ForbiddenError(f"{rec['label']} is not verified at {step.name}")
                before = rec.get("value")
                try:
                    fieldmodel.apply_action(rec, d.get("action"), by=by, at=at, registry=registry,
                                            value=d.get("value"), reason=d.get("reason") or "")
                except fieldmodel.FieldActionError as e:
                    raise InvalidRequestError(str(e))
                done.append({"field_id": fid, "label": rec["label"], "action": d.get("action"), "status": rec["status"],
                             "original": (rec.get("proposal") or {}).get("value"), "was": before,
                             "value": rec.get("value"), "reason": (d.get("reason") or "").strip()})
            # Workspace fields: the decided value is written back into the workspace record.
            reconcile.materialise(app, fields, [x["field_id"] for x in done])
            self._auto_raroc(app, case, at)
            app["field_reviews"] = fieldmodel.legacy_reviews(fields)
            app["updated_at"] = at
            overrides = [x for x in done if x["status"] == "overridden"]
            comment = ("; ".join(f"{x['label']}: {x['original']} → {x['value']} ({x['reason']})" for x in overrides)
                       if overrides else None)
            actor = {"id": session["user"]["id"], "role": session["role"]}
            detail = {"reviews": done, **({"populated": populated} if populated and
                                          (populated["new"] or populated["updated"] or populated["conflicts"]) else {})}
            self.store.save(app, self._event(app, event, actor=actor, from_step=step.id, to_step=step.id,
                                             comment=comment, detail=detail))
            return app, done

    def _require_verifier(self, app: dict, session: dict) -> None:
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or app["status"] in TERMINAL or not self.field_registry.domains_verified_at(step.id):
            raise ConflictError("No fields are verified at this step")
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step) or \
                app.get("assignee_id") not in (None, session["user"]["id"]):
            raise ForbiddenError(f"Fields are verified by the assigned {self._wf(app).roles[step.role]}")
        if not self._app_case(app)[0]:
            raise ConflictError("Run the credit assessment before verifying its fields")

    def verify_fields(self, application_id: str, session: dict, decisions: list[dict]) -> dict:
        """People's decisions on fields: confirm | override (value + reason) | keep (a conflict,
        with a reason) | reopen. Audited; returns the refreshed workspace."""
        app = self._require(application_id)
        self._require_verifier(app, session)
        if not decisions:
            raise InvalidRequestError("No fields to verify")
        _, done = self._apply_field_actions(application_id, session, decisions, event="fields_verified")
        self._rerun_if_inputs_changed(application_id, session, done)
        return self.assessment(application_id, session)

    def _rerun_if_inputs_changed(self, application_id: str, session: dict, done: list[dict]) -> None:
        """Feedback loop: a person's change to an engine input (a CMA row, a security value) re-runs the
        credit case for this application with that value, so ratios, grade, RAROC and the CAM follow it."""
        changed = [d for d in done if d["field_id"].split(".")[0] in ("cma", "securities") and d["was"] != d["value"]
                   and (d["field_id"].split(".")[0] != "cma" or d["field_id"].split(".")[-1] in self._CMA_LINE_ITEMS)]
        if not changed or not self.cases:
            return
        reason = "Re-running the credit case with the verified value(s): " + "; ".join(
            f"{d['label']} {d['was']} → {d['value']}" for d in changed[:4])
        self._launch_assessment(application_id, {"id": session["user"]["id"], "role": session["role"],
                                                 "agent": "feedback"}, reason=reason[:500])

    def bulk_confirm(self, application_id: str, session: dict, field_ids: Optional[list[str]] = None) -> dict:
        """Confirm many proposals at once: the given ids, or every pre-ticked field in the queue.
        Decision-driving (must_verify) fields, conflicts and fields with critic issues are refused."""
        app = self._require(application_id)
        self._require_verifier(app, session)
        self.populate_fields(application_id)
        app = self._require(application_id)
        registry, fields = self.field_registry, app.get("fields") or {}
        step = self._wf(app).step(app["step_id"])
        if field_ids is None:
            ids = [i["field_id"] for i in fieldmodel.queue(fields, registry, step.id) if i["preticked"]]
        else:
            ids = list(dict.fromkeys(field_ids))
            refused = [fields[f]["label"] if f in fields else f for f in ids
                       if f not in fields or not fieldmodel.bulk_eligible(fields[f], registry)
                       or not registry.verifiable_at(f, step.id)]
            if refused:
                raise InvalidRequestError("These fields need an individual decision: " + ", ".join(refused[:8])
                                          + (f" (+{len(refused) - 8} more)" if len(refused) > 8 else ""))
        if not ids:
            raise InvalidRequestError("Nothing to bulk-confirm")
        self._apply_field_actions(application_id, session, [{"field_id": f, "action": "confirm"} for f in ids],
                                  event="fields_bulk_confirmed")
        return self.assessment(application_id, session)

    def review_fields(self, application_id: str, session: dict, reviews: list[dict]) -> dict:
        """Confirm or override Risk Maker fields. An override needs a value and a reason. Audited.
        (The earlier review API, now served by the field store: confirmed → confirm,
        overridden → override, clear → reopen.)"""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in RISK_MAKER_STEPS or app["status"] in TERMINAL:
            raise ConflictError("Fields are reviewed at the Risk Maker step")
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step) or \
                app.get("assignee_id") not in (None, session["user"]["id"]):
            raise ForbiddenError("Only the assigned Risk Maker can review the assessment")
        if not reviews:
            raise InvalidRequestError("No fields to review")
        case, final = self._app_case(app)
        if not case:
            raise ConflictError("Run the credit assessment before reviewing it")
        view = build_risk_maker_view(case, final, self._view_context(app))
        known = {f["id"] for t in view["tabs"] for sec in t["sections"] for f in sec.get("fields") or []}
        actions = {"confirmed": "confirm", "overridden": "override", "clear": "reopen"}
        decisions = []
        for r in reviews:
            if r.get("field_id") not in known:
                raise InvalidRequestError(f"Unknown field {r.get('field_id')}")
            if r.get("status") not in actions:
                raise InvalidRequestError("Review status must be confirmed, overridden or clear")
            decisions.append({"field_id": r["field_id"], "action": actions[r["status"]],
                              "value": r.get("value"), "reason": r.get("reason")})
        self._apply_field_actions(application_id, session, decisions, event="field_review", known=known)
        return self.assessment(application_id, session)

    def start_assessment(self, application_id: str, session: dict) -> dict:
        """Run the credit-intelligence pipeline for the application's borrower (background job)."""
        if not self.cases:
            raise OperationFailedError("The credit-intelligence engine is not connected")
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in RISK_MAKER_STEPS or app["status"] in TERMINAL:
            raise ConflictError("The credit assessment is run at the Risk Maker step")
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"Only the {self._wf(app).roles[step.role]} role can run the credit assessment")
        if app.get("assignee_id") and app["assignee_id"] != session["user"]["id"]:
            raise ForbiddenError(f"Assigned to {self._user_name(app['assignee_id'])}")
        if not self._launch_assessment(application_id, {"id": session["user"]["id"], "role": session["role"]}):
            raise ConflictError("A credit assessment is already running for this application")
        return self.assessment(application_id, session)

    def _on_progress(self, job: dict, event: dict) -> None:
        kind = event.get("type")
        if kind in ("agent_start", "agent_complete"):
            # Parallel lanes: one entry per agent in pipeline order, several may be running at once.
            lanes = job.setdefault("lanes", [])
            lane = next((l for l in lanes if l["agent"] == event.get("agent")), None)
            if lane is None:
                lane = {"agent": event.get("agent"), "step": event.get("step"),
                        "description": event.get("description"), "kind": event.get("lane")}
                lanes.append(lane)
                lanes.sort(key=lambda l: l.get("step") or 0)
            lane["status"] = "running" if kind == "agent_start" else event.get("status")
            job["running"] = [l["agent"] for l in lanes if l["status"] == "running"]
        if kind == "agent_start":
            job["message"] = f"Agent {event.get('step')}/{event.get('total')}: {event.get('description') or event.get('agent')}"
        elif kind == "agent_complete":
            job["agents_done"] += 1
        elif kind == "section_complete":
            job["sections_done"] += 1
            job["message"] = f"Writing the CAM: {event.get('title', '')} ({job['sections_done']} sections done)"
        elif kind == "info" and event.get("message"):
            job["message"] = event["message"]
        job["progress"] = min(99, round(55 * job["agents_done"] / _AGENTS + 45 * job["sections_done"] / _SECTIONS))

    def _launch_assessment(self, application_id: str, actor: dict, reason: Optional[str] = None) -> bool:
        """Start the credit-case run as a background job; False when one is already running."""
        app = self._require(application_id)
        with self._jobs_lock:
            running = self._jobs.get(application_id)
            if running and running["state"] == "running":
                return False
            job = {"state": "running", "started_at": self.now().isoformat(timespec="seconds"), "finished_at": None,
                   "message": reason or "Starting the credit assessment…", "progress": 0, "agents_done": 0,
                   "sections_done": 0, "error": None, "run_id": None, "reason": reason}
            self._jobs[application_id] = job
        self.store.save(app, self._event(app, "assessment_started", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment=reason))
        job["thread"] = threading.Thread(target=self._run_assessment, args=(application_id, app["entity_id"], actor),
                                         daemon=True, name=f"los-assessment-{application_id}")
        job["thread"].start()
        return True

    # Field-store values a person verified that the engines take as input on the next run (feedback loop).
    _CMA_LINE_ITEMS = {"revenue": "revenue_operating", "income": "total_income", "depreciation": "depreciation",
                       "finance_cost": "finance_cost", "pbt": "pbt", "pat": "pat"}

    def _engine_overrides(self, app: dict) -> dict:
        """The person's overrides of engine inputs, in the shape CaseService.run takes."""
        out: dict = {"financials": {}, "collateral": {}}
        for fid, rec in (app.get("fields") or {}).items():
            if rec.get("status") != "overridden":
                continue
            parts = fid.split(".")
            try:
                value = float(str(rec["value"]).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if parts[0] == "cma" and len(parts) == 4 and parts[3] in self._CMA_LINE_ITEMS:
                out["financials"].setdefault(parts[2], {})[self._CMA_LINE_ITEMS[parts[3]]] = value
            elif parts[0] == "securities" and parts[-1] == "proposed_value_cr":
                target = (rec.get("proposal") or {}).get("target") or []
                desc = (target[1].get("new") or {}).get("description") if len(target) > 1 and isinstance(target[1], dict) else None
                if desc:
                    out["collateral"][desc] = value
        # A new prospect has no statements on record: the figures the RM accepted from its audited
        # statements at Prospect Sourcing are its statement for that year (the engine's own extraction
        # reads the P&L only — without these, debt and net worth would be zero).
        company = self.companies.get(app.get("entity_id")) or {}
        if not self._has_master_financials(company):
            stmt = self._accepted_statement(app)
            if stmt:
                out["statement"] = stmt
        # The credit case assesses this application's request, not the facility on the borrower record
        # (which, for a catalogue borrower, can be a different proposal altogether).
        fac = app.get("facility") or (app.get("facilities") or [{}])[0]
        rec = (self.companies.get(app.get("entity_id")) or {}).get("facility")
        wanted = {"amount_cr": app.get("amount_cr"), "tenor_months": fac.get("tenor_months"),
                  "facility_type": fac.get("facility_type"), "purpose": fac.get("purpose")}
        if rec is not None and wanted["amount_cr"] and (
                abs(float(wanted["amount_cr"]) - float(getattr(rec, "amount_requested_cr", 0) or 0)) > 1e-6
                or (wanted["tenor_months"] and int(wanted["tenor_months"]) != getattr(rec, "tenor_months", None))
                or (wanted["facility_type"] and wanted["facility_type"] != getattr(getattr(rec, "facility_type", None), "value", None))):
            out["facility"] = wanted
        return {k: v for k, v in out.items() if v}

    _ACCEPTED_STATEMENT = {"revenue_cr": "revenue_operating", "ebitda_cr": "ebitda", "pat_cr": "pat",
                           "net_worth_cr": "total_equity", "total_debt_cr": "total_debt"}

    def _accepted_statement(self, app: dict) -> Optional[dict]:
        """{"period", "as_of", "items"} from the financial figures accepted at Prospect Sourcing, or None."""
        accepted = ((app.get("sourcing") or {}).get("accepted")) or {}
        items, docs = {}, []
        for fid, key in self._ACCEPTED_STATEMENT.items():
            a = accepted.get(fid)
            try:
                items[key] = float(str((a or {}).get("value")).replace(",", ""))
            except (TypeError, ValueError):
                continue
            docs.append(str(((a or {}).get("source") or {}).get("document") or ""))
        if not items:
            return None
        year = next((int(m.group(1)) for d in docs for m in [re.search(r"fy\s*_?(\d{4})", d, re.I)] if m), None)
        if year is None:                                     # the last completed financial year
            today = self.now().date()
            year = today.year if today.month > 3 else today.year - 1
        return {"period": f"FY{year}", "as_of": f"{year}-03-31", "items": items}

    def _run_case(self, entity_id: str, app: dict, on_progress=None) -> tuple:
        """Run the credit case for this application, with the person's verified overrides."""
        overrides = self._engine_overrides(app)
        kwargs = {"overrides": overrides} if overrides else {}
        return self.cases.run(entity_id, on_progress=on_progress, **kwargs)

    def _run_assessment(self, application_id: str, entity_id: str, actor: dict) -> None:
        job = self._jobs[application_id]
        try:
            case, _ = self._run_case(entity_id, self._require(application_id),
                                     on_progress=lambda e: self._on_progress(job, e))
            job["message"] = "Composing the credit memorandum…"
            summary = self._record_assessment(application_id, case, actor, defer_routing=True)
            # Populate the application's fields from the new run, ready to verify.
            job["message"] = "Populating the fields from the credit case…"
            try:
                job["populated"] = self.populate_fields(application_id, actor)
            except Exception:                                        # the assessment itself succeeded
                log.exception("Field population failed for %s", application_id)
            if self._routing_defer.pop(application_id, False):
                self._recompute_routing(self._require(application_id), actor,
                                        "route recalculated after the credit reassessment")
            job.update(state="done", progress=100, run_id=case.get("run_id"),
                       message=f"Credit assessment complete: {summary['decision_label'] or 'no reassessment'}",
                       finished_at=self.now().isoformat(timespec="seconds"))
        except Exception as e:                                       # recorded on the job and in the audit trail
            log.exception("Credit assessment failed for %s", application_id)
            job.update(state="failed", error=str(e), message=f"Credit assessment failed: {e}",
                       finished_at=self.now().isoformat(timespec="seconds"))
            try:
                app = self._require(application_id)
                self.store.save(app, self._event(app, "assessment_failed", actor=actor, from_step=app.get("step_id"),
                                                 to_step=app.get("step_id"), comment=str(e)[:300]))
            except Exception:
                log.exception("Could not record the failed assessment for %s", application_id)

    _routing_defer = {}

    def _record_assessment(self, application_id: str, case: dict, actor: dict, defer_routing: bool = False) -> dict:
        """Pin a finished credit-case run to the application, with its audit event.

        With ``defer_routing`` the route recalculation is recorded as pending (and performed
        by the caller after the field population) so the audit trail reads assessment →
        fields populated → route recalculated."""
        if defer_routing:
            self._routing_defer[application_id] = True
        final = self.final_cam.get(case["entity_id"])["final_cam"] if self.final_cam else {}
        rea = case.get("reassessment") or {}
        fr = rea.get("facility_recommendation") or {}
        summary = {"run_id": case.get("run_id"), "run_at": case.get("run_at"),
                   "decision": rea.get("decision"), "decision_label": rea.get("decision_label"),
                   "requested_cr": fr.get("requested_cr"), "recommended_cr": fr.get("recommended_cr"),
                   "risk_grade": case.get("risk_grade"), "system_recommendation": case.get("recommendation"),
                   "narrative_mode": case.get("narrative_mode"),
                   "final_cam_available": bool((final or {}).get("available"))}
        with self._app_lock(application_id):
            app = self._require(application_id)
            app["credit_assessment"] = summary
            app["updated_at"] = self.now().isoformat(timespec="seconds")
            self.store.save(app, self._event(app, "assessment", actor=actor, from_step=app.get("step_id"),
                                             to_step=app.get("step_id"), detail=summary))
            # R9: a post-sanction reassessment is a reassessment record on the standing sanction —
            # the sanctioned amount and route are unaffected; the committee can act on the new grade.
            if app.get("status") not in TERMINAL and (app.get("sanctions") or {}):
                app.setdefault("reassessments", []).append(
                    {"run_id": summary.get("run_id"), "risk_grade": summary.get("risk_grade"),
                     "recommended_cr": summary.get("recommended_cr"),
                     "decision": summary.get("decision"), "at": summary.get("run_at") or self.now().isoformat(timespec="seconds"),
                     "by": (actor or {}).get("id")})
            if not defer_routing:
                self._recompute_routing(app, actor, "route recalculated after the credit reassessment")
        return summary

    def wait_for_assessment(self, application_id: str, timeout: float = 600) -> dict:
        """Block until the running job finishes (tests and scripts)."""
        job = self._jobs.get(application_id)
        if job and job.get("thread"):
            job["thread"].join(timeout)
        return {k: v for k, v in (job or {}).items() if k != "thread"}

    # ── prospect sourcing: documents and AI prefill ─────────────────────────
    def _maker_at(self, app: dict, session: dict, steps: tuple, what: str) -> None:
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in steps or app["status"] in TERMINAL:
            raise ConflictError(f"{what} is done at the {' / '.join(self._wf(app).step(s).name for s in steps)} step")
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step belongs to the {self._wf(app).roles[step.role]} role")
        if app.get("assignee_id") not in (None, session["user"]["id"]):
            raise ForbiddenError(f"Assigned to {self._user_name(app['assignee_id'])}; reassign it first")

    def _can(self, app: dict, session: Optional[dict], steps: tuple) -> bool:
        try:
            self._maker_at(app, session, steps, "") if session else None
            return bool(session)
        except (ConflictError, ForbiddenError):
            return False

    def _entity_dir(self, entity_id: str) -> Optional[Path]:
        return self.documents_root / entity_id if self.documents_root else None

    def _link_documents(self, app: dict, at: str) -> list[str]:
        """The document agent: link the borrower's documents on file to the checklist items they satisfy."""
        d = self._entity_dir(app["entity_id"])
        if not d or not d.exists():
            return []
        files = [p.relative_to(d).as_posix() for p in d.rglob("*.pdf")]
        linked = dreg.link_on_file(app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app))), files, at)
        return linked + dreg.link_workspace(app, at)

    def _documents_on_file(self, entity_id: str) -> list[dict]:
        d = self._entity_dir(entity_id)
        if not d or not d.exists():
            return []
        return [{"document": p.relative_to(d).as_posix(), "category": p.parent.name, "size_kb": round(p.stat().st_size / 1024, 1)}
                for p in sorted(d.rglob("*.pdf"))]

    def sourcing(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        src = app.get("sourcing") or {}
        prefill = src.get("prefill")
        accepted = src.get("accepted") or {}
        if prefill:
            for f in prefill["fields"]:
                f["accepted"] = accepted.get(f["id"])
        prep = self._prep_job(application_id)
        return {"application_id": application_id, "entity_id": app["entity_id"],
                "can_edit": self._can(app, session, SOURCING_STEPS),
                "at_sourcing": bool(app.get("step_id") in SOURCING_STEPS),
                "documents": self._documents_on_file(app["entity_id"]), "categories": list(UPLOAD_CATEGORIES),
                "prefill": prefill, "accepted_count": len(accepted),
                "intake": (prefill or {}).get("intake"), "prep": prep,
                "fields": fieldmodel.stats(app.get("fields") or {}, self.field_registry, ["sourcing"])}

    def upload_document(self, application_id: str, session: dict, category: str, filename: str,
                        content: bytes, link_to: Optional[str] = None) -> dict:
        """Add a document to the borrower's folder and the logical document registry.
        Existing documents are never overwritten; ``link_to`` binds the upload to a
        checklist document (GAP-P0-12: multiple versions under one logical name)."""
        app = self._require(application_id)
        self._maker_at(app, session, UPLOAD_STEPS, "Uploading documents")
        if category not in UPLOAD_CATEGORIES:
            raise InvalidRequestError(f"Unknown document category: {category}")
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename or "").name)
        if not name.lower().endswith(".pdf") or not content.startswith(b"%PDF"):
            raise InvalidRequestError("Only PDF documents can be uploaded")
        if len(content) > _MAX_UPLOAD_BYTES:
            raise InvalidRequestError("The document is larger than 25 MB")
        target = self._entity_dir(app["entity_id"])
        if not self.doc_store or not target:
            raise OperationFailedError("Document storage is not connected")
        # Multiple versions under one logical name (GAP-P0-12): never overwrite, auto-version.
        final_name = name
        if (target / category / final_name).exists():
            stem, suffix = Path(name).stem, Path(name).suffix
            v = 2
            while (target / category / f"{stem}-{v}{suffix}").exists():
                v += 1
            final_name = f"{stem}-{v}{suffix}"
        self.doc_store.store_document(app["entity_id"], category, final_name, content, source="los_upload",
                                      document_role=None)
        # Register in the logical document registry (a checklist document when linked).
        registry = app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app)))
        linked = next((d for d in registry if d["doc_id"] == link_to), None) if link_to else None
        dreg.register_upload(registry, name=(linked["name"] if linked else final_name), category=category,
                             scope="application", file_name=f"{category}/{final_name}",
                             by_name=session["user"]["name"], at=self.now().isoformat(timespec="seconds"),
                             doc_id=link_to)
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "document_upload", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment=f"Uploaded {category}/{final_name}",
                                         detail={"document": f"{category}/{final_name}", "bytes": len(content),
                                                 "linked_to": link_to}))
        return self.sourcing(application_id, session)

    def _intake_llm(self):
        """The model the intake agent may use (vision for scans, structured extraction), if any."""
        if not self.llm_factory:
            return None
        try:
            return self.llm_factory()
        except Exception:                                            # intake runs deterministically without it
            log.warning("No LLM for document intake", exc_info=True)
            return None

    def _has_documents(self, entity_id: str) -> bool:
        d = self._entity_dir(entity_id)
        return bool(d and d.exists() and next(d.rglob("*.pdf"), None))

    def _merge_sourcing(self, app: dict, prefill: dict, at: str, domain: str = "sourcing") -> dict:
        """The intake's proposals into the field store, critic-checked (caller holds the lock and saves)."""
        proposals = intake.proposals_from_prefill(prefill, domain)
        checkable = [p for p in proposals if fieldmodel.available(p["value"], p["provenance"])]
        for p, verdict in zip(checkable, CriticAgent().review_proposals(checkable)):
            p["issues"] = list(p.get("issues") or []) + verdict.issues
        fields = app.setdefault("fields", {})
        summary = fieldmodel.merge(fields, proposals, self.field_registry, at)
        app["field_reviews"] = fieldmodel.legacy_reviews(fields)
        return summary

    def _save_prefill(self, application_id: str, prefill: dict, actor: dict) -> dict:
        """Store a prefill and merge it into the field store, as one audited write (single writer)."""
        with self._app_lock(application_id):
            app = self._require(application_id)
            at = self.now().isoformat(timespec="seconds")
            app.setdefault("sourcing", {})["prefill"] = prefill
            merged = self._merge_sourcing(app, prefill, at)
            s, i = prefill["summary"], prefill.get("intake") or {}
            self.store.save(app, self._event(app, "document_prefill", actor=actor, from_step=app["step_id"],
                                             to_step=app["step_id"],
                                             comment=f"Read {i.get('documents', len(prefill['documents']))} documents: "
                                                     f"{s['found']}/{s['total']} fields found, {s['conflicts']} conflict(s)",
                                             detail={"summary": s, "ai": prefill["ai"], "intake": i, "fields": merged}))
            return merged

    def run_prefill(self, application_id: str, session: dict) -> dict:
        """The document intake agent reads the borrower's documents (in parallel) and proposes the
        Prospect Sourcing values; nothing is applied until the RM accepts them."""
        app = self._require(application_id)
        self._maker_at(app, session, SOURCING_STEPS, "Document prefill")
        if not self._has_documents(app["entity_id"]):
            raise ConflictError("No documents are on file for this borrower — upload documents first")
        prefill = intake.run_intake(self._entity_dir(app["entity_id"]),
                                    master_values(self.companies.get(app["entity_id"]), app), self._intake_llm(),
                                    now=self.now())
        self._save_prefill(application_id, prefill, {"id": session["user"]["id"], "role": session["role"]})
        return self.sourcing(application_id, session)

    def apply_prefill(self, application_id: str, session: dict, items: list[dict]) -> dict:
        """Accept proposed values (optionally edited). Facility values update the application, and
        the decisions are recorded in the field store (confirm / override / reopen)."""
        with self._app_lock(application_id):
            self._apply_prefill(application_id, session, items)
        return self.sourcing(application_id, session)

    def _apply_prefill(self, application_id: str, session: dict, items: list[dict]) -> None:
        app = self._require(application_id)
        self._maker_at(app, session, SOURCING_STEPS, "Applying prefilled values")
        prefill = (app.get("sourcing") or {}).get("prefill")
        if not prefill:
            raise ConflictError("Run the document prefill first")
        by_id = {f["id"]: f for f in prefill["fields"]}
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        accepted = app["sourcing"].setdefault("accepted", {})
        facility = dict(app.get("facility") or {})
        changes = []
        for item in items or []:
            f = by_id.get(item.get("field_id"))
            if not f:
                raise InvalidRequestError(f"Unknown field: {item.get('field_id')}")
            if item.get("status") == "clear":
                accepted.pop(f["id"], None)
                changes.append(f"{f['label']}: cleared")
                continue
            edited = item.get("value") not in (None, "") and str(item["value"]).strip() != f["display"]
            raw = str(item["value"]).strip() if edited else f["value"]
            if raw in (None, ""):
                raise InvalidRequestError(f"{f['label']} has no value to accept — enter one")
            value = _typed(f["kind"], raw, f["label"])
            if edited and not (item.get("reason") or "").strip():
                raise InvalidRequestError(f"Editing {f['label']} needs a reason")
            accepted[f["id"]] = {"value": value, "display": str(raw) if edited else f["display"], "edited": edited,
                                 "proposed": f["display"] or None, "reason": item.get("reason") or None,
                                 "confidence": f["confidence"], "status": f["status"],
                                 "source": (f["sources"] or [{}])[0] if not edited else {},
                                 "by": session["user"]["id"], "by_name": session["user"]["name"], "at": at}
            if f.get("target"):
                facility[f["target"]] = value
            changes.append(f"{f['label']}: {accepted[f['id']]['display']}" + (" (edited)" if edited else ""))
        if not changes:
            raise InvalidRequestError("Nothing to apply")
        if facility.get("amount_cr") in (None, 0) or float(facility["amount_cr"]) <= 0:
            raise InvalidRequestError("Proposed amount must be greater than zero")
        app["facility"] = facility
        facilities = list(app.get("facilities") or [])
        if facilities:
            facilities[0] = {**facilities[0], **facility, "facility_id": facilities[0].get("facility_id", "FAC-001")}
            if facility.get("amount_cr") is not None and not facilities[0].get("sanctioned_cr"):
                facilities[0]["proposed_cr"] = facility["amount_cr"]       # the request, everywhere
        else:
            facilities = [dict(facility, facility_id="FAC-001")]
        app["facilities"] = facilities
        app["amount_cr"] = round(sum(float(row.get("amount_cr") or 0) for row in facilities), 2)
        # The same decisions in the field store, so Prospect Sourcing counts in the populate / verify metrics.
        fields, by = app.get("fields") or {}, {"id": session["user"]["id"], "name": session["user"]["name"]}
        for item in items or []:
            rec = fields.get(intake.field_id(by_id[item["field_id"]]))
            if not rec:
                continue
            acc = accepted.get(item["field_id"])
            action = "reopen" if item.get("status") == "clear" else ("override" if acc and acc["edited"] else "confirm")
            try:
                fieldmodel.apply_action(rec, action, by=by, at=at, registry=self.field_registry,
                                        value=acc["display"] if acc else None, reason=(acc or {}).get("reason") or "")
            except fieldmodel.FieldActionError:
                log.warning("Could not mirror %s on %s into the field store", item["field_id"], application_id)
        app["field_reviews"] = fieldmodel.legacy_reviews(fields)
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "prefill_apply", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment="; ".join(changes)[:600],
                                         detail={"fields": [i.get("field_id") for i in items]}))

    # ── New prospect from documents, and the preparation agent ───────────────
    #
    # A new-to-bank borrower is sourced from its documents: the RM stages them, the intake
    # agent reads them and proposes the identity and facility, duplicates are checked, and on
    # creation the borrower is registered (no invented identifiers), the documents move into its
    # folder and the application is prepared by agents running in parallel lanes.

    _STAGING = "_staging"
    _IDENTITY_FIELDS = ("legal_name", "cin", "pan", "gstin", "date_of_incorporation", "registered_address",
                        "listed_exchange", "external_rating")
    _FACILITY_FIELDS = ("facility_type", "case_type", "amount_cr", "tenor_months", "purpose")

    def _require_sourcing_maker(self, session: dict) -> None:
        first = self.wf.first_step
        if session["role"] != first.role:
            raise ForbiddenError(f"Only the {self.wf.roles[first.role]} role sources new prospects")

    def _staging_dir(self, staging_id: str) -> Path:
        if not self.documents_root:
            raise OperationFailedError("Document storage is not connected")
        if not re.fullmatch(r"[a-f0-9]{12}", staging_id or ""):
            raise InvalidRequestError("Unknown staging id")
        return self.documents_root / self._STAGING / staging_id

    def _staged_documents(self, d: Path) -> list[dict]:
        return [{"document": p.relative_to(d).as_posix(), "category": p.parent.name,
                 "size_kb": round(p.stat().st_size / 1024, 1)} for p in sorted(d.rglob("*.pdf"))] if d.exists() else []

    def stage_document(self, session: dict, category: str, filename: str, content: bytes,
                       staging_id: Optional[str] = None) -> dict:
        """Add a document to a new prospect's staging area (before the borrower exists)."""
        self._require_sourcing_maker(session)
        if category not in UPLOAD_CATEGORIES:
            raise InvalidRequestError(f"Unknown document category: {category}")
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename or "").name)
        if not name.lower().endswith(".pdf") or not content.startswith(b"%PDF"):
            raise InvalidRequestError("Only PDF documents can be uploaded")
        if len(content) > _MAX_UPLOAD_BYTES:
            raise InvalidRequestError("The document is larger than 25 MB")
        sid = staging_id or secrets.token_hex(6)
        target = self._staging_dir(sid) / category
        target.mkdir(parents=True, exist_ok=True)
        final, v = name, 2
        while (target / final).exists():
            final, v = f"{Path(name).stem}-{v}{Path(name).suffix}", v + 1
        (target / final).write_bytes(content)
        return {"staging_id": sid, "documents": self._staged_documents(self._staging_dir(sid))}

    @staticmethod
    def _name_key(name: Optional[str]) -> str:
        key = re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower().replace("&", " and "))
        key = re.sub(r"\b(the|limited|ltd|private|pvt|company|co|inc|llp)\b", " ", key)
        return re.sub(r"\s+", "", key)

    def _prospect_matches(self, name: Optional[str], pan: Optional[str], cin: Optional[str]) -> list[dict]:
        """Borrowers already on record with the same PAN, CIN or name (and their LOS applications)."""
        out, key = [], self._name_key(name)
        for eid, company in self.companies.items():
            b = company.get("borrower")
            why = [w for w, hit in (("PAN", pan and getattr(b, "pan", None) == pan),
                                    ("CIN", cin and getattr(b, "cin", None) == cin),
                                    ("name", key and self._name_key(getattr(b, "company_name", "")) == key)) if hit]
            if why:
                apps = [a["application_id"] for a in self.store.list() if a["entity_id"] == eid]
                out.append({"entity_id": eid, "name": getattr(b, "company_name", eid), "matched_on": why,
                            "applications": apps})
        return out

    def read_staged(self, session: dict, staging_id: str) -> dict:
        """The intake agent reads the staged documents and proposes the identity and facility."""
        self._require_sourcing_maker(session)
        d = self._staging_dir(staging_id)
        if not self._staged_documents(d):
            raise ConflictError("Upload the prospect's documents first")
        prefill = intake.run_intake(d, {}, self._intake_llm(), now=self.now())
        by_id = {f["id"]: f for f in prefill["fields"]}
        (d / "intake.json").write_text(json.dumps(prefill, default=str), encoding="utf-8")

        def pick(fid):
            f = by_id.get(fid) or {}
            return {"value": f.get("value"), "display": f.get("display") or "", "confidence": f.get("confidence"),
                    "status": f.get("status"), "source": (f.get("sources") or [None])[0],
                    "alternatives": f.get("alternatives") or []}

        identity = {fid: pick(fid) for fid in self._IDENTITY_FIELDS}
        facility = {fid: pick(fid) for fid in self._FACILITY_FIELDS}
        matches = self._prospect_matches(identity["legal_name"]["value"], identity["pan"]["value"],
                                         identity["cin"]["value"])
        cam = cam_intake.read_cams(d, self._intake_llm())
        if cam:
            (d / "cam.json").write_text(json.dumps(cam, default=str), encoding="utf-8")
        return {"staging_id": staging_id, "documents": self._staged_documents(d), "prefill": prefill,
                "identity": identity, "facility": facility, "matches": matches,
                "sectors": [s.value for s in Sector], "cam": self._cam_preview(cam)}

    @staticmethod
    def _cam_preview(cam: Optional[dict]) -> Optional[dict]:
        if not cam:
            return None
        return {"document": cam["document"], "summary": cam["summary"], "ai": cam.get("ai"),
                "sections": [{"key": k, "heading": s["heading"], "page": s["page"], "preview": s["text"][:160]}
                             for k, s in cam["sections"].items()],
                "labels": {k: {"value": v["value"], "page": v["page"]} for k, v in cam["labels"].items()}}

    def _new_entity_id(self, name: str) -> str:
        stem = (re.sub(r"[^A-Z]", "", self._name_key(name).upper()) or "NEWB")[:4].ljust(4, "X")
        n = 1
        while f"{stem}{n:03d}" in self.companies:
            n += 1
        return f"{stem}{n:03d}"

    def create_prospect(self, session: dict, *, staging_id: str, identity: dict, facilities: list[dict],
                        related_parties: Optional[list[dict]] = None, prospect_discussion: Optional[dict] = None,
                        sourcing_decision: Optional[dict] = None, priority: str = "Normal",
                        confirm_not_duplicate: bool = False, prepare: bool = True,
                        cam: Optional[dict] = None, product: Optional[str] = None) -> dict:
        """Register a new prospect from its staged documents and create its application."""
        self._require_sourcing_maker(session)
        d = self._staging_dir(staging_id)
        if not self._staged_documents(d):
            raise ConflictError("Upload the prospect's documents first")
        ident = {k: (str(v).strip() if v not in (None, "") else None) for k, v in (identity or {}).items()}
        if not ident.get("company_name"):
            raise InvalidRequestError("The prospect's legal name is required")
        if ident.get("pan"):
            ident["pan"] = ident["pan"].upper()
            if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", ident["pan"]):
                raise InvalidRequestError("PAN must look like AAAAA9999A")
        if ident.get("cin"):
            ident["cin"] = ident["cin"].upper()
            if not re.fullmatch(r"[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}", ident["cin"]):
                raise InvalidRequestError("CIN is not in the registry format")
        if ident.get("date_of_incorporation"):
            try:
                datetime.fromisoformat(ident["date_of_incorporation"])
            except ValueError:
                raise InvalidRequestError("Date of incorporation must be YYYY-MM-DD")
        matches = self._prospect_matches(ident["company_name"], ident.get("pan"), ident.get("cin"))
        hard = [m for m in matches if {"PAN", "CIN"} & set(m["matched_on"])]
        if hard:
            m = hard[0]
            raise ConflictError(f"{m['name']} is already on record as {m['entity_id']} (same "
                                f"{' and '.join(x for x in m['matched_on'] if x != 'name')}) — create the "
                                "application for that borrower instead")
        if matches and not confirm_not_duplicate:
            raise ConflictError(f"A borrower with the same name is on record ({matches[0]['entity_id']}) — "
                                "confirm this prospect is a different company")
        if not facilities:
            raise InvalidRequestError("At least one proposed facility is required")
        if cam and cam.get("mode") not in ("document", "generate"):
            raise InvalidRequestError("A new prospect starts from its CAM document or generates one")
        cam_reading = self._staged_cam(d) if cam and cam["mode"] == "document" else None
        entity_id = self._new_entity_id(ident["company_name"])
        first = dict(facilities[0])
        if self.company_registrar:
            self.company_registrar(entity_id, ident, first)
        else:                                                      # no catalog service (tests): in memory only
            from src.application.company_service import build_prospect_company
            self.companies[entity_id] = build_prospect_company(entity_id, ident, first)
        moved = self._move_staged(d, entity_id)
        app = self.create(session, entity_id=entity_id, facilities=facilities, related_parties=related_parties,
                          priority=priority, prospect_discussion=prospect_discussion,
                          sourcing_decision=sourcing_decision, customer_id_selection="new", product=product)
        with self._app_lock(app["application_id"]):
            app = self._require(app["application_id"])
            at = self.now().isoformat(timespec="seconds")
            registry = app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app)))
            for doc in moved:
                dreg.register_upload(registry, name=Path(doc).name, category=doc.split("/")[0], scope="application",
                                     file_name=doc, by_name=session["user"]["name"], at=at)
            self.store.save(app, self._event(app, "prospect_sourced", actor={"id": session["user"]["id"],
                                                                              "role": session["role"]},
                                             from_step=app["step_id"], to_step=app["step_id"],
                                             comment=f"New prospect {ident['company_name']} ({entity_id}) sourced from "
                                                     f"{len(moved)} document(s)",
                                             detail={"identity": ident, "documents": moved,
                                                     "name_matches_confirmed": [m["entity_id"] for m in matches]}))
        if cam:
            self._attach_cam(app["application_id"], session, cam, cam_reading)
        if prepare:
            self.prepare_application(app["application_id"], session)
        return self.get(app["application_id"], session)

    def _move_staged(self, d: Path, entity_id: str) -> list[str]:
        """The staged documents into the borrower's folder (through the document store when connected)."""
        moved = []
        for p in sorted(d.rglob("*.pdf")):
            category, name = p.parent.name, p.name
            if self.doc_store:
                self.doc_store.store_document(entity_id, category, name, p.read_bytes(), source="los_prospect_intake")
            else:
                target = self.documents_root / entity_id / category
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target / name)
            moved.append(f"{category}/{name}")
        shutil.rmtree(d, ignore_errors=True)
        return moved

    def prepare_application(self, application_id: str, session: dict, wait: bool = False) -> dict:
        """The preparation agent for Prospect Sourcing: identity & dedupe, document intake and every
        API due-diligence check run in parallel lanes; one writer applies the results.
        ``wait=True`` runs the lanes inline (the router's sync call path) so callers observe
        the applied result immediately instead of a still-running job."""
        app = self._require(application_id)
        self._maker_at(app, session, PREP_STEPS, "Preparing the application")
        with self._jobs_lock:
            running = self._prep_jobs.get(application_id)
            if running and running["state"] == "running":
                # a worker that died with the process (server restart) strands the job 'running';
                # a dead thread can never finish it, so the slot is released for a fresh run
                if not running.get("thread") or not running["thread"].is_alive():
                    running["state"], running["finished_at"] = "failed", self.now().isoformat(timespec="seconds")
                    running["error"] = "preparation was interrupted (server restart) — run it again"
                    running = None
            if running and running["state"] == "running":
                raise ConflictError("The application is already being prepared")
            job = {"state": "running", "started_at": self.now().isoformat(timespec="seconds"), "finished_at": None,
                   "lanes": [], "running": [], "summary": None, "error": None}
            self._prep_jobs[application_id] = job
        actor = {"id": session["user"]["id"], "role": session["role"]}
        if wait:
            try:
                self._prepare(application_id, session, actor)
            except OperationFailedError:
                raise
            except Exception as e:                    # controlled: the job view carries the error
                with self._jobs_lock:
                    job["state"], job["finished_at"] = "failed", self.now().isoformat(timespec="seconds")
                    job["error"] = str(e) or e.__class__.__name__
                raise OperationFailedError(f"Preparation failed: {e}")
        else:
            # the lanes must never outlive the process: a worker that dies mid-prepare would
            # strand the job in 'running' and refuse every retry (ConflictError forever)
            def _guarded(*a_, **kw_):
                try:
                    self._prepare(*a_, **kw_)
                except Exception as e:
                    with self._jobs_lock:
                        j = self._prep_jobs.get(application_id)
                        if j and j.get("state") == "running":
                            j["state"], j["finished_at"] = "failed", self.now().isoformat(timespec="seconds")
                            j["error"] = str(e) or e.__class__.__name__
            job["thread"] = threading.Thread(target=_guarded, args=(application_id, session, actor), daemon=True,
                                              name=f"los-prepare-{application_id}")
            job["thread"].start()
            if wait:
                job["thread"].join(timeout=600)
        return self.sourcing(application_id, session)

    def wait_for_preparation(self, application_id: str, timeout: float = 600) -> dict:
        job = self._prep_jobs.get(application_id)
        if job and job.get("thread"):
            job["thread"].join(timeout=timeout)
        return {k: v for k, v in (job or {}).items() if k != "thread"}

    def _prepare(self, application_id: str, session: dict, actor: dict) -> None:
        step_id = self._require(application_id).get("step_id")
        if step_id in SOURCING_STEPS:
            return self._prepare_sourcing(application_id, session, actor)
        if step_id in later_intake.STAGES:
            return self._prepare_fulfilment(application_id, session, actor)
        return self._prepare_appraisal(application_id, session, actor)

    def _prepare_fulfilment(self, application_id: str, session: dict, actor: dict) -> None:
        """Post Sanction / Disbursement Maker: the intake agent reads the signed sanction letter and the
        facility agreement (or the drawdown request) and pre-fills the step's forms; at the Disbursement
        Maker the carry-forward agent (R-P3) proposes the operational record from the sanctioned record,
        in parallel."""
        job = self._prep_jobs[application_id]
        try:
            app = self._require(application_id)
            step_id, entity_id = app["step_id"], app["entity_id"]
            domain, specs = later_intake.STAGES[step_id]
            has_docs, carry = self._has_documents(entity_id), step_id == "dis_maker"
            if not has_docs and not carry:
                raise ConflictError("No documents are on file — upload the signed sanction letter, the facility "
                                    "agreement or the drawdown request")
            nodes = []
            if has_docs:
                llm = self._intake_llm()
                nodes.append(Node("intake", run=lambda ctx: intake.run_intake(self._entity_dir(entity_id), {}, llm,
                                                                              now=self.now(), specs=specs),
                                  description=f"document intake: {domain.replace('_', ' ')} documents"))
            if carry:
                nodes.append(Node("carry_forward", run=lambda ctx: self._carry_proposals(application_id),
                                  description="carry-forward agent: interest, repayment, fees and securities "
                                              "from the sanctioned record"))
            run = AgentGraph(nodes, name="fulfilment-prep",
                             on_start=lambda n, s: self._lane(job, n.name, "running", n.description),
                             on_result=lambda n, s, r: self._lane(job, n.name, r.status, n.description)).run({})
            prefill, carried = run.data("intake"), run.data("carry_forward")
            if has_docs and not prefill:
                raise RuntimeError(run.results["intake"].error or "Document intake failed")
            with self._app_lock(application_id):
                app = self._require(application_id)
                at = self.now().isoformat(timespec="seconds")
                merged, carry_summary = None, None
                if prefill:
                    app.setdefault("later_intake", {})[domain] = prefill
                    merged = self._merge_sourcing(app, prefill, at, domain)
                if carried:
                    fields = app.setdefault("fields", {})
                    carry_summary = fieldmodel.merge(fields, carried, self.field_registry, at)
                    carry_summary["workspaces"] = reconcile.materialise(app, fields, [p["field_id"] for p in carried])
                    carry_summary["proposals"] = len(carried)
                    carry_summary["filled"] = sum(1 for p in carried if p.get("provenance") != "unavailable")
                    app["field_reviews"] = fieldmodel.legacy_reviews(fields)
                summary = {"lanes": [{"lane": e["agent_name"], "status": e["status"], "ms": e["duration_ms"]}
                                     for e in run.log()], "duration_ms": run.duration_ms,
                           "max_concurrency": run.max_concurrency,
                           "prefill": prefill["summary"] if prefill else None, "fields": merged,
                           "carry_forward": carry_summary}
                parts = []
                if prefill:
                    parts.append(f"Agents read {prefill['intake']['documents']} document(s): {prefill['summary']['found']} "
                                 f"of {prefill['summary']['total']} {domain.replace('_', ' ')} fields found")
                if carry_summary:
                    parts.append(f"carried forward {carry_summary['filled']} of {carry_summary['proposals']} "
                                 "operational value(s) from the sanctioned record")
                linked_docs = self._link_documents(app, self.now().isoformat(timespec="seconds"))
                if linked_docs:
                    summary["documents_linked"] = linked_docs
                self.store.save(app, self._event(
                    app, "application_prepared", actor={**actor, "agent": "preparation"}, from_step=step_id,
                    to_step=step_id, detail=summary, comment="; ".join(parts)))
            job.update(state="done", summary=summary, finished_at=self.now().isoformat(timespec="seconds"))
        except Exception as e:                                       # recorded on the job; the maker can retry
            log.exception("Preparation failed for %s", application_id)
            job.update(state="failed", error=str(e), finished_at=self.now().isoformat(timespec="seconds"))

    def _carry_proposals(self, application_id: str) -> list[dict]:
        """The carry-forward agent's proposals for the Disbursement Maker (R-P3), critic-checked."""
        app = self._require(application_id)
        case, _ = self._app_case(app)
        ctx = {"app": app, "registry": self.field_registry, "fact_pack": (case or {}).get("fact_pack") or {},
               "run_id": (case or {}).get("run_id")}
        resolvers = {name: (lambda c, fn=fn: fn(ctx)) for name, fn in carry_forward.RESOLVERS.items()}
        return run_population(resolvers, self.field_registry)["proposals"]

    def _mirror_carry(self, app: dict, section: str, session: dict) -> None:
        """The maker saved a section the carry-forward agent filled (see ``_mirror_paths``)."""
        self._mirror_paths(app, ["disops", section], session, "in the disbursement record")

    def _mirror_paths(self, app: dict, prefix: list, session: dict, where: str) -> None:
        """A person saved a workspace section the agents fill: each value is recorded against the agent's
        proposal (same → confirmed, different → overridden), so a later run never overwrites it."""
        fields = app.get("fields") or {}
        by = {"id": session["user"]["id"], "name": session["user"]["name"]}
        at = self.now().isoformat(timespec="seconds")
        for rec in fields.values():
            prop = rec.get("proposal") or {}
            target = prop.get("target") or []
            if target[:len(prefix)] != prefix or rec.get("decision") or rec.get("status") == "unavailable":
                continue                # a person's entry where the agent had nothing is not a correction
            parent, leaf = reconcile._resolve_parent(app, target, create=False)
            value = parent.get(leaf) if isinstance(parent, dict) else None
            if value in (None, ""):
                continue
            a, b = str(prop.get("value")).replace(",", "").strip().lower(), str(value).replace(",", "").strip().lower()
            try:
                same = abs(float(a) - float(b)) < 1e-6
            except ValueError:
                same = a == b
            try:
                fieldmodel.apply_action(rec, "confirm" if same else "override", by=by, at=at,
                                        registry=self.field_registry, value=None if same else str(value),
                                        reason="" if same else f"Entered by {by['name']} {where}")
            except fieldmodel.FieldActionError:
                continue
        app["field_reviews"] = fieldmodel.legacy_reviews(fields)

    def _mirror_entries(self, app: dict, domain: str, entered: dict, session: dict, what: str) -> None:
        """A form the maker saved, recorded against the agent's proposals: unchanged → confirmed,
        different → overridden (with the form as the reason). Caller saves."""
        fields = app.get("fields") or {}
        by = {"id": session["user"]["id"], "name": session["user"]["name"]}
        at = self.now().isoformat(timespec="seconds")
        specs = {f["id"]: f for f in later_intake.STAGES_BY_DOMAIN[domain]}
        for fid, value in entered.items():
            rec = fields.get(intake.field_id(specs[fid], domain)) if fid in specs else None
            if rec is None or rec.get("decision") or value in (None, ""):
                continue
            if rec.get("status") == "unavailable":
                continue        # the agent proposed nothing: a person's entry is not a correction of the agent
            proposed = (rec.get("proposal") or {}).get("value")
            a, b = str(proposed).replace(",", "").strip().lower(), str(value).replace(",", "").strip().lower()
            try:
                same = abs(float(a) - float(b)) < 1e-6           # "20" and 20.0 are the same amount
            except ValueError:
                same = a == b
            try:
                fieldmodel.apply_action(rec, "confirm" if same else "override", by=by, at=at,
                                        registry=self.field_registry, value=None if same else str(value),
                                        reason="" if same else f"Entered by {by['name']} when {what}")
            except fieldmodel.FieldActionError:
                continue
        app["field_reviews"] = fieldmodel.legacy_reviews(fields)

    def _lane(self, job: dict, name: str, status: str, description: str = "") -> None:
        entry = next((x for x in job["lanes"] if x["lane"] == name), None)
        if entry is None:
            entry = {"lane": name, "description": description}
            job["lanes"].append(entry)
        entry["status"] = status
        job["running"] = [x["lane"] for x in job["lanes"] if x["status"] == "running"]

    def _prepare_appraisal(self, application_id: str, session: dict, actor: dict) -> None:
        """IP Note / AP note / Risk Maker: the credit case (run if this application has none pinned) and the
        API checks in parallel; then the Risk Maker fields and the reconciliation agents populate the
        workspaces (in parallel, single writer); at the IP Note step the note is drafted."""
        job = self._prep_jobs[application_id]
        try:
            app = self._require(application_id)
            entity_id, step_id = app["entity_id"], app["step_id"]
            company = self.companies.get(entity_id) or {}
            pinned = (self._app_case(app)[0] if (app.get("credit_assessment") or {}).get("run_id") else None)
            if pinned and self._case_stale(pinned, app):
                pinned = None           # the request changed since the CAM: assess this one (with the app's facility)
            check_ids = self._checks_to_refresh(app) if step_id in DD_STEPS else []

            def credit_case(ctx):
                if pinned:
                    return {"case": pinned, "ran": False}
                if not self.cases:
                    raise RuntimeError("The credit-intelligence engine is not connected")
                case, _ = self._run_case(entity_id, self._require(application_id))
                return {"case": case, "ran": True}

            nodes = [Node("credit_case", run=credit_case,
                          description="the credit case: the pinned run, or a new pipeline run")]
            if check_ids:
                nodes.append(Node("checks", fan_out=lambda ctx: check_ids,
                                  run_item=lambda ctx, cid: dd.run_api_check(cid, company),
                                  description=f"{len(check_ids)} API due-diligence checks"))
            graph = AgentGraph(nodes, name="appraisal-prep",
                               on_start=lambda n, s: self._lane(job, n.name, "running", n.description),
                               on_result=lambda n, s, r: self._lane(job, n.name, r.status, n.description))
            run = graph.run({})
            cc, checks = run.data("credit_case"), run.data("checks") or {}
            if not cc:
                raise RuntimeError((run.results.get("credit_case").error if run.results.get("credit_case") else None)
                                   or "No credit case")
            if cc["ran"]:
                self._record_assessment(application_id, cc["case"], actor)
            if checks:
                with self._app_lock(application_id):
                    app = self._require(application_id)
                    at = self.now().replace(microsecond=0)
                    for cid, result in checks.items():
                        self._dd_finish(app, self._dd_check(app, cid), session, at, result, "agent")
                    self.store.save(app, self._event(app, "checks_refreshed", actor={**actor, "agent": "preparation"},
                                                     from_step=step_id, to_step=step_id,
                                                     detail={cid: r["status"] for cid, r in checks.items()}))
            self._lane(job, "populate", "running", "Risk Maker fields + reconciliation agents per workspace")
            populated = self.populate_fields(application_id, {**actor, "agent": "reconciliation"}, force=True)
            self._lane(job, "populate", "completed")
            if step_id == IP_NOTE_STEP:
                self._lane(job, "ip_note", "running", "IP Note draft")
                self.generate_ip_note(application_id, session, with_ai=True)
                self._lane(job, "ip_note", "completed")
            summary = {"lanes": [{"lane": e["agent_name"], "status": e["status"], "ms": e["duration_ms"]}
                                 for e in run.log()],
                       "duration_ms": run.duration_ms, "max_concurrency": max(run.max_concurrency,
                                                                              (populated or {}).get("max_concurrency") or 0),
                       "credit_case_ran": cc["ran"], "run_id": cc["case"].get("run_id"),
                       "warnings": [cc["case"]["narrative_warning"]] if cc["case"].get("narrative_warning") else [],
                       "checks": {cid: r["status"] for cid, r in checks.items()}, "populated": populated}
            with self._app_lock(application_id):
                app = self._require(application_id)
                linked_docs = self._link_documents(app, self.now().isoformat(timespec="seconds"))
                if linked_docs:
                    summary["documents_linked"] = linked_docs
                self.store.save(app, self._event(
                    app, "application_prepared", actor={**actor, "agent": "preparation"}, from_step=step_id,
                    to_step=step_id, detail=summary,
                    comment=(("Ran the credit case; " if cc["ran"] else "Used the pinned credit case; ")
                             + f"{(populated or {}).get('new', 0)} new and {(populated or {}).get('updated', 0)} updated "
                             f"field(s); workspaces: {((populated or {}).get('workspaces') or {}).get('written', 0)} value(s) written"
                             + ("; IP Note drafted" if step_id == IP_NOTE_STEP else ""))))
            job.update(state="done", summary=summary, finished_at=self.now().isoformat(timespec="seconds"))
        except Exception as e:                                       # recorded on the job; the maker can retry
            log.exception("Preparation failed for %s", application_id)
            job.update(state="failed", error=str(e), finished_at=self.now().isoformat(timespec="seconds"))

    def _prepare_sourcing(self, application_id: str, session: dict, actor: dict) -> None:
        job = self._prep_jobs[application_id]
        try:
            app = self._require(application_id)
            entity_id = app["entity_id"]
            company = self.companies.get(entity_id) or {}
            check_ids = self._checks_to_refresh(app)
            has_docs = self._has_documents(entity_id)
            llm = self._intake_llm() if has_docs else None

            def lane(node: Node, status: str) -> None:
                entry = next((x for x in job["lanes"] if x["lane"] == node.name), None)
                if entry is None:
                    entry = {"lane": node.name, "description": node.description}
                    job["lanes"].append(entry)
                entry["status"] = status
                job["running"] = [x["lane"] for x in job["lanes"] if x["status"] == "running"]

            nodes = [
                Node("identity", run=lambda ctx: self.borrower_identity(entity_id, exclude_app=application_id),
                     description="identity, core-banking and LOS duplicate check"),
                Node("checks", fan_out=lambda ctx: check_ids, run_item=lambda ctx, cid: dd.run_api_check(cid, company),
                     description=f"{len(check_ids)} API due-diligence checks"),
            ]
            if has_docs:
                nodes.append(Node("intake", description="document intake agent",
                                  run=lambda ctx: intake.run_intake(self._entity_dir(entity_id),
                                                                    master_values(company, app), llm, now=self.now())))
            pinned = self._app_case(app)[0] if (app.get("credit_assessment") or {}).get("run_id") else None
            generate = bool(self.cases) and (
                ((app.get("cam_source") or {}).get("mode") == "generate" and not pinned)
                or bool(pinned and self._case_stale(pinned, app)))
            if generate:
                nodes.append(Node("credit_case", description="generate the CAM (credit-intelligence pipeline)",
                                  run=lambda ctx: self._run_case(entity_id, self._require(application_id))[0]))
            graph = AgentGraph(nodes, name="prospect-prep", on_start=lambda n, s: lane(n, "running"),
                               on_result=lambda n, s, r: lane(n, r.status))
            ctx: dict = {}
            run = graph.run(ctx)
            identity, checks, prefill = run.data("identity"), run.data("checks") or {}, run.data("intake")
            with self._app_lock(application_id):
                app = self._require(application_id)
                at = self.now().replace(microsecond=0)
                if identity:
                    app["customer_identity"] = identity
                for cid, result in checks.items():
                    c = self._dd_check(app, cid)
                    self._dd_finish(app, c, session, at, result, "agent")
                    if cid == "name_screening":
                        self._link_party_screening(app, result, session["user"]["name"], at.isoformat(timespec="seconds"))
                merged = None
                if prefill:
                    app.setdefault("sourcing", {})["prefill"] = prefill
                    merged = self._merge_sourcing(app, prefill, at.isoformat(timespec="seconds"))
                summary = {"lanes": [{"lane": e["agent_name"], "status": e["status"], "ms": e["duration_ms"]}
                                     for e in run.log()],
                           "duration_ms": run.duration_ms, "max_concurrency": run.max_concurrency,
                           "checks": {cid: r["status"] for cid, r in checks.items()},
                           "duplicates": len((identity or {}).get("los_duplicates", {}).get("matches") or []),
                           "prefill": (prefill or {}).get("summary"), "fields": merged}
                app["updated_at"] = at.isoformat(timespec="seconds")
                found = (prefill or {}).get("summary", {}).get("found")
                linked_docs = self._link_documents(app, self.now().isoformat(timespec="seconds"))
                if linked_docs:
                    summary["documents_linked"] = linked_docs
                self.store.save(app, self._event(
                    app, "application_prepared", actor={**actor, "agent": "preparation"}, from_step=app["step_id"],
                    to_step=app["step_id"], detail=summary,
                    comment=(f"Agents prepared the application in {run.duration_ms / 1000:.1f}s: "
                             f"{len(checks)} checks run" + (f", {found} fields read from documents" if prefill else ""))))
            if generate:                                  # the generated CAM is pinned and populates the IP fields
                case = run.data("credit_case")
                if not case:
                    err = run.results.get("credit_case")
                    raise RuntimeError(f"The CAM could not be generated: {getattr(err, 'error', None) or 'no result'}")
                self._record_assessment(application_id, case, {**actor, "agent": "cam"})
                summary["cam_generated"] = case.get("run_id")
                if case.get("narrative_warning"):
                    summary["warnings"] = [case["narrative_warning"]]
                summary["populated"] = self.populate_fields(application_id, {**actor, "agent": "cam"}, force=True)
            job.update(state="done", summary=summary, finished_at=self.now().isoformat(timespec="seconds"))
        except Exception as e:                                       # recorded on the job; the RM can retry
            log.exception("Preparation failed for %s", application_id)
            job.update(state="failed", error=str(e), finished_at=self.now().isoformat(timespec="seconds"))

    # ── governed due-diligence workspace (Client One GAP-P0-05/06) ──────────
    def _dd_may(self, app: dict, session: dict, what: str) -> None:
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in DD_STEPS or app["status"] in TERMINAL:
            raise ConflictError(f"{what} is done at the prospect-sourcing and risk-maker steps")
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step belongs to the {self._wf(app).roles[step.role]} role")
        if app.get("assignee_id") not in (None, session["user"]["id"]):
            raise ForbiddenError(f"Assigned to {self._user_name(app['assignee_id'])}; reassign it first")

    def due_diligence(self, application_id: str, session: Optional[dict] = None) -> dict:
        """The fifteen-check workspace: statuses, retrigger history, comments and exceptions."""
        app = self._require(application_id)
        prof = self._profile(app)
        rec = app.get("due_diligence") or {"version": dd.CHECK_VERSION, "checks": dd.initial_checks(self._check_catalog(app))}
        checks = rec["checks"]
        validity = (prof.get("checks") or {}).get("validity_days") or {}
        # R5: per-check applicability (profile/product conditions) and validity — a check that
        # does not apply is waived; a result past its validity must be re-run
        applicability = []
        for c in checks:
            conds = (prof.get("checks") or {}).get("applicability", {}).get(c["id"]) or {}
            applies, reason = dd.check_applies(conds, app)
            expires = dd.valid_expiry(c, self.now(), int(validity[c["id"]])) if (applies and validity.get(c["id"])) else None
            applicability.append({"id": c["id"], "name": c["name"], "applies": applies, "reason": reason,
                                  "validity_days": validity.get(c["id"]), "expires_at": expires,
                                  "expired": bool(expires and self.now().date().isoformat() >= expires)})
        effective = [c for c, a in zip(checks, applicability) if a["applies"]]
        return {"application_id": application_id, "version": rec.get("version"),
                "initiated_at": rec.get("initiated_at"), "seeded": bool(rec.get("seeded")),
                "can_edit": self._can(app, session, DD_STEPS),
                "checks": checks, "summary": dd.summary(effective, self.now()),
                "applicability": applicability,
                "blocking": [c["name"] for c in dd.blocking(effective, now=self.now(),
                                                            validity_days={k: int(v) for k, v in validity.items()})],
                "screening": dd.screening_review(checks, self.now(), profiles.check_policy(prof)),
                "note": "API checks run against the in-app record and demo services (results are labelled); "
                        "manual checks are recorded by the analyst. An 'unavailable' result means the provider "
                        "returned nothing — it is never a clear result. Checks the profile's applicability "
                        "conditions waive do not block."}

    def _dd_check(self, app: dict, check_id: str) -> dict:
        checks = app.setdefault("due_diligence", {"version": dd.CHECK_VERSION, "checks": dd.initial_checks(self._check_catalog(app))})["checks"]
        c = next((x for x in checks if x["id"] == check_id), None)
        if not c:
            raise InvalidRequestError(f"Unknown due-diligence check: {check_id}")
        return c

    def _dd_finish(self, app: dict, c: dict, session: dict, at: datetime, result: dict, trigger: str) -> None:
        c["history"].append({"at": at.isoformat(timespec="seconds"), "by": session["user"]["id"],
                             "by_name": session["user"]["name"], "trigger": trigger,
                             "previous_status": c["status"], **{k: result[k] for k in ("status", "detail", "source", "error")}})
        # Re-running a check invalidates any previously approved exception: the exception covered the
        # previous result, so the new result must be reviewed again (UAT-P0-2).
        if c.get("exception"):
            c.setdefault("exception_history", []).append({**c["exception"], "invalidated_at": at.isoformat(timespec="seconds"),
                                                          "invalidated_by": session["user"]["name"],
                                                          "reason": f"check re-triggered ({trigger}) — the approved exception "
                                                                    "covered the previous result only"})
            c["exception"] = None
        c.update(status=result["status"], detail=result["detail"], source=result["source"],
                 error=result.get("error"), last_triggered=at.isoformat(timespec="seconds"),
                 triggered_by=session["user"]["name"])
        if result.get("grid") is not None:
            c["grid"] = result["grid"]

    def trigger_check(self, application_id: str, session: dict, check_id: str) -> dict:
        """Run (or re-run) an API-mode check. The previous result is preserved in the check's history."""
        app = self._require(application_id)
        self._dd_may(app, session, "Triggering due-diligence checks")
        spec = dd.CHECK_IDS.get(check_id)
        if not spec or spec["mode"] != "api":
            raise InvalidRequestError(f"{spec['name'] if spec else check_id} is recorded manually, not triggered")
        self._dd_check(app, check_id)
        self._apply_check(application_id, session, check_id,
                          dd.run_api_check(check_id, self.companies.get(app["entity_id"]) or {}))
        return self.due_diligence(application_id, session)

    def _apply_check(self, application_id: str, session: dict, check_id: str, result: dict) -> None:
        """Record one API check result with its audit event (single writer)."""
        spec = dd.CHECK_IDS[check_id]
        with self._app_lock(application_id):
            app = self._require(application_id)
            c = self._dd_check(app, check_id)
            at = self.now().replace(microsecond=0)
            self._apply_check_locked(app, c, session, at, spec, check_id, result)

    def _apply_check_locked(self, app, c, session, at, spec, check_id, result) -> None:
        self._dd_finish(app, c, session, at, result, "api")
        if check_id == "name_screening":
            # UAT-P0-3: the application-level screening auto-links the individuals' party evidence.
            self._link_party_screening(app, result, session["user"]["name"],
                                       at.isoformat(timespec="seconds"))
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_trigger", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"{spec['name']}: {result['status']} (was {c['history'][-1]['previous_status']})",
                                         detail={"check_id": check_id, "source": result["source"], "error": result.get("error")}))

    # entity-level prospect fields (UAT-P1-4/5): incorporated flag and latest material information date
    def save_entity_flags(self, application_id: str, session: dict, payload: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Entity maintenance")
        ent = app.setdefault("entity", {})
        changed = []
        if "entity_incorporated" in payload:
            flag = bool(payload["entity_incorporated"])
            if ent.get("entity_incorporated") != flag:
                ent["entity_incorporated"] = flag
                ent["entity_incorporated_by"] = session["user"]["name"]
                changed.append("entity_incorporated")
        if "latest_material_information_date" in payload:
            raw = str(payload["latest_material_information_date"] or "").strip()
            if raw:
                try:
                    d = datetime.strptime(raw, "%Y-%m-%d").date()
                except ValueError:
                    raise InvalidRequestError("latest_material_information_date must be a date (YYYY-MM-DD)")
                if d > self.now().date():
                    raise InvalidRequestError("The latest material information date cannot be in the future")
            else:
                d = None
            if ent.get("latest_material_information_date") != (d.isoformat() if d else None):
                ent["latest_material_information_date"] = d.isoformat() if d else None
                ent["latest_material_information_by"] = session["user"]["name"]
                changed.append("latest_material_information_date")
        if not changed:
            raise InvalidRequestError("Nothing to update")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "entity_updated", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment="Entity: " + ", ".join(changed),
                                         detail={"changed": changed, "at": at}))
        return self.get(application_id, session)
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_trigger", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"{spec['name']}: {result['status']} (was {c['history'][-1]['previous_status']})",
                                         detail={"check_id": check_id, "source": result["source"], "error": result.get("error")}))
        return self.due_diligence(application_id, session)

    def _checks_to_refresh(self, app: dict) -> list[str]:
        """The API checks a preparation agent runs: those still needing a result. A clear result (not due
        for re-screening) or a match / failure released by a valid Compliance VP exception is a settled
        outcome; re-running it would void the exception (UAT-P0-2), so the agent leaves it alone."""
        now, out = self.now(), []
        for c in app["due_diligence"]["checks"]:
            if c["mode"] != "api":
                continue
            rescreen = dd.rescreen_state(c, now) if c["status"] == "clear" else None
            settled = (c["status"] == "clear" and not (rescreen and rescreen["state"] == "overdue")) or \
                (c["status"] in ("matched", "failed", "unavailable") and bool(dd.effective_exception(c, now)))
            if not settled:
                out.append(c["id"])
        return out

    def run_due_diligence(self, application_id: str, session: dict) -> dict:
        """Run every API check that still needs a result. A settled check — clear (not due for re-screening),
        or a match / failure released by a valid Compliance VP exception — is left alone: re-running it would
        void the exception and send it back to the Compliance VP."""
        app = self._require(application_id)
        self._dd_may(app, session, "Running the due-diligence checks")
        ids = self._checks_to_refresh(app)
        if not ids:
            raise ConflictError("Every API check is settled (clear, or released by a Compliance VP exception) — "
                                "re-run a single check only if its underlying record changed")
        # The providers are called in parallel (one lane per check); results are applied one by one,
        # each with its own audit event, exactly as a single trigger would.
        company = self.companies.get(app["entity_id"]) or {}
        run = AgentGraph([Node("checks", fan_out=lambda ctx: ids,
                               run_item=lambda ctx, cid: dd.run_api_check(cid, company))], name="dd-checks").run({})
        results = run.data("checks") or {}
        for cid in ids:
            if cid in results:
                self._apply_check(application_id, session, cid, results[cid])
        return self.due_diligence(application_id)

    def record_check(self, application_id: str, session: dict, check_id: str, result: str, remarks: str = "") -> dict:
        """Record a manual check (or re-record it). A non-clear result needs a remark (reason)."""
        app = self._require(application_id)
        self._dd_may(app, session, "Recording due-diligence checks")
        spec = dd.CHECK_IDS.get(check_id)
        if not spec or spec["mode"] != "manual":
            raise InvalidRequestError(f"{spec['name'] if spec else check_id} is an API check — trigger it instead")
        if result not in dd.MANUAL_RESULTS:
            raise InvalidRequestError(f"Result must be one of {', '.join(dd.MANUAL_RESULTS)}")
        if result != "clear" and not (remarks or "").strip():
            raise InvalidRequestError("A remark (reason) is required for a matched or failed result")
        c = self._dd_check(app, check_id)
        at = self.now().replace(microsecond=0)
        self._dd_finish(app, c, session, at,
                        {"status": result, "detail": (remarks or "").strip() or None,
                         "source": "Manually recorded" + (" (demo)" if spec["id"] in ("crilc", "cfr", "ceib") else ""),
                         "error": None}, "manual")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_record", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"{spec['name']}: {result}" + (f" — {remarks.strip()}" if remarks else ""),
                                         detail={"check_id": check_id, "previous_status": c["history"][-1]["previous_status"]}))
        return self.due_diligence(application_id, session)

    def comment_check(self, application_id: str, session: dict, check_id: str, text: str) -> dict:
        app = self._require(application_id)
        self._dd_may(app, session, "Commenting on due-diligence checks")
        c = self._dd_check(app, check_id)
        if not (text or "").strip():
            raise InvalidRequestError("Enter a comment")
        c["comments"].append({"by_name": session["user"]["name"], "at": self.now().isoformat(timespec="seconds"),
                              "text": text.strip()[:500]})
        # Persist: comments are part of the check record and must survive a reload (UAT-P0-1).
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_comment", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"{dd.CHECK_IDS[check_id]['name']}: {text.strip()[:120]}",
                                         detail={"check_id": check_id}))
        return self.due_diligence(application_id, session)

    def _approvers(self, role: Optional[str] = None, wf: Optional[Workflow] = None) -> list[dict]:
        wf = wf or self.wf
        role = role or profiles.exception_authority()["role"]
        return [{"id": u["id"], "name": u["name"], "email": u.get("email"), "branch": u.get("branch")}
                for u in wf.users_with_role(role)]

    @staticmethod
    def _who(people: list[dict]) -> str:
        return ", ".join(f"{p['name']} ({p['email']})" if p.get("email") else p["name"] for p in people)

    def request_exception(self, application_id: str, session: dict, check_id: str, note: str,
                          to: Optional[str] = None) -> dict:
        """The step holder asks the Compliance VP for an exception on a check only that authority can release
        (a match / failure, or a mandatory 'unavailable'). The request is in the Compliance VP's queue."""
        app = self._require(application_id)
        self._dd_may(app, session, "Requesting a Compliance VP exception")
        if not (note or "").strip():
            raise InvalidRequestError("Say why an exception is justified (the Compliance VP decides on it)")
        c = self._dd_check(app, check_id)
        if c["status"] not in ("matched", "failed", "unavailable"):
            raise ConflictError(f"{c['name']} is {c['status']} — an exception applies to a match, a failure or "
                                "an unavailable result")
        if dd.effective_exception(c, self.now()):
            raise ConflictError(f"{c['name']} already has a Compliance VP exception")
        at = self.now().isoformat(timespec="seconds")
        approvers = self._approvers(self._exc_authority(app)["role"], self._wf(app))
        target = next((p for p in approvers if p["id"] == to), None) if to else (approvers[0] if len(approvers) == 1 else None)
        if to and not target:
            raise InvalidRequestError("Choose a Compliance VP from the list")
        c["exception_request"] = {"status": "pending", "by": session["user"]["id"], "by_name": session["user"]["name"],
                                  "at": at, "note": note.strip(),
                                  "to_id": (target or {}).get("id"), "to_name": (target or {}).get("name"),
                                  "to_email": (target or {}).get("email")}
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_exception_requested", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment=f"Exception requested for {c['name']}: {note.strip()}",
                                         detail={"check_id": check_id, "status": c["status"]}))
        return self.due_diligence(application_id, session)

    def decline_exception(self, application_id: str, session: dict, check_id: str, reason: str) -> dict:
        app = self._require(application_id)
        exc = self._exc_authority(app)
        if session["role"] != exc["role"]:
            raise ForbiddenError(f"Only the {exc['name']} decides on a due-diligence exception")
        if not (reason or "").strip():
            raise InvalidRequestError("Give the reason for declining — the step holder sees it")
        c = self._dd_check(app, check_id)
        req = c.get("exception_request") or {}
        if req.get("status") != "pending":
            raise ConflictError(f"There is no pending exception request on {c['name']}")
        req.update(status="declined", decided_by=session["user"]["name"], decided_at=self.now().isoformat(timespec="seconds"),
                   decision_note=reason.strip())
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_exception_declined", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment=f"Exception declined for {c['name']}: {reason.strip()}",
                                         detail={"check_id": check_id}))
        return self.due_diligence(application_id, session)

    def exception_check(self, application_id: str, session: dict, check_id: str, reason: str) -> dict:
        """The only thing that releases a mandatory match/failure block: a recorded Compliance VP exception.
        Under the ``vp_approval`` unavailable policy the same authority also releases a mandatory check
        whose provider returned nothing ('unavailable') — never a silent skip."""
        app = self._require(application_id)
        exc = self._exc_authority(app)
        if session["role"] != exc["role"]:
            raise ForbiddenError(f"Only the {exc['name']} can approve a due-diligence exception")
        if not (reason or "").strip():
            raise InvalidRequestError("A reason is required for an exception")
        c = self._dd_check(app, check_id)
        if c["status"] not in ("matched", "failed", "unavailable"):
            raise ConflictError(f"An exception applies to a matched, failed or unavailable check, not one that is {c['status']}")
        c["exception"] = {"by": session["user"]["id"], "by_name": session["user"]["name"],
                          "at": self.now().isoformat(timespec="seconds"), "reason": reason.strip(),
                          "expires_at": dd.exception_expiry(self.now().isoformat(timespec="seconds"),
                                                            ttl_days=profiles.check_policy(self._profile(app))["exception_ttl_days"])}
        if (c.get("exception_request") or {}).get("status") == "pending":
            c["exception_request"].update(status="approved", decided_by=session["user"]["name"],
                                          decided_at=self.now().isoformat(timespec="seconds"), decision_note=reason.strip())
        # Time-based expiry note: the exception lapses 90 days after it is granted (UAT-P0-2).
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_exception", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"Exception approved for {dd.CHECK_IDS[check_id]['name']}: {reason.strip()}",
                                         detail={"check_id": check_id, "status": c["status"]}))
        return self.due_diligence(application_id, session)

    # per-check evidence upload + detailed grids (UAT-P1-8)
    def add_check_evidence(self, application_id: str, session: dict, check_id: str, name: str, note: str = "") -> dict:
        app = self._require(application_id)
        self._dd_may(app, session, "Attaching evidence to due-diligence checks")
        c = self._dd_check(app, check_id)
        name = str(name or "").strip()
        if not name:
            raise InvalidRequestError("Enter the evidence reference (document name / report ID)")
        if len(c.setdefault("evidence", [])) >= 25:
            raise InvalidRequestError("At most 25 evidence references per check")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        c["evidence"].append({"name": name[:300], "note": (str(note or "").strip()[:300] or None),
                              "by_name": session["user"]["name"], "at": at})
        # also register it in the document registry so the evidence is visible and attributable
        dreg.register_generated(app.setdefault("documents", []), name=name, kind="check_evidence",
                                by_name=session["user"]["name"], at=at, detail=f"evidence for {check_id}")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_evidence", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"{dd.CHECK_IDS[check_id]['name']}: evidence '{name}'",
                                         detail={"check_id": check_id, "evidence": name}))
        return self.due_diligence(application_id, session)

    def save_check_grid(self, application_id: str, session: dict, check_id: str, rows: list) -> dict:
        """Record the detailed grid for a manual check that has one (currently UDIN)."""
        app = self._require(application_id)
        self._dd_may(app, session, "Recording the check grid")
        if check_id != "udin":
            raise InvalidRequestError(f"{dd.CHECK_IDS[check_id]['name']} has no manual grid — record its result instead")
        normalised = []
        for i, raw in enumerate(rows or [], 1):
            doc = str((raw or {}).get("document") or "").strip()
            code = str((raw or {}).get("udin_code") or "").strip()
            status = str((raw or {}).get("status") or "").strip()
            if not doc or not code:
                raise InvalidRequestError(f"UDIN row {i}: document and UDIN code are required")
            if status not in dd.UDIN_STATUSES:
                raise InvalidRequestError(f"UDIN row {i}: status must be one of {', '.join(dd.UDIN_STATUSES)}")
            normalised.append({"document": doc[:300], "udin_code": code[:40], "status": status,
                               "by_name": session["user"]["name"],
                               "at": self.now().isoformat(timespec="seconds")})
        c = self._dd_check(app, check_id)
        c["grid"] = normalised
        # reflect the grid in the check result: all verified -> clear, any not_verified -> matched, else pending
        if normalised and all(r["status"] == "verified" for r in normalised):
            if c["status"] != "clear":
                c.update(status="clear", detail=f"{len(normalised)} professional document(s) verified via UDIN (demo)",
                         source="UDIN (demo — recorded manually)", error=None,
                         last_triggered=self.now().isoformat(timespec="seconds"), triggered_by=session["user"]["name"])
        elif any(r["status"] == "not_verified" for r in normalised):
            c.update(status="matched", detail="One or more professional documents are not verified via UDIN (demo)",
                     source="UDIN (demo — recorded manually)", error=None,
                     last_triggered=self.now().isoformat(timespec="seconds"), triggered_by=session["user"]["name"])
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_grid", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"UDIN grid recorded: {len(normalised)} row(s)",
                                         detail={"check_id": check_id, "rows": len(normalised)}))
        return self.due_diligence(application_id, session)

    def _seed_due_diligence(self, application_id: str, at: datetime) -> None:
        """Seeded history: the checks were run and recorded before the replay point."""
        app = self.store.get(application_id)
        rec = app.setdefault("due_diligence", {"version": dd.CHECK_VERSION, "checks": dd.initial_checks(self._check_catalog(app))})
        company = self.companies.get(app["entity_id"]) or {}
        for c in rec["checks"]:
            if c["mode"] == "api":
                result = dd.run_api_check(c["id"], company)
            else:
                result = {"status": "clear", "detail": "Recorded (seeded demo history)",
                          "source": "Manually recorded", "error": None}
            c.update(status=result["status"], detail=result["detail"], source=result["source"], error=None,
                     last_triggered=at.isoformat(timespec="seconds"), triggered_by="Demo seed",
                     exception={"by_name": "Compliance VP (demo seed)", "at": at.isoformat(timespec="seconds"),
                                "reason": "Seeded demo history"}
                               if result["status"] in ("matched", "failed", "unavailable") else None)
        rec["seeded"] = True
        self.store.save(app)

    # ── IP Note ──────────────────────────────────────────────────────────────
    def ip_note(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        stored = app.get("ip_note")
        note = stored or build_ip_note(app, self.companies.get(app["entity_id"]), now=self.now())
        return {"application_id": application_id, "generated": bool(stored), "preview": not stored,
                "can_generate": self._can(app, session, (IP_NOTE_STEP,)),
                "at_ip_note": app.get("step_id") == IP_NOTE_STEP, "note": note,
                "assignments": app.get("ip_assignments") or {},
                "crac_vocabulary": self.CRAC_VOCABULARY}

    def generate_ip_note(self, application_id: str, session: dict, with_ai: bool = True) -> dict:
        app = self._require(application_id)
        self._maker_at(app, session, (IP_NOTE_STEP,), "The IP Note")
        note = build_ip_note(app, self.companies.get(app["entity_id"]), now=self.now())
        note["ai_status"] = "not requested"
        if with_ai and self.llm_factory:
            llm = self.llm_factory()
            if getattr(llm, "name", "") == "mock":
                note["ai_status"] = "skipped — the active LLM provider is 'mock'"
            else:
                try:
                    note["ai_summary"] = summarise(note, llm)
                    note["ai_status"] = "ok"
                except Exception as e:                              # the deterministic note stands
                    note["ai_status"] = f"rejected: {e}"
        note["prepared_by"] = session["user"]["name"]
        app = self._require(application_id)
        app["ip_note"] = note
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "ip_note", actor=actor, from_step=app["step_id"], to_step=app["step_id"],
                                         comment=f"IP Note generated — {note['prescreen']['outcome']}",
                                         detail={"ai_status": note["ai_status"],
                                                 "breaches": note["prescreen"]["breaches"]}))
        return self.ip_note(application_id, session)

    def ip_note_html(self, application_id: str) -> str:
        return render_html(self.ip_note(application_id)["note"])

    # LPFG analyst assignments + CRAC vocabulary (UAT-P1-6)
    CRAC_VOCABULARY = ("Recommend sanction", "Recommend sanction with conditions",
                       "Recommend for modification", "Recommend decline", "Defer")

    def save_ip_assignments(self, application_id: str, session: dict, payload: dict) -> dict:
        """Explicit LPFG Analyst / Senior Analyst assignments and the CRAC recommendation
        (a labelled demo vocabulary — the client's exact committee labels are confirmation-required)."""
        app = self._require(application_id)
        self._workspace_may(app, session, "IP Note assignments")
        a = app.setdefault("ip_assignments", {})
        changed = []
        for key, label in (("lpfg_analyst", "LPFG Analyst"), ("lpfg_senior_analyst", "LPFG Senior Analyst")):
            if key in payload:
                name = str(payload[key] or "").strip()
                if name and a.get(key) != name:
                    a[key] = name[:120]; a[key + "_at"] = self.now().isoformat(timespec="seconds")
                    changed.append(label)
        if "crac_recommendation" in payload:
            rec = str(payload["crac_recommendation"] or "").strip()
            if rec and rec not in self.CRAC_VOCABULARY:
                raise InvalidRequestError(f"CRAC recommendation must be one of {', '.join(self.CRAC_VOCABULARY)}")
            if rec:
                remarks = str(payload.get("crac_remarks") or "").strip()
                if rec in ("Recommend for modification", "Recommend decline", "Defer") and not remarks:
                    raise InvalidRequestError(f"A remark is required for the CRAC recommendation '{rec}'")
                a["crac_recommendation"] = rec
                a["crac_remarks"] = remarks or None
                a["crac_by"] = session["user"]["name"]
                a["crac_at"] = self.now().isoformat(timespec="seconds")
                changed.append("CRAC recommendation")
        if not changed:
            raise InvalidRequestError("Nothing to update")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "ip_assignments", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment="IP assignments: " + ", ".join(changed),
                                         detail={"changed": changed, "assignments": a}))
        return self.ip_note(application_id, session)

    # ── post sanction & disbursement ─────────────────────────────────────────
    def _disbursement(self, app: dict) -> dict:
        summary = condition_summary(app.get("conditions") or [], self.now().date().isoformat())
        return build_disbursement(app, summary, bool(app.get("pos_approved")))

    def post_sanction(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        today = self.now().date().isoformat()
        conditions = [dict(c, state=condition_state(c, today)) for c in app.get("conditions") or []]
        case = None
        if app.get("sanctions") and self.cases and self.cases.get(app["entity_id"]):
            case, _ = self._app_case(app)
        stage = app.get("stage_id")
        return {"application_id": application_id,
                "visible": bool(app.get("sanctions")),
                "at_post_sanction": stage in ("POS", "DIS") or app["status"] == STATUS_APPROVED,
                "consent": app.get("consent"),
                # What the intake agent read from the signed sanction letter, the facility agreement and the
                # drawdown request: it pre-fills the forms; saving the form verifies it.
                "suggested": {domain: later_intake.values((app.get("later_intake") or {}).get(domain))
                              for domain in later_intake.STAGES_BY_DOMAIN},
                "intake": {domain: (pf or {}).get("intake") for domain, pf in (app.get("later_intake") or {}).items()},
                "conditions": conditions, "condition_summary": condition_summary(app.get("conditions") or [], today),
                "covenant_summary": covenant_summary(app.get("conditions") or [], today),
                "can_update_conditions": self._can(app, session, CONDITION_STEPS),
                "deviations": build_deviations(app, case, committee_deviations(case) + manual_deviations(app)),
                "comparison": build_comparison(app),
                "disops": do.disops_view(app) | {"maker_gate": do.maker_gate(app)},
                "securities": app.get("securities") or [],
                "security_cover": sec.cover_ratio(app.get("securities") or [],
                                                  (app.get("sanctions") or {}).get("AP", {}).get("sanctioned_cr")
                                                  or app.get("amount_cr")),
                "documents": dreg.registry_view(app),
                "material_changes": snap.material_changes(app) if app.get("snapshots") else [],
                "material_change_gate": snap.material_change_gate(app) if app.get("snapshots") else None,
                "disbursement": self._disbursement(app) | {
                    "visible": stage == "DIS" or bool((app.get("disbursement") or {}).get("tranches")),
                    "can_edit": self._can(app, session, ("dis_maker",)),
                    "settlement_note": "Tranche status reflects workflow approval (authorisation to release). "
                                       "Payment execution and reconciliation with core banking are outside the LOS."}}

    def update_conditions(self, application_id: str, session: dict, updates: list[dict]) -> dict:
        """Satisfy (with evidence or a note), defer (new due date + reason), waive (reason) or reopen conditions.
        Deferrals and waivers wait for the Post Sanction Checker's approval."""
        app = self._require(application_id)
        self._maker_at(app, session, CONDITION_STEPS, "Updating conditions")
        by_id = {c["id"]: c for c in app.get("conditions") or []}
        today = self.now().date().isoformat()
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        changes = []
        for u in updates or []:
            c = by_id.get(u.get("id"))
            if not c:
                raise InvalidRequestError(f"Unknown condition: {u.get('id')}")
            status = u.get("status")
            if status not in CONDITION_STATUSES:
                raise InvalidRequestError(f"Unknown condition status: {status}")
            note, evidence = (u.get("note") or "").strip() or None, (u.get("evidence") or "").strip() or None
            if status == "non_compliant" and not note:
                raise InvalidRequestError(f"{c['id']}: a reason for non-compliance and remarks are required")
            if status == "satisfied" and not (note or evidence):
                raise InvalidRequestError(f"{c['id']}: record the evidence or a note to satisfy it")
            if status in ("deferred", "waived") and not note:
                raise InvalidRequestError(f"{c['id']}: a reason is required to {status[:-1]} a condition")
            # facility / party / category / stipulated value / frequency (GAP-P0-14)
            for key in ("facility_id", "party", "category", "stipulated_value", "frequency", "existing"):
                if key in u and u[key] is not None:
                    c[key] = u[key]
            due = c.get("due")
            if status == "deferred":
                due = (u.get("due") or "").strip()
                try:
                    datetime.fromisoformat(due)
                except ValueError:
                    raise InvalidRequestError(f"{c['id']}: a new due date (YYYY-MM-DD) is required to defer it")
                if due <= today:
                    raise InvalidRequestError(f"{c['id']}: the new due date must be after today")
            c["history"].append({"from": c["status"], "to": status, "note": note, "by_name": session["user"]["name"],
                                 "at": at})
            c.update(status=status, note=note, evidence=evidence, due=due, updated_by=session["user"]["name"],
                     updated_at=at, approval=None)
            # R10: owner, due date, testing frequency and the waiver authority / expiry
            if "owner" in u and u["owner"] is not None:
                c["owner"] = str(u["owner"]).strip() or None
            if "frequency" in u and u["frequency"] is not None:
                c["frequency"] = str(u["frequency"]).strip() or None
            if status == "waived":
                wa = u.get("waiver") or {}
                prof = self._profile(app).get("waiver") or {}
                authority = str(wa.get("authority") or prof.get("default_authority") or "Post Sanction Checker").strip()
                max_days = int(prof.get("max_days") or 0)
                expiry = None
                if max_days:
                    try:
                        base = datetime.fromisoformat(str(wa.get("until") or "")).date() if wa.get("until") else self.now().date()
                    except ValueError:
                        base = self.now().date()
                    expiry = (base + timedelta(days=max_days)).isoformat()
                c["waiver"] = {"authority": authority, "reason": note,
                               "by_name": session["user"]["name"], "at": at,
                               "expires_at": expiry, "status": "granted"}
            elif status != "waived" and c.get("waiver"):
                c["waiver"] = {**c["waiver"], "status": "superseded"}
            changes.append(f"{c['id']} → {status}" + (f" ({note})" if note else ""))
        if not changes:
            raise InvalidRequestError("Nothing to update")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "conditions_update", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment="; ".join(changes)[:600]))
        return self.post_sanction(application_id, session)

    def record_covenant(self, application_id: str, session: dict, condition_id: str,
                        action: str, result: str = "", remarks: str = "") -> dict:
        """Recurring covenant monitoring (UAT-P2-11): test a covenant (pass/fail) or record an
        explicit cure of a breached one. A failed test makes the condition non-compliant; a
        passing test after a breach records the cure; the next due date follows the frequency."""
        app = self._require(application_id)
        self._maker_at(app, session, CONDITION_STEPS, "Covenant monitoring")
        c = next((x for x in app.get("conditions") or [] if x["id"] == condition_id), None)
        if not c:
            raise InvalidRequestError(f"Unknown condition: {condition_id}")
        if c.get("type") not in ("FC", "NC", "CS", "PD"):
            raise InvalidRequestError(f"{condition_id} is not a monitored covenant (FC/NC/CS/PD)")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        try:
            if action == "test":
                record_covenant_test(c, at, result, session["user"]["name"], remarks)
            elif action == "cure":
                record_covenant_cure(c, at, session["user"]["name"], remarks)
            else:
                raise InvalidRequestError("action must be 'test' or 'cure'")
        except ValueError as e:
            raise InvalidRequestError(str(e))
        actor = {"id": session["user"]["id"], "role": session["role"]}
        verb = f"tested {'pass' if result == 'pass' else 'fail'}" if action == "test" else "cured"
        self.store.save(app, self._event(app, "covenant_monitor", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"{condition_id} covenant {verb}",
                                         detail={"condition_id": condition_id, "action": action,
                                                 "result": result or None, "remarks": (remarks or "").strip() or None}))
        return self.post_sanction(application_id, session)

    def update_checklist(self, application_id: str, session: dict, items: list[dict]) -> dict:
        app = self._require(application_id)
        self._maker_at(app, session, ("dis_maker",), "The disbursement checklist")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        checklist = app.setdefault("disbursement", {}).setdefault("checklist", {})
        changes = []
        for i in items or []:
            if i.get("id") not in MANUAL_ITEMS:
                raise InvalidRequestError(f"{i.get('id')} is checked by the system, not confirmed manually")
            checklist[i["id"]] = {"done": bool(i.get("done")), "note": (i.get("note") or "").strip() or None,
                                  "by": session["user"]["id"], "by_name": session["user"]["name"], "at": at}
            changes.append(f"{i['id']}: {'confirmed' if i.get('done') else 'unchecked'}")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "checklist_update", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment="; ".join(changes)))
        return self.post_sanction(application_id, session)

    def _open_modification_blocker(self, app: dict):
        mod = next((m for m in app.get("modifications") or [] if m["status"] == "open"), None)
        if mod:
            return (f"Modification {mod['modification_id']} is open — the sanctioned terms stay in force "
                    "until it is recommended and decided")
        return None

    def request_tranche(self, application_id: str, session: dict, amount_cr: float, value_date: str,
                        purpose: str = "", facility_id: Optional[str] = None) -> dict:
        app = self._require(application_id)
        if b := self._open_modification_blocker(app):
            raise ConflictError(b)
        self._maker_at(app, session, ("dis_maker",), "Recording a tranche")
        dis = self._disbursement(app)
        if dis["available_cr"] is None:
            raise ConflictError("No sanctioned limit is recorded for this application")
        try:
            amount = float(amount_cr)
            datetime.fromisoformat(value_date or "")
        except (TypeError, ValueError):
            raise InvalidRequestError("A tranche needs an amount and a value date (YYYY-MM-DD)")
        if amount <= 0 or amount > dis["available_cr"] + 1e-6:
            raise InvalidRequestError(f"The tranche must be greater than zero and within the undisbursed limit of "
                                      f"₹{dis['available_cr']:,.2f} Cr")
        tranches = app.setdefault("disbursement", {}).setdefault("tranches", [])
        tranches[:] = [t for t in tranches if t["status"] not in ("requested", "verified")]     # replaces a pending one
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        facmod.allocate_tranche(app.get("facilities") or [], facility_id, amount, at)
        tranches.append({"no": len(tranches) + 1, "amount_cr": round(amount, 2), "facility_id": facility_id,
                         "value_date": value_date,
                         "purpose": (purpose or "").strip() or None, "status": "requested",
                         "requested": {"by": session["user"]["id"], "by_name": session["user"]["name"], "at": at}})
        self._mirror_entries(app, "disbursement", {"drawdown_amount_cr": round(amount, 2), "value_date": value_date,
                                                   "drawdown_purpose": (purpose or "").strip() or None},
                             session, "recording the tranche")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "tranche_request", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"Tranche {len(tranches)}: ₹{amount:,.2f} Cr value {value_date}"))
        return self.post_sanction(application_id, session)

    # repeat-tranche re-entry after Exit (UAT-P2-12): only where the demonstration must show
    # multiple drawdowns. A governed, audited re-open at the Disbursement Maker.
    def request_subsequent_tranche(self, application_id: str, session: dict, reason: str) -> dict:
        app = self._require(application_id)
        if b := self._open_modification_blocker(app):
            raise ConflictError(b)
        if app["status"] != STATUS_APPROVED:
            raise ConflictError("A subsequent tranche can only be requested after the application has reached Exit (approved)")
        if not (reason or "").strip():
            raise InvalidRequestError("A reason is required to request a subsequent tranche")
        tranches = (app.get("disbursement") or {}).get("tranches") or []
        if not any(t.get("status") == "approved" for t in tranches):
            raise ConflictError("There is no approved tranche to follow up")
        at = self.now().replace(microsecond=0)
        app["tranche_rounds"] = app.get("tranche_rounds", 1) + 1
        app.setdefault("subsequent_tranches", []).append(
            {"round": app["tranche_rounds"], "reason": reason.strip()[:500],
             "by_name": session["user"]["name"], "at": at.isoformat(timespec="seconds")})
        # Re-open at the Disbursement Maker; the usual DIS gates apply to the new tranche.
        step = self._wf(app).step("dis_maker")
        app.update(status=STATUS_IN_PROGRESS, step_id=step.id, stage_id=step.stage_id,
                   step_entered_at=at.isoformat(timespec="seconds"), assignee_id=self._default_assignee(step.role, self._wf(app)))
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "subsequent_tranche", actor=actor, from_step=None,
                                         to_step=step.id, comment=f"Subsequent tranche round {app['tranche_rounds']}: {reason.strip()[:120]}",
                                         detail={"round": app["tranche_rounds"], "reason": reason.strip()[:500]}))
        return self.get(application_id, session)

    # ── post-sanction consent & facility execution (Client One GAP-P0-13) ────
    def record_consent(self, application_id: str, session: dict, *, acknowledged_by: str, consent_date: str,
                       remarks: str = "", facilities: Optional[list[dict]] = None,
                       raw_meta: Optional[dict] = None) -> dict:
        """Customer's sanction consent/acceptance and per-facility execution, recorded at Post-Sanction Maker."""
        app = self._require(application_id)
        self._maker_at(app, session, ("pos_maker",), "Recording sanction consent")
        if not (acknowledged_by or "").strip():
            raise InvalidRequestError("The customer acknowledgement is required")
        try:
            datetime.fromisoformat(consent_date or "")
        except ValueError:
            raise InvalidRequestError("A consent date (YYYY-MM-DD) is required")
        fac_ids = {f["facility_id"] for f in (app.get("facilities") or [app.get("facility") or {}])}
        rows = []
        for raw in facilities or []:
            fid = str(raw.get("facility_id") or "")
            if fid not in fac_ids:
                raise InvalidRequestError(f"Unknown facility: {fid}")
            status = str(raw.get("execution_status") or "").strip()
            if status not in EXECUTION_STATUSES:
                raise InvalidRequestError(f"Facility {fid}: execution status must be executed, partial or not_executed")
            adate = (raw.get("agreement_date") or "").strip() or None
            if adate:
                try:
                    datetime.fromisoformat(adate)
                except ValueError:
                    raise InvalidRequestError(f"Facility {fid}: the agreement date must be YYYY-MM-DD")
            if status == "executed" and not adate:
                raise InvalidRequestError(f"Facility {fid}: an executed facility needs the Facility Agreement date")
            rows.append({"facility_id": fid, "execution_status": status, "agreement_date": adate})
        if {r["facility_id"] for r in rows} != fac_ids:
            raise InvalidRequestError("Record an execution status for every facility")
        # R8: the signed copy of the sanction letter is uploaded first, the acceptance is
        # recorded against a specific letter version, and the consent date must fall inside
        # that version's validity — a missing / rejected / outdated version blocks the POS gate.
        letters = app.get("letters") or {}
        sanc_versions = letters.get("sanction_letter") or []
        if not sanc_versions:
            raise ConflictError("Generate and issue the Sanction Letter before recording the customer's acceptance")
        sanc = sanc_versions[-1]                      # the current version of record
        sc = app.get("letters", {}).get("sanction_letter_signed") or {}
        if not sc:
            raise ConflictError("Upload the customer's signed copy of the Sanction Letter before recording the acceptance")
        if sc.get("status") == "rejected":
            raise ConflictError("The signed copy was rejected — re-upload a legible copy matching the letter version")
        version = sanc.get("version")
        acceptance = {"date": consent_date, "by": acknowledged_by.strip(),
                      "method": (str((raw_meta or {}).get("method") or "signed copy").strip() or "signed copy"),
                      "letter_version": version,
                      "letter_reference": sanc.get("reference"),
                      "letter_valid_until": sanc.get("valid_until")}
        if sanc.get("valid_until") and sc.get("letter_version") in (None, version):
            v = datetime.fromisoformat(str(sanc["valid_until"])[:10]).date()
            c = datetime.fromisoformat(str(consent_date)[:10]).date()
            if c > v:
                raise InvalidRequestError(
                    f"The consent date ({consent_date}) is after the letter's validity ({sanc['valid_until']}) — "
                    "issue a fresh letter or re-accept within its validity")
        # the signed copy must match the current letter version
        if sc.get("letter_version") not in (None, version):
            raise InvalidRequestError(
                f"The signed copy is of letter version {sc.get('letter_version')} but the letter on record "
                f"is version {version} — re-upload the current version")
        at = self.now().replace(microsecond=0)
        app["consent"] = {"acknowledged_by": acknowledged_by.strip(), "consent_date": consent_date,
                          "remarks": (remarks or "").strip() or None, "facilities": rows,
                          "acceptance": acceptance,
                          "by": session["user"]["id"], "by_name": session["user"]["name"],
                          "at": at.isoformat(timespec="seconds")}
        # Per-facility execution flows into the facility amount lifecycle (GAP-P0-13).
        facmod.apply_execution(app.get("facilities") or [], rows, at.isoformat(timespec="seconds"), session["user"]["name"])
        dreg.register_generated(app.setdefault("documents", []), name="Sanction consent / acceptance",
                                kind="consent", by_name=session["user"]["name"],
                                at=at.isoformat(timespec="seconds"), detail=f"acknowledged by {acknowledged_by.strip()}")
        self._mirror_entries(app, "post_sanction", {"accepted_by": acknowledged_by.strip(), "acceptance_date": consent_date,
                                                    "agreement_date": next((r["agreement_date"] for r in rows
                                                                            if r.get("agreement_date")), None)},
                             session, "recording the sanction consent")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "consent_recorded", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"],
                                         comment=f"Sanction consent acknowledged by {acknowledged_by.strip()} on {consent_date}",
                                         detail={"facilities": rows}))
        return self.post_sanction(application_id, session)

    # ── R8: sanction-letter acceptance ────────────────────────────────────
    def upload_signed_letter(self, application_id: str, session: dict, kind: str,
                             filename: str, content: bytes) -> dict:
        """The customer's signed copy of the letter, uploaded at Post-Sanction Maker against
        the letter's current version."""
        if kind not in lt.KINDS:
            raise InvalidRequestError(f"Unknown letter kind: {kind}")
        app = self._require(application_id)
        self._maker_at(app, session, ("pos_maker",), "Uploading the signed letter")
        lts = app.setdefault("letters", {})
        versions = lts.get(kind) or []
        if not versions:
            raise ConflictError(f"The {lt.KINDS[kind]} is not on record — generate it first")
        version = versions[-1].get("version")
        lts["%s_signed" % kind] = {"filename": filename, "letter_version": version,
                                   "uploaded_by": session["user"]["name"], "at": self.now().isoformat(timespec="seconds"),
                                   "status": "uploaded", "hash": hashlib.sha256(content or b"").hexdigest()}
        dreg.register_generated(app.setdefault("documents", []), name=f"Signed copy — {lt.KINDS[kind]}",
                                kind="signed_letter", by_name=session["user"]["name"],
                                at=self.now().isoformat(timespec="seconds"), detail=filename)
        self.store.save(app, self._event(app, "signed_letter_uploaded",
                                         actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=app.get("step_id"), to_step=app.get("step_id"),
                                         comment=f"Signed copy of the {kind} v{version} uploaded"))
        return self.get(application_id, session)

    def review_signed_letter(self, application_id: str, session: dict, kind: str, outcome: str,
                             note: str = "") -> dict:
        """The reviewer's verification of the signed copy: verified, or rejected (re-upload)."""
        app = self._require(application_id)
        self._maker_at(app, session, ("pos_maker", "pos_checker"), "Reviewing the signed letter")
        lts = app.get("letters") or {}
        sc = lts.get("%s_signed" % kind) or {}
        if not sc:
            raise ConflictError("There is no signed copy to review")
        if outcome not in ("verified", "rejected"):
            raise InvalidRequestError("The review outcome must be verified or rejected")
        lts["%s_signed" % kind] = {**sc, "status": outcome,
                                   "review_note": (note or "").strip() or None,
                                   "reviewed_by": session["user"]["name"],
                                   "reviewed_at": self.now().isoformat(timespec="seconds")}
        self.store.save(app, self._event(app, "signed_letter_" + outcome,
                                         actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=app.get("step_id"), to_step=app.get("step_id"),
                                         comment=(note or "").strip()[:300]))
        return self.get(application_id, session)

    # ── governance workspaces (GAP-P0-01/04/07/08/09, P1-01…05, P0-12/15) ────
    # ── R17: field-level edit permissions ────────────────────────────────
    # The institution's field policy: which fields are material (a change to them is a
    # material edit and is audited with before/after), and which roles may edit which
    # domain (default: the current maker step's role; reviewers decide, they do not edit).

    def _field_policy(self, app: dict) -> dict:
        prof = self._profile(app)
        return {"material_fields": list(prof.get("field_material_fields") or []),
                "edit_roles": prof.get("field_edit_roles") or {}}

    def _material_fields(self, app: dict, raw: dict) -> list[str]:
        mat = self._field_policy(app)["material_fields"]
        changed = {k: v.get("after") for k, v in (raw or {}).items() if isinstance(v, dict)}
        if not changed:
            changed = dict(raw or {})
        return sorted(k for k in changed if k in mat)

    def _workspace_may(self, app: dict, session: Optional[dict], what: str, review: bool = False,
                       domain: Optional[str] = None, raw: Optional[dict] = None) -> None:
        """Who may change a workspace now: the current step's role. Maker steps edit the proposal;
        checker, VP-review, committee and allocation steps are read-only on it (process §3) and may
        only record their review (``review=True``: approving the CMA, reviewing a document, …).
        R17: ``domain`` is the institution policy's edit scope for that domain (which roles may
        edit it); a violation is a 403, and material fields edited outside the making stage are
        recorded as material edits (audited with before/after in the change event)."""
        if app.get("status") in TERMINAL:
            raise ConflictError(f"{what} is not available on a completed application")
        if not app.get("step_id"):
            raise ConflictError(f"{what} is not available on a completed application")
        step = self._wf(app).step(app["step_id"])
        if not session or not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"{what} is available to the current step's role ({self._wf(app).roles[step.role]})")
        roles = (self._field_policy(app)["edit_roles"] or {}).get(domain)
        if domain and roles is not None and session["role"] not in roles:
            raise ForbiddenError(f"{what} may be edited only by {', '.join(roles)} — your role "
                                 f"({self._wf(app).roles.get(session['role'], session['role'])}) is read-only here")
        if not review and step.kind != "maker":
            raise ForbiddenError(f"{what} is read-only at {step.name}: a review step does not change the proposal "
                                 "(return it for rework instead)")

    def _workspace_save(self, app: dict, session: dict, action: str, comment: str,
                        detail: Optional[dict] = None) -> dict:
        actor = {"id": session["user"]["id"], "role": session["role"]}
        app["updated_at"] = self.now().isoformat(timespec="seconds")
        if detail is None:
            detail = {}
        # R17: a change to a material field is audited with before/after (the institution's
        # field policy names them) and flagged in the decision record.
        mat = self._material_fields(app, detail.get("changes") or {})
        if mat:
            detail = {**detail, "material_fields": mat}
            app.setdefault("material_change_reviews", []).append(
                {"fields": mat, "by": session["user"]["name"],
                 "at": app["updated_at"], "stage": app.get("stage_id")})
            comment = f"[material edit: {', '.join(mat)}] " + (comment or "")
        self.store.save(app, self._event(app, action, actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment=(comment or "")[:600],
                                         detail=detail))
        return self.get(app["application_id"], session)

    # dependency invalidations (UAT-P2-10): group / ownership / rating changes that make a prior
    # conclusion stale must be flagged for re-evaluation rather than silently kept.
    def _invalidate(self, app: dict, inv_type: str, detail: str, by_name: str, at: str) -> dict:
        invs = app.setdefault("invalidations", [])
        entry = {"invalidation_id": f"INV-{len(invs) + 1:03d}", "type": inv_type, "detail": detail,
                 "by_name": by_name, "at": at, "status": "open", "resolved_by": None,
                 "resolved_at": None, "resolution": None}
        invs.append(entry)
        return entry

    def resolve_invalidation(self, application_id: str, session: dict, invalidation_id: str, resolution: str) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Invalidation review", review=True)
        entry = next((i for i in app.get("invalidations", []) if i["invalidation_id"] == invalidation_id), None)
        if not entry:
            raise InvalidRequestError(f"Unknown invalidation: {invalidation_id}")
        if entry["status"] != "open":
            raise ConflictError("This invalidation is already resolved")
        if not (resolution or "").strip():
            raise InvalidRequestError("A resolution note is required to close an invalidation")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        entry.update(status="resolved", resolved_by=session["user"]["name"], resolved_at=at,
                     resolution=resolution.strip()[:500])
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "invalidation_resolved", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"),
                                         comment=f"{entry['type']}: resolved — {resolution.strip()[:120]}",
                                         detail={"invalidation_id": invalidation_id, "type": entry["type"]}))
        return self.get(application_id, session)

    # parties (GAP-P0-01: party maintenance with PAN-change dependency)
    def save_party(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Party maintenance", domain="party")
        parties = app.setdefault("related_parties", [])
        party_id = str(raw.get("party_id") or "").strip() or None
        existing = next((p for p in parties if p["party_id"] == party_id), None) if party_id else None
        rec = {**(existing or {}), **{k: v for k, v in dict(raw or {}).items() if v not in (None, "")}}
        rec.setdefault("party_type", "non_individual")
        rec.setdefault("party_status", "active")
        rec["pan"] = str(rec.get("pan") or "").strip().upper()[:10] or None
        rec["cin"] = str(rec.get("cin") or "").strip().upper()[:21] or None
        ownership = rec.get("ownership_pct")
        if ownership not in (None, ""):
            try:
                ownership = round(float(ownership), 4)
            except (TypeError, ValueError):
                raise InvalidRequestError("Party: ownership must be a percentage")
            if ownership < 0 or ownership > 100:
                raise InvalidRequestError("Party: ownership must be between 0 and 100")
            rec["ownership_pct"] = ownership
        for key, allowed in (("role", _PARTY_ROLES), ("party_type", _PARTY_TYPES), ("party_status", _PARTY_STATUSES)):
            if str(rec.get(key) or "") not in allowed:
                raise InvalidRequestError(f"Party: {key} must be one of {', '.join(sorted(allowed))}")
        if not str(rec.get("name") or "").strip():
            raise InvalidRequestError("Party: the name is required")
        if not existing:
            if len(parties) >= 50:
                raise InvalidRequestError("An application cannot contain more than 50 related parties")
            rec["party_id"] = f"RP-{len(parties) + 1:03d}"
            parties.append(rec)
        else:
            rec["party_id"] = party_id
            # Ownership / group dependency invalidations (UAT-P2-10).
            at0 = self.now().replace(microsecond=0).isoformat(timespec="seconds")
            prev_own, new_own = existing.get("ownership_pct"), rec.get("ownership_pct")
            prev_f = float(prev_own) if prev_own not in (None, "") else None
            new_f = float(new_own) if new_own not in (None, "") else None
            if new_f is not None and new_f != prev_f:
                self._invalidate(app, "ownership_change",
                                 f"{rec['name']} ({rec.get('role')}): ownership {prev_own if prev_own not in (None, '') else 'not recorded'}% → {new_own}% "
                                 "— the credit assessment and group rating are stale; re-evaluation required",
                                 session["user"]["name"], at0)
            old_role, new_role = existing.get("role"), rec.get("role")
            if old_role != new_role and (old_role in _GROUP_ROLES or new_role in _GROUP_ROLES):
                self._invalidate(app, "group_change",
                                 f"{rec['name']}: role {old_role} → {new_role} — the group structure changed; "
                                 "the group rating and group-level conclusions are stale",
                                 session["user"]["name"], at0)
            parties[parties.index(existing)] = rec
            if existing.get("pan") and rec.get("pan") and existing["pan"] != rec["pan"].upper():
                # PAN-change dependency (spec §6.2): re-evaluate identity, rerun dedupe,
                # invalidate PAN-dependent checks and flag affected decisions.
                app["customer_identity"] = self.borrower_identity(app["entity_id"], exclude_app=app["application_id"])
                for cid in ("kyc", "gstin"):
                    c = next((x for x in (app.get("due_diligence") or {}).get("checks") or [] if x["id"] == cid), None)
                    if c and c["status"] in ("clear", "failed"):
                        c.update(status="pending", result=None, detail=None,
                                 invalidated_reason="PAN changed — retrigger required")
                self._workspace_save(app, session, "party_pan_changed", f"{rec['name']}: PAN changed — identity and dedupe re-evaluated, PAN-dependent checks invalidated")
                return self.get(application_id, session)
        self._workspace_save(app, session, "party_updated" if existing else "party_added", f"{rec.get('name')} ({rec.get('role')})")
        return self.get(application_id, session)

    # party-level evidence (UAT-P0-3): each party is linked separately to KYC, bureau checks,
    # name screening, ratings, financial records, documents and exceptions.
    def save_party_verification(self, application_id: str, session: dict, party_id: str, payload: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Party-level evidence")
        party = next((p for p in app.get("related_parties", []) if p["party_id"] == party_id), None)
        if not party:
            raise InvalidRequestError(f"Unknown party: {party_id}")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        try:
            changed = pev.apply_update(party, payload, session["user"]["name"], at, vp=session["role"] == "compliance_vp")
        except ValueError as e:
            raise InvalidRequestError(str(e))
        if not changed:
            raise InvalidRequestError("Nothing to update")
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "party_evidence", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"),
                                         comment=f"{party['name']}: {'/'.join(changed)}", detail={"party_id": party_id, "changed": changed}))
        return self.get(application_id, session)

    def _link_party_screening(self, app: dict, result: dict, by_name: str, at: str) -> None:
        """Application-level name screening auto-links the individuals' party evidence (demo),
        so the analyst confirms or overwrites it at party level."""
        try:
            self._link_party_screening_impl(app, result, by_name, at)
        except Exception:                    # controlled: a link failure must never 500 the check run
            app.setdefault("_link_warnings", []).append(
                f"party screening link failed: {type(Exception).__name__} — confirm party evidence manually")
            try:
                self.store.save(app)
            except Exception:
                pass

    def _link_party_screening_impl(self, app: dict, result: dict, by_name: str, at: str) -> None:
        for p in app.get("related_parties", []):
            if p.get("party_type") != "individual":
                continue
            v = p.setdefault("verification", pev.initial_verification())
            ns = v.get("name_screening") or {}
            if ns.get("status") not in ("pending",) and ns.get("by_name") and ns["by_name"] != "auto-linked":
                continue                     # an analyst record is never overwritten
            hits = None
            if result["status"] == "matched":
                m = re.search(r"(\d+)\s+PEP", result.get("detail") or "")
                hits = int(m.group(1)) if m else None
            v["name_screening"] = {"status": result["status"], "hits": hits,
                                   "remarks": "Auto-linked from the application-level screening — confirm at party level (demo reference list)",
                                   "by_name": "auto-linked", "at": at}

    # facilities (GAP-P0-04)
    def update_facility(self, application_id: str, session: dict, facility_id: str, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Facility maintenance", domain="facility")
        if app.get("sanctions"):
            raise ConflictError("Facilities cannot be edited after sanction — raise a modification instead")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        fac = next((f for f in app.get("facilities") or [] if f.get("facility_id") == facility_id), None)
        if not fac:
            raise InvalidRequestError(f"Unknown facility: {facility_id}")
        changes = {k: {"before": fac.get(k), "after": raw[k]}
                   for k in raw if fac.get(k) != raw.get(k) and raw.get(k) is not None}
        facmod.change_facility(app, facility_id, raw, at, session["user"]["name"])
        errors = facmod.validate_hierarchy(app)
        if errors:
            raise InvalidRequestError("Facility hierarchy: " + "; ".join(errors))
        return self._workspace_save(app, session, "facility_updated",
                                    f"{facility_id} updated",
                                    detail={"facility_id": facility_id, "changes": changes})

    def field_permissions(self, application_id: str, session: Optional[dict] = None) -> dict:
        """R17: the effective field-level edit policy for this application: which roles may
        edit which domain, which fields are material, and what the current session may do."""
        app = self._require(application_id)
        pol = self._field_policy(app)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        current = session.get("role") if session else None
        domains = {"facility": "Facility maintenance", "party": "Party maintenance",
                   "security": "Security maintenance", "project": "Project maintenance",
                   "esms": "ESMS screening", "ewp": "External work-party management"}

        def _editable(roles):
            # the same rule _workspace_may enforces: the session holds the current step's
            # role, the step is a maker step, and (when the profile names the domain's
            # editors) the role is among them — so the UI disables exactly what the API refuses
            if step is None or current is None or current != step.role or step.kind != "maker":
                return False
            return roles is None or current in roles

        editable = {d: _editable(roles) for d, roles in sorted(pol["edit_roles"].items())}
        if not editable:                       # no per-domain policy: the step's role edits its own domains
            editable = {d: _editable(None) for d in domains}
        return {"application_id": application_id,
                "material_fields": pol["material_fields"],
                "edit_roles": pol["edit_roles"],
                "step": step.id if step else None,
                "editable_now": editable if step else {},
                "note": "Maker steps edit their own domains; reviewers decide (decision fields only). "
                        "A change to a material field is audited with before/after and flagged in "
                        "the decision record. The UI disables exactly these fields — the API enforces the same policy."}

    def facility_hierarchy(self, application_id: str, session: Optional[dict] = None) -> dict:
        """R6: the facility hierarchy with utilisation per node and the validation result."""
        app = self._require(application_id)
        facs = app.get("facilities") or []
        by_id = {f.get("facility_id"): f for f in facs}
        nodes = []
        for f in facs:
            committed = f.get("committed_cr") or f.get("sanctioned_cr") or 0
            disbursed = f.get("disbursed_cr") or 0
            nodes.append({"facility_id": f.get("facility_id"), "facility_type": f.get("facility_type"),
                          "currency": f.get("currency") or "INR",
                          "proposed_cr": f.get("proposed_cr") or f.get("amount_cr"),
                          "committed_cr": committed, "disbursed_cr": disbursed,
                          "balance_cr": round(committed - disbursed, 2) if committed else None,
                          "parent_limit_id": f.get("parent_limit_id"),
                          "reimbursement_facility": bool(f.get("reimbursement_facility")),
                          "interchangeable": bool(f.get("interchangeable")),
                          "takeover": f.get("takeover")})
        return {"application_id": application_id, "facilities": nodes,
                "errors": facmod.validate_hierarchy(app)}

    # securities (GAP-P1-03)
    def save_security(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Security maintenance", domain="security")
        securities = app.setdefault("securities", [])
        security_id = str(raw.get("security_id") or "").strip() or None
        existing = next((s for s in securities if s["security_id"] == security_id), None) if security_id else None
        known = {f["facility_id"] for f in app.get("facilities", [])}
        rec = sec.normalise_security(raw, (securities.index(existing) + 1) if existing else len(securities) + 1,
                                     known, existing)
        if existing:
            changed = [k for k in ("proposed_value_cr", "apportioned_value_cr", "valuation_date", "charge_type",
                                   "perfection_status", "facility_ids") if existing.get(k) != rec.get(k)]
            rec["history"] = existing.get("history", [])
            for k in changed:
                rec["history"].append({"at": self.now().isoformat(timespec="seconds"), "by": session["user"]["name"],
                                       "change": f"{k}: {existing.get(k)!r} → {rec.get(k)!r}"})
            securities[securities.index(existing)] = rec
        else:
            rec["security_id"] = f"SEC-{len(securities) + 1:03d}"
            securities.append(rec)
        # link the security-perfection conditions (GAP-P0-14)
        if app.get("conditions"):
            sec.link_conditions(securities, app["conditions"])
        return self._workspace_save(app, session, "security_updated" if existing else "security_added",
                                    f"{rec['security_id']} {rec.get('type') or ''}".strip())

    # projects (GAP-P1-01)
    def save_project(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Project maintenance", domain="project")
        projects = app.setdefault("projects", [])
        project_id = str(raw.get("project_id") or "").strip() or None
        existing = next((p for p in projects if p["project_id"] == project_id), None) if project_id else None
        known = {f["facility_id"] for f in app.get("facilities", [])}
        rec = prj.normalise_project(raw, (projects.index(existing) + 1) if existing else len(projects) + 1,
                                    known, existing)
        if existing:
            rec["changes"] = existing.get("changes", [])
            projects[projects.index(existing)] = rec
        else:
            rec["project_id"] = f"PRJ-{len(projects) + 1:03d}"
            projects.append(rec)
        return self._workspace_save(app, session, "project_updated" if existing else "project_added", rec["name"])

    def record_project_change(self, application_id: str, session: dict, project_id: str, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Recording a project change", domain="project")
        p = next((x for x in app.get("projects", []) if x["project_id"] == project_id), None)
        if not p:
            raise InvalidRequestError(f"Unknown project: {project_id}")
        change = prj.record_change(p, raw, self.now().isoformat(timespec="seconds"), session["user"]["name"])
        return self._workspace_save(app, session, "project_change",
                                    f"{project_id}: {change['field']} → {change['current']} (flagged for reappraisal)",
                                    detail={"changes": {change["field"]: {"before": change.get("previous"),
                                                                            "after": change["current"]}}})

    # ESMS (GAP-P1-02)
    def update_esms(self, application_id: str, session: dict, payload: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "ESMS screening")
        esms = app.setdefault("esms", es.initial_esms(app))
        for key in ("screening_date", "category", "cpcb_category", "coastal_zone_impact", "resettlement",
                    "environmental_impact", "es_litigation", "monuments_impact", "eia_category",
                    "information_source", "remarks",
                    "proposed_category", "introduction", "proposal_summary", "company_es_risk_assessment",
                    "esdd", "committee_recommendation"):
            if key in payload:
                esms[key] = (str(payload[key]).strip() or None) if payload[key] is not None else None
        if payload.get("checklist"):
            esms["checklist"] = es.normalise_checklist(payload["checklist"], esms.get("checklist") or [])
        elif not esms.get("checklist"):
            esms["checklist"] = es.normalise_checklist([], [])
        if payload.get("additional_conditions"):
            esms["additional_conditions"] = [str(x).strip() for x in payload["additional_conditions"] if str(x).strip()]
        if esms.get("checklist") and all(i.get("answer") for i in esms["checklist"]) and esms.get("category"):
            esms["status"] = "complete"
        elif esms.get("screening_date") or any(i.get("answer") for i in esms.get("checklist", [])):
            esms["status"] = "in_progress"
        if esms.get("esdd") or esms.get("committee_recommendation"):
            esms["status"] = "complete"
        if "category" in payload or "checklist" in payload:
            self._recompute_routing(app, {"id": session["user"]["id"], "role": session["role"]},
                                    "route recalculated after the E&S category / excluded-activity screen")
        return self._workspace_save(app, session, "esms_update", f"ESMS: category {esms.get('category') or '—'}")

    # ── R5: E&S exceptions for excluded activities ─────────────────────────

    def _esms_exception(self, app: dict, esms: dict) -> Optional[dict]:
        """The application's E&S exception when the institution allows them (profile:
        ``esms.exceptions``); profiles without the block (e.g. Client One) never release
        the excluded-activity block."""
        pol = profiles.esms_policy(self._profile(app))
        if not pol.get("exceptions_enabled"):
            return None
        return esms.get("exception")

    def request_esms_exception(self, application_id: str, session: dict, note: str) -> dict:
        """The step holder asks the institution's configured E&S authority for an exception
        to the excluded-activity screen. The request is queued for that authority."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Requesting an E&S exception")
        esms = app.get("esms") or {}
        pol = profiles.esms_policy(self._profile(app))
        if not pol.get("exceptions_enabled"):
            raise ConflictError("This institution does not allow exceptions to the excluded-activity screen")
        excluded = [i for i in esms.get("checklist", []) if i.get("answer") == "Yes"]
        if not excluded:
            raise ConflictError("An E&S exception applies to an excluded activity answered 'Yes' on the ESMS screen")
        if exc0 := esms.get("exception") or {}:
            if exc0.get("status") == "pending":
                raise ConflictError("An E&S exception request is already pending with "
                                    + (exc0.get("to_name") or "the E&S authority"))
            if es.esms_exception_active(exc0, self.now()):
                raise ConflictError("A valid E&S exception is already on file")
        if not (note or "").strip():
            raise InvalidRequestError("Say why the excluded activity is acceptable — the E&S authority decides on it")
        at = self.now().isoformat(timespec="seconds")
        role = pol["exception_authority"]["role"]
        approvers = self._approvers(role, self._wf(app))
        if not approvers:
            raise InvalidRequestError(f"No approver with the E&S exception role ({role}) is configured")
        esms["exception"] = {"status": "pending", "by": session["user"]["id"], "by_name": session["user"]["name"],
                             "at": at, "note": note.strip(), "activities": [i["id"] for i in excluded],
                             "to_name": approvers[0]["name"], "to_email": approvers[0].get("email")}
        self._workspace_save(app, session, "esms_exception_requested",
                             f"E&S exception requested: {note.strip()[:200]}",
                             detail={"activities": esms["exception"]["activities"]})

    def decide_esms_exception(self, application_id: str, session: dict, outcome: str, reason: str) -> dict:
        """The configured E&S authority decides: ``approved`` (with a TTL that lapses the
        release) or ``declined`` (the block stands — the proposal cannot proceed)."""
        app = self._require(application_id)
        pol = profiles.esms_policy(self._profile(app))
        if not pol.get("exceptions_enabled"):
            raise ConflictError("This institution does not allow exceptions to the excluded-activity screen")
        if session["role"] != pol["exception_authority"]["role"]:
            raise ForbiddenError(f"Only the {pol['exception_authority']['name']} decides on an E&S exception")
        if outcome not in ("approved", "declined"):
            raise InvalidRequestError("Outcome must be approved or declined")
        if not (reason or "").strip():
            raise InvalidRequestError("A reason is required for the E&S exception decision")
        esms = app.get("esms") or {}
        exc = esms.get("exception") or {}
        if exc.get("status") != "pending":
            raise ConflictError("There is no pending E&S exception request")
        at = self.now().isoformat(timespec="seconds")
        exc.update(status=outcome, decided_by=session["user"]["name"], decided_at=at,
                   decision_note=reason.strip())
        if outcome == "approved":
            exc["expires_at"] = (self.now() + timedelta(days=int(pol.get("exception_ttl_days") or 180))).isoformat(timespec="seconds")
        self._workspace_save(app, session, f"esms_exception_{outcome}",
                             f"E&S exception {outcome} by {session['user']['name']}: {reason.strip()[:200]}",
                             detail={"by": session["user"]["name"], "expires_at": exc.get("expires_at")})

    # external work parties (GAP-P1-05)
    def save_ewp(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "External work-party management", domain="ewp")
        ewps = app.setdefault("ewps", [])
        ewp_id = str(raw.get("ewp_id") or "").strip() or None
        existing = next((x for x in ewps if x["ewp_id"] == ewp_id), None) if ewp_id else None
        known = {"projects": {p["project_id"] for p in app.get("projects", [])},
                 "facilities": {f["facility_id"] for f in app.get("facilities", [])},
                 "securities": {s["security_id"] for s in app.get("securities", [])}}
        rec = ewp_mod.normalise_ewp(raw, (ewps.index(existing) + 1) if existing else len(ewps) + 1, known, existing)
        if existing:
            ewps[ewps.index(existing)] = rec
        else:
            rec["ewp_id"] = f"EWP-{len(ewps) + 1:03d}"
            ewps.append(rec)
        return self._workspace_save(app, session, "ewp_updated" if existing else "ewp_added",
                                    f"{rec['role']}: {rec['name']}")

    # ratings & RAROC (GAP-P0-08)
    def record_rating(self, application_id: str, session: dict, kind: str, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Rating records")
        ratings = app.setdefault("ratings", rat.initial_ratings(app, self.companies))
        if kind == "external":
            entry = rat.external_rating_entry(raw, app.get("related_parties") or [])
        elif kind == "internal":
            entry = rat.internal_rating_entry(raw)
        elif kind == "adverse_event":
            entry = rat.adverse_event_entry(raw)
        else:
            raise InvalidRequestError("kind must be external, internal or adverse_event")
        target = {"external": "external_ratings", "internal": "internal_ratings"}.get(kind, "adverse_events")
        rows = ratings.setdefault(target, [])
        if kind != "adverse_event":
            same = next((r for r in rows if r["subject"] == entry["subject"]
                         and (r.get("party_name") or None) == (entry.get("party_name") or None)), None)
            if same:
                if (same.get("rating") or same.get("grade")) != (entry.get("rating") or entry.get("grade")):
                    # Rating dependency invalidation (UAT-P2-10): the RAROC and any committee
                    # recommendation that relied on the previous rating are now stale.
                    self._invalidate(app, "rating_change",
                                     f"{entry.get('subject', '')} rating changed "
                                     f"{(same.get('rating') or same.get('grade') or '—')} → "
                                     f"{(entry.get('rating') or entry.get('grade') or '—')} — RAROC and recommendations are stale",
                                     session["user"]["name"], self.now().isoformat(timespec="seconds"))
                rows[rows.index(same)] = entry
            else:
                rows.append(entry)
        else:
            rows.append(entry)
        action = {"external": "external_rating", "internal": "internal_rating"}.get(kind, "adverse_event_review")
        label = entry.get("rating") or entry.get("grade") or entry.get("trigger") or ""
        return self._workspace_save(app, session, action,
                                    f"{entry.get('subject', '')} {label}".strip())

    _DECIDED = ("confirmed", "overridden")

    def _auto_raroc(self, app: dict, case: Optional[dict], at: str) -> list[str]:
        """R-P2: the RAROC agent computes a facility's RAROC once its inputs are verified — the borrower's
        internal rating grade and the facility's rate — and again whenever those inputs change (stale).
        The verified rate is recorded on the facility when the facility has none yet. Caller saves."""
        fields = app.get("fields") or {}
        if (fields.get("internal_rating.borrower.grade") or {}).get("status") not in self._DECIDED:
            return []
        ratings = app.setdefault("ratings", rat.initial_ratings(app, self.companies))
        stale, done = set(rat.stale_raroc(app)), []
        for f in app.get("facilities") or []:
            fid = f["facility_id"]
            rate = fields.get(f"facility_pricing.{fid}.proposed_rate") or {}
            if rate.get("status") not in self._DECIDED or rate.get("value") in (None, ""):
                continue
            pricing = f.setdefault("pricing", {})
            if pricing.get("interest_rate") is None:
                spread = (fields.get(f"facility_pricing.{fid}.proposed_spread_bps") or {}).get("value")
                try:
                    pricing.update(benchmark="MCLR", interest_rate=float(rate["value"]),
                                   spread=round(float(spread) / 100, 4) if spread not in (None, "") else None)
                except (TypeError, ValueError):
                    continue
            if fid in (ratings.get("raroc") or {}) and fid not in stale:
                continue
            entry = rat.compute_raroc(app, fid, case, at, "RAROC agent (inputs verified)")
            ratings.setdefault("raroc", {})[fid] = {**entry, "origin": "agent"}
            done.append(fid)
        return done


    # The decision tab (G-W5): the computed committee, deviations (auto + manual) and the remarks history
    # (ACTION_WORDS lists the decisions that appear in the remarks history.)
    DEVIATION_STEPS = ("ip_note", "ap_note", "ip_risk_maker", "ap_risk_maker")

    def _decision_record(self, app: dict, step, session: dict, action: str, at: datetime,
                         comment: str, decision: dict, route: dict) -> Optional[dict]:
        """The standard decision record (R3): what was decided, by whom, when, the authority and
        route version it was taken under, the material-information date it stands on, and the
        open deviation references. Terminal decisions (drop/withdraw/reject) and governed
        negative decisions (return/rework) are recorded too, so the timeline is complete."""
        if action not in ("submit", "approve", "sanction", "return", "reject", "drop", "withdraw",
                          "propose_modification", "recommend_modification", "allocate", "defer",
                          "reactivate"):
            return None
        if not decision and action not in ("drop", "withdraw", "reject", "return", "defer", "reactivate"):
            return None
        stage_final = step.stage_id in ("AP", "POS", "DIS")
        rec = {"decision_id": f"DEC-{len(app.get('decisions', [])) + 1:03d}",
               "step": step.id, "step_name": step.name, "action": action,
               "by": session["user"]["id"], "by_name": session["user"]["name"],
               "at": at.isoformat(timespec="seconds"),
               "remarks": (comment or "").strip() or None,
               **dict(decision or {}),
               "authority": ((route.get("final_authority") if stage_final else route.get("preliminary_authority")) or {}).get("required"),
               "route_seq": (app.get("routing_history") or [{}])[-1].get("seq"),
               "route_stage": route.get("stage"),
               "material_information_date": (decision or {}).get("material_information_date")
                   or (app.get("entity") or {}).get("latest_material_information_date"),
               "deviation_refs": sorted({(d.get("id") or d.get("type")) for d in
                                         (app.get("manual_deviations") or []) if not d.get("removed")}),
               "supersedes": None}
        return rec

    def decision_view(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        case, _ = self._app_case(app)
        auto, manual = committee_deviations(case), manual_deviations(app)
        final = app.get("stage_id") not in ("PS", "IP")
        ca = app.get("credit_assessment") or {}
        committee = authority.required_authority(app.get("amount_cr"), ca.get("risk_grade"),
                                                 deviations=len(auto) + len(manual), final=final,
                                                 app=app, product=profiles.primary_product(app))
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        labels = {e: ACTION_WORDS.get(e, e.replace("_", " ").title()) for e in ACTION_WORDS}
        history = []
        for e in reversed(self.store.events(application_id, limit=2000)):           # oldest first
            if not (e.get("comment") or "").strip() or e["action"] not in ACTION_WORDS:
                continue                      # decisions and Compliance exceptions, not workspace edits
            try:
                fs = self._wf(app).step(e["from_step"]) if e.get("from_step") else None
            except wfmod.WorkflowError:       # a step since removed from the configuration
                fs = None
            word = (wfmod.action_label(fs, e["action"]) if fs else None) or labels.get(e["action"]) \
                or e["action"].replace("_", " ").capitalize()
            history.append({"at": e["at"], "step": fs.name if fs else "—", "stage": fs.stage_name if fs else "—",
                            "by": self._user_name(e.get("actor_id")) or e.get("actor_role") or "agent",
                            "role": self._wf(app).roles.get(e.get("actor_role") or "", e.get("actor_role") or ""),
                            "decision": word, "remarks": e["comment"]})
        fields = app.get("fields") or {}
        notes = [{"key": k, "label": label, "text": (app.get("decision_notes") or {}).get(k),
                  "status": (fields.get(f"decision_notes.{k}") or {}).get("status"),
                  "field_id": f"decision_notes.{k}" if f"decision_notes.{k}" in fields else None}
                 for k, label in prefill.DECISION_NOTES.items()
                 if k != "ip_observations" or final]
        return {"notes": notes, "committee": committee, "stage": "final" if final else "in-principle",
                "auto_deviations": [{"deviation": d[0], "value": d[1], "basis": d[2]} for d in auto],
                "manual_deviations": app.get("manual_deviations") or [],
                "deviation_types": list(DEVIATION_TYPES),
                "can_add_deviation": bool(step and step.id in self.DEVIATION_STEPS and session
                                          and app.get("status") not in TERMINAL
                                          and can_act(self._wf(app), session["user"]["id"], session["role"], step)),
                "decision_records": app.get("decisions") or [],
                # R17: material edits (audited with before/after in the change event)
                "material_change_flags": [" · ".join(m["fields"]) + " — " + m["by"] + " at " + m["at"][:10]
                                          for m in app.get("material_change_reviews") or []],
                # R3: the decision timeline — every recorded decision with its authority,
                # route version, material-information date and deviation references
                "timeline": self._decision_timeline(app),
                "remarks_history": history}

    @staticmethod
    def _decision_timeline(app: dict) -> list:
        """The append-only decision record, oldest first, each entry carrying what it was
        decided under (authority + route version) and what it stands on (material-information
        date, deviation references)."""
        out = []
        for d in app.get("decisions") or []:
            out.append({
                "decision_id": d.get("decision_id"), "at": d.get("at"),
                "step": d.get("step"), "step_name": d.get("step_name"), "action": d.get("action"),
                "by_name": d.get("by_name"), "remarks": d.get("remarks"),
                "authority": d.get("authority"), "route_seq": d.get("route_seq"),
                "material_information_date": d.get("material_information_date"),
                "deviation_refs": d.get("deviation_refs") or []})
        return out

    # ── R7: governed modifications of sanctioned terms ─────────────────────────────────────────
    # A modification proposed after sanction is evaluated against the institution's
    # materiality thresholds (profile: modifications:) — a material change re-enters the
    # credit-reassessment route (new authority, fresh review), a minor change only the
    # recommendation route. The sanctioned terms stay in force and disbursement is blocked
    # while the modification is undecided.

    def propose_modification_request(self, application_id: str, session: dict, raw: dict) -> dict:
        """Propose a modification of sanctioned terms (amount / tenor / rate / type / other).
        Before it is recommended (checker) and approved (committee), the sanctioned terms
        remain in force and no new disbursement proceeds against the open modification."""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in ("pos_maker", "dis_maker", "pos_checker", "dis_checker", "dis_vp_review", "dis_approver"):
            raise ForbiddenError("A modification can be proposed at the post-sanction maker / checker steps")
        if app.get("status") in TERMINAL:
            raise ConflictError("This application is complete")
        mods = app.setdefault("modifications", [])
        open_mod = next((m for m in mods if m["status"] == "open"), None)
        if open_mod:
            raise ConflictError(f"Modification {open_mod['modification_id']} is still open — "
                                "it must be recommended and decided before another is proposed")
        changed, errors = [], []
        fields = {"amount_cr": "amount_cr", "tenor_months": "tenor_months",
                  "interest_rate": "interest_rate", "facility_type": "facility_type"}
        before = {"amount_cr": app.get("amount_cr"), "tenor_months": None, "interest_rate": None,
                  "facility_type": (app.get("facility") or {}).get("facility_type")}
        fac = (app.get("facilities") or [app.get("facility") or {}])[0] or {}
        before["tenor_months"] = fac.get("tenor_months")
        before["interest_rate"] = fac.get("interest_rate")
        for key, label in fields.items():
            if key in raw and raw[key] not in (None, ""):
                try:
                    val = raw[key]
                    if key in ("amount_cr", "tenor_months", "interest_rate"):
                        val = float(raw[key])
                except (TypeError, ValueError):
                    errors.append(f"{label} must be a positive number")
                    continue
                if key in ("amount_cr", "tenor_months", "interest_rate") and val <= 0:
                    errors.append(f"{label} must be a positive number")
                    continue
                if key == "facility_type":
                    if before.get("facility_type") != str(val):
                        changed.append({"field": "facility_type", "before": before.get("facility_type"), "after": str(val)})
                elif str(before.get(key)) != str(val):
                    changed.append({"field": key, "before": before.get(key), "after": val})
        if errors:
            raise InvalidRequestError("; ".join(errors))
        if not changed:
            raise InvalidRequestError("A modification needs at least one changed term "
                                      "(amount_cr, tenor_months, interest_rate or facility_type)")
        cfg = self._profile(app).get("modifications") or {}
        thresholds = cfg.get("material") or {}
        material = []
        amt = next((c for c in changed if c["field"] == "amount_cr"), None)
        if amt and before.get("amount_cr"):
            pct = (amt["after"] - before["amount_cr"]) / before["amount_cr"] * 100
            lim = float(thresholds.get("amount_increase_pct") or 0)
            if pct > lim:
                material.append(f"amount +{pct:.1f}% (threshold {lim:g}%)")
        if any(c["field"] == "tenor_months" for c in changed) and float(thresholds.get("any_tenor_change", 1)):
            material.append("tenor changed")
        if any(c["field"] == "interest_rate" for c in changed) and float(thresholds.get("any_rate_change", 0)):
            material.append("rate changed")
        if any(c["field"] == "facility_type" for c in changed):
            material.append("facility type changed")
        is_material = bool(material)
        target = ("ap_risk_maker" if is_material
                  else str(cfg.get("minor_target_step") or "ap_evp"))
        at = self.now().isoformat(timespec="seconds")
        mod = {"modification_id": f"MOD-{len(mods) + 1:03d}",
               "by": session["user"]["id"], "by_name": session["user"]["name"], "at": at,
               "at_step": step.id, "reason": (str(raw.get("reason") or "").strip() or "modification of sanctioned terms")[:1000],
               "changes": changed, "material": is_material,
               "material_basis": material, "target_step": target, "status": "open",
               "recommended": None, "decision": None}
        mods.append(mod)
        self.store.save(app, self._event(app, "modification_proposed", actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=step.id, to_step=step.id, at=self.now(),
                                         comment=f"Modification {mod['modification_id']} proposed: "
                                                 + ", ".join(c["field"] for c in changed),
                                         detail=mod))
        return self.get(application_id, session)

    def recommend_modification_request(self, application_id: str, session: dict, raw: dict) -> dict:
        """The checker's recommendation on the open modification (recommend / reject)."""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.kind not in ("checker", "vp_review") or step.id not in ("pos_checker", "dis_checker", "ap_sanction"):
            raise ForbiddenError("The modification is recommended at the Post-Sanction Checker (or the disbursement checker)")
        mod = next((m for m in app.get("modifications") or [] if m["status"] == "open"), None)
        if not mod:
            raise ConflictError("There is no open modification to recommend")
        decision = str(raw.get("decision") or "").strip().lower()
        if decision not in ("recommend", "reject"):
            raise InvalidRequestError("The recommendation needs a decision (recommend or reject)")
        remarks = str(raw.get("remarks") or "").strip()
        if not remarks:
            raise InvalidRequestError("The recommendation needs its remarks")
        at = self.now().isoformat(timespec="seconds")
        mod["recommended"] = {"by": session["user"]["id"], "by_name": session["user"]["name"],
                              "at": at, "decision": decision, "remarks": remarks[:1000]}
        if decision == "reject":
            mod["status"] = "rejected"
            mod["decision"] = {"outcome": "rejected", "at": at, "by_name": session["user"]["name"],
                               "remarks": remarks[:1000]}
        self.store.save(app, self._event(app, "modification_recommended", actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=step.id, to_step=step.id, at=self.now(),
                                         comment=f"Modification {mod['modification_id']} {decision}d",
                                         detail=mod))
        return self.get(application_id, session)

    def decide_modification_request(self, application_id: str, session: dict, raw: dict) -> dict:
        """The committee's decision on a recommended modification. Approving a *material*
        modification applies the new terms, re-enters the case at the credit reassessment and
        records the recalculated route (the new authority applies); approving a minor one
        applies the terms directly with the committee's decision recorded."""
        app = self._require(application_id)
        mod = next((m for m in app.get("modifications") or [] if m["status"] == "open"), None)
        if not mod:
            raise ConflictError("There is no open modification to decide")
        if not mod.get("recommended"):
            raise ConflictError(f"Modification {mod['modification_id']} has not been recommended by the checker yet")
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in ("pos_checker", "dis_checker", "ap_sanction"):
            raise ForbiddenError("The modification is decided at the Post-Sanction Checker (the post-sanction "
                                 "modification authority) or, once the case has re-entered, at the sanction committee")
        outcome = str(raw.get("outcome") or "").strip().lower()
        if outcome not in ("approve", "reject"):
            raise InvalidRequestError("The decision needs an outcome (approve or reject)")
        minutes = str(raw.get("minutes") or "").strip()
        if not minutes:
            raise InvalidRequestError("The committee decision needs its minutes")
        at = self.now().isoformat(timespec="seconds")
        mod["decision"] = {"outcome": outcome, "at": at, "by": session["user"]["id"],
                           "by_name": session["user"]["name"], "minutes": minutes[:2000],
                           "authority": ((app.get("routing") or {}).get("final_authority") or {}).get("required")}
        if outcome == "reject":
            mod["status"] = "rejected"
        else:
            mod["status"] = "approved"

            def apply_terms():
                for c in mod["changes"]:
                    if c["field"] == "amount_cr":
                        app["amount_cr"] = c["after"]
                    if c["field"] in ("tenor_months", "interest_rate", "facility_type"):
                        for f in app.get("facilities") or []:
                            f[c["field"]] = c["after"]
                        fac = app.get("facility")
                        if isinstance(fac, dict):
                            fac[c["field"]] = c["after"]

            apply_terms()
            if mod["material"]:
                wf = self._wf(app)
                tgt = wf.step(mod["target_step"])
                app["modification_reentry"] = {"modification_id": mod["modification_id"], "at": at,
                                               "target": mod["target_step"],
                                               "reason": "material modification approved — credit reassessment required"}
                app.update(step_id=tgt.id, stage_id=tgt.stage_id,
                           status=wfmod.STATUS_IN_PROGRESS,
                           step_entered_at=at, assignee_id=self._default_assignee(tgt.role, wf))
                self._recompute_routing(app, {"id": session["user"]["id"], "role": session["role"]},
                                        f"route recalculated for the approved material modification {mod['modification_id']}")
        self.store.save(app, self._event(app, "modification_decided", actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=step.id if step else None, to_step=app.get("step_id"), at=self.now(),
                                         comment=f"Modification {mod['modification_id']} {outcome}d",
                                         detail=mod))
        return self.get(application_id, session)

    def save_deviation(self, application_id: str, session: dict, raw: dict) -> dict:
        """Add a manual deviation (type, description, justification) or remove one (with a reason)."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Deviations")
        step = self._wf(app).step(app["step_id"])
        if step.id not in self.DEVIATION_STEPS:
            raise ForbiddenError("Deviations are added at the IP / AP Note and the Risk Maker steps")
        devs = app.setdefault("manual_deviations", [])
        at, name = self.now().isoformat(timespec="seconds"), session["user"]["name"]
        if raw.get("action") == "remove":
            d = next((x for x in devs if x["id"] == raw.get("id")), None)
            reason = str(raw.get("reason") or "").strip()
            if not d:
                raise InvalidRequestError(f"Unknown deviation {raw.get('id')}")
            if not reason:
                raise InvalidRequestError("Give a reason for removing the deviation")
            d.update(removed=True, removed_reason=reason, removed_by=name, removed_at=at)
            self._recompute_routing(app, {"id": session["user"]["id"], "role": session["role"]},
                                    "route recalculated after a policy deviation was removed")
            return self._workspace_save(app, session, "deviation_removed", f"{d['id']}: {reason}")
        dev_type = str(raw.get("type") or "").strip()
        description = str(raw.get("description") or "").strip()
        justification = str(raw.get("justification") or "").strip()
        if dev_type not in DEVIATION_TYPES:
            raise InvalidRequestError(f"Deviation type must be one of {', '.join(DEVIATION_TYPES)}")
        if not description or not justification:
            raise InvalidRequestError("A deviation needs its description and its justification")
        d = {"id": f"MDV-{len(devs) + 1:02d}", "type": dev_type, "description": description[:500],
             "justification": justification[:1000], "raised_by": name, "raised_at": at, "raised_at_step": step.name,
             "stage": step.stage_id, "removed": False}
        devs.append(d)
        self._recompute_routing(app, {"id": session["user"]["id"], "role": session["role"]},
                                "route recalculated after a policy deviation was recorded")
        return self._workspace_save(app, session, "deviation_added", f"{d['id']} {dev_type}: {description[:200]}")

    # R1: the concurrences the calculated authority requires, and the committee's route reapproval
    @staticmethod
    def _concurrences_needed(app: dict, step_id: str) -> list:
        route = app.get("routing") or {}
        if step_id == "ip_sanction":
            return route.get("preliminary_concurrences") or []
        if step_id == "ap_sanction":
            return route.get("final_concurrences") or []
        return []

    CONCURRENCE_ROLES = {"evp_note": "evp_recommender", "crp_note": "crp_vp",
                         "executive_note": "dmd", "board_intimation": "sanction_committee"}

    def concurrences_view(self, application_id: str, session: dict) -> dict:
        app = self._require(application_id)
        route = app.get("routing") or {}
        needed = rt_routing.required_concurrences(app, app.get("step_id") or "")
        if not needed and route:
            needed = route.get("final_concurrences") or route.get("preliminary_concurrences") or []
        recs = app.get("concurrences") or []
        return {"route": rt_routing.public_route(route),
                "concurrences": [{"required": n, "recorded": next((r for r in recs if r["id"] == n["id"]), None)}
                                  for n in needed],
                "reapproval_required": bool(route.get("reapproval_required")),
                "routing_ack": app.get("routing_ack") or None,
                "can_record": {n["id"]: (session and session["role"] == self.CONCURRENCE_ROLES.get(n["id"]))
                                for n in needed}}

    def record_concurrence(self, application_id: str, session: dict, raw: dict) -> dict:
        """A concurrence is a standalone credit decision by the role that owns it — available at any
        in-progress stage (the note is often signed before the committee meets), not limited to the
        step's current holder."""
        app = self._require(application_id)
        if app.get("status") in TERMINAL or not app.get("step_id"):
            raise ConflictError("Concurrence records are not available on a completed application")
        cid = str(raw.get("concurrence_id") or "").strip()
        if cid not in self.CONCURRENCE_ROLES:
            raise InvalidRequestError(f"Unknown concurrence '{cid}' (one of {', '.join(self.CONCURRENCE_ROLES)})")
        if session["role"] != self.CONCURRENCE_ROLES[cid]:
            raise ForbiddenError(f"The {cid.replace('_', ' ')} concurrence is recorded by the "
                                 f"{self._wf(app).roles.get(self.CONCURRENCE_ROLES[cid])} role")
        route = app.get("routing") or {}
        required = rt_routing.required_concurrences(app, app.get("step_id") or "")
        if not any(c["id"] == cid for c in (required or route.get("final_concurrences")
                                            or route.get("preliminary_concurrences") or [])):
            raise InvalidRequestError(f"The calculated route for this case does not require the {cid.replace('_', ' ')} concurrence")
        remarks = str(raw.get("remarks") or "").strip()
        if not remarks:
            raise InvalidRequestError("The concurrence needs its remarks (what was concurred to)")
        at = (str(raw.get("at") or "").strip() or self.now().isoformat(timespec="seconds"))
        recs = app.setdefault("concurrences", [])
        prev = next((r for r in recs if r["id"] == cid), None)
        rec = {"id": cid, "role": session["role"], "by": session["user"]["id"],
               "by_name": session["user"]["name"], "remarks": remarks[:1000],
               "evidence": (str(raw.get("evidence") or "").strip() or None),
               "approved_at": at, "supersedes": prev.get("approved_at") if prev else None}
        recs.append(rec)
        self.store.save(app, self._event(app, "concurrence_recorded", actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=app.get("step_id"), to_step=app.get("step_id"), at=self._dt(at),
                                         detail={"concurrence_id": cid}))
        return self.get(application_id, session)

    @staticmethod
    def _dt(iso: str) -> datetime:
        try:
            return datetime.fromisoformat(iso)
        except ValueError:
            return datetime.now()

    def acknowledge_route(self, application_id: str, session: dict, remarks: str) -> dict:
        """The sanction committee's reapproval after a material route change (R1)."""
        app = self._require(application_id)
        route = app.get("routing") or {}
        if not route.get("reapproval_required"):
            raise ConflictError("No material route change is outstanding — nothing to reapprove")
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.role != route.get("sanction_role", "sanction_committee") or session["role"] != step.role:
            raise ForbiddenError("Only the sanction committee can acknowledge the changed route")
        if not (remarks or "").strip():
            raise InvalidRequestError("The reapproval needs remarks (why the new authority is appropriate)")
        at = self.now().isoformat(timespec="seconds")
        app["routing_ack"] = {"by": session["user"]["id"], "by_name": session["user"]["name"],
                              "role": session["role"], "at": at, "remarks": remarks.strip()[:1000]}
        route["reapproval_required"] = False
        route["status"] = "reapproved"
        self.store.save(app, self._event(app, "route_reapproved", actor={"id": session["user"]["id"], "role": session["role"]},
                                         from_step=step.id, to_step=step.id, at=self.now(), comment=remarks,
                                         detail={"route": rt_routing.public_route(route)}))
        return self.get(application_id, session)

    UNIT_VISIT_STEPS = ("ap_note", "ap_risk_maker")
    SOURCING_DETAIL_STEPS = ("ps_maker", "ip_note")

    def save_unit_visit(self, application_id: str, session: dict, raw: dict) -> dict:
        """Unit Visit Details (G-F1 / F-4): add a visit, or remove one with a reason. At the AP makers."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Unit visits")
        if app["step_id"] not in self.UNIT_VISIT_STEPS:
            raise ForbiddenError("Unit visits are recorded at Application Note Processing or the Risk Maker step")
        visits = app.setdefault("unit_visits", [])
        if raw.get("action") == "remove":
            v = next((x for x in visits if x["visit_id"] == raw.get("visit_id")), None)
            if not v:
                raise InvalidRequestError(f"Unknown unit visit {raw.get('visit_id')}")
            visits.remove(v)
            return self._workspace_save(app, session, "unit_visit_removed", v["visit_id"])
        visit = prop_mod.normalise_unit_visit({"entity_name": app.get("borrower_name"), **raw}, len(visits) + 1)
        visit.update(recorded_by=session["user"]["name"], recorded_at=self.now().isoformat(timespec="seconds"))
        visits.append(visit)
        return self._workspace_save(app, session, "unit_visit_added",
                                    f"{visit['visit_id']} {visit['date_of_visit']}: {visit['observation']}")

    def save_sourcing_details(self, application_id: str, session: dict, raw: dict) -> dict:
        """Sourcing details (F-5): received date, source, branch, owners, Sol ID, sub-sub-sector, LPFG analysts."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Sourcing details")
        if app["step_id"] not in self.SOURCING_DETAIL_STEPS:
            raise ForbiddenError("Sourcing details are kept at Prospect Sourcing and IP Note Processing")
        app["sourcing_details"] = prop_mod.normalise_sourcing_details(raw, app.get("sourcing_details") or {})
        return self._workspace_save(app, session, "sourcing_details", "Sourcing details updated")

    # ── R4: the full prospect-sourcing field set ──────────────────────────
    PROSPECT_LEAD_SOURCES = ("rm_sourced", "referral", "walk_in", "digital", "channel_partner", "existing_customer")
    PROSPECT_STATUSES = ("new", "engaged", "proposal_stage", "sanctioned", "closed_won", "closed_lost", "dormant")
    DISCUSSION_STATUSES = ("positive", "neutral", "hold", "negative")

    def _prospect_record(self, app: dict) -> dict:
        p = app.get("prospect") or {}
        fac = app.get("facility") or {}
        return {"request_currency": p.get("request_currency") or fac.get("currency") or "INR",
                "infra_qualified": bool(p.get("infra_qualified")),
                "lead_source": p.get("lead_source"),
                "prospect_status": p.get("prospect_status") or "new",
                "next_follow_up": p.get("next_follow_up"),
                "discussions": p.get("discussions") or []}

    def update_prospect(self, session: dict, application_id: str, raw: dict) -> dict:
        """The RM's prospect fields: currency, infra qualification, lead source, status,
        next follow-up. Only the sourcing maker edits; values are validated."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Prospect details")
        if app["step_id"] not in SOURCING_STEPS:
            raise ForbiddenError("Prospect details are kept at the sourcing steps")
        p = app.setdefault("prospect", {})
        if raw.get("request_currency") not in (None, ""):
            cur = str(raw["request_currency"] or "").strip().upper()
            if not (cur and len(cur) == 3 and cur.isalpha()):
                raise InvalidRequestError("The request currency must be a 3-letter code (e.g. INR)")
            p["request_currency"] = cur
        if "infra_qualified" in raw:
            p["infra_qualified"] = bool(raw["infra_qualified"])
        if "lead_source" in raw and raw["lead_source"] not in (None, ""):
            src = profiles.get_profile(app=app).get("prospect", {}).get("lead_sources") or list(self.PROSPECT_LEAD_SOURCES)
            if raw["lead_source"] not in src:
                raise InvalidRequestError(f"Lead source must be one of {', '.join(src)}")
            p["lead_source"] = raw["lead_source"]
        if "prospect_status" in raw and raw["prospect_status"] not in (None, ""):
            if raw["prospect_status"] not in self.PROSPECT_STATUSES:
                raise InvalidRequestError(f"Prospect status must be one of {', '.join(self.PROSPECT_STATUSES)}")
            p["prospect_status"] = raw["prospect_status"]
        if "next_follow_up" in raw and raw["next_follow_up"] not in (None, ""):
            try:
                p["next_follow_up"] = datetime.fromisoformat(str(raw["next_follow_up"])[:10]).date().isoformat()
            except ValueError:
                raise InvalidRequestError("The next follow-up must be a date (YYYY-MM-DD)")
        p["updated_at"] = self.now().isoformat(timespec="seconds")
        p["updated_by"] = session["user"]["name"]
        return self._workspace_save(app, session, "prospect_updated", "Prospect details updated")

    def add_prospect_discussion(self, session: dict, application_id: str, raw: dict) -> dict:
        """A dated prospect discussion (participants, status, notes). Records append —
        the application keeps its discussion history."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Prospect details")
        if app["step_id"] not in SOURCING_STEPS:
            raise ForbiddenError("Prospect discussions are recorded at the sourcing steps")
        try:
            d = datetime.fromisoformat(str(raw.get("date") or "")[:10]).date()
        except ValueError:
            raise InvalidRequestError("A discussion date (YYYY-MM-DD) is required")
        if d > self.now().date():
            raise InvalidRequestError("A discussion date cannot be in the future")
        status = str(raw.get("status") or "").strip().lower()
        if status not in self.DISCUSSION_STATUSES:
            raise InvalidRequestError(f"Discussion status must be one of {', '.join(self.DISCUSSION_STATUSES)}")
        p = app.setdefault("prospect", {})
        ds = p.setdefault("discussions", [])
        rec = {"id": f"PD-{len(ds) + 1:03d}", "date": d.isoformat(),
               "participants": (str(raw.get("participants") or "").strip() or None),
               "status": status, "notes": (str(raw.get("notes") or "").strip() or None)[:4000],
               "by": session["user"]["name"], "at": self.now().isoformat(timespec="seconds")}
        ds.append(rec)
        return self._workspace_save(app, session, "prospect_discussion_added", rec["id"])

    def save_security_notes(self, application_id: str, session: dict, raw: dict) -> dict:
        """The AP security remarks (F-9), recorded against the agent's drafts."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Security remarks")
        notes = app.setdefault("security_notes", {})
        for key in prefill.SECURITY_NOTES:
            if key in raw:
                notes[key] = (str(raw[key] or "").strip() or None)
        self._mirror_paths(app, ["security_notes"], session, "in the security remarks")
        return self._workspace_save(app, session, "security_notes", "Security remarks updated")

    def save_decision_note(self, application_id: str, session: dict, key: str, text: str) -> dict:
        """A decision-tab narrative (F-2): the agent's draft confirmed or rewritten by the maker."""
        app = self._require(application_id)
        self._workspace_may(app, session, "The decision notes")
        if app["step_id"] not in self.DEVIATION_STEPS:
            raise ForbiddenError("The decision notes are written at the IP / AP Note and the Risk Maker steps")
        if key not in prefill.DECISION_NOTES:
            raise InvalidRequestError(f"Unknown decision note {key}")
        app.setdefault("decision_notes", {})[key] = (str(text or "").strip() or None)
        self._mirror_paths(app, ["decision_notes", key], session, "on the decision tab")
        return self._workspace_save(app, session, "decision_note", f"{prefill.DECISION_NOTES[key]}")

    def _decision_defaults(self, app: dict, step) -> dict:
        """G-W6: the decision record carried forward — the latest value of each of this step's decision fields
        recorded earlier in the same stage, for the person to confirm or change."""
        out = {}
        stage = step.stage_id
        for rec in reversed(app.get("decisions") or []):
            try:
                if self._wf(app).step(rec["step"]).stage_id != stage:
                    continue
            except Exception:
                continue
            for f in step.decision_fields:
                if f["id"] not in out and rec.get(f["id"]):
                    out[f["id"]] = rec[f["id"]]
        return out

    # Terms & conditions authored at AP (G-F2), drafted by the T&C agent (R-P2)
    def terms(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        t = app.get("terms") or terms_mod.initial_terms()
        fields = app.get("fields") or {}
        rows = []
        for r in t.get("conditions") or []:
            fid = f"{terms_mod.DOMAIN}.{r['agent_key']}.text" if r.get("agent_key") else None
            rec = (fields.get(fid) or {}) if fid else {}
            rows.append({**r, "category_label": terms_mod.CATEGORIES.get(r["category"], r["category"]),
                         "field_id": fid if rec else None, "field_status": rec.get("status"),
                         "proposed_text": (rec.get("proposal") or {}).get("value"),
                         "evidence": (rec.get("proposal") or {}).get("evidence")})
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        editable = bool(step and step.id in terms_mod.AUTHOR_STEPS and t.get("status") != "sanctioned"
                        and app.get("status") not in TERMINAL and session
                        and can_act(self._wf(app), session["user"]["id"], session["role"], step))
        return {"rows": rows, "summary": terms_mod.summary(t, fields), "status": t.get("status", "draft"),
                "locked_at": t.get("locked_at"), "locked_by": t.get("locked_by"), "editable": editable,
                "categories": terms_mod.CATEGORIES, "frequencies": list(terms_mod.FREQUENCIES),
                "gate": terms_mod.submit_gate(t, fields) if t.get("conditions") else None,
                "author_step": "Application Note Processing (AP maker)"}

    def save_term(self, application_id: str, session: dict, raw: dict) -> dict:
        """add | update | remove | restore a term & condition. Editing the text of an agent's draft is an
        override of its field (a reason is required); a person's own row is edited directly."""
        app = self._require(application_id)
        self._workspace_may(app, session, "The terms & conditions")
        step = self._wf(app).step(app["step_id"])
        if step.id not in terms_mod.AUTHOR_STEPS:
            raise ForbiddenError("The terms & conditions are authored at Application Note Processing (AP maker)")
        t = app.setdefault("terms", terms_mod.initial_terms())
        if t.get("status") == "sanctioned":
            raise ConflictError("The terms & conditions are locked at final sanction")
        rows, action = t.setdefault("conditions", []), str(raw.get("action") or "add")
        facilities = {f["facility_id"] for f in app.get("facilities") or []}
        at, name = self.now().isoformat(timespec="seconds"), session["user"]["name"]
        if action == "add":
            row = terms_mod.normalise_row(raw, facilities)
            row.update(term_id=terms_mod.next_id(rows), origin="person", provenance="person",
                       source=f"Added by {name}", history=[{"at": at, "by": name, "change": "added"}])
            rows.append(row)
            return self._workspace_save(app, session, "term_added", f"{row['term_id']} {row['category']}: {row['text'][:200]}")
        row = next((r for r in rows if r.get("term_id") == raw.get("term_id")), None)
        if not row:
            raise InvalidRequestError(f"Unknown term {raw.get('term_id')}")
        if action in ("remove", "restore"):
            reason = str(raw.get("reason") or "").strip()
            if action == "remove" and not reason:
                raise InvalidRequestError("Give a reason for removing the condition")
            row.update(removed=action == "remove", removed_reason=reason or None)
            row.setdefault("history", []).append({"at": at, "by": name, "change": action, "reason": reason or None})
            return self._workspace_save(app, session, f"term_{action}d", f"{row['term_id']}: {reason or 'restored'}")
        if action != "update":
            raise InvalidRequestError("Action must be add, update, remove or restore")
        new_text = str(raw.get("text") or "").strip() or row.get("text")
        text_changed = new_text != row.get("text")
        if text_changed and row.get("origin") == "agent" and not str(raw.get("reason") or "").strip():
            raise InvalidRequestError("Give a reason for changing the agent's drafted text")
        updated = terms_mod.normalise_row({**raw, "text": row.get("text")}, facilities, row)
        row.update({k: updated[k] for k in ("category", "facility_id", "frequency", "stipulated_value", "party")})
        row.setdefault("history", []).append({"at": at, "by": name, "change": "updated" + (" text" if text_changed else "")})
        if text_changed and row.get("origin") == "agent":
            self.store.save(app, self._event(app, "term_updated", actor={"id": session["user"]["id"], "role": session["role"]},
                                             from_step=step.id, to_step=step.id, comment=row["term_id"]))
            self._apply_field_actions(application_id, session, [{
                "field_id": f"{terms_mod.DOMAIN}.{row['agent_key']}.text", "action": "override", "value": new_text,
                "reason": str(raw.get("reason")).strip()}], event="fields_verified")
            return self.get(application_id, session)
        if text_changed:
            row["text"] = new_text
        return self._workspace_save(app, session, "term_updated", f"{row['term_id']}: {row['text'][:200]}")

    def compute_raroc(self, application_id: str, session: dict, facility_id: Optional[str] = None) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "RAROC")
        case, _ = self._app_case(app)
        ratings = app.setdefault("ratings", rat.initial_ratings(app, self.companies))
        target_ids = [facility_id] if facility_id else [f["facility_id"] for f in app.get("facilities", [])]
        computed = []
        for fid in target_ids:
            entry = rat.compute_raroc(app, fid, case, self.now().isoformat(timespec="seconds"), session["user"]["name"])
            ratings.setdefault("raroc", {})[fid] = entry
            computed.append(fid)
        return self._workspace_save(app, session, "raroc_computed", ", ".join(computed))

    def save_crp_note(self, application_id: str, session: dict, raw: dict, review: bool = False) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "CRP notes", review=True)
        ratings = app.setdefault("ratings", rat.initial_ratings(app, self.companies))
        notes = ratings.setdefault("crp_notes", [])
        if review:
            note = next((n for n in notes if n.get("kind") == raw.get("kind") and n.get("title") == raw.get("title")
                         and n["status"] == "uploaded"), None)
            if not note:
                raise InvalidRequestError("No uploaded CRP note matches that kind and title")
            note.update(status="reviewed", reviewed_by=session["user"]["name"],
                        reviewed_at=self.now().isoformat(timespec="seconds"),
                        remarks=(str(raw.get("remarks") or "").strip() or None))
            self._workspace_save(app, session, "crp_note_reviewed", f"{note['kind']}: {note['title']}")
        else:
            entry = rat.crp_note_entry(raw)
            entry.update(uploaded_by=session["user"]["name"], uploaded_at=self.now().isoformat(timespec="seconds"))
            notes.append(entry)
            self._workspace_save(app, session, "crp_note_uploaded", f"{entry['kind']}: {entry['title'] or entry['file_name']}")
        return self.get(application_id, session)

    # CMA (GAP-P0-07)
    def record_cma(self, application_id: str, session: dict, subject: str, rows: dict, value_class: str = "audited") -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The CMA workspace")
        if subject not in cma_mod.CMA_SUBJECTS:
            raise InvalidRequestError(f"CMA subject must be one of {', '.join(cma_mod.CMA_SUBJECTS)}")
        if value_class not in cma_mod.VALUE_CLASSES:
            raise InvalidRequestError(f"Value class must be one of {', '.join(cma_mod.VALUE_CLASSES)}")
        cma = app.setdefault("cma", cma_mod.initial_cma())
        parsed = cma_mod.normalise_rows(rows, subject)
        subjects = cma.setdefault("subjects", [])
        entry = next((s for s in subjects if s["subject"] == subject), None)
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        if not entry:
            entry = {"subject": subject, "rows": {}, "versions": []}
            subjects.append(entry)
        for period, vals in parsed.items():
            entry["rows"].setdefault(period, {}).update(vals)
        entry["versions"].append({"v": len(entry["versions"]) + 1, "by": session["user"]["name"], "at": at,
                                  "value_class": value_class, "periods": sorted(parsed.keys()),
                                  "highlights": {p: cma_mod.highlights(v) for p, v in parsed.items()}})
        if cma.get("review_status") == "approved":
            cma["review_status"] = "submitted"          # a change after approval needs review again
        if cma.get("review_status") in (None, "draft"):
            cma["review_status"] = "submitted"
        # The CMA download is a registry output (GAP-P1-06).
        dreg.register_generated(app.setdefault("documents", []), name="CMA (prepared in the CMA workspace)",
                                kind="cma_download", by_name=session["user"]["name"], at=at, detail=subject)
        self._workspace_save(app, session, "cma_recorded", f"CMA {subject}: {', '.join(sorted(parsed.keys()))}")
        return self.get(application_id, session)

    def review_cma(self, application_id: str, session: dict, approve: bool, remarks: str = "") -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "CMA review", review=True)
        cma = app.setdefault("cma", cma_mod.initial_cma())
        if not cma.get("subjects"):
            raise InvalidRequestError("There is no CMA entry to review")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        cma["review_status"] = "approved" if approve else "returned"
        cma["review_by"], cma["review_at"], cma["review_remarks"] = session["user"]["name"], at, (remarks or None)
        self._workspace_save(app, session, "cma_reviewed", f"CMA {'approved' if approve else 'returned'}")
        return self.get(application_id, session)

    # proposal / exposure / banking / conduct (GAP-P0-09)
    def update_proposal(self, application_id: str, session: dict, section: str, payload: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The proposal workspace")
        proposal = app.setdefault("proposal", prop_mod.initial_proposal(app, (self.companies.get(app["entity_id"]) or {})))
        if section == "summary" or section == "background":
            if app["step_id"] not in ("ip_note", "ap_note", "ap_risk_maker"):
                raise ForbiddenError("The proposal narratives are written at the IP / AP Note and the Risk Maker steps")
            for k, v in dict(payload or {}).items():
                proposal[section][k] = (str(v).strip() or None) if isinstance(v, str) else v
            self._mirror_paths(app, ["proposal", section], session, "in the proposal")
        elif section == "exposure":
            proposal["exposure"].update(prop_mod.normalise_exposure(payload))
        elif section == "banking":
            proposal["banking"] = prop_mod.normalise_banking(payload)
            stuck = prop_mod.banking_gate(proposal["banking"])
            if stuck:
                raise InvalidRequestError(stuck)
        elif section == "conduct":
            proposal["conduct"]["rows"] = prop_mod.normalise_conduct(payload.get("rows") or [])
        elif section == "compliance":
            proposal["compliance"] = {"rows": [str(x).strip() for x in payload.get("rows") or [] if str(x).strip()],
                                      "non_compliance_justification":
                                          (str(payload.get("non_compliance_justification") or "").strip() or None)}
        elif section == "inter_firm":
            proposal["inter_firm"] = prop_mod.normalise_inter_firm(payload.get("rows") or [])
        elif section in ("write_off_losses", "connected_lending", "annexure_vi", "annexure_xiii", "annexure_xiv"):
            proposal[section] = (str(payload.get("text") or "").strip() or None)
        elif section == "applicable_conditions":
            for k in ("esg", "listed_company", "insurance", "other"):
                if k in payload:
                    proposal["applicable_conditions"][k] = (str(payload[k]).strip() or None) if payload[k] else None
        else:
            raise InvalidRequestError(f"Unknown proposal section: {section}")
        return self._workspace_save(app, session, "proposal_update", f"proposal: {section}")

    def fetch_exposure(self, application_id: str, session: dict, kind: str) -> dict:
        """Fetch Bond / Loan Exposure — labelled demo source (GAP-P0-17)."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Exposure fetch")
        if kind not in ("bond", "loan"):
            raise InvalidRequestError("kind must be bond or loan")
        from src.services import adapters
        company = self.companies.get(app["entity_id"]) or {}
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        if kind == "loan":
            rows = (company.get("existing_exposure") or [])
            total = round(sum(r.get("outstanding_cr") or 0 for r in rows if isinstance(r, dict)), 2)
            breakdown = [{"name": r.get("bank") or r.get("name") or f"{i + 1}", "cr": r.get("outstanding_cr")}
                         for i, r in enumerate(rows) if isinstance(r, dict)] or None
            state = "demo_data" if rows else "unavailable"
        else:
            state = "unavailable"                      # FT is not connected in the demo
            total, breakdown = None, None
        adapters.invoke("ft" if kind == "bond" else "lms", request={"entity_id": app["entity_id"], "kind": kind},
                        response={"total_cr": total, "rows": len(breakdown or [])}, status=state,
                        provider_ref=f"demo-{app['entity_id']}-{kind}")
        proposal = app.setdefault("proposal", prop_mod.initial_proposal(app, company))
        proposal["exposure"][kind] = {"total_cr": total, "breakdown": breakdown, "fetched_at": at,
                                      "fetched_by": session["user"]["name"],
                                      "source": "Core banking (demo data)" if kind == "loan" else "FT (not connected — demo)",
                                      "status": "fetched" if state == "demo_data" else "unavailable"}
        return self._workspace_save(app, session, "exposure_fetched", f"{kind} exposure: "
                                    + (f"₹{total:,.2f} Cr (demo)" if total is not None else "unavailable"))

    # ── R10: condition / covenant indicators and the waiver authority ─────
    def condition_indicators(self, application_id: str) -> dict:
        """R10: the post-sanction condition indicators — open, overdue, breached, waived
        (with the waiver's authority and expiry) and pending — plus the covenant testing state."""
        app = self._require(application_id)
        today = self.now().date().isoformat()
        out = {"open": 0, "overdue": 0, "breached": 0, "waived": 0, "pending_approval": 0,
               "satisfied": 0, "deferred": 0, "covenants": {"open": 0, "pass": 0, "fail": 0, "cured": 0}}
        for c in app.get("conditions") or []:
            st = c.get("status")
            if st == "open":
                out["open"] += 1
                if c.get("due") and c["due"] < today:
                    out["overdue"] += 1
            elif st == "non_compliant":
                out["breached"] += 1
            elif st == "waived":
                out["waived"] += 1
            elif st == "satisfied":
                out["satisfied"] += 1
            elif st == "deferred":
                out["deferred"] += 1
                if c.get("due") and c["due"] < today:
                    out["overdue"] += 1
            if st in ("deferred", "waived") and not (c.get("approval") or {}).get("by"):
                out["pending_approval"] += 1
        for c in app.get("conditions") or []:
            if c.get("type") in ("FC", "NC", "CS", "PD"):
                mon = c.get("monitoring") or {}
                compliance = mon.get("compliance") if isinstance(mon, dict) else None
                if c.get("status") == "non_compliant" or compliance == "breached":
                    out["covenants"]["fail"] += 1
                elif compliance == "cured" or (isinstance(mon.get("cure"), dict)):
                    out["covenants"]["cured"] += 1
                elif compliance == "compliant":
                    out["covenants"]["pass"] += 1
                else:
                    out["covenants"]["open"] += 1
        out["as_of"] = self.now().date().isoformat()
        return out

    # ── R12: group exposure ───────────────────────────────────────────────
    def group_exposure(self, application_id: str, session: Optional[dict] = None) -> dict:
        """The group / connected-party exposure: the group's entities and their existing
        funded / non-funded exposure, the product split, the security allocation, the
        institution's group-exposure norm, the headroom and the breach flag. The proposed
        request is included in the total. Seeded demo model (no real integrations)."""
        app = self._require(application_id)
        company = self.companies.get(app["entity_id"]) or {}
        group = company.get("group") or {}
        group_id = getattr(group, "group_id", None) or f"GRP-{app['entity_id']}"
        group_name = getattr(group, "group_name", None) or app.get("borrower_name")
        parent = getattr(group, "parent_entity_id", None) or app["entity_id"]
        entities_ids = list(getattr(group, "entities", None) or [app["entity_id"]])
        if app["entity_id"] not in entities_ids:
            entities_ids.append(app["entity_id"])
        # seeded related entities: the parent's reference subsidiaries (deterministic demo)
        rel = self._group_related_entities(app["entity_id"])
        for r in rel:
            if r["entity_id"] not in entities_ids:
                entities_ids.append(r["entity_id"])
        fin = company.get("financials") or {}
        net_worth = None
        try:
            # the latest available statement year (the financials are keyed FY...)
            years = sorted(k for k in fin if isinstance(k, str) and k.startswith("FY"))
            if years:
                stmt = fin[years[-1]]
                items = getattr(stmt, "line_items", None) or (stmt if isinstance(stmt, dict) else {})
                net_worth = float(items.get("total_equity") or 0) or None
        except Exception:
            net_worth = None
        prof = profiles.get_profile(app=app)
        exp_cfg = (prof.get("exposure") or {})
        norm_pct = float(exp_cfg.get("group_limit_pct") or 0) or None
        norm_abs = float(exp_cfg.get("group_limit_cr") or 0) or None
        limit = (net_worth * norm_pct / 100.0) if (net_worth and norm_pct) else norm_abs
        entities = []
        total_funded = 0.0
        total_non_funded = 0.0
        product_totals: dict = {}
        for eid in entities_ids:
            c = self.companies.get(eid) or (company if eid == app["entity_id"] else {})
            borrower = c.get("borrower")
            name = getattr(borrower, "company_name", None) or eid
            rows = c.get("existing_exposure") or []
            funded = round(sum(float(getattr(r, "outstanding_cr", 0) or 0) for r in rows), 2)
            non_funded = round(sum(float(getattr(r, "sanctioned_limit_cr", 0) or 0) - float(getattr(r, "outstanding_cr", 0) or 0)
                                   for r in rows if float(getattr(r, "sanctioned_limit_cr", 0) or 0) > float(getattr(r, "outstanding_cr", 0) or 0)), 2)
            for r in rows:
                ft = getattr(r, "facility_type", None) or "facility"
                product_totals[ft] = round(product_totals.get(ft, 0.0) + float(getattr(r, "outstanding_cr", 0) or 0), 2)
            entities.append({"entity_id": eid, "name": name,
                             "funded_cr": funded, "non_funded_cr": max(non_funded, 0.0),
                             "is_borrower": eid == app["entity_id"],
                             "is_parent": eid == parent})
            total_funded = round(total_funded + funded, 2)
            total_non_funded = round(total_non_funded + max(non_funded, 0.0), 2)
        proposed = float(app.get("amount_cr") or 0)
        for ft in (f.get("facility_type") for f in (app.get("facilities") or [])):
            if ft:
                product_totals[ft] = round(product_totals.get(ft, 0.0) + 0.0, 2)
        product_split = [{"facility_type": k, "cr": v} for k, v in sorted(product_totals.items())]
        # security: the proposal's security cover (deterministic demo model)
        sec_value = round(proposed * 1.25, 2)
        # the seeded related entities carry their demo exposure into the group total
        related_funded = round(sum(float(r.get("exposure_cr") or 0) for r in rel), 2)
        total_exposure = round(total_funded + total_non_funded + related_funded + proposed, 2)
        headroom = round(limit - total_exposure, 2) if limit else None
        breach = bool(limit and total_exposure > limit + 1e-9)
        connected = []
        for d in (company.get("directors") or []):
            nm = getattr(d, "name", None)
            if nm:
                connected.append({"name": nm, "relationship": "director"})
        for r in rel:
            if r.get("relationship"):
                connected.append({"name": r.get("name") or r["entity_id"],
                                  "relationship": r["relationship"],
                                  "exposure_cr": r.get("exposure_cr")})
        return {"application_id": application_id,
                "group_id": group_id, "group_name": group_name,
                "entities": entities,
                "connected_parties": connected,
                "total_existing_funded_cr": total_funded,
                "total_existing_non_funded_cr": total_non_funded,
                "proposed_cr": proposed,
                "total_funded_cr": round(total_funded + (proposed if (app.get("facility") or {}).get("facility_nature") == "fund_based" else 0.0), 2),
                "total_non_funded_cr": total_non_funded,
                "total_exposure_cr": total_exposure,
                "product_split": product_split,
                "security": {"allocation": "first charge on the proposed facility (demo model)",
                             "covered_cr": sec_value},
                "norm": {"basis": ("group net worth × {:.0f}%".format(norm_pct) if (net_worth and norm_pct)
                                    else ("absolute cap" if norm_abs else "not configured")),
                         "limit_cr": round(limit, 2) if limit else None,
                         "net_worth_cr": net_worth},
                "headroom_cr": headroom, "breach": breach,
                "as_of": self.now().date().isoformat(),
                "source": "Seeded group model (demo data — no live core-banking connection)"}

    def _group_related_entities(self, entity_id: str) -> list[dict]:
        """The borrower's seeded related entities (deterministic demo model)."""
        company = self.companies.get(entity_id) or {}
        borrower = company.get("borrower")
        name = getattr(borrower, "company_name", None) or entity_id
        short = (name.split()[0] if name else entity_id)[:20]
        return [
            {"entity_id": f"{entity_id}-SUB1", "name": f"{short} Metals (demo)", "relationship": "subsidiary",
             "exposure_cr": 25.0},
            {"entity_id": f"{entity_id}-SUB2", "name": f"{short} Agro (demo)", "relationship": "subsidiary",
             "exposure_cr": 12.5},
            {"entity_id": f"{entity_id}-RP1", "name": f"{short} Holdings (demo)", "relationship": "promoter group",
             "exposure_cr": 40.0},
        ]

    # pricing / fees / tentative schedule (GAP-P1-04)
    def record_pricing(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Pricing records")
        pricing = app.setdefault("pricing", pricing_mod.initial_pricing())
        f = next((x for x in app.get("facilities", []) if x["facility_id"] == raw.get("facility_id")), None)
        if not f:
            raise InvalidRequestError(f"Unknown facility: {raw.get('facility_id')}")
        entry = pricing_mod.normalise_pricing_entry(raw, f)
        pricing.setdefault("facilities", {})[f["facility_id"]] = entry
        if raw.get("other_banks_comparison") is not None:
            pricing["other_banks_comparison"] = str(raw["other_banks_comparison"]).strip() or None
        if raw.get("justification") is not None:
            pricing["justification"] = str(raw["justification"]).strip() or None
        pricing["change_alert"] = pricing_mod.pricing_change_alert(app, pricing)
        return self._workspace_save(app, session, "pricing_recorded", f"{f['facility_id']} pricing")

    def record_fee(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Fee records")
        pricing = app.setdefault("pricing", pricing_mod.initial_pricing())
        fee = pricing_mod.normalise_fee(raw, len(pricing.get("fees", [])) + 1)
        pricing.setdefault("fees", []).append(fee)
        return self._workspace_save(app, session, "fee_recorded", f"{fee['nature']} {fee['type'] or ''}".strip())

    def record_tentative_schedule(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The tentative schedule")
        pricing = app.setdefault("pricing", pricing_mod.initial_pricing())
        known = {f["facility_id"] for f in app.get("facilities", [])}
        pricing.setdefault("tentative_schedules", []).extend(
            pricing_mod.normalise_tentative_schedule(raw, len(pricing["tentative_schedules"]) + 1, known))
        return self._workspace_save(app, session, "tentative_schedule", "tentative term-loan schedule")

    # disbursement operational record (GAP-P0-15)
    def update_disops(self, application_id: str, session: dict, section: str, payload: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The disbursement record")
        disops = app.setdefault("disops", {"sop": do.initial_sop()})
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        if section == "cif":
            disops["cif"] = do.normalise_cif(payload)
        elif section == "limits":
            disops["limits"] = do.normalise_limits(payload.get("rows") or [])
        elif section == "loan_accounts":
            disops["loan_accounts"] = do.normalise_loan_accounts(payload.get("rows") or [])
        elif section == "security_refs":
            disops["security_refs"] = do.normalise_security_refs(payload.get("rows") or [])
        elif section == "beneficiaries":
            disops["beneficiaries"] = do.normalise_beneficiaries(payload.get("rows") or [])
            first = disops["beneficiaries"][0]
            self._mirror_entries(app, "disbursement", {"beneficiary_name": first.get("name"),
                                                       "account_number": first.get("account_no"),
                                                       "ifsc": first.get("ifsc")}, session, "recording the beneficiary")
        elif section == "fees":
            disops["fees"] = do.normalise_fees(payload.get("rows") or [])
        elif section == "non_fund_charges":
            disops["non_fund_charges"] = do.normalise_non_fund_charges(payload)
        elif section == "repayment_final":
            disops["repayment_final"] = do.normalise_repayment_final(payload)
        elif section == "interest_terms":
            disops["interest_terms"] = do.normalise_interest_terms(payload)
        elif section == "arrears":
            disops["arrears"] = do.normalise_arrears(payload)
        elif section == "drawdown":
            disops["drawdown"] = do.normalise_drawdown(payload)
        elif section == "sop":
            current = disops.get("sop") or do.initial_sop()
            disops["sop"] = do.normalise_sop(payload.get("items") or [], current)
            for item in disops["sop"]:
                if item.get("status") and not item.get("at"):
                    item.update(by_name=session["user"]["name"], at=at)
        elif section == "external_rating_retrigger":
            disops["external_rating_retrigger"] = {"at": at, "by_name": session["user"]["name"],
                                                   "result": (str(payload.get("result") or "").strip() or None)}
        elif section == "missing_info":
            field = (str(payload.get("field") or "").strip() or None)
            value = (str(payload.get("value") or "").strip() or None)
            if not field:
                raise InvalidRequestError("The missing-information field is required")
            disops.setdefault("missing_info", []).append({"field": field, "value": value or None,
                                                          "by_name": session["user"]["name"], "at": at})
        elif section == "exposure":
            disops["exposure"] = {"total_cr": _num_or_none(payload.get("total_cr")),
                                  "fund_based_cr": _num_or_none(payload.get("fund_based_cr")),
                                  "non_fund_cr": _num_or_none(payload.get("non_fund_cr"))}
        else:
            raise InvalidRequestError(f"Unknown disbursement section: {section}")
        if section in carry_forward.SECTIONS:      # the maker's values recorded against the carry-forward agent's
            self._mirror_carry(app, section, session)
        return self._workspace_save(app, session, "disops_update", f"disbursement record: {section}")

    def generate_memo(self, application_id: str, session: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The Disbursement Memo")
        disops = app.setdefault("disops", {"sop": do.initial_sop()})
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        disops["memo"] = {"version": 1, "generated_at": at, "generated_by": session["user"]["name"],
                          "content_hash": do.memo_hash(disops), "reviewed": False,
                          "reviewed_by": None, "reviewed_at": None, "review_remarks": None,
                          "note": "The memo freezes the operational record at generation; changes after "
                                  "generation require regeneration."}
        dreg.register_generated(app.setdefault("documents", []), name="Disbursement memo (generated and reviewed)",
                                kind="disbursement_memo", by_name=session["user"]["name"], at=at)
        return self._workspace_save(app, session, "memo_generated", "Disbursement Memo generated")

    def review_memo(self, application_id: str, session: dict, approve: bool, remarks: str = "") -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The Disbursement Memo review", review=True)
        memo = (app.get("disops") or {}).get("memo")
        if not memo:
            raise InvalidRequestError("Generate the Disbursement Memo before reviewing it")
        if do.memo_hash(app.get("disops") or {}) != memo.get("content_hash"):
            raise InvalidRequestError("The operational record changed after the memo was generated — regenerate it")
        memo.update(reviewed=bool(approve), reviewed_by=session["user"]["name"],
                    reviewed_at=self.now().isoformat(timespec="seconds"), review_remarks=(remarks or None))
        if not approve:
            memo["reviewed"] = False
        doc = next((d for d in app.get("documents") or [] if d["name"].startswith("Disbursement memo")), None)
        if doc:
            doc.update(status="reviewed" if approve else "rework", reviewer=session["user"]["name"],
                       reviewed_at=self.now().isoformat(timespec="seconds"))
        self._workspace_save(app, session, "memo_reviewed", f"Memo {'reviewed' if approve else 'returned'}")
        return self.get(application_id, session)

    def update_dis_review(self, application_id: str, session: dict, stage: str, items: list) -> dict:
        """The read-only review checklists of the Disbursement Checker and Final Approver (GAP-P0-16).
        ``items`` are the checklist item IDs the reviewer has verified."""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"])
        if stage == "checker" and step.id != "dis_checker":
            raise ForbiddenError("The checker review is available at the Disbursement Checker step")
        if stage == "final" and step.id != "dis_approver":
            raise ForbiddenError("The final review is available at the Disbursement Approval step")
        disops = app.setdefault("disops", {})
        labels = do.CHECKER_REVIEW_ITEMS if stage == "checker" else do.FINAL_REVIEW_ITEMS
        key = "checker_review" if stage == "checker" else "final_review"
        current = disops.get(key) or do.initial_review(labels)
        for raw in items or []:         # an item ID (verified), or {"id", "done"} to tick or untick
            item_id, done = (raw.get("id"), bool(raw.get("done"))) if isinstance(raw, dict) else (raw, True)
            it = next((i for i in current if i["id"] == str(item_id)), None)
            if not it:
                raise InvalidRequestError(f"Unknown review item: {item_id}")
            it["done"] = done
        disops[key] = current
        self._workspace_save(app, session, f"{key}_update", f"{sum(1 for i in current if i['done'])}/{len(current)} review items verified")
        return self.get(application_id, session)

    def dis_review_gate(self, app: dict) -> Optional[str]:
        view = do.disops_view(app)
        step_id = app.get("step_id")
        if step_id == "dis_checker":
            return do.review_gate(view["checker_review"], "Disbursement Checker")
        if step_id == "dis_approver":
            return do.review_gate(view["final_review"], "Final Disbursement Approval")
        return None

    # documents (GAP-P0-12)
    def review_document(self, application_id: str, session: dict, doc_id: str, status: str, remarks: str = "") -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Document review", review=True)
        doc = dreg.review_document(app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app))), doc_id, status,
                                   session["user"]["name"], self.now().isoformat(timespec="seconds"), remarks)
        return self._workspace_save(app, session, "document_reviewed", f"{doc['name']} → {status}")

    def documents(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        if dreg.link_workspace(app, self.now().isoformat(timespec="seconds")):   # the CMA, once prepared
            self.store.save(app)
        return dreg.registry_view(app)

    # material change review (GAP-P0-11 / P2-02)
    def review_material_changes(self, application_id: str, session: dict, decision: str, remarks: str) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "The material-change review", review=True)
        if not (remarks or "").strip():
            raise InvalidRequestError("Remarks are required for the material-change decision")
        review = snap.review_material_changes(app, decision, session["user"]["name"],
                                              self.now().isoformat(timespec="seconds"), remarks)
        return self._workspace_save(app, session, "material_change_review",
                                    f"{decision} material change(s) in {', '.join(review['domains']) or 'ALL'}")

    def snapshot_view(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        snaps = app.get("snapshots") or []
        return {"refs": [s["ref"] for s in snaps],
                "snapshots": {s["ref"]: {"at": s["at"], "by": s["by"], "seq": s.get("seq"),
                                  "content_hash": s["content_hash"],
                                  "domains": s["domains"], "note": s["note"]}
                              for s in snaps},
                "material_changes": snap.material_changes(app) if snaps else [],
                "gate": snap.material_change_gate(app) if snaps else None,
                "reviews": app.get("material_change_reviews") or []}

    # rules & integrations (GAP-P2-01, P0-17)
    def rules_view(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        return {"rules": rules_mod.evaluate(app), "dependencies": rules_mod.DEPENDENCIES}

    def integrations(self) -> dict:
        from src.services import adapters
        return {"adapters": adapters.view(),
                "note": "Every adapter is labelled with its honest state. Nothing here is a production "
                        "integration; demo data is explicitly labelled (GAP-P0-17)."}

    # generated outputs (GAP-P1-06)
    def generate_output(self, application_id: str, session: dict, kind: str) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Generated outputs", review=True)
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        if kind == "executive_summary":
            name, html = "Executive Summary", self._output_executive_summary(app)
        elif kind == "due_diligence_report":
            name, html = "Customer Due Diligence / Due Diligence Report", self._output_dd_report(app)
        elif kind == "esms_approval_note":
            if not (app.get("esms") or {}).get("checklist"):
                raise InvalidRequestError("Complete the ESMS screen before generating the ESMS Approval Note")
            name, html = "ESMS Approval Note", es.approval_note(app, app.get("esms") or {})
        elif kind == "committee_minutes":
            name, html = "Committee minutes", self._output_minutes(app)
        elif kind == "cma_download":
            name, html = "CMA (prepared in the CMA workspace)", self._output_cma(app)
        elif kind == "disbursement_memo":
            name, html = "Disbursement memo (generated and reviewed)", self._output_memo(app)
            disops = app.setdefault("disops", {})
            disops["memo"] = {"version": 1, "generated_at": at, "generated_by": session["user"]["name"],
                              "content_hash": do.memo_hash(disops), "reviewed": False, "reviewed_by": None,
                              "reviewed_at": None, "review_remarks": None}
        elif kind in ("mca_report", "cibil_report", "crif_report"):
            cid = {"mca_report": "mca", "cibil_report": "cibil", "crif_report": "crif"}[kind]
            title = {"mca_report": "MCA report", "cibil_report": "CIBIL commercial credit report",
                     "crif_report": "CRIF bureau score & status report"}[kind]
            name, html = f"{title} (demo data)", self._output_check_report(app, cid, title)
        elif kind == "ceib_proforma_a":
            name, html = "CEIB Proforma A (demo data)", self._output_ceib_proforma_a(app)
        elif kind == "udin_response":
            name, html = "UDIN response (demo data)", self._output_udin_response(app)
        elif kind == "drawdown_request":
            name, html = "Drawdown Request (demo data)", self._output_drawdown_request(app)
        elif kind == "drawdown_schedule":
            name, html = "Drawdown Schedule (demo data)", self._output_drawdown_schedule(app)
        elif kind in OUTPUT_ANNEXURES:
            numeral, title = OUTPUT_ANNEXURES[kind]
            name, html = f"Annexure {numeral} — {title} (labelled demo template)", self._output_annexure(app, numeral, title)
        else:
            raise InvalidRequestError(f"Unknown output: {kind}")
        dreg.register_generated(app.setdefault("documents", []), name=name, kind=kind,
                                by_name=session["user"]["name"], at=at)
        self._workspace_save(app, session, "output_generated", name)
        return {"kind": kind, "name": name, "html": html, "generated_at": at}

    def _output_executive_summary(self, app: dict) -> str:
        split = self._view_split(app)
        sanc = (app.get("sanctions") or {}).get("AP") or (app.get("sanctions") or {}).get("IP") or {}
        return f"""
        <h2>Executive Summary — {app.get('borrower_name')}</h2>
        <p><b>CLOS {app.get('application_id')}</b> · sector {app.get('sector') or '—'} ·
        proposed exposure <b>₹{(app.get('amount_cr') or 0):,.2f} Cr</b> (fund-based ₹{split['fund_based_cr']:,.2f} / non-fund ₹{split['non_fund_based_cr']:,.2f})</p>
        <p>Sanction: {f"₹{(sanc.get('sanctioned_cr') or 0):,.2f} Cr by {sanc.get('by_name')} on {sanc.get('at', '')[:10]}" if sanc else 'not recorded'}</p>
        <p>Stage: {app.get('stage_id')} · status {app.get('status')}</p>"""

    def _output_dd_report(self, app: dict) -> str:
        checks = (app.get("due_diligence") or {}).get("checks") or []
        rows = "".join(f"<tr><td>{c['name']}</td><td>{c['status']}</td><td>{c.get('result') or '—'}</td>"\
                       f"<td>{c.get('last_triggered') or '—'}</td><td>{c.get('detail') or '—'}</td></tr>"
                       for c in checks)
        return f"""
        <h2>Customer Due Diligence Report — {app.get('borrower_name')}</h2>
        <table><tr><th>Check</th><th>Status</th><th>Result</th><th>Last triggered</th><th>Remarks</th></tr>{rows}</table>
        <p class="note">Governance report from the due-diligence workspace; a green trigger is never a clear result.</p>"""

    def _output_minutes(self, app: dict) -> str:
        sanc = (app.get("sanctions") or {}).get("AP") or (app.get("sanctions") or {}).get("IP") or {}
        rec = (app.get("recommendations") or {}).get("AP") or (app.get("recommendations") or {}).get("IP") or {}
        return f"""
        <h2>Committee Minutes — {app.get('borrower_name')}</h2>
        <p>Committee: {(sanc.get('by_name') or '—')} · {sanc.get('at', '')[:10]}</p>
        <p>Decision: sanction ₹{(sanc.get('sanctioned_cr') or 0):,.2f} Cr (recommended ₹{(sanc.get('recommended_cr') or 0):,.2f} Cr)</p>
        <p>Authority: {(sanc.get('authority') or {}).get('required') or '—'}</p>
        <p>Minutes: {sanc.get('minutes') or '—'}</p>
        <p>Recommendations Committee: {rec.get('by_name') or '—'} — {rec.get('remarks') or '—'}</p>"""

    def _output_cma(self, app: dict) -> str:
        rows = ""
        for s in (app.get("cma") or {}).get("subjects") or []:
            for period, vals in sorted((s.get("rows") or {}).items()):
                rows += f"<tr><td>{s['subject']}</td><td>{period}</td><td>{len(vals)} rows recorded</td></tr>"
        return f"<h2>CMA Download — {app.get('borrower_name')}</h2>\n<table><tr><th>Entity</th><th>Period</th><th>Rows</th></tr>{rows}</table>"\
               "\n<p class='note'>Values in ₹ crores with source, period and version per entry.</p>"

    def _output_memo(self, app: dict) -> str:
        d = app.get("disops") or {}
        cif = d.get("cif") or {}
        bens = ", ".join(b["name"] for b in d.get("beneficiaries", [])) or "—"
        return f"""
        <h2>Disbursement Memo — {app.get('borrower_name')}</h2>
        <p>CIF {cif.get('cif_no') or '—'} ({cif.get('status') or '—'})</p>
        <p>Benefits: {bens}</p>
        <p>Limits: {', '.join(l['limit_id'] for l in d.get('limits', [])) or '—'}</p>
        <p>Loan accounts: {', '.join(l['account_no'] for l in d.get('loan_accounts', [])) or '—'}</p>
        <p>Security references: {', '.join(s['cbs_security_no'] or s['security_id'] for s in d.get('security_refs', [])) or '—'}</p>"""

    # ── UAT-P1-7: separate downloadable demo outputs ────────────────────────
    def _output_check_report(self, app: dict, check_id: str, title: str) -> str:
        c = self._dd_check(app, check_id)
        identity = app.get("customer_identity") or {}
        return f"""
        <h2>{title} — {app.get('borrower_name')}</h2>
        <p class='note'>Labelled demo artefact (GAP-P0-17): no live bureau/registry is connected. The figures below are
        taken from the governed due-diligence workspace and the stored customer identity, not from a production source.</p>
        <table>
          <tr><th>Entity</th><td>{app.get('borrower_name')}</td></tr>
          <tr><th>Application</th><td>{app.get('application_id')}</td></tr>
          <tr><th>PAN</th><td>{identity.get('pan') or '—'}</td></tr>
          <tr><th>CIN</th><td>{identity.get('cin') or '—'}</td></tr>
          <tr><th>Check status</th><td><b>{c['status']}</b></td></tr>
          <tr><th>Source (as labelled)</th><td>{c.get('source') or '—'}</td></tr>
          <tr><th>Detail</th><td>{c.get('detail') or '—'}</td></tr>
          <tr><th>Last triggered</th><td>{c.get('last_triggered') or '—'} by {c.get('triggered_by') or '—'}</td></tr>
        </table>
        <p class='note'>Status reflects the application's due-diligence record; 'unavailable' means the provider returned nothing and is never a clear result.</p>"""

    def _output_ceib_proforma_a(self, app: dict) -> str:
        rows = ""
        for p in app.get("related_parties", []):
            rows += (f"<tr><td>{p.get('name')}</td><td>{p.get('role')}</td><td>{p.get('party_type')}</td>"
                     f"<td>{p.get('pan') or '—'}</td><td>{p.get('cin') or '—'}</td>"
                     f"<td>{p.get('relationship') or '—'}</td></tr>")
        if not rows:
            rows = "<tr><td colspan='6'>No related parties on record.</td></tr>"
        c = self._dd_check(app, "ceib")
        return f"""
        <h2>CEIB Proforma A — {app.get('borrower_name')}</h2>
        <p class='note'>Labelled demo artefact (GAP-P0-17): entity &amp; relationship search proforma assembled from the party register.
        The CEIB source is <b>{c.get('source') or 'manual (demo)'} — not connected</b>.</p>
        <table>
          <tr><th>Party</th><th>Role</th><th>Type</th><th>PAN</th><th>CIN</th><th>Relationship</th></tr>
          {rows}
        </table>
        <p>CEIB check status: <b>{c['status']}</b> — {c.get('detail') or '—'}</p>"""

    def _output_udin_response(self, app: dict) -> str:
        c = self._dd_check(app, "udin")
        docs = [d for d in app.get("documents", []) if d.get("versions")]
        rows = "".join(f"<tr><td>{d['name']}</td><td>v{len(d['versions'])}</td><td>{d.get('status') or '—'}</td></tr>"
                       for d in docs) or "<tr><td colspan='3'>No verified professional documents on file.</td></tr>"
        return f"""
        <h2>UDIN Response — {app.get('borrower_name')}</h2>
        <p class='note'>Labelled demo artefact (GAP-P0-17): UDIN verification response for professional documents. The UDIN source is not connected.</p>
        <table>
          <tr><th>Document</th><th>Version</th><th>Status</th></tr>
          {rows}
        </table>
        <p>UDIN check status: <b>{c['status']}</b> — {c.get('detail') or '—'}</p>"""

    def _output_drawdown_request(self, app: dict) -> str:
        d = app.get("disops") or {}
        tranches = d.get("tranches") or []
        t = tranches[-1] if tranches else {}
        cif = d.get("cif") or {}
        return f"""
        <h2>Drawdown Request — {app.get('borrower_name')}</h2>
        <p class='note'>Labelled demo artefact (GAP-P0-17): the latest drawdown request assembled from the disbursement operational record.</p>
        <table>
          <tr><th>CIF</th><td>{cif.get('cif_no') or '—'} ({cif.get('status') or '—'})</td></tr>
          <tr><th>Tranche</th><td>{t.get('tranche_id') or '—'}</td></tr>
          <tr><th>Amount (₹ Cr)</th><td>{(t.get('amount_cr') or 0):,.2f}</td></tr>
          <tr><th>Value date</th><td>{t.get('value_date') or '—'}</td></tr>
          <tr><th>Purpose</th><td>{t.get('purpose') or '—'}</td></tr>
          <tr><th>Status</th><td>{t.get('status') or '—'}</td></tr>
        </table>"""

    def _output_drawdown_schedule(self, app: dict) -> str:
        tranches = (app.get("disops") or {}).get("tranches") or []
        rows = "".join(f"<tr><td>{t.get('tranche_id')}</td><td>{(t.get('amount_cr') or 0):,.2f}</td>"
                       f"<td>{t.get('value_date') or '—'}</td><td>{t.get('purpose') or '—'}</td><td>{t.get('status') or '—'}</td></tr>"
                       for t in tranches) or "<tr><td colspan='5'>No tranches recorded.</td></tr>"
        return f"""
        <h2>Drawdown Schedule — {app.get('borrower_name')}</h2>
        <p class='note'>Labelled demo artefact (GAP-P0-17): the drawdown schedule from the disbursement operational record.</p>
        <table>
          <tr><th>Tranche</th><th>Amount (₹ Cr)</th><th>Value date</th><th>Purpose</th><th>Status</th></tr>
          {rows}
        </table>"""

    def _output_annexure(self, app: dict, numeral: str, title: str) -> str:
        return f"""
        <h2>Annexure {numeral} — {title} · {app.get('borrower_name')}</h2>
        <p class='note'>Labelled demo template (GAP-P0-17). The client's exact annexure text is confirmation-required,
        so this placeholder is intentionally not filled with fabricated content — it confirms the annexure is part of the
        downloadable set for {app.get('application_id')}.</p>
        <table><tr><th>Application</th><td>{app.get('application_id')}</td></tr>
        <tr><th>Borrower</th><td>{app.get('borrower_name')}</td></tr>
        <tr><th>Stage</th><td>{app.get('stage_id')}</td></tr></table>"""

    def _output_body(self, app: dict, kind: str) -> tuple[str, str]:
        """Read-only (name, html) for a downloadable output — no side effects."""
        if kind == "executive_summary":
            return "Executive Summary", self._output_executive_summary(app)
        if kind == "due_diligence_report":
            return "Customer Due Diligence / Due Diligence Report", self._output_dd_report(app)
        if kind == "committee_minutes":
            return "Committee minutes", self._output_minutes(app)
        if kind == "esms_approval_note" and (app.get("esms") or {}).get("checklist"):
            return "ESMS Approval Note", es.approval_note(app, app.get("esms") or {})
        if kind == "cma_download":
            return "CMA (prepared in the CMA workspace)", self._output_cma(app)
        if kind == "disbursement_memo":
            return "Disbursement memo", self._output_memo(app)
        if kind in ("mca_report", "cibil_report", "crif_report"):
            cid = {"mca_report": "mca", "cibil_report": "cibil", "crif_report": "crif"}[kind]
            title = {"mca_report": "MCA report", "cibil_report": "CIBIL commercial credit report",
                     "crif_report": "CRIF bureau score & status report"}[kind]
            return f"{title} (demo data)", self._output_check_report(app, cid, title)
        if kind == "ceib_proforma_a":
            return "CEIB Proforma A (demo data)", self._output_ceib_proforma_a(app)
        if kind == "udin_response":
            return "UDIN response (demo data)", self._output_udin_response(app)
        if kind == "drawdown_request":
            return "Drawdown Request (demo data)", self._output_drawdown_request(app)
        if kind == "drawdown_schedule":
            return "Drawdown Schedule (demo data)", self._output_drawdown_schedule(app)
        if kind in OUTPUT_ANNEXURES:
            numeral, title = OUTPUT_ANNEXURES[kind]
            return f"Annexure {numeral} — {title}", self._output_annexure(app, numeral, title)
        raise InvalidRequestError(f"Unknown output: {kind}")

    def output_html(self, application_id: str, kind: str) -> str:
        """A self-contained, downloadable HTML page for one output (GET)."""
        app = self._require(application_id)
        name, body = self._output_body(app, kind)
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{name} — {app.get('application_id')}</title>
<style>body{{font-family:system-ui,Segoe UI,Arial;max-width:900px;margin:32px auto;padding:0 16px;color:#111}}
h2{{margin-top:0}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border:1px solid #ccc;padding:6px 10px;text-align:left;font-size:14px}}
th{{background:#f3f4f6}}.note{{color:#6b7280;font-size:13px}}</style></head>
<body>{body}<p class="note">Generated {self.now().isoformat(timespec='seconds')} · Corporate LOS demo (labelled demo data, GAP-P0-17).</p>
</body></html>"""

    def _view_split(self, app: dict) -> dict:
        _facs, split = facmod.facilities_view(app)
        return split

    # ── term sheet & sanction letter ─────────────────────────────────────────
    def letters(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        kinds = []
        kind_titles = profiles.letter_branding(self._profile(app))["kind_titles"]
        for kind, title in kind_titles.items():
            ok, reason = lt.available(app, kind)
            versions = (app.get("letters") or {}).get(kind) or []
            kinds.append({"kind": kind, "title": title, "available": ok, "reason": None if ok else reason,
                          "can_generate": bool(ok and session and session["role"] in LETTER_ROLES[kind]
                                               and app["status"] != STATUS_REJECTED),
                          "issuer_role": " / ".join(self._wf(app).roles.get(r, r) for r in LETTER_ROLES[kind]),
                          "versions": [{k: d[k] for k in ("version", "reference", "issued_at", "issued_by",
                                                          "valid_until")} for d in reversed(versions)],
                          "latest": versions[-1] if versions else None})
        return {"application_id": application_id, "letters": kinds}

    def generate_letter(self, application_id: str, session: dict, kind: str,
                        at: Optional[datetime] = None) -> dict:
        app = self._require(application_id)
        at = (at or self.now()).replace(microsecond=0)
        if kind not in lt.KINDS:
            raise InvalidRequestError(f"Unknown document: {kind}")
        ok, reason = lt.available(app, kind)
        if not ok:
            raise ConflictError(reason)
        if session["role"] not in LETTER_ROLES[kind]:
            raise ForbiddenError(f"The {profiles.letter_branding(self._profile(app))['kind_titles'][kind].lower()} is issued by the "
                                 f"{' / '.join(self._wf(app).roles.get(r, r) for r in LETTER_ROLES[kind])} role")
        case = None
        if self.cases and self.cases.get(app["entity_id"]):
            case, _ = self._app_case(app)
        deviations = build_deviations(app, case, committee_deviations(case) + manual_deviations(app))
        from src.los.ip_note import _thresholds
        versions = app.setdefault("letters", {}).setdefault(kind, [])
        doc = lt.build_letter(kind, app, self.companies.get(app["entity_id"]), case, deviations, _thresholds(),
                              session["user"]["name"], at, len(versions) + 1)
        versions.append(doc)
        if kind == "sanction_letter":
            dreg.register_generated(app.setdefault("documents", []),
                                    name="Sanction letter (generated, issued and uploaded back)",
                                    kind="sanction_letter", by_name=session["user"]["name"],
                                    at=self.now().isoformat(timespec="seconds"), detail=doc["reference"])
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "letter_issued", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"),
                                         comment=f"{doc['title']} {doc['reference']} issued",
                                         at=at, detail={"kind": kind, "reference": doc["reference"]}))
        return self.letters(application_id, session)

    def letter_html(self, application_id: str, kind: str, version: Optional[int] = None) -> str:
        app = self._require(application_id)
        versions = (app.get("letters") or {}).get(kind) or []
        doc = next((d for d in versions if d["version"] == version), None) if version else (versions[-1] if versions else None)
        if not doc:
            raise NotFoundError("This document has not been issued yet")
        return lt.render_html(doc)

    # ── management MIS ───────────────────────────────────────────────────────
    def mis(self) -> dict:
        apps = self._active_profile_apps()
        application_ids = {a["application_id"] for a in apps}
        events = [e for e in self.store.events(limit=1_000_000)
                  if e.get("application_id") in application_ids]
        by_app: dict[str, list[dict]] = {}
        for e in events:
            by_app.setdefault(e["application_id"], []).append(e)
        mis = build_mis(apps, by_app, self.wf, self.now(),
                        [e for e in events if e["action"] in ("copilot_action", "copilot_ask")])
        mis["agents"] = agent_metrics(apps, events, self.field_registry)     # Populate → Verify headline numbers
        return mis

    # ── copilot ──────────────────────────────────────────────────────────────
    def _is_holder(self, app: dict, session: Optional[dict]) -> bool:
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        return bool(session and step and app["status"] not in TERMINAL
                    and can_act(self._wf(app), session["user"]["id"], session["role"], step)
                    and app.get("assignee_id") in (None, session["user"]["id"]))

    def _copilot_state(self, app: dict, session: Optional[dict], light: bool = False) -> dict:
        """What the planner reads. ``light`` skips the credit case (used for the dashboard digest)."""
        view = self._view(app, session)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        sla = dict(view.get("sla") or {})
        if step and sla:
            sla.update(sla_days=step.sla_days, due_soon=0 <= sla.get("days_remaining", 99) < 1)
        s = {"step_id": step.id if step else None, "step_name": step.name if step else None,
             "step_kind": step.kind if step else None, "role_name": self._wf(app).roles.get(step.role) if step else None,
             "status": app["status"], "holder": view.get("assignee_name"), "is_holder": self._is_holder(app, session),
             "sla": sla, "can_submit": bool(view.get("actions")), "committee_steps": COMMITTEE_STEPS,
             "documents": len(self._documents_on_file(app["entity_id"])),
             "credit_assessment": bool(app.get("credit_assessment")),
             "approvers": self._who(self._approvers(self._exc_authority(app)["role"], self._wf(app))),
             "exception_requests": ([r["name"] for r in self._pending_exception_requests(app)]
                                    if session and session["role"] == self._exc_authority(app)["role"] else [])}
        if app["status"] == "RETURNED":
            ret = next((e for e in self.store.events(application_id=app["application_id"], limit=50)
                        if e["action"] == "return"), None)
            s["returned_comment"] = (ret or {}).get("comment")
        src = app.get("sourcing") or {}
        if src.get("prefill"):
            accepted = src.get("accepted") or {}
            fields = src["prefill"]["fields"]
            s["prefill"] = {"unaccepted_high": sum(1 for f in fields if f["band"] == "high" and f["id"] not in accepted),
                            "conflicts": [f["label"] for f in fields if f["status"] == "conflict" and f["id"] not in accepted],
                            "not_found": [f["label"] for f in fields if f["status"] == "not_found" and f["id"] not in accepted]}
        if app.get("ip_note"):
            s["ip_note"] = {"breaches": app["ip_note"]["prescreen"]["breaches"]}
        if app.get("due_diligence"):
            checks = app["due_diligence"]["checks"]
            _app5 = ((self._profile(app).get("checks") or {}).get("applicability") or {})
            _val5 = {k: int(v) for k, v in (((self._profile(app).get("checks") or {}).get("validity_days")) or {}).items()}
            blocking = dd.blocking([c for c in checks if dd.check_applies(_app5.get(c["id"]) or {}, app)[0]],
                                   now=self.now(), validity_days=_val5)
            s["due_diligence"] = {"blocking": [c["name"] for c in blocking],
                                  "need_exception": [c["name"] for c in blocking if c["status"] in ("matched", "failed", "unavailable")
                                                     and (c.get("exception_request") or {}).get("status") != "pending"],
                                  "awaiting_exception": [c["name"] + (f" — with {c['exception_request']['to_name']}"
                                                                      if c["exception_request"].get("to_name") else "")
                                                         for c in blocking
                                                         if (c.get("exception_request") or {}).get("status") == "pending"],
                                  "runnable": [c["name"] for c in blocking if c["status"] == "pending" and c["mode"] == "api"],
                                  "to_record": [c["name"] for c in blocking if c["status"] == "pending" and c["mode"] == "manual"],
                                  "pending": sum(1 for c in checks if c["status"] == "pending"),
                                  "at_dd_step": bool(step and step.id in DD_STEPS)}
        with self._jobs_lock:
            s["job_state"] = (self._jobs.get(app["application_id"]) or {}).get("state")
        if step and step.kind == "allocation":
            s["suggested_allocatee"] = self._user_name(self._default_assignee(step.allocates_to))
        if not light and step and step.id in RISK_MAKER_STEPS and app.get("credit_assessment"):
            s["review"] = self.assessment(app["application_id"], session)["review_summary"]
        if not light and step and step.id in COMMITTEE_STEPS:
            pack = self.committee_pack(app["application_id"], session)
            if pack.get("available"):
                s["pack"] = {"can_brief": pack["can_brief"],
                             "brief_done": any((pack.get("brief") or {}).values()),
                             "overrides": len(pack["overrides"]), "open_items": len(pack["open_items"]),
                             "deviations": len(pack["deviations"]),
                             "high_risks": [r["risk"] for r in pack["risks"]
                                            if r["severity"] in ("CRITICAL", "HIGH") and r["status"] != "RESOLVED"]}
        if app.get("conditions"):
            s["conditions"] = condition_summary(app["conditions"], self.now().date().isoformat())
        s["sanction_letter_issued"] = bool((app.get("letters") or {}).get("sanction_letter"))
        if step and step.stage_id == "DIS":
            d = self._disbursement(app)
            s["disbursement"] = {"pending_tranche": d["pending_tranche"], "available_cr": d["available_cr"],
                                 "missing": [i["label"] for i in d["checklist"] if not i["done"]]}
        return s

    def copilot(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        state = self._copilot_state(app, session)
        return {"application_id": application_id, "version": cp.COPILOT_VERSION,
                "actions": cp.next_actions(state), "is_holder": state["is_holder"],
                "ai_available": self._ai_available(), "tools": cp.TOOLS,
                "history": list(reversed((app.get("copilot_log") or [])[-10:]))}

    def _ai_available(self) -> bool:
        if not self.llm_factory:
            return False
        try:
            return getattr(self.llm_factory(), "name", "") != "mock"
        except Exception:
            return False

    def copilot_run(self, application_id: str, session: dict, tool: str) -> dict:
        """Run a proposed action as the signed-in user (their permissions apply). Never a workflow decision."""
        if tool not in cp.TOOLS:
            raise InvalidRequestError(f"The copilot cannot run '{tool}'")
        app = self._require(application_id)
        if not self._is_holder(app, session):
            raise ForbiddenError("The copilot acts only for the person holding the step")
        # Audit first: the tool saves the application itself (an assessment saves from its own thread), so the
        # copilot must not save an older copy afterwards.
        before = self._open_items(application_id)
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "copilot_action", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"),
                                         comment=f"Copilot: {cp.TOOLS[tool]} (run at the user's request)",
                                         detail={"tool": tool}))
        if tool == "run_prefill":
            self.run_prefill(application_id, session)
        elif tool == "accept_high_confidence":
            fields = ((app.get("sourcing") or {}).get("prefill") or {}).get("fields") or []
            accepted = (app.get("sourcing") or {}).get("accepted") or {}
            ids = [f["id"] for f in fields if f["band"] == "high" and f["id"] not in accepted]
            if not ids:
                raise ConflictError("There are no high-confidence values left to accept")
            self.apply_prefill(application_id, session, [{"field_id": i} for i in ids])
        elif tool == "run_due_diligence":
            self.run_due_diligence(application_id, session)
        elif tool == "generate_ip_note":
            self.generate_ip_note(application_id, session, with_ai=True)
        elif tool == "start_assessment":
            self.start_assessment(application_id, session)
        elif tool == "committee_brief":
            self.committee_brief(application_id, session)
        elif tool == "issue_sanction_letter":
            self.generate_letter(application_id, session, "sanction_letter")
        after = self._open_items(application_id)
        b_items, a_items = self._atomise(before), self._atomise(after)
        resolved = [k for k in b_items if k not in a_items]
        changed = [f"{k}: {b_items[k]} → {a_items[k]}" for k in b_items if k in a_items and b_items[k] != a_items[k] and b_items[k]]
        still = after
        detail = ""
        if tool == "run_due_diligence":                      # what the checks came back with
            checks = (self._require(application_id).get("due_diligence") or {}).get("checks") or []
            bad = [f"{c['name']}: {c['status']}" for c in checks if c["mode"] == "api" and c["status"] in ("matched", "failed", "unavailable")]
            detail = ("Checks run. Needing attention: " + "; ".join(bad)) if bad else "Checks run — all API checks came back clear."
        outcome = "resolved" if before and not still else "partial" if resolved else "unchanged"
        message = {"resolved": "Done — this cleared everything that was blocking the step.",
                   "partial": f"Done — resolved {len(resolved)} item(s); {len(still)} still open.",
                   "unchanged": "Done, but nothing that blocks the step was resolved by it."}[outcome]
        if not before and not still:
            outcome, message = "resolved", "Done — nothing is blocking the step."
        return self.copilot(application_id, session) | {
            "ran": tool, "message": cp.TOOLS[tool] + ": " + message,
            "outcome": outcome, "resolved": resolved, "changed": changed, "still_open": still, "detail": detail}

    @staticmethod
    def _atomise(messages: list[str]) -> dict:
        """Blocker messages as {item: state}: "Resolve …: MCA (pending); KYC (pending)" → {"MCA": "pending", …}."""
        out = {}
        for m in messages:
            head, _, rest = m.partition(": ")
            parts, depth, cur = [], 0, ""
            for ch in (rest or head):
                depth += ch == "("
                depth -= ch == ")" and depth > 0
                if ch == ";" and not depth:
                    parts.append(cur); cur = ""
                else:
                    cur += ch
            parts.append(cur)
            for p in parts:
                p = p.strip().rstrip("…").strip()
                if not p or p.startswith("(+"):
                    continue
                name, _, state = p.partition(" (")
                out[name.strip()] = state.rstrip(")").strip()
        return out

    def _open_items(self, application_id: str) -> list[str]:
        """What still blocks the step holder's forward action (the same gates as Submit / Approve)."""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step:
            return []
        action = {"maker": "submit", "checker": "approve", "vp_review": "submit"}.get(step.kind)
        return [m for m, _ in self._gates(app, step, action)] if action else []

    def copilot_draft(self, application_id: str, session: dict, kind: str) -> dict:
        app = self._require(application_id)
        if kind == "return_note":
            text = cp.draft_return_note(self._copilot_state(app, session))
        elif kind == "document_request":
            docs = [d["document"] for d in self._documents_on_file(app["entity_id"])]
            fields = ((app.get("sourcing") or {}).get("prefill") or {}).get("fields") or []
            accepted = (app.get("sourcing") or {}).get("accepted") or {}
            not_found = [f["label"] for f in fields if f["status"] == "not_found" and f["id"] not in accepted]
            text = cp.draft_document_request(app.get("borrower_name"), session["user"]["name"], docs, not_found)
        else:
            raise InvalidRequestError(f"Unknown draft: {kind}")
        return {"kind": kind, "text": text, "provenance": "derived",
                "note": "Draft assembled from the record — edit before use. Nothing has been sent."}

    def _copilot_record(self, app: dict) -> dict:
        """The application record the copilot answers from."""
        v = self.get(app["application_id"])
        src = app.get("sourcing") or {}
        rec = {
            "application": {k: v.get(k) for k in ("application_id", "borrower_name", "entity_id", "sector", "constitution",
                                                   "status", "priority", "amount_cr", "tat_days", "assignee_name")}
            | {"stage": (v.get("step") or {}).get("stage_name"), "step": (v.get("step") or {}).get("name"),
               "sla": v.get("sla")},
            "facility": app.get("facility"),
            "customer_identity": app.get("customer_identity"),
            "prospect_discussion": app.get("prospect_discussion"),
            "due_diligence": (dd.summary(app["due_diligence"]["checks"], self.now())
                              if app.get("due_diligence") else None),
            "sourcing_accepted": {k: a.get("display") for k, a in (src.get("accepted") or {}).items()},
            "prefill_summary": (src.get("prefill") or {}).get("summary"),
            "credit_assessment": app.get("credit_assessment"),
            "sanctions": {k: {x: s.get(x) for x in ("sanctioned_cr", "recommended_cr", "requested_cr", "minutes",
                                                     "by_name", "at")} for k, s in (app.get("sanctions") or {}).items()},
            "comments": [{"by": e.get("actor_name"), "step": e.get("from_step_name"), "action": e["action"],
                          "comment": e["comment"]} for e in v["events"] if e.get("comment")][:10],
        }
        if app.get("ip_note"):
            n = app["ip_note"]
            rec["ip_note"] = {"outcome": n["prescreen"]["outcome"], "period": n["prescreen"]["period"],
                              "checks": [{k: c[k] for k in ("label", "value", "limit", "result")}
                                         for c in n["prescreen"]["checks"]],
                              "financials": n["financials"]}
        if app.get("sanctions") or (app.get("step_id") in COMMITTEE_STEPS):
            pack = self.committee_pack(app["application_id"])
            if pack.get("available"):
                rec["credit_case"] = {"headline": pack["headline"], "risks": pack["risks"][:8],
                                      "deviations": pack["deviations"], "conditions": pack["conditions"],
                                      "overrides": pack["overrides"], "open_items": pack["open_items"][:8]}
        if app.get("conditions"):
            rec["conditions_tracker"] = [{k: c.get(k) for k in ("id", "type", "text", "status", "due", "note")}
                                         for c in app["conditions"]]
        if app.get("disbursement") or app.get("stage_id") == "DIS":
            d = self._disbursement(app)
            rec["disbursement"] = {k: d[k] for k in ("sanctioned_cr", "disbursed_cr", "available_cr", "tranches")}
        return rec

    def copilot_ask(self, application_id: str, session: dict, question: str) -> dict:
        app = self._require(application_id)
        if not (question or "").strip():
            raise InvalidRequestError("Ask a question")
        llm = self.llm_factory() if self.llm_factory else None
        answer = cp.ask(question.strip()[:500], self._copilot_record(app), llm)
        entry = {"question": question.strip()[:500], **answer, "by_name": session["user"]["name"],
                 "at": self.now().isoformat(timespec="seconds")}
        app = self._require(application_id)
        app["copilot_log"] = ((app.get("copilot_log") or []) + [entry])[-30:]
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "copilot_ask", actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment=f"Asked: {entry['question'][:200]}",
                                         detail={"mode": answer["mode"]}))
        return entry

    def copilot_digest(self, session: dict) -> dict:
        """The signed-in user's queue, ordered by urgency, with the copilot's top proposal for each."""
        items = []
        for a in self.list(session, mine=True):
            app = self.store.get(a["application_id"])
            actions = cp.next_actions(self._copilot_state(app, session, light=True))
            top = next((x for x in actions if x["id"] not in ("sla", "return_draft")),
                       {"id": "open", "title": f"Open and complete {(a.get('step') or {}).get('name')}",
                        "why": "", "priority": "medium", "tool": None, "draft": None})
            sla = a.get("sla") or {}
            items.append({"application_id": a["application_id"], "borrower_name": a["borrower_name"],
                          "step_name": (a.get("step") or {}).get("name"), "amount_cr": a.get("amount_cr"),
                          "sla_breached": bool(sla.get("breached")), "days_remaining": sla.get("days_remaining"),
                          "status": a["status"], "top_action": top,
                          "high": sum(1 for x in actions if x["priority"] == "high")})
        items.sort(key=lambda i: (not i["sla_breached"], -i["high"], i["days_remaining"] if i["days_remaining"]
                                  is not None else 99))
        breached = sum(1 for i in items if i["sla_breached"])
        return {"items": items, "summary": (f"{len(items)} item(s) in your queue" +
                                            (f", {breached} past SLA" if breached else "") + "."
                                            if items else "Nothing is waiting for you.")}

    # ── review & committee pack ──────────────────────────────────────────────
    def committee_pack(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        case, final = self._app_case(app)
        review_summary = self.assessment(application_id, session)["review_summary"] if case else {}
        events = self.get(application_id)["events"]
        pack = build_committee_pack(case, final, app, events, review_summary,
                                    {s.id: s.name for s in self._wf(app).steps})
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        pack["can_brief"] = bool(session and step and step.id in COMMITTEE_STEPS and app["status"] not in TERMINAL
                                 and can_act(self._wf(app), session["user"]["id"], session["role"], step)
                                 and pack.get("available"))
        pack["at_committee_step"] = bool(step and step.id in COMMITTEE_STEPS)
        return pack

    def committee_brief(self, application_id: str, session: dict) -> dict:
        """AI committee brief: the number-guarded CAM interpretation of the executive summary and recommendation."""
        app = self._require(application_id)
        step = self._wf(app).step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in COMMITTEE_STEPS or app["status"] in TERMINAL:
            raise ConflictError("The committee brief is prepared at the review and committee steps")
        if not can_act(self._wf(app), session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step belongs to the {self._wf(app).roles[step.role]} role")
        if not self.final_cam:
            raise OperationFailedError("The credit-intelligence engine is not connected")
        if not self.cases.get(app["entity_id"]):
            raise ConflictError("No credit assessment is available for this application yet")
        out = self.final_cam.interpret(app["entity_id"], list(BRIEF_SECTIONS))
        results = {sid: r.get("status") for sid, r in (out.get("results") or {}).items()}
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "committee_brief", actor=actor, from_step=step.id, to_step=step.id,
                                         detail={"results": results}))
        pack = self.committee_pack(application_id, session)
        pack["brief_results"] = out.get("results") or {}
        return pack

    # ── demo seed ────────────────────────────────────────────────────────────
    def _system_session(self, role: str, user_id: Optional[str] = None, wf: Optional[Workflow] = None) -> dict:
        wf = wf or self.wf
        uid = user_id or wf.users_with_role(role)[0]["id"]
        user = wf.user(uid)
        return {"user": {k: user[k] for k in ("id", "name", "email", "branch", "roles")}, "role": role}

    def seed_demo(self, force: bool = False) -> int:
        """Seed the demo applications once (or again with force=True). Returns the number created."""
        if force:
            self.store.clear()
        elif self.store.count():
            return 0
        active = profiles.active_profile_id()
        # A deployment presents one coherent institution configuration.  The legacy
        # walkthrough is seeded only when Client One is the selected configuration;
        # presentation profiles seed only their own applications.
        if active == "client_one":
            return self._seed_legacy_once()
        return self.seed_profile_apps(active)

    def _seed_legacy_once(self) -> int:
        """The legacy Client One walkthrough applications, idempotent per entity (existing kept)."""
        have = {a["entity_id"] for a in self.store.list()}
        created = 0
        for entity_id, target, flag, days_ago, idle_days, note in DEMO_SEED:
            if entity_id not in self.companies or entity_id in have:
                continue
            created += 1
            t0 = self.now() - timedelta(days=days_ago)
            rm = self._system_session("ps_maker")
            facilities = None
            related_parties = None
            if entity_id == "ABCE001":
                facilities = [
                    {"facility_type": "working_capital", "facility_nature": "fund_based",
                     "proposal_type": "Enhancement", "amount_cr": 200, "tenor_months": 12,
                     "purpose": "Working-capital cycle and receivables funding", "benchmark": "MCLR",
                     "benchmark_rate": 11.55, "spread": 0.85, "interest_rate": 12.4,
                     "repayment_type": "interest_only", "repayment_frequency": "monthly",
                     "total_limit_id": "TL-ABCE-01", "fund_limit_id": "FL-ABCE-01",
                     "limit_suffix": "001", "loan_account": "ABCE-WC-001",
                     "next_review_date": (self.now() + timedelta(days=330)).date().isoformat()},
                    {"facility_type": "bank_guarantee", "facility_nature": "non_fund_based",
                     "proposal_type": "Fresh", "amount_cr": 50, "tenor_months": 18,
                     "purpose": "Performance guarantees for infrastructure contracts",
                     "repayment_type": "bullet", "repayment_frequency": "annual",
                     "total_limit_id": "TL-ABCE-01", "non_fund_limit_id": "NFL-ABCE-01",
                     "limit_suffix": "002", "next_review_date": (self.now() + timedelta(days=330)).date().isoformat()},
                ]
                related_parties = [
                    {"name": "Rajesh Mehta", "role": "promoter", "party_type": "individual",
                     "ownership_pct": 61, "pan": "ABCDE1234F",
                     "relationship": "61% shareholder and promoter",
                     "sourced_address": "33 MG Road, Mumbai - Aadhaar/KYC",
                     "key_person_role": "Managing Director", "party_status": "active"},
                    {"name": "ABC Holdings Private Limited", "role": "parent", "party_type": "non_individual",
                     "ownership_pct": 26, "pan": "AABCA1234B", "cin": "U70100MH2011PTC123456",
                     "relationship": "Parent and group holding company",
                     "sourced_address": "BKC, Mumbai - MCA master data", "party_status": "active"},
                    {"name": "Anita Mehta", "role": "guarantor", "party_type": "individual",
                     "ownership_pct": 13, "pan": "BCDEA2345G", "relationship": "Personal guarantor",
                     "sourced_address": "33 MG Road, Mumbai - KYC declaration",
                     "key_person_role": "Whole-time Director", "party_status": "active"},
                ]
            app = self.create(rm, entity_id=entity_id, at=t0, seeded=True, facilities=facilities,
                              related_parties=related_parties, profile="client_one",
                              priority="High" if entity_id in ("ABCE001", "APOL001") else "Normal",
                              prospect_discussion={"project_type": "Corporate lending",
                                                   "funding_type": "Bank facilities",
                                                   "brief_description": "Client walkthrough case with governed sourcing data.",
                                                   "detailed_discussion": "Business need, proposed facilities, repayment source and next steps discussed with the prospect (demo).",
                                                   "initial_remarks": "Proceed subject to due diligence and credit appraisal (demo)."},
                              sourcing_decision={"decision": "Refer for in-principle",
                                                 "mandatory_remarks": "Demo seed — RM proposal sourced per the prospect discussion on file."})
            end = self.now() - timedelta(days=idle_days)
            self._replay_to(app["application_id"], target, t0, end)
            if entity_id == "PNCR001":               # the disbursement record is on file; memo + SOP items remain
                self._seed_disbursement_record(app["application_id"], end)
            if flag == "returned":
                self._seed_return(app["application_id"], end)
            elif flag == "escalated":
                holder = self._system_session(self._wf(app).step(target).role, wf=self._wf(app))
                self._force_assignee(app["application_id"], holder["user"]["id"])
                self.escalate(app["application_id"], holder, "Tranche timing depends on the borrower's "
                                                             "project milestones (demo note).")
            self._annotate(app["application_id"], note)
            self._seed_presentation_evidence(app["application_id"], entity_id, end)
        if DEMO_EXIT_ENTITY not in have:
            created += self._seed_exit_showcase()
        return created

    def seed_profile_apps(self, profile_id: Optional[str] = None, force: bool = False) -> int:
        """Create (or recreate with force=True) the demo applications declared by an institution
        profile (``demo_applications`` in its YAML): deterministic fictional borrowers replayed to
        a fixed stage. Idempotent per (profile, entity). Returns the number created."""
        pid = profile_id or profiles.active_profile_id()
        prof = profiles.get_profile(pid)
        specs = prof.get("demo_applications") or []
        if not specs and pid == "client_one":
            # the legacy Client One walkthrough set is seeded from code (DEMO_SEED), not YAML
            if force:
                for a in list(self.store.list()):
                    if (a.get("profile") or "client_one") == "client_one" and a.get("is_demo"):
                        self.store.delete(a["application_id"])
            return self._seed_legacy_once()
        if force:
            for a in list(self.store.list()):
                if a.get("profile") == pid and a.get("is_demo"):
                    self.store.delete(a["application_id"])
        existing = {(a.get("profile"), a.get("entity_id")) for a in self.store.list()}
        prof_wf = self.wf_for_profile(pid)
        first = prof_wf.first_step
        created = 0
        for spec in specs:
            eid = spec.get("entity_id")
            if not eid or eid not in self.companies:
                continue
            if not force and (pid, eid) in existing:
                continue
            t0 = self.now() - timedelta(days=int(spec.get("days_ago", 3)))
            end = self.now()
            sess = self._system_session(first.id)
            app = self.create(sess, entity_id=eid, at=t0, seeded=True, profile=pid,
                              facilities=spec.get("facilities") or None,
                              priority=spec.get("priority", "Normal"))
            target = spec.get("target") or first.id
            if target != first.id:
                self._replay_to(app["application_id"], target, t0, end)
            self._annotate(app["application_id"], spec.get("note") or "")
            created += 1
        return created

    def _seed_presentation_evidence(self, application_id: str, entity_id: str, at: datetime) -> None:
        """Add deterministic, visibly labelled evidence used by the 42-card client walkthrough.

        This is presentation data, not a shortcut through the workflow: each record is stored in
        the same governed domain shape used by the UI and its normal write endpoints.
        """
        app = self.store.get(application_id)
        stamp = at.isoformat(timespec="seconds")

        if entity_id == "ABCE001":
            app["entity"] = {"entity_incorporated": True, "entity_incorporated_by": "Demo seed",
                             "latest_material_information_date": at.date().isoformat(),
                             "latest_material_information_by": "Demo seed"}
            # Same keys and CRAC vocabulary as save_ip_assignments, so the seeded record displays.
            app["ip_assignments"] = {"lpfg_analyst": "Vivek Iyer", "lpfg_senior_analyst": "Sunil Chopra",
                                     "crac_recommendation": "Recommend sanction with conditions",
                                     "crac_remarks": "Proceed to detailed appraisal with the recorded controls.",
                                     "crac_by": "Demo seed"}
            for f in app.get("facilities", []):
                f.setdefault("change_history", []).append(
                    {"at": stamp, "by": "Demo seed", "change": "Facility terms and operational references recorded"})
            for p in app.get("related_parties", []):
                p["verification"] = pev.initial_verification()
                pev.apply_update(p, {"kyc_status": "clear", "kyc_evidence": ["KYC pack / PAN / address proof"],
                                     "cibil_status": "clear", "crif_status": "unavailable",
                                     "screening_status": "clear", "screening_hits": 0,
                                     "rating_ref": f"RATING-{p['party_id']}", "financial_ref": "CMA-borrower",
                                     "document_ids": ["KYC-01", "PAN-01"]}, "Demo seed", stamp, vp=False)
            checks = {c["id"]: c for c in app["due_diligence"]["checks"]}
            checks["kyc"].setdefault("comments", []).append(
                {"by_name": "Neha Kulkarni", "at": stamp,
                 "text": "Identity, address and beneficial-ownership evidence reviewed; demo comment persists after reload."})
            checks["kyc"].setdefault("evidence", []).append(
                {"name": "ABCE KYC evidence pack", "note": "Linked to this check (demo)",
                 "by_name": "Neha Kulkarni", "at": stamp})
            checks["udin"]["grid"] = [
                {"document": "FY2025 audited financial statements", "udin_code": "25123456ABCDE1234F",
                 "status": "verified", "by_name": "Neha Kulkarni", "at": stamp}]
            checks["name_screening"].setdefault("exception_history", []).append(
                {"by_name": "Priya Raghavan", "at": stamp, "reason": "Prior-result demo exception",
                 "invalidated_at": stamp, "invalidated_by": "Demo seed",
                 "reason_invalidated": "Re-screened; previous exception does not carry forward"})
            app["demo_features"] = ["multi_party", "multi_facility", "party_evidence", "dd_comment",
                                    "dd_evidence", "dd_exception_history", "udin_grid", "ip_note", "ai_cam"]

        elif entity_id == "IHCL001":
            app["sourcing_decision"]["customer_id_selection"] = \
                app.get("customer_identity", {}).get("customer_id") or "new"
            app["demo_features"] = ["sourcing", "identity", "dedupe"]

        elif entity_id == "MFL001":
            kyc = next(x for x in app["due_diligence"]["checks"] if x["id"] == "kyc")
            kyc.update(status="unavailable", detail="KYC provider unavailable - Compliance VP approval required (demo)",
                       source="KYC adapter (not connected)", error="Provider unavailable", last_triggered=stamp,
                       triggered_by="Demo seed", exception=None)
            c = next(x for x in app["due_diligence"]["checks"] if x["id"] == "name_screening")
            old = self.now() - timedelta(days=100)
            c["last_triggered"] = old.isoformat(timespec="seconds")
            if c.get("exception"):
                c["exception"]["expires_at"] = (self.now() - timedelta(days=10)).isoformat(timespec="seconds")
            self._invalidate(app, "ownership_change",
                             "Promoter ownership changed - credit assessment and group rating require re-evaluation",
                             "Demo seed", stamp)
            app["demo_features"] = ["returned_rework", "mandatory_unavailable", "screening_expiry",
                                    "dependency_invalidation"]

        elif entity_id == "MRF001":
            self.store.save(app)
            self._seed_ap_workspace(application_id, at)
            app = self.store.get(application_id)
            f = app["facilities"][0]
            fid = f["facility_id"]
            f["pricing"].update(benchmark="MCLR", benchmark_rate=11.35, spread=0.9,
                                interest_rate=12.25, reset_frequency="annual", penal_rate=2.0,
                                effective_rate=12.25)
            f["repayment"].update(repayment_type="quarterly_quarters", repayment_frequency="quarterly",
                                  moratorium_months=6)
            project = prj.normalise_project({
                "name": "MRF Capacity Expansion Phase II", "type": "brownfield", "funding_type": "term_loan",
                "purpose": "Expansion of manufacturing capacity", "description": "Brownfield expansion (demo)",
                "location": "Chennai", "state": "Tamil Nadu", "facility_ids": [fid],
                "tev": {"total_cr": 480, "consultant": "Demo Technical Consultants",
                        "agency": "Independent engineer (demo)", "report": "TEV-2026-014",
                        "report_date": at.date().isoformat()},
                "cost": {"total_cr": 480, "appraised_cr": 465, "incurred_cr": 85,
                         "financing_arrangement": "Debt and promoter contribution",
                         "means_of_finance": "Term loan 300; promoter contribution 180",
                         "promoter_contribution_cr": 180, "tied_up_loans": "₹300 Cr proposed"},
                "commercial_viability": "Base-case project DSCR 1.54x (demo appraisal input)",
                "plan": {"repayment_schedule": "Quarterly after six-month moratorium", "dsra": "3 months debt service",
                         "disbursement_plan": "Milestone-linked", "original_dcco": "2027-03-31",
                         "revised_dcco": "2027-06-30", "repayment_shift": "One quarter"},
                "risks": [{"category": "funding", "description": "Cost overrun",
                           "allocated_party": "Promoter", "residual_comments": "Standby contribution",
                           "level": "Medium"}], "evidence": ["TEV report", "Cost certificate"]}, 1, {fid})
            project["project_id"] = "PRJ-001"
            prj.record_change(project, {"field": "dcco", "previous": "2027-03-31", "current": "2027-06-30",
                                                "reason": "Equipment delivery revision",
                                                "impact_on_repayment": "One-quarter shift",
                                                "impact_on_finance": "No increase in debt"}, stamp, "Demo seed")
            app["projects"] = [project]
            security = sec.normalise_security({"category": "primary", "type": "plant_machinery",
                                               "facility_ids": [fid], "description": "First charge on project assets",
                                               "proposed_value_cr": 390, "apportioned_value_cr": 360,
                                               "valuation_date": at.date().isoformat(),
                                               "valuation_basis": "Independent valuation (demo)",
                                               "charge_type": "first_charge", "charge_priority": 1,
                                               "creation_status": "pending", "perfection_status": "in_progress",
                                               "perfection_eta": (at + timedelta(days=30)).date().isoformat(),
                                               "los_security_id": "LOS-MRF-SEC-01", "cersai": "pending", "roc": "pending",
                                               "evidence": ["Valuation report"]}, 1, {fid})
            security["security_id"] = "SEC-001"
            security["history"] = [{"at": stamp, "by": "Demo seed", "change": "Security appraisal recorded"}]
            app["securities"] = [security]
            checklist = [{"id": item_id, "answer": "No", "remarks": "Screened - no exclusion identified (demo)",
                          "source": "ESMS questionnaire (demo)"} for item_id, _ in es.ES_CHECKLIST]
            app["esms"].update(screening_date=at.date().isoformat(), checklist=es.normalise_checklist(checklist, []),
                               category="B", cpcb_category="Orange", environmental_impact="Mitigation plan recorded",
                               information_source="Borrower questionnaire and ESDD summary (demo)",
                               proposed_category="B", company_es_risk_assessment="Moderate and manageable",
                               esdd="ESDD completed (demo)", additional_conditions=["Quarterly E&S monitoring"],
                               committee_recommendation="Proceed subject to mitigation monitoring", status="complete")
            known = {"projects": {"PRJ-001"}, "facilities": {fid}, "securities": {"SEC-001"}}
            roles = (("LIA", "Demo Lenders Independent Advisor"), ("LIE", "Demo Lenders Independent Engineer"),
                     ("Security Trustee", "Demo Trusteeship Services"), ("ESDD Provider", "Demo E&S Consultants"),
                     ("Legal Loan Counsel", "Demo Legal Partners"))
            app["ewps"] = []
            for i, (role, name) in enumerate(roles, 1):
                rec = ewp_mod.normalise_ewp({"role": role, "name": name, "contact_person": f"Demo contact {i}",
                                             "contact_number": f"98100000{i:02d}", "email": f"ewp{i}@demo.in",
                                             "phase": "appraisal", "status": "engaged", "project_ids": ["PRJ-001"],
                                             "facility_ids": [fid], "security_ids": ["SEC-001"]}, i, known)
                rec["ewp_id"] = f"EWP-{i:03d}"
                app["ewps"].append(rec)
            ratings = app["ratings"]
            ratings["internal_ratings"] = [rat.internal_rating_entry(
                {"subject": "borrower", "grade": "A", "score": 78.5, "date": at.date().isoformat(),
                 "note": "Internal rating - demo model"})]
            ratings["adverse_events"] = [rat.adverse_event_entry(
                {"trigger": "Input-cost volatility review", "review_date": at.date().isoformat(),
                 "downgrade_notches": 0, "revised_rating": "A", "comments": "No downgrade after review (demo)"})]
            ratings["raroc"][fid] = rat.compute_raroc(app, fid, self.cases.get(entity_id) if self.cases else None,
                                                       stamp, "Demo seed")
            app["proposal"]["summary"].update(purpose="Capacity expansion and working capital",
                                                 tenure_months=f.get("tenor_months"),
                                                 pricing_note="MCLR plus recorded spread (demo)",
                                                 security_note="First charge on project assets")
            app["proposal"]["background"].update(borrower_and_business="Established tyre manufacturer (demo summary)",
                                                    industry_outlook="Stable demand with input-cost sensitivity",
                                                    strengths="Brand, distribution and operating history",
                                                    weaknesses="Commodity price exposure", key_risks="Project execution and margins")
            _lead = ((profiles.get_profile(app=app).get("branding") or {}).get("short_name")) or "The institution"
            app["proposal"]["banking"] = prop_mod.normalise_banking(
                {"arrangement": "consortium", "lead_bank": _lead, "number_of_banks": 3,
                 "institution_share_pct": 42, "banks": [{"name": _lead, "share_pct": 42, "role": "Lead"},
                                                                   {"name": "Bank B", "share_pct": 33, "role": "Member"},
                                                                   {"name": "Bank C", "share_pct": 25, "role": "Member"}]})
            app["proposal"]["conduct"] = {"period": "preceding 12 months", "rows": prop_mod.normalise_conduct([
                {"month": "2026-08", "limit_cr": 300, "outstanding_cr": 291, "status": "irregular",
                 "irregularity": "Temporary excess regularised", "peak_irregularity_cr": 8,
                 "instances": 1, "irregular_days": 3, "remarks": "Regularised within the month"},
                {"month": "2026-09", "limit_cr": 300, "outstanding_cr": 275, "status": "regular"}])}
            app["proposal"]["exposure"].update(prop_mod.normalise_exposure(
                {"sector_wise": [{"label": "Tyres", "cr": 415}], "state_wise": [{"label": "Tamil Nadu", "cr": 415}],
                 "sanctioned_cr": 350, "disbursed_cr": 300, "outstanding_cr": 285, "lms_committed_cr": 350,
                 "sector": "Manufacturing", "state": "Tamil Nadu", "norms": {"lef": 400, "epm": 375},
                 "breach_alert": "EPM threshold exceeded by proposed exposure (demo)",
                 "exception": {"description": "Temporary EPM breach", "justification": "Time-bound reduction plan",
                               "decided_by": "Credit Committee (demo)", "decided_at": stamp}}))
            app["pricing"].update(other_banks_comparison="Peer pricing 12.10%-12.50% (demo)",
                                  justification="Risk-adjusted pricing within peer range")
            app["pricing"]["fees"] = [pricing_mod.normalise_fee(
                {"facility_id": fid, "nature": "Processing fee", "type": "upfront", "scope": "facility",
                 "amount_cr": 1.25, "pct": 0.5, "milestone": "On acceptance", "total_cr": 1.475}, 1)]
            app["pricing"]["tentative_schedules"] = pricing_mod.normalise_tentative_schedule(
                {"facility_ids": [fid], "amount_cr": f["amount_cr"], "tenor_months": f.get("tenor_months") or 36,
                 "pricing": "MCLR + 90 bps", "repayment_type": "quarterly_quarters",
                 "repayment_frequency": "quarterly", "moratorium_months": 6,
                 "repayment_period": "30 months", "acceptability_comments": "Acceptable in base case"}, 1, {fid})
            dreg.register_generated(app["documents"], name="ESMS Approval Note", kind="esms_note",
                                    by_name="Demo seed", at=stamp)
            app["demo_features"] = ["cma", "ratings", "raroc", "proposal", "exposure", "project", "esms",
                                    "security", "pricing", "fees", "schedule", "external_parties"]

        elif entity_id == "APOL001":
            snap.record_snapshot(app, "IP-review", stamp, "Demo seed")
            app["demo_features"] = ["authority", "committee", "approval_snapshot"]

        elif entity_id == "INFY001":
            facs = app.get("facilities") or []
            app["consent"] = {"acknowledged_by": "Authorised Signatory - Infosys Limited (demo)",
                              "consent_date": at.date().isoformat(), "remarks": "Sanction terms accepted (demo)",
                              "facilities": [{"facility_id": f["facility_id"], "execution_status": "executed",
                                              "agreement_date": at.date().isoformat()} for f in facs],
                              "by": "seed", "by_name": "Demo seed", "at": stamp}
            facmod.apply_execution(facs, app["consent"]["facilities"], stamp, "Demo seed")
            registry = app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app)))
            dreg.register_generated(registry, name="Sanction letter - accepted", kind="sanction_letter",
                                    by_name="Demo seed", at=stamp)
            covenants = [c for c in app.get("conditions") or [] if c.get("type") in ("FC", "NC", "CS")]
            if covenants:
                record_covenant_test(covenants[0], stamp, "fail", "Demo seed", "DSCR below stipulated level (demo)")
            if len(covenants) > 1:
                record_covenant_test(covenants[1], stamp, "fail", "Demo seed", "Reporting delayed (demo)")
                record_covenant_cure(covenants[1], stamp, "Demo seed", "Required report received (demo cure)")
            if len(covenants) > 2:
                mon = covenant_monitor(covenants[2])
                mon.update(compliance="compliant", next_due=(self.now() - timedelta(days=5)).date().isoformat())
            app["demo_features"] = ["consent", "facility_execution", "conditions", "covenant_breach",
                                    "covenant_cure", "covenant_reminder", "sanction_letter"]

        elif entity_id == "PNCR001":
            app["demo_features"] = ["disbursement_ops", "sop", "memo", "review_chain"]

        self.store.save(app)

    def _seed_exit_showcase(self) -> int:
        """Create a separate completed case so repeat-tranche re-entry is visible without consuming PNCR001."""
        source = self.companies.get("PNCR001")
        if not source:
            return 0
        self.companies.setdefault(DEMO_EXIT_ENTITY, source)
        now = self.now().replace(microsecond=0)
        rm = self._system_session("ps_maker")
        app = self.create(rm, entity_id=DEMO_EXIT_ENTITY, at=now - timedelta(days=55), seeded=True, profile="client_one",
                          priority="Normal", prospect_discussion={"project_type": "Infrastructure",
                          "funding_type": "Term facility", "brief_description": "Approved first-tranche showcase.",
                          "detailed_discussion": "First tranche completed; later drawdowns remain governed (demo).",
                          "initial_remarks": "Dedicated repeat-tranche presentation case."},
                          sourcing_decision={"decision": "Refer for in-principle",
                          "mandatory_remarks": "Demo seed - separate approved first-tranche showcase."})
        self._replay_to(app["application_id"], "dis_maker", now - timedelta(days=55), now - timedelta(days=10))
        self._seed_disbursement_record(app["application_id"], now - timedelta(days=10))
        app = self.store.get(app["application_id"])
        fac = app["facilities"][0]
        amount = round(min(float(fac.get("committed_cr") or fac.get("proposed_cr") or 1), 25.0), 2)
        facmod.allocate_tranche(app["facilities"], fac["facility_id"], amount, now.isoformat(timespec="seconds"))
        app["disbursement"] = {"tranches": [{"no": 1, "amount_cr": amount, "facility_id": fac["facility_id"],
                                               "value_date": (now - timedelta(days=7)).date().isoformat(),
                                               "purpose": "First milestone drawdown (demo)", "status": "approved",
                                               "requested": {"by": "seed", "by_name": "Demo seed", "at": now.isoformat(timespec="seconds")},
                                               "approved": {"by": "seed", "by_name": "Final Approver (demo)", "at": now.isoformat(timespec="seconds")}}]}
        app.update(status=STATUS_APPROVED, step_id=None, stage_id="EXIT", assignee_id=None,
                   updated_at=now.isoformat(timespec="seconds"), completed_at=now.isoformat(timespec="seconds"),
                   demo_note="Exit (approved) showcase - first tranche approved; use Request subsequent tranche.",
                   demo_features=["exit_approved", "subsequent_tranche"])
        self.store.save(app, self._event(app, "approve", actor={"id": "seed", "role": "dis_approver"},
                                         from_step="dis_approver", to_step=None, at=now,
                                         comment="First tranche approved for release (demo; no payment settlement claimed)"))
        return 1

    def _seed_stage_docs(self, application_id: str, stage: str, at: datetime) -> None:
        """Seeded history: the stage's mandatory documents were previously on file (demo)."""
        app = self.store.get(application_id)
        registry = app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app)))
        v = at.isoformat(timespec="seconds")
        for d in registry:
            if d.get("mandatory_stage") != stage:
                continue
            if d["versions"]:                     # linked by the document agent: the review is the seeded part
                if d["status"] not in dreg.MANDATORY_STATUSES:
                    d.update(status="reviewed", reviewer="Legacy system (demo seed)", reviewed_at=v)
                continue
            if stage == "AP" and d["name"].startswith("Valuation") and not app.get("securities"):
                continue
            if stage == "AP" and d["name"].startswith("TEV") and not app.get("projects"):
                continue
            d["versions"].append({"v": 1, "file_name": f"seeded-{d['doc_id']}.pdf", "uploaded_by": "Legacy system (demo seed)",
                                  "at": v, "source": "seeded", "detail": "Previously on file (demo seed)"})
            d.update(status="reviewed", reviewer="Legacy system (demo seed)", reviewed_at=v)
        self.store.save(app)

    def _seed_ap_workspace(self, application_id: str, at: datetime) -> None:
        """Seeded history past the AP Risk Maker: CMA recorded and the pricing benchmark/spread set (RUL-07)."""
        app = self.store.get(application_id)
        at_s = at.isoformat(timespec="seconds")
        cma = app.setdefault("cma", cma_mod.initial_cma())
        if not cma.get("subjects"):
            case = self.cases.get(app["entity_id"]) if self.cases else None
            hist = ((case or {}).get("financials") or {}).get("historical") or []
            rows = {}
            for h in hist[-3:]:
                if isinstance(h, dict) and h.get("year"):
                    rows[str(h["year"])] = {k: v for k, v in (("revenue", h.get("revenue_cr")), ("pat", h.get("pat_cr")),
                                                               ("pbt", h.get("pbt_cr"))) if v not in (None, "")}
            if not rows:      # fallback: the borrower's (demo) financial statements
                company = self.companies.get(app["entity_id"]) or {}
                for period, stmt in sorted((company.get("financials") or {}).items(), reverse=True)[:3]:
                    li = getattr(stmt, "line_items", None) or {}
                    vals = {"revenue": li.get("revenue_operating"), "income": li.get("total_income"),
                            "expenses": ((li.get("raw_material_cost") or 0) + (li.get("employee_cost") or 0)
                                         + (li.get("other_expenses") or 0)) or None,
                            "depreciation": li.get("depreciation"), "finance_cost": li.get("finance_cost"),
                            "pbt": li.get("pbt"), "pat": li.get("pat"), "cash_accruals": li.get("ocf")}
                    rows[str(period)] = {k: v for k, v in vals.items() if v not in (None, "")}
            if rows:
                cma["subjects"] = [{"subject": "borrower", "rows": rows,
                                    "versions": [{"v": 1, "by": "Demo seed", "at": at_s, "value_class": "audited",
                                                  "periods": sorted(rows), "highlights": {}}]}]
                cma.update(review_status="approved", review_by="Demo seed", review_at=at_s)
        pricing = app.setdefault("pricing", pricing_mod.initial_pricing())
        for f in app.get("facilities", []):
            if f.get("facility_nature") == "fund_based" and f["facility_id"] not in pricing.get("facilities", {}):
                pricing.setdefault("facilities", {})[f["facility_id"]] = {
                    "recommended_benchmark": "MCLR", "proposed_benchmark": "MCLR",
                    "recommended_rate": 12.2, "proposed_rate": 12.4,
                    "recommended_spread_bps": 80, "proposed_spread_bps": 85,
                    "borrower_risk_rating": None, "comparison": None}
        dreg.register_generated(app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app))),
                                name="CMA (prepared in the CMA workspace)", kind="cma_download",
                                by_name="Demo seed", at=at_s)
        self.store.save(app)

    def _seed_disbursement_record(self, application_id: str, at: datetime) -> None:
        """PNCR001 (demo): the operational disbursement record is on file; the memo review and two SOP items remain."""
        app = self.store.get(application_id)
        stamp = at.isoformat(timespec="seconds")
        fac = (app.get("facilities") or [app.get("facility") or {}])[0]
        fac_id = fac["facility_id"]
        amount = fac.get("committed_cr") or fac.get("proposed_cr") or 100.0
        app["securities"] = [{"security_id": "SEC-001", "category": "primary", "type": "land_building",
                              "subtype": None, "facility_ids": [fac_id], "description": "Land and building (demo)",
                              "proposed_value_cr": round(amount * 1.2, 2), "apportioned_value_cr": round(amount * 1.2, 2),
                              "valuation_date": at.date().isoformat(), "valuation_basis": "Chartered valuer (demo)",
                              "charge_type": "first_charge", "charge_priority": 1, "creation_status": "created",
                              "creation_date": at.date().isoformat(), "perfection_status": "in_progress",
                              "perfection_eta": None, "los_security_id": "LOS-SEC-7841", "cersai": "filed", "roc": "filed",
                              "cbs_security_no": None, "evidence": [], "history": []}]
        d = app.setdefault("disops", {"sop": do.initial_sop()})
        d.update(cif={"status": "exists", "cif_no": "CIF-440291", "note": "ETB — existing CIF verified (demo)"},
                 exposure={"total_cr": amount, "fund_based_cr": amount, "non_fund_cr": 0.0},
                 limits=[{"facility_id": fac_id, "kind": "total", "limit_id": "LMT-77120", "suffix": None,
                          "next_review_date": None},
                         {"facility_id": fac_id, "kind": "fund", "limit_id": "LMT-77121", "suffix": None,
                          "next_review_date": None}],
                 loan_accounts=[{"facility_id": fac_id, "account_no": "3140-0442-771", "status": "active"}],
                 security_refs=[{"security_id": "SEC-001", "los_security_id": "LOS-SEC-7841", "type": "land_building",
                                 "facility_id": fac_id, "description": "Land and building (demo)",
                                 "creation_status": "created", "creation_date": at.date().isoformat(),
                                 "perfection_status": "in_progress", "perfection_eta": None,
                                 "valuation_date": at.date().isoformat(), "valuation_cr": round(amount * 1.2, 2),
                                 "cersai": "filed", "roc": "filed", "cbs_security_no": "CBS-884213"}],
                 beneficiaries=[{"beneficiary_id": "BEN-01", "facility_id": fac_id, "type": "borrower",
                                 "name": app.get("borrower_name"), "account_no": "3140101429000442", "bank": ((profiles.get_profile(app=app).get("branding") or {}).get("short_name")) or "The institution",
                                 "branch": "Corporate Centre", "ifsc": "DEMB0000442", "payment_mode": "RTGS",
                                 "amount_cr": amount}],
                 fees=[{"fee_id": "FEE-01", "facility_id": fac_id, "nature": "upfront", "type": "Arrangement fee",
                        "scope": "facility", "amount_cr": round(amount * 0.005, 2), "pct": 0.5,
                        "milestone": "At execution", "comments": None, "gross_cr": round(amount * 0.005, 2),
                        "due_cr": round(amount * 0.005, 2), "gst_cr": round(amount * 0.0009, 2),
                        "total_cr": round(amount * 0.0059, 2), "receipt_date": at.date().isoformat(),
                        "received_cr": round(amount * 0.0059, 2), "balance_cr": 0.0, "pending_due_date": None,
                        "remarks": None}],
                 non_fund_charges={"charges": [], "gst_cr": None, "deferred_balance_cr": None,
                                  "collection_frequency": None, "due_date": None, "pending_recovery_remarks": None},
                 repayment_final={"moratorium_months": 6, "tenor_months": 36, "instalment_frequency": "quarterly",
                                  "interest_payment_details": "Interest quarterly in advance", "repayment_conditions": None},
                 interest_terms={"benchmark": "MCLR", "rate": 12.4, "spread": 0.85, "reset_frequency": "annual",
                                 "reset_date": None, "additional_interest_non_perfection": 0.5,
                                 "effective_rate": 12.9, "penal_rate": 15.4, "start_date": at.date().isoformat(),
                                 "calculation_parameters": "Interest on actuals, 365-day base (demo)"},
                 arrears={"exists": False, "rows": []},
                 drawdown={"request_ref": "DD-77120-01", "request_date": at.date().isoformat(),
                           "schedule": [{"tranche": 1, "amount_cr": amount, "date": at.date().isoformat()}],
                           "annexures": ["Annexure I — Repayment Schedule", "Annexure IV — Security Details"]})
        sop = do.initial_sop()
        for item in sop:
            if item["id"] in ("sop_treasury", "sop_legal"):
                continue
            item.update(status="in_compliance", remarks="Confirmed (demo seed)", by_name="Disbursement Maker (demo seed)", at=stamp)
        d["sop"] = sop
        d["memo"] = {"version": 1, "generated_at": stamp, "generated_by": "Disbursement Maker (demo seed)",
                     "content_hash": do.memo_hash(d), "reviewed": False, "reviewed_by": None, "reviewed_at": None,
                     "review_remarks": None}
        registry = app.setdefault("documents", dreg.initial_registry(self._doc_checklist(app)))
        for doc_name, detail in (("Drawdown request", "DD-77120-01"), ("Drawdown schedule report", "1 tranche")):
            doc = next((x for x in registry if x["name"] == doc_name), None)
            if doc and not doc["versions"]:
                doc["versions"].append({"v": 1, "file_name": f"seeded-{doc['doc_id']}.pdf", "uploaded_by": "Legacy system (demo seed)",
                                        "at": stamp, "source": "seeded", "detail": f"{detail} (demo seed)"})
                doc.update(status="reviewed", reviewer="Legacy system (demo seed)", reviewed_at=stamp)
        dreg.register_generated(registry, name="Disbursement memo (generated and reviewed)", kind="disbursement_memo",
                                by_name="Disbursement Maker (demo seed)", at=stamp)
        self.store.save(app, self._event(app, "disops_seeded", actor={"id": "seed", "role": "dis_maker"},
                                         from_step=app.get("step_id"), to_step=app.get("step_id"), at=at,
                                         comment="Disbursement operational record on file (demo seed)"))
        # The seeded security is part of the approved package — refresh the snapshot so the
        # material-change gate does not flag the seeded history itself.
        snap.record_snapshot(app, "sanction", stamp, "Demo seed")
        self.store.save(app)

    def _seed_pos_history(self, application_id: str, at: datetime, session: dict) -> None:
        """Seeded history for the post-sanction stage: conditions satisfied, the Sanction
        Letter issued (RUL-10) with its acceptance window running to the walk's clock, the
        customer's acceptance and signed copy on file (R8), per-facility execution recorded."""
        app = self.store.get(application_id)
        for c in app.get("conditions") or []:
            if c["type"] in ("PC", "CP", "CPS"):
                c.update(status="satisfied", note="Satisfied (seeded demo history)", updated_by="Demo seed",
                         updated_at=at.isoformat(timespec="seconds"))
        self.store.save(app)
        self.generate_letter(application_id, session, "sanction_letter", at=at)   # RUL-10: the letter is on file
        app = self.store.get(application_id)
        lts = app.setdefault("letters", {})
        vers = lts.get("sanction_letter") or []
        if vers and at:
            # the acceptance window must still be open at the walk's clock (the seeded
            # acceptance is recorded against it)
            end0 = max(at, self.now())
            for vv in vers:
                vv["valid_until"] = (end0 + timedelta(days=30)).date().isoformat()
        app["consent"] = {"acknowledged_by": "Customer authorisation (demo seed)", "consent_date": at.date().isoformat(),
                          "remarks": "Sanction accepted (seeded demo history)",
                          "facilities": [{"facility_id": f["facility_id"], "execution_status": "executed",
                                           "agreement_date": at.date().isoformat()}
                                          for f in (app.get("facilities") or [app.get("facility") or {}])],
                          "by": "seed", "by_name": "Demo seed", "at": at.isoformat(timespec="seconds")}
        if vers:
            # R8: the seeded history includes the customer's signed copy of the letter (verified)
            lts["sanction_letter_signed"] = {"filename": "signed-copy-seeded.pdf",
                                             "letter_version": vers[-1]["version"],
                                             "uploaded_by": "Demo seed", "at": at.isoformat(timespec="seconds"),
                                             "status": "verified", "reviewed_by": "Demo seed",
                                             "reviewed_at": at.isoformat(timespec="seconds"),
                                             "hash": hashlib.sha256(b"seeded-signed-copy").hexdigest()}
        self.store.save(app)
        app = self.store.get(application_id)
        facmod.apply_execution(app.get("facilities") or [], app["consent"]["facilities"],
                               at.isoformat(timespec="seconds"), "Demo seed")
        self.store.save(app)
        self._seed_stage_docs(application_id, "POS", at)

    def _replay_to(self, application_id: str, target: str, t0: datetime, end: datetime) -> None:
        """Walk the application forward to ``target`` with the default holders, spacing the events between
        ``t0`` and ``end`` (when it enters the target step). The walk follows the application's own
        profile workflow."""
        app0 = self.store.get(application_id)
        wf = self._wf(app0)
        target_index = wf.step(target).index
        span = max(target_index, 1)
        for i in range(target_index):
            app = self.store.get(application_id)
            if app["step_id"] == target:                    # route skips move the case ahead faster
                break
            step = wf.step(app["step_id"])
            session = self._system_session(step.role, app.get("assignee_id"), wf)
            action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                      "allocation": "allocate"}[step.kind]
            allocate_to = self._default_assignee(step.allocates_to, wf) if step.kind == "allocation" else None
            at = t0 + (end - t0) * (i + 1) / span
            # seeded history for the stage the walk is completing (must run before the act:
            # the PS seed feeds the gates, the POS seed records the acceptance on file)
            if step.id == "ps_maker":
                self._seed_due_diligence(application_id, at)
                self._seed_stage_docs(application_id, "PS", at)
            if step.id == "pos_maker":
                self._seed_pos_history(application_id, at, session)
            if step.id == IP_NOTE_STEP:              # seeded history: the IP Note was prepared
                app = self.store.get(application_id)
                app["ip_note"] = build_ip_note(app, self.companies.get(app["entity_id"]), now=at) | {"seeded": True}
                self.store.save(app)
                self._seed_stage_docs(application_id, "IP", at)
            # R1: the concurrences the profile's calculated route requires at this sanction,
            # signed by their own roles before the committee meets (seeded demo history)
            if step.id in SANCTION_STEPS:
                app = self.store.get(application_id)
                for c in self._concurrences_needed(app, step.id):
                    self.record_concurrence(application_id, self._system_session(self.CONCURRENCE_ROLES[c["id"]], None, wf),
                                             {"concurrence_id": c["id"], "remarks": f"{c['label']} (seeded demo history)",
                                              "at": at.isoformat(timespec="seconds")})
            # R9: when the institution governs committee meetings, the seeded history carries
            # the meeting record (attendance, minutes, a fully approving vote) — on file before
            # the walk performs the committee's decision (a governed institution's history
            # includes its meetings; live decisions are always gated the same way)
            if step.kind == "committee" and (self._profile(app).get("committee_governance") or {}).get("enabled"):
                self._seed_committee_meeting(application_id,
                                             self._system_session(step.role, app.get("assignee_id"), wf),
                                             step.id, at)
            if step.id == "ap_note":                # seeded history: the AP-stage documents were on file
                self._seed_stage_docs(application_id, "AP", at)
            if step.id == "ap_risk_maker":           # seeded history: CMA recorded, pricing benchmark set
                self._seed_ap_workspace(application_id, at)
                self._seed_stage_docs(application_id, "AP", at)
            if step.id == "dis_maker":               # later-stage showcases need a completed maker record
                self._seed_disbursement_record(application_id, at)
                self._seed_stage_docs(application_id, "DIS", at)
                app = self.store.get(application_id)
                disops = app.setdefault("disops", {})
                for item in disops.get("sop") or []:
                    item.update(status="in_compliance", remarks="Confirmed (seeded demo history)",
                                by_name="Disbursement Maker (demo seed)",
                                at=at.isoformat(timespec="seconds"))
                if disops.get("memo"):
                    disops["memo"].update(reviewed=True, reviewed_by="Disbursement Reviewer (demo seed)",
                                          reviewed_at=at.isoformat(timespec="seconds"),
                                          review_remarks="Reviewed (seeded demo history)")
                self.store.save(app)
            if step.id == ES_MAKER_STEP:             # seeded history: the ESMS screen and categorisation
                app = self.store.get(application_id)
                esms = app.setdefault("esms", es.initial_esms(app))
                esms.update(screening_date=at.date().isoformat(), category=esms.get("category") or
                            esms.get("proposed_category") or "B", information_source="Seeded demo history",
                            checklist=[{"id": i, "label": label, "answer": "No", "remarks": "Screened (seeded demo history)",
                                        "source": "Demo seed"} for i, label in es.ES_CHECKLIST], status="complete")
                if esms["category"] == "A" and not esms.get("esdd"):
                    esms["esdd"] = "ESDD required (seeded demo history)"
                self.store.save(app)
            if step.id == ES_PREP_STEP:              # seeded history: the ESMS Approval Note was generated
                app = self.store.get(application_id)
                dreg.register_generated(app.setdefault("documents", []), name="ESMS Approval Note",
                                        kind="esms_approval_note", by_name="Demo seed", at=at.isoformat(timespec="seconds"))
                self.store.save(app)
            if step.id in RISK_MAKER_STEPS:          # seeded history: the assessment is recorded as done
                app = self.store.get(application_id)
                app["credit_assessment"] = self._seed_assessment_summary(app)
                self.store.save(app)
            required = {f["id"]: at.date().isoformat() if wfmod.DECISION_FIELD_TYPES[f["id"]] == "date"
                        else "None (seeded demo history)" for f in step.decision_fields if f.get("required")}
            self.act(application_id, session, action, at=at, allocate_to=allocate_to, decision_data=required,
                     comment="Sanctioned by the committee (seeded demo history)." if action == "sanction"
                     else ("Post-sanction documentation verified (seeded demo history)." if step.id == "pos_checker"
                           else f"{step.name}: {action} (seeded demo history)."))

    def _seed_assessment_summary(self, app: dict) -> dict:
        """For applications seeded past the Risk Maker: the borrower's stored credit case, if any."""
        case = self.cases.get(app["entity_id"]) if self.cases else None
        if case and self._case_stale(case, app):          # the stored case is for another request: assess this one
            case = self._run_case(app["entity_id"], app)[0]
        rea = (case or {}).get("reassessment") or {}
        fr = rea.get("facility_recommendation") or {}
        return {"run_id": (case or {}).get("run_id"), "run_at": (case or {}).get("run_at"),
                "decision": rea.get("decision"), "decision_label": rea.get("decision_label"),
                "requested_cr": fr.get("requested_cr"), "recommended_cr": fr.get("recommended_cr"),
                "risk_grade": (case or {}).get("risk_grade"), "seeded": True}

    def _seed_return(self, application_id: str, entered: datetime) -> None:
        """Seed a return: the maker submits, the reviewer returns it with a comment (after ``entered``)."""
        app = self.store.get(application_id)
        app["credit_assessment"] = self._seed_assessment_summary(app)
        self.store.save(app)
        maker = self._system_session(self._wf(app).step(app["step_id"]).role, app.get("assignee_id"), self._wf(app))
        self.act(application_id, maker, "submit", at=entered + (self.now() - entered) / 3,
                 comment="Assessment complete; submitted for review (seeded demo history).")
        app = self.store.get(application_id)
        reviewer = self._system_session(self._wf(app).step(app["step_id"]).role, app.get("assignee_id"), self._wf(app))
        self.act(application_id, reviewer, "return", at=entered + (self.now() - entered) * 2 / 3,
                 comment="Please address the debt-servicing shortfall and the open due-diligence items before "
                         "resubmitting (demo note).")

    def _force_assignee(self, application_id: str, user_id: str) -> None:
        app = self.store.get(application_id)
        app["assignee_id"] = user_id
        self.store.save(app)

    def _annotate(self, application_id: str, note: str) -> None:
        app = self.store.get(application_id)
        app["demo_note"] = note
        self.store.save(app)


def _facility_from_company(fac) -> dict:
    if fac is None:
        return {}
    return {
        "facility_type": getattr(getattr(fac, "facility_type", None), "value", None),
        "amount_cr": getattr(fac, "amount_requested_cr", None),
        "tenor_months": getattr(fac, "tenor_months", None),
        "purpose": getattr(fac, "purpose", None),
        "case_type": getattr(getattr(fac, "case_type", None), "value", None),
        "proposal_type": "Fresh",
    }


def _num_or_none(value):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        raise InvalidRequestError("The exposure value must be a number")


_FACILITY_NATURES = {"fund_based", "non_fund_based"}
_PARTY_TYPES = {"individual", "non_individual"}
_PARTY_STATUSES = {"active", "inactive", "withdrawn"}
_PARTY_ROLES = {
    "promoter", "sponsor", "guarantor", "spv", "parent", "subsidiary", "associate",
    "group_concern", "group_company", "joint_venture", "collaborator", "beneficial_owner",
    "director", "key_person",
}
# Roles that change the group structure: a change among these (or their presence) invalidates
# the group rating and any group-level conclusion (UAT-P2-10).
_GROUP_ROLES = {"parent", "subsidiary", "associate", "group_concern", "group_company", "joint_venture"}

# Prospect discussion captured at creation: field → character limit.
_PROSPECT_FIELDS = {
    "project_type": 100,
    "funding_type": 100,
    "brief_description": 500,
    "detailed_discussion": 4000,
    "initial_remarks": 2000,
}


def _normalise_facilities(rows: list[dict], first_defaults: Optional[dict] = None) -> list[dict]:
    """Validate and assign stable application-local IDs to proposed facilities."""
    if not rows:
        raise InvalidRequestError("At least one proposed facility is required")
    if len(rows) > 20:
        raise InvalidRequestError("An application cannot contain more than 20 proposed facilities")
    out = []
    for index, raw in enumerate(rows, 1):
        raw = {k: v for k, v in dict(raw or {}).items() if v not in (None, "")}
        merged = {**(first_defaults or {})} if index == 1 else {}
        merged.update(raw)
        facility_type = str(merged.get("facility_type") or "").strip().lower()
        nature = str(merged.get("facility_nature") or "fund_based").strip().lower()
        try:
            amount = float(merged.get("amount_cr"))
        except (TypeError, ValueError):
            raise InvalidRequestError(f"Facility {index}: proposed amount is required and must be a number")
        if amount <= 0:
            raise InvalidRequestError(f"Facility {index}: proposed amount must be greater than zero")
        if not facility_type:
            raise InvalidRequestError(f"Facility {index}: facility type is required")
        if nature not in _FACILITY_NATURES:
            raise InvalidRequestError(f"Facility {index}: nature must be fund_based or non_fund_based")
        tenor = merged.get("tenor_months")
        if tenor not in (None, ""):
            try:
                tenor = int(tenor)
            except (TypeError, ValueError):
                raise InvalidRequestError(f"Facility {index}: tenor must be a whole number of months")
            if tenor < 0:
                raise InvalidRequestError(f"Facility {index}: tenor cannot be negative")
        out.append({
            "facility_id": f"FAC-{index:03d}",
            "proposal_type": str(merged.get("proposal_type") or "Fresh").strip(),
            "facility_nature": nature,
            "facility_type": facility_type,
            "amount_cr": round(amount, 2),
            "tenor_months": tenor,
            "purpose": str(merged.get("purpose") or "").strip()[:1000],
            "ad_hoc": bool(merged.get("ad_hoc", False)),
            **({"case_type": merged["case_type"]} if merged.get("case_type") else {}),
        })
    return out


def _normalise_sourcing_decision(raw: Optional[dict], *, required: bool = True,
                                 customer: Optional[dict] = None) -> dict:
    """The RM's sourcing decision and mandatory / conditional remarks, captured at creation.
    UAT-P0-4: the decision and the remarks applicable to it are mandatory, and the selected
    Customer ID must match one of the available core-banking (demo data) results."""
    raw = raw or {}
    decision = str(raw.get("decision") or "").strip()
    if required and not decision:
        raise InvalidRequestError("A sourcing decision is required before the application can be created")
    if decision and decision not in SOURCING_DECISIONS:
        raise InvalidRequestError(f"Sourcing decision must be one of: {', '.join(SOURCING_DECISIONS)}")
    out = {"decision": decision or None, "customer_id_selection": None}
    mandatory = str(raw.get("mandatory_remarks") or "").strip()
    if len(mandatory) > 1000:
        raise InvalidRequestError("Sourcing mandatory remarks are limited to 1000 characters")
    if required and decision and not mandatory:
        raise InvalidRequestError("Mandatory remarks are required with the sourcing decision")
    conditional = str(raw.get("conditional_remarks") or "").strip()
    if len(conditional) > 1000:
        raise InvalidRequestError("Sourcing conditional remarks are limited to 1000 characters")
    if required and decision == "Defer" and not conditional:
        raise InvalidRequestError("A deferred decision requires conditional remarks (what must be in place before reconsideration)")
    out["mandatory_remarks"] = mandatory or None
    out["conditional_remarks"] = conditional or None
    selection = str(raw.get("customer_id_selection") or "").strip()
    if selection and selection != "new":
        valid = (customer or {}).get("customer_id")
        if valid != selection:
            hint = (f"Available core-banking result: {valid}." if valid
                    else "No customer record on the core-banking book (new-to-bank) — select 'New customer'.")
            raise InvalidRequestError(
                f"The selected Customer ID {selection} is not among the available core-banking "
                f"results for this borrower. {hint}")
        out["customer_id_selection"] = selection
    return out


def _normalise_prospect_discussion(raw: Optional[dict]) -> dict:
    """The RM's prospect discussion: free text with per-field character limits."""
    raw = raw or {}
    out = {}
    for key, limit in _PROSPECT_FIELDS.items():
        value = str(raw.get(key) or "").strip()
        if len(value) > limit:
            raise InvalidRequestError(f"Prospect discussion field '{key}' is limited to {limit} characters")
        out[key] = value or None
    return out


def _normalise_related_parties(rows: list[dict]) -> list[dict]:
    """Validate related parties captured at application creation."""
    if len(rows) > 50:
        raise InvalidRequestError("An application cannot contain more than 50 related parties")
    out, seen = [], set()
    for index, raw in enumerate(rows, 1):
        raw = dict(raw or {})
        name = str(raw.get("name") or "").strip()
        role = str(raw.get("role") or "").strip().lower()
        party_type = str(raw.get("party_type") or "non_individual").strip().lower()
        if not name:
            raise InvalidRequestError(f"Related party {index}: name is required")
        if role not in _PARTY_ROLES:
            raise InvalidRequestError(f"Related party {index}: select a valid role")
        if party_type not in _PARTY_TYPES:
            raise InvalidRequestError(f"Related party {index}: type must be individual or non_individual")
        party_status = str(raw.get("party_status") or "active").strip().lower()
        if party_status not in _PARTY_STATUSES:
            raise InvalidRequestError(f"Related party {index}: party status must be one of {', '.join(sorted(_PARTY_STATUSES))}")
        key = (name.casefold(), role)
        if key in seen:
            raise InvalidRequestError(f"Related party {index}: {name} is already listed as {role.replace('_', ' ')}")
        seen.add(key)
        ownership = raw.get("ownership_pct")
        if ownership not in (None, ""):
            try:
                ownership = round(float(ownership), 4)
            except (TypeError, ValueError):
                raise InvalidRequestError(f"Related party {index}: ownership must be a percentage")
            if ownership < 0 or ownership > 100:
                raise InvalidRequestError(f"Related party {index}: ownership must be between 0 and 100")
        out.append({
            "party_id": f"RP-{index:03d}",
            "name": name[:200],
            "role": role,
            "party_type": party_type,
            "ownership_pct": ownership,
            "pan": str(raw.get("pan") or "").strip().upper()[:10] or None,
            "cin": str(raw.get("cin") or "").strip().upper()[:21] or None,
            "relationship": str(raw.get("relationship") or "").strip()[:300] or None,
            "sourced_address": str(raw.get("sourced_address") or "").strip()[:400] or None,
            "key_person_role": str(raw.get("key_person_role") or "").strip()[:120] or None,
            "party_status": party_status,
            "verification_status": "pending",
        })
    return out


def _typed(kind: str, raw, label: str):
    """An accepted value in the field's type (amounts and months are numbers)."""
    if kind in ("amount", "int"):
        try:
            v = float(str(raw).replace(",", "").replace("₹", "").strip())
        except ValueError:
            raise InvalidRequestError(f"{label} must be a number")
        if v <= 0:
            raise InvalidRequestError(f"{label} must be greater than zero")
        return int(v) if kind == "int" else v
    return str(raw).strip()


def load_workflow(profile_id: Optional[str] = None) -> Workflow:
    """The institution's journey: the base workflow (config/los_workflow.yaml) resolved
    through the institution profile's module switches and step / stage overrides."""
    pid = profile_id or profiles.active_profile_id()
    cfg = profiles.workflow_config(pid)
    return Workflow.from_config(cfg, decision_field_labels=profiles.decision_field_labels(profiles.get_profile(pid)))
