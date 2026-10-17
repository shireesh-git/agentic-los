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
import secrets
import shutil
import re
import threading
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


class LosService:
    def __init__(self, store, workflow_loader: Callable[[], Workflow], companies: dict,
                 clock: Callable[[], datetime] = datetime.now, cases=None, final_cam=None,
                 documents_root: Optional[Path] = None, doc_store=None, llm_factory: Optional[Callable] = None,
                 company_registrar: Optional[Callable] = None):
        self.store = store
        self._workflow_loader = workflow_loader
        self._workflow: Optional[Workflow] = None
        self.companies = companies          # entity_id → company record (AppState.companies)
        self.clock = clock
        self.cases = cases                  # CaseService: runs the credit-intelligence pipeline
        self.final_cam = final_cam          # FinalCamService: re-syncs M1–M7 for a case
        self._sessions: dict[str, dict] = {}
        self._jobs: dict[str, dict] = {}    # application_id → running / last credit-assessment job
        self._jobs_lock = threading.Lock()
        self.documents_root = Path(documents_root) if documents_root else None   # storage/documents/{entity}/...
        self.doc_store = doc_store          # DocumentStore: writes uploads into the borrower's folders
        self.llm_factory = llm_factory      # optional AI fallback / IP Note summary
        self._field_registry: Optional[FieldRegistry] = None
        self._app_locks: dict[str, threading.Lock] = {}
        self._app_locks_guard = threading.Lock()
        self._prep_jobs: dict[str, dict] = {}   # application_id → stage-preparation job (agent lanes)
        self.company_registrar = company_registrar   # registers a new prospect borrower (CompanyService)

    @property
    def wf(self) -> Workflow:
        if self._workflow is None:
            self._workflow = self._workflow_loader()
        return self._workflow

    def now(self) -> datetime:
        return self.clock().replace(microsecond=0)

    # ── demo sign-in ─────────────────────────────────────────────────────────
    def directory(self) -> dict:
        """Groups, roles and demo users for the sign-in screen and allocation pickers."""
        return {"groups": self.wf.groups, "roles": self.wf.roles,
                "users": [{k: u[k] for k in ("id", "name", "email", "branch", "roles")} for u in self.wf.users],
                "note": DEMO_NOTE}

    def sign_in(self, user_id: str, role: str) -> dict:
        try:
            user = self.wf.user(user_id)
        except WorkflowError as e:
            raise NotFoundError(str(e))
        if role not in user.get("roles", []):
            raise ForbiddenError(f"{user['name']} does not hold the role {role}")
        token = secrets.token_urlsafe(24)
        session = {"token": token, "user": {k: user[k] for k in ("id", "name", "email", "branch", "roles")},
                   "role": role, "role_name": self.wf.roles[role], "group": self.wf.group_of_role(role)}
        self._sessions[token] = session
        return session

    def session(self, token: Optional[str]) -> dict:
        s = self._sessions.get(token or "")
        if not s:
            raise ForbiddenError("Not signed in (demo session expired — sign in again)")
        return s

    def switch_role(self, token: str, role: str) -> dict:
        s = self.session(token)
        if role not in s["user"]["roles"]:
            raise ForbiddenError(f"{s['user']['name']} does not hold the role {role}")
        s.update(role=role, role_name=self.wf.roles[role], group=self.wf.group_of_role(role))
        return s

    def sign_out(self, token: str) -> None:
        self._sessions.pop(token or "", None)

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
            step = self.wf.step(app["step_id"])
            view["step"] = {"id": step.id, "name": step.name, "kind": step.kind, "role": step.role,
                            "role_name": self.wf.roles[step.role], "stage_id": step.stage_id,
                            "stage_name": step.stage_name, "sla_days": step.sla_days,
                            "allocates_to": step.allocates_to}
            active = app["status"] not in TERMINAL
            deferred = app["status"] == wfmod.STATUS_DEFERRED
            # A deferred application is on hold: its SLA clock is paused (restarted on reactivation).
            view["sla"] = (sla_state(datetime.fromisoformat(app["step_entered_at"]), step, now)
                           if active and not deferred else None)
            holder = app.get("assignee_id") in (None, (session or {}).get("user", {}).get("id"))
            in_role = bool(session and active and can_act(self.wf, session["user"]["id"], session["role"], step))
            # the step's actions are offered to the person it is assigned to; others in the role see who holds it
            view["actions"] = list(wfmod.available_actions(self.wf, step, app["status"])) if in_role and holder else []
            view["assigned_to_other"] = in_role and not holder
            view["action_labels"] = {a: wfmod.action_label(step, a) for a in view["actions"]
                                     if wfmod.action_label(step, a)}
            view["decision_fields"] = [dict(f, type=wfmod.DECISION_FIELD_TYPES[f["id"]],
                                            label=wfmod.DECISION_FIELD_LABELS.get(f["id"], f["id"].replace("_", " ").capitalize()))
                                       for f in step.decision_fields]
            view["decision_defaults"] = self._decision_defaults(app, step) if step.decision_fields else {}
            view["remarks_required"] = self.wf.remarks_required
            view["deferral"] = (app.get("deferrals") or [None])[-1] if deferred else None
            view["rework_destinations"] = (wfmod.rework_destinations(self.wf, step)
                                           if step.kind in ("checker", "committee", "vp_review") else [])
            view["can_reassign"] = bool(session and active and self._may_reassign(session, step))
        else:
            view["step"], view["sla"], view["actions"], view["can_reassign"] = None, None, [], False
        view["rail"] = self._rail(app)
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
        view["proposal"] = app.get("proposal")
        view["pricing"] = app.get("pricing")
        view["terms_summary"] = terms_mod.summary(app.get("terms"), app.get("fields"))
        secured_ids = {fid for s in app.get("securities") or [] for fid in s.get("facility_ids") or []}
        view["facilities"] = [dict(f, secured=f["facility_id"] in secured_ids) if isinstance(f, dict) and "facility_id" in f
                              else f for f in view.get("facilities") or []]
        view["unit_visits"] = app.get("unit_visits") or []
        view["unit_visit_observations"] = list(prop_mod.UNIT_VISIT_OBSERVATIONS)
        view["sourcing_details"] = app.get("sourcing_details")
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
        current = self.wf.step(app["step_id"]).index if app.get("step_id") else len(self.wf.steps)
        done_all = app["status"] == STATUS_APPROVED
        returned = app["status"] == "RETURNED"
        rail = []
        for stage in self.wf.stages:
            steps = []
            for s in (x for x in self.wf.steps if x.stage_id == stage["id"]):
                state = ("done" if done_all or s.index < current
                         else "current" if s.index == current else "pending")
                if state == "current" and returned:
                    state = "returned"
                if state == "current" and app["status"] == STATUS_REJECTED:
                    state = "rejected"
                steps.append({"id": s.id, "name": s.name, "state": state, "role_name": self.wf.roles[s.role]})
            states = {x["state"] for x in steps}
            stage_state = ("done" if states == {"done"} else
                           "current" if states & {"current", "returned", "rejected"} else "pending")
            rail.append({"id": stage["id"], "name": stage["name"], "state": stage_state, "steps": steps})
        return rail

    def list(self, session: Optional[dict] = None, *, status: str = "", stage: str = "", mine: bool = False,
             query: str = "") -> list[dict]:
        now = self.now()
        out = []
        for app in self.store.list():
            if status and app["status"] != status:
                continue
            if stage and app.get("stage_id") != stage:
                continue
            if mine and session and session["role"] == "compliance_vp":
                if app["status"] in TERMINAL or not self._pending_exception_requests(app):
                    continue
            elif mine and session:
                step = self.wf.step(app["step_id"]) if app.get("step_id") else None
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
        return view

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
            step = self.wf.step(app["step_id"]) if app.get("step_id") else None
            stage = next((s for s in self.wf.stages if s["id"] == app.get("stage_id")), None)
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
        return [self._event_view(e) for e in self.store.events(limit=limit)]

    def dashboard(self, session: Optional[dict] = None) -> dict:
        now = self.now()
        apps = [self._view(a, session, now) for a in self.store.list()]
        active = [a for a in apps if a["status"] not in TERMINAL]
        month_start = now.replace(day=1, hour=0, minute=0, second=0)
        sanctioned_mtd = {e["application_id"] for e in self.store.events(limit=5000)
                          if e["action"] == "sanction" and datetime.fromisoformat(e["at"]) >= month_start}
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
                                   if a.get("due_diligence") and dd.blocking(a["due_diligence"]["checks"], now=now)),
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
            rev = dd.screening_review(a["due_diligence"]["checks"], now)
            if not rev["needs_attention"]:
                continue
            items = [f"{r['name']}: 90-day re-screening due {r['due_at']} ({r['days_left']} days left)"
                     for r in rev["rescreens"] if r["state"] != "current"]
            items += [f"{e['name']}: Compliance VP exception {e['state']} on {e['expires_at']}"
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

    def _default_assignee(self, role: str) -> Optional[str]:
        """The holder of ``role`` with the fewest active applications (simple load balancing)."""
        users = self.wf.users_with_role(role)
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
               at: Optional[datetime] = None, seeded: bool = False, cam: Optional[dict] = None) -> dict:
        """A new draft at Prospect Sourcing. ``cam`` starts it from a CAM (see ``_attach_cam``):
        {"mode": "workspace", "run_id"?} · {"mode": "document", "staging_id"} · {"mode": "generate"};
        the preparation agent then starts at once."""
        if cam and cam.get("mode") not in CAM_MODES:
            raise InvalidRequestError(f"Unknown CAM option: {cam.get('mode')} (one of {', '.join(CAM_MODES)})")
        first = self.wf.first_step
        if not seeded and session["role"] != first.role:
            raise ForbiddenError(f"Only the {self.wf.roles[first.role]} role can create applications")
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
            "documents": dreg.initial_registry(),
            "disops": {"sop": do.initial_sop()},
            "snapshots": [], "material_change_reviews": [],
            "due_diligence": {"version": dd.CHECK_VERSION, "initiated_at": at.isoformat(timespec="seconds"),
                              "checks": dd.initial_checks()},
            "amount_cr": total_amount,
            "stage_id": first.stage_id, "step_id": first.id, "status": STATUS_DRAFT,
            "assignee_id": session["user"]["id"], "priority": priority, "escalated": False,
            "created_by": session["user"]["id"], "created_at": at.isoformat(timespec="seconds"),
            "updated_at": at.isoformat(timespec="seconds"), "step_entered_at": at.isoformat(timespec="seconds"),
            "seeded_demo": seeded,
        }
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "create", actor=actor, to_step=first.id, at=at,
                                         detail={"facilities": facilities, "related_parties": related_parties,
                                                 "total_amount_cr": total_amount,
                                                 "customer_identity": identity, "prospect_discussion": prospect,
                                                 "sourcing_decision": decision}))
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
        """Why the pinned CAM no longer fits this application, or None."""
        other = self._cam_for_other_request(case, app)
        if other or self._has_master_financials(self.companies.get(app.get("entity_id")) or {}):
            return other
        stmt = self._accepted_statement(app)
        if not stmt:
            return None
        used = (((case.get("fact_pack") or {}).get("financial_summary") or {}).get("periods") or {}).get(stmt["period"]) or {}
        keys = {"revenue_operating": "revenue_cr", "ebitda": "ebitda_cr", "pat": "pat_cr",
                "total_equity": "net_worth_cr", "total_debt": "total_debt_cr"}
        differ = [k for k, v in stmt["items"].items()
                  if abs(float(used.get(keys[k]) or 0) - float(v)) > 0.01 * max(abs(float(v)), 1.0)]
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
            registry = app.setdefault("documents", dreg.initial_registry())
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
            deferred_until: Optional[str] = None) -> dict:
        app = self._require(application_id)
        if not app.get("step_id"):
            raise ConflictError("This application is complete")
        step = self.wf.step(app["step_id"])
        if not can_act(self.wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step ({step.name}) belongs to the {self.wf.roles[step.role]} role")
        if app.get("assignee_id") and app["assignee_id"] != session["user"]["id"]:
            raise ForbiddenError(f"Assigned to {self._user_name(app['assignee_id'])}; reassign it first")
        try:
            out = transition(self.wf, step, action, comment=comment, allocate_to=allocate_to,
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
        if step.id == "pos_checker" and not (comment or "").strip():
            raise InvalidRequestError("Post-Sanction Checker remarks are mandatory for every decision at this step")
        stuck = self._gates(app, step, action)
        if stuck:
            raise InvalidRequestError(stuck[0][0])
        # The decision record the step asks for (G-04 / G-W6): e.g. the material-information date.
        decision = self._decision_fields(step, action, decision_data, significant_changes)
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
                "authority": self.wf.roles.get(step.role, step.role)})
        elif action == "defer":
            app.setdefault("deferrals", []).append({
                "at": at.isoformat(timespec="seconds"), "by": session["user"]["id"], "by_name": session["user"]["name"],
                "at_step": step.id, "reason": (comment or "").strip(), "until": str(deferred_until)[:10],
                "reactivated_at": None, "reactivated_by": None})
        elif action == "reactivate":
            last = (app.get("deferrals") or [{}])[-1]
            last.update(reactivated_at=at.isoformat(timespec="seconds"), reactivated_by=session["user"]["name"],
                        reactivation_remarks=(comment or "").strip())
            app["step_entered_at"] = at.isoformat(timespec="seconds")      # the SLA restarts on reactivation
        elif action in ("withdraw", "drop"):
            app["terminated"] = {"type": "withdrawn" if action == "withdraw" else "dropped",
                                 "at": at.isoformat(timespec="seconds"), "by_name": session["user"]["name"],
                                 "at_step": step.id, "reason": (comment or "").strip()}
            app.setdefault("deviations", []).append({
                "type": "withdrawal" if action == "withdraw" else "drop",
                "at": at.isoformat(timespec="seconds"), "by_name": session["user"]["name"],
                "detail": (comment or "")[:300], "authority": self.wf.roles.get(step.role, step.role)})
        if out.step_id and out.step_id != step.id:
            nxt = self.wf.step(out.step_id)
            assignee = (out.assign_user
                        or (self._last_worker(application_id, nxt.id) if action == "return" else None)
                        # the next step in the same role stays with the person who did this one (the RM who sourced
                        # the prospect writes its IP Note), unless they no longer hold the role
                        or (session["user"]["id"] if nxt.role == step.role and nxt.role in session["user"]["roles"] else None)
                        or self._last_worker(application_id, nxt.id)
                        # a later step in a role already worked on this application (the RM's AP Note after
                        # their IP Note) goes back to the same person
                        or self._last_in_role(application_id, nxt.role)
                        or self._default_assignee(nxt.role))
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
        if decision:
            app.setdefault("decisions", []).append({"step": step.id, "step_name": step.name, "action": action,
                                                    "by": session["user"]["id"], "by_name": session["user"]["name"],
                                                    "at": at.isoformat(timespec="seconds"),
                                                    "remarks": (comment or "").strip() or None, **decision})
        self.store.save(app, self._event(app, action, actor=actor, from_step=step.id, to_step=app.get("step_id"),
                                         comment=comment, at=at,
                                         detail={"message": out.message, "allocated_to": allocate_to,
                                                 **({"sanction": sanction} if sanction else {}),
                                                 **({"deferred_until": str(deferred_until)[:10]} if action == "defer" else {}),
                                                 **decision}))
        return self.get(application_id, session)

    _FORWARD = ("submit", "approve", "sanction")

    def _decision_fields(self, step, action: str, data: Optional[dict], significant_changes: Optional[str]) -> dict:
        """The step's decision fields for this decision (G-04), validated; required ones only on a
        forward decision (a return or drop is explained by its remarks)."""
        data = dict(data or {})
        if significant_changes and "significant_changes" not in data:
            data["significant_changes"] = significant_changes              # the earlier API parameter
        out = {}
        for f in step.decision_fields:
            raw = str(data.get(f["id"]) or "").strip()
            label = wfmod.DECISION_FIELD_LABELS.get(f["id"], f["id"].replace("_", " ").capitalize())
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
                                            final=step.id == "ap_sanction")
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
                "at": at.isoformat(timespec="seconds")}

    def _gates(self, app: dict, step, action: str) -> list[tuple[str, str]]:
        """What stops ``action`` at ``step`` now, in the order the bank's gates apply: (message, where to fix
        it — a page section). ``act`` refuses with the first; the application view lists them all, so the
        step holder sees every blocker before pressing the button."""
        out: list[tuple[str, str]] = []
        add = lambda msg, where: msg and out.append((msg, where))
        checks = (app.get("due_diligence") or {}).get("checks") or []
        if action == "submit" and step.id == IP_NOTE_STEP and app.get("ip_note"):
            # G-10: the IP proposal goes for review only with blocking checks resolved and its documents in place
            stuck = dd.blocking(checks, now=self.now())
            if stuck:
                add("Resolve the blocking due-diligence check(s) before submitting the IP Note: "
                    + "; ".join(f"{c['name']} ({c['status']})" for c in stuck[:4]), "checks")
            add(dreg.stage_gate(app), "documents")
        # Mandatory gates (due diligence, consent)
        waiting = {r["check_id"]: r for r in self._pending_exception_requests(app)}
        if action == "submit" and step.id in DD_GATE_STEPS and app.get("due_diligence") and waiting:
            add("Waiting for the Compliance VP's exception decision on: "
                + "; ".join(f"{r['name']} (requested {r['at'][:10]})" for r in waiting.values()), "checks")
        if action == "submit" and step.id in DD_GATE_STEPS and app.get("due_diligence"):
            stuck = [c for c in dd.blocking(app["due_diligence"]["checks"], now=self.now()) if c["id"] not in waiting]
            if stuck:
                names = "; ".join(f"{c['name']} ({c['status']})" for c in stuck[:4])
                add("Resolve the outstanding mandatory due-diligence check(s) before "
                    f"submitting: {names}" + (f" (+{len(stuck) - 4} more)" if len(stuck) > 4 else ""), "checks")
        # the stage's mandatory documents, present and reviewed, at the step that answers for them
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
            add(dreg.stage_gate(app, skip={dreg.CMA_DOC}), "documents")       # the CMA is the Risk Maker's
        if action == "submit" and step.id == "ap_risk_maker":
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
            # an ESMS screen in progress (or any project) complete (RUL-06)
            if not any(s.get("rows") for s in (app.get("cma") or {}).get("subjects") or []):
                add("Record the CMA (financial analysis) in the CMA workspace before submitting", "cma")
            add(pricing_mod.pricing_gate(app.get("pricing") or {}, app.get("facilities") or []), "pricing")
            esms = app.get("esms") or {}
            if any(i.get("answer") for i in esms.get("checklist", [])) or bool(app.get("projects")):
                add(es.esms_gate(esms), "projects")
        if action == "submit" and step.id == ES_MAKER_STEP:
            # G-W2: the CRP ES Maker records the E&S risk categorisation the ES preparation works from
            if (app.get("esms") or {}).get("category") not in es.ES_CATEGORIES:
                add("Record the E&S risk category (A, B or C) in Projects & ESMS — the agent's proposed "
                    "category is there to confirm", "projects")
        if action == "submit" and step.id == ES_PREP_STEP:
            add(es.esms_gate(app.get("esms") or {}), "projects")
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
        return out

    def blockers(self, app: dict, step=None) -> list[dict]:
        """The blockers of the step's forward action (submit / approve), for the view."""
        step = step or (self.wf.step(app["step_id"]) if app.get("step_id") else None)
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
        for e in self.store.events(application_id):
            st = e.get("from_step")
            if not st or e["action"] not in ("submit", "allocate") or not e.get("actor_id"):
                continue
            try:
                if self.wf.step(st).role != role:
                    continue
            except Exception:
                continue
            user = next((u for u in self.wf.users_with_role(role) if u["id"] == e["actor_id"]), None)
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
        step = self.wf.step(app["step_id"])
        if not self._may_reassign(session, step):
            raise ForbiddenError("Your role cannot reassign this step")
        try:
            user = self.wf.user(user_id)
        except WorkflowError as e:
            raise InvalidRequestError(str(e))
        if step.role not in user.get("roles", []):
            raise InvalidRequestError(f"{user['name']} does not hold the {self.wf.roles[step.role]} role")
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
                    final=app.get("stage_id") not in ("PS", "IP"))}
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        return bool(session and step and app["status"] not in TERMINAL
                    and self.field_registry.domains_verified_at(step.id)
                    and can_act(self.wf, session["user"]["id"], session["role"], step)
                    and app.get("assignee_id") in (None, session["user"]["id"]))

    def assessment(self, application_id: str, session: Optional[dict] = None) -> dict:
        """The Risk Maker workspace: job status, the tabs built from the application's pinned
        credit case, and the verify queue for the current step."""
        app = self._require(application_id)
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        can_run = bool(session and step and step.id in RISK_MAKER_STEPS and app["status"] not in TERMINAL
                       and can_act(self.wf, session["user"]["id"], session["role"], step)
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
            step = self.wf.step(app["step_id"])
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or app["status"] in TERMINAL or not self.field_registry.domains_verified_at(step.id):
            raise ConflictError("No fields are verified at this step")
        if not can_act(self.wf, session["user"]["id"], session["role"], step) or \
                app.get("assignee_id") not in (None, session["user"]["id"]):
            raise ForbiddenError(f"Fields are verified by the assigned {self.wf.roles[step.role]}")
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
        step = self.wf.step(app["step_id"])
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in RISK_MAKER_STEPS or app["status"] in TERMINAL:
            raise ConflictError("Fields are reviewed at the Risk Maker step")
        if not can_act(self.wf, session["user"]["id"], session["role"], step) or \
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in RISK_MAKER_STEPS or app["status"] in TERMINAL:
            raise ConflictError("The credit assessment is run at the Risk Maker step")
        if not can_act(self.wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"Only the {self.wf.roles[step.role]} role can run the credit assessment")
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
            summary = self._record_assessment(application_id, case, actor)
            # Populate the application's fields from the new run, ready to verify.
            job["message"] = "Populating the fields from the credit case…"
            try:
                job["populated"] = self.populate_fields(application_id, actor)
            except Exception:                                        # the assessment itself succeeded
                log.exception("Field population failed for %s", application_id)
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

    def _record_assessment(self, application_id: str, case: dict, actor: dict) -> dict:
        """Pin a finished credit-case run to the application, with its audit event."""
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
        return summary

    def wait_for_assessment(self, application_id: str, timeout: float = 600) -> dict:
        """Block until the running job finishes (tests and scripts)."""
        job = self._jobs.get(application_id)
        if job and job.get("thread"):
            job["thread"].join(timeout)
        return {k: v for k, v in (job or {}).items() if k != "thread"}

    # ── prospect sourcing: documents and AI prefill ─────────────────────────
    def _maker_at(self, app: dict, session: dict, steps: tuple, what: str) -> None:
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in steps or app["status"] in TERMINAL:
            raise ConflictError(f"{what} is done at the {' / '.join(self.wf.step(s).name for s in steps)} step")
        if not can_act(self.wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step belongs to the {self.wf.roles[step.role]} role")
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
        linked = dreg.link_on_file(app.setdefault("documents", dreg.initial_registry()), files, at)
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
        registry = app.setdefault("documents", dreg.initial_registry())
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
                        cam: Optional[dict] = None) -> dict:
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
                          sourcing_decision=sourcing_decision, customer_id_selection="new")
        with self._app_lock(app["application_id"]):
            app = self._require(app["application_id"])
            at = self.now().isoformat(timespec="seconds")
            registry = app.setdefault("documents", dreg.initial_registry())
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
        API due-diligence check run in parallel lanes; one writer applies the results."""
        app = self._require(application_id)
        self._maker_at(app, session, PREP_STEPS, "Preparing the application")
        with self._jobs_lock:
            running = self._prep_jobs.get(application_id)
            if running and running["state"] == "running":
                raise ConflictError("The application is already being prepared")
            job = {"state": "running", "started_at": self.now().isoformat(timespec="seconds"), "finished_at": None,
                   "lanes": [], "running": [], "summary": None, "error": None}
            self._prep_jobs[application_id] = job
        actor = {"id": session["user"]["id"], "role": session["role"]}
        job["thread"] = threading.Thread(target=self._prepare, args=(application_id, session, actor), daemon=True,
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
            pinned = self._app_case(app)[0] if (app.get("credit_assessment") or {}).get("run_id") else None
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in DD_STEPS or app["status"] in TERMINAL:
            raise ConflictError(f"{what} is done at the prospect-sourcing and risk-maker steps")
        if not can_act(self.wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step belongs to the {self.wf.roles[step.role]} role")
        if app.get("assignee_id") not in (None, session["user"]["id"]):
            raise ForbiddenError(f"Assigned to {self._user_name(app['assignee_id'])}; reassign it first")

    def due_diligence(self, application_id: str, session: Optional[dict] = None) -> dict:
        """The fifteen-check workspace: statuses, retrigger history, comments and exceptions."""
        app = self._require(application_id)
        rec = app.get("due_diligence") or {"version": dd.CHECK_VERSION, "checks": dd.initial_checks()}
        checks = rec["checks"]
        return {"application_id": application_id, "version": rec.get("version"),
                "initiated_at": rec.get("initiated_at"), "seeded": bool(rec.get("seeded")),
                "can_edit": self._can(app, session, DD_STEPS),
                "checks": checks, "summary": dd.summary(checks, self.now()),
                "blocking": [c["name"] for c in dd.blocking(checks, now=self.now())],
                "screening": dd.screening_review(checks, self.now()),
                "note": "API checks run against the in-app record and demo services (results are labelled); "
                        "manual checks are recorded by the analyst. An 'unavailable' result means the provider "
                        "returned nothing — it is never a clear result."}

    def _dd_check(self, app: dict, check_id: str) -> dict:
        checks = app.setdefault("due_diligence", {"version": dd.CHECK_VERSION, "checks": dd.initial_checks()})["checks"]
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
                (c["status"] in ("matched", "failed") and bool(dd.effective_exception(c, now)))
            if not settled:
                out.append(c["id"])
        return out

    def run_due_diligence(self, application_id: str, session: dict) -> dict:
        """Run every API check that has no clear result yet (re-screens include matched and failed)."""
        app = self._require(application_id)
        self._dd_may(app, session, "Running the due-diligence checks")
        ids = [c["id"] for c in app["due_diligence"]["checks"] if c["mode"] == "api" and c["status"] != "clear"]
        if not ids:
            raise ConflictError("Every API check already has a clear result — trigger individual checks to re-run")
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

    def request_exception(self, application_id: str, session: dict, check_id: str, note: str) -> dict:
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
        c["exception_request"] = {"status": "pending", "by": session["user"]["id"], "by_name": session["user"]["name"],
                                  "at": at, "note": note.strip()}
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "dd_exception_requested", actor=actor, from_step=app["step_id"],
                                         to_step=app["step_id"], comment=f"Exception requested for {c['name']}: {note.strip()}",
                                         detail={"check_id": check_id, "status": c["status"]}))
        return self.due_diligence(application_id, session)

    def decline_exception(self, application_id: str, session: dict, check_id: str, reason: str) -> dict:
        if session["role"] != "compliance_vp":
            raise ForbiddenError("Only the Compliance VP decides on a due-diligence exception")
        if not (reason or "").strip():
            raise InvalidRequestError("Give the reason for declining — the step holder sees it")
        app = self._require(application_id)
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
        if session["role"] != "compliance_vp":
            raise ForbiddenError("Only the Compliance VP can approve a due-diligence exception")
        app = self._require(application_id)
        if not (reason or "").strip():
            raise InvalidRequestError("A reason is required for an exception")
        c = self._dd_check(app, check_id)
        if c["status"] not in ("matched", "failed", "unavailable"):
            raise ConflictError(f"An exception applies to a matched, failed or unavailable check, not one that is {c['status']}")
        c["exception"] = {"by": session["user"]["id"], "by_name": session["user"]["name"],
                          "at": self.now().isoformat(timespec="seconds"), "reason": reason.strip(),
                          "expires_at": dd.exception_expiry(self.now().isoformat(timespec="seconds"))}
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
        rec = app.setdefault("due_diligence", {"version": dd.CHECK_VERSION, "checks": dd.initial_checks()})
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
                                "reason": "Seeded demo history"} if result["status"] in ("matched", "failed") else None)
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

    def request_tranche(self, application_id: str, session: dict, amount_cr: float, value_date: str,
                        purpose: str = "", facility_id: Optional[str] = None) -> dict:
        app = self._require(application_id)
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
        step = self.wf.step("dis_maker")
        app.update(status=STATUS_IN_PROGRESS, step_id=step.id, stage_id=step.stage_id,
                   step_entered_at=at.isoformat(timespec="seconds"), assignee_id=self._default_assignee(step.role))
        actor = {"id": session["user"]["id"], "role": session["role"]}
        self.store.save(app, self._event(app, "subsequent_tranche", actor=actor, from_step=None,
                                         to_step=step.id, comment=f"Subsequent tranche round {app['tranche_rounds']}: {reason.strip()[:120]}",
                                         detail={"round": app["tranche_rounds"], "reason": reason.strip()[:500]}))
        return self.get(application_id, session)

    # ── post-sanction consent & facility execution (Client One GAP-P0-13) ────
    def record_consent(self, application_id: str, session: dict, *, acknowledged_by: str, consent_date: str,
                       remarks: str = "", facilities: Optional[list[dict]] = None) -> dict:
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
        at = self.now().replace(microsecond=0)
        app["consent"] = {"acknowledged_by": acknowledged_by.strip(), "consent_date": consent_date,
                          "remarks": (remarks or "").strip() or None, "facilities": rows,
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

    # ── governance workspaces (GAP-P0-01/04/07/08/09, P1-01…05, P0-12/15) ────
    def _workspace_may(self, app: dict, session: Optional[dict], what: str, review: bool = False) -> None:
        """Who may change a workspace now: the current step's role. Maker steps edit the proposal;
        checker, VP-review, committee and allocation steps are read-only on it (process §3) and may
        only record their review (``review=True``: approving the CMA, reviewing a document, …)."""
        if app.get("status") in TERMINAL:
            raise ConflictError(f"{what} is not available on a completed application")
        if not app.get("step_id"):
            raise ConflictError(f"{what} is not available on a completed application")
        step = self.wf.step(app["step_id"])
        if not session or not can_act(self.wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"{what} is available to the current step's role ({self.wf.roles[step.role]})")
        if not review and step.kind != "maker":
            raise ForbiddenError(f"{what} is read-only at {step.name}: a review step does not change the proposal "
                                 "(return it for rework instead)")

    def _workspace_save(self, app: dict, session: dict, action: str, comment: str) -> dict:
        actor = {"id": session["user"]["id"], "role": session["role"]}
        app["updated_at"] = self.now().isoformat(timespec="seconds")
        self.store.save(app, self._event(app, action, actor=actor, from_step=app.get("step_id"),
                                         to_step=app.get("step_id"), comment=(comment or "")[:600]))
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
        self._workspace_may(app, session, "Party maintenance")
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
        self._workspace_may(app, session, "Facility maintenance")
        if app.get("sanctions"):
            raise ConflictError("Facilities cannot be edited after sanction — raise a modification instead")
        at = self.now().replace(microsecond=0).isoformat(timespec="seconds")
        facmod.change_facility(app, facility_id, raw, at, session["user"]["name"])
        return self._workspace_save(app, session, "facility_updated", f"{facility_id} updated")

    # securities (GAP-P1-03)
    def save_security(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "Security maintenance")
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
        self._workspace_may(app, session, "Project maintenance")
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
        self._workspace_may(app, session, "Recording a project change")
        p = next((x for x in app.get("projects", []) if x["project_id"] == project_id), None)
        if not p:
            raise InvalidRequestError(f"Unknown project: {project_id}")
        change = prj.record_change(p, raw, self.now().isoformat(timespec="seconds"), session["user"]["name"])
        return self._workspace_save(app, session, "project_change",
                                    f"{project_id}: {change['field']} → {change['current']} (flagged for reappraisal)")

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
        return self._workspace_save(app, session, "esms_update", f"ESMS: category {esms.get('category') or '—'}")

    # external work parties (GAP-P1-05)
    def save_ewp(self, application_id: str, session: dict, raw: dict) -> dict:
        app = self._require(application_id)
        self._workspace_may(app, session, "External work-party management")
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

    def decision_view(self, application_id: str, session: Optional[dict] = None) -> dict:
        app = self._require(application_id)
        case, _ = self._app_case(app)
        auto, manual = committee_deviations(case), manual_deviations(app)
        final = app.get("stage_id") not in ("PS", "IP")
        ca = app.get("credit_assessment") or {}
        committee = authority.required_authority(app.get("amount_cr"), ca.get("risk_grade"),
                                                 deviations=len(auto) + len(manual), final=final)
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        labels = {e: ACTION_WORDS.get(e, e.replace("_", " ").title()) for e in ACTION_WORDS}
        history = []
        for e in reversed(self.store.events(application_id, limit=2000)):           # oldest first
            if not (e.get("comment") or "").strip() or e["action"] not in ACTION_WORDS:
                continue                      # decisions and Compliance exceptions, not workspace edits
            try:
                fs = self.wf.step(e["from_step"]) if e.get("from_step") else None
            except wfmod.WorkflowError:       # a step since removed from the configuration
                fs = None
            word = (wfmod.action_label(fs, e["action"]) if fs else None) or labels.get(e["action"]) \
                or e["action"].replace("_", " ").capitalize()
            history.append({"at": e["at"], "step": fs.name if fs else "—", "stage": fs.stage_name if fs else "—",
                            "by": self._user_name(e.get("actor_id")) or e.get("actor_role") or "agent",
                            "role": self.wf.roles.get(e.get("actor_role") or "", e.get("actor_role") or ""),
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
                                          and can_act(self.wf, session["user"]["id"], session["role"], step)),
                "decision_records": app.get("decisions") or [], "remarks_history": history}

    def save_deviation(self, application_id: str, session: dict, raw: dict) -> dict:
        """Add a manual deviation (type, description, justification) or remove one (with a reason)."""
        app = self._require(application_id)
        self._workspace_may(app, session, "Deviations")
        step = self.wf.step(app["step_id"])
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
        return self._workspace_save(app, session, "deviation_added", f"{d['id']} {dev_type}: {description[:200]}")

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
                if self.wf.step(rec["step"]).stage_id != stage:
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        editable = bool(step and step.id in terms_mod.AUTHOR_STEPS and t.get("status") != "sanctioned"
                        and app.get("status") not in TERMINAL and session
                        and can_act(self.wf, session["user"]["id"], session["role"], step))
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
        step = self.wf.step(app["step_id"])
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
        step = self.wf.step(app["step_id"])
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
        doc = dreg.review_document(app.setdefault("documents", dreg.initial_registry()), doc_id, status,
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
        for kind, title in lt.KINDS.items():
            ok, reason = lt.available(app, kind)
            versions = (app.get("letters") or {}).get(kind) or []
            kinds.append({"kind": kind, "title": title, "available": ok, "reason": None if ok else reason,
                          "can_generate": bool(ok and session and session["role"] in LETTER_ROLES[kind]
                                               and app["status"] != STATUS_REJECTED),
                          "issuer_role": " / ".join(self.wf.roles.get(r, r) for r in LETTER_ROLES[kind]),
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
            raise ForbiddenError(f"The {lt.KINDS[kind].lower()} is issued by the "
                                 f"{' / '.join(self.wf.roles.get(r, r) for r in LETTER_ROLES[kind])} role")
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
        apps = self.store.list()
        events = self.store.events(limit=1_000_000)
        by_app: dict[str, list[dict]] = {}
        for e in events:
            by_app.setdefault(e["application_id"], []).append(e)
        mis = build_mis(apps, by_app, self.wf, self.now(),
                        [e for e in events if e["action"] in ("copilot_action", "copilot_ask")])
        mis["agents"] = agent_metrics(apps, events, self.field_registry)     # Populate → Verify headline numbers
        return mis

    # ── copilot ──────────────────────────────────────────────────────────────
    def _is_holder(self, app: dict, session: Optional[dict]) -> bool:
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        return bool(session and step and app["status"] not in TERMINAL
                    and can_act(self.wf, session["user"]["id"], session["role"], step)
                    and app.get("assignee_id") in (None, session["user"]["id"]))

    def _copilot_state(self, app: dict, session: Optional[dict], light: bool = False) -> dict:
        """What the planner reads. ``light`` skips the credit case (used for the dashboard digest)."""
        view = self._view(app, session)
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        sla = dict(view.get("sla") or {})
        if step and sla:
            sla.update(sla_days=step.sla_days, due_soon=0 <= sla.get("days_remaining", 99) < 1)
        s = {"step_id": step.id if step else None, "step_name": step.name if step else None,
             "step_kind": step.kind if step else None, "role_name": self.wf.roles.get(step.role) if step else None,
             "status": app["status"], "holder": view.get("assignee_name"), "is_holder": self._is_holder(app, session),
             "sla": sla, "can_submit": bool(view.get("actions")), "committee_steps": COMMITTEE_STEPS,
             "documents": len(self._documents_on_file(app["entity_id"])),
             "credit_assessment": bool(app.get("credit_assessment")),
             "exception_requests": ([r["name"] for r in self._pending_exception_requests(app)]
                                    if session and session["role"] == "compliance_vp" else [])}
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
            blocking = dd.blocking(checks, now=self.now())
            s["due_diligence"] = {"blocking": [c["name"] for c in blocking],
                                  "need_exception": [c["name"] for c in blocking if c["status"] in ("matched", "failed", "unavailable")
                                                     and (c.get("exception_request") or {}).get("status") != "pending"],
                                  "awaiting_exception": [c["name"] for c in blocking
                                                         if (c.get("exception_request") or {}).get("status") == "pending"],
                                  "runnable": [c["name"] for c in blocking if c["status"] == "pending"],
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
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
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
                                    {s.id: s.name for s in self.wf.steps})
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        pack["can_brief"] = bool(session and step and step.id in COMMITTEE_STEPS and app["status"] not in TERMINAL
                                 and can_act(self.wf, session["user"]["id"], session["role"], step)
                                 and pack.get("available"))
        pack["at_committee_step"] = bool(step and step.id in COMMITTEE_STEPS)
        return pack

    def committee_brief(self, application_id: str, session: dict) -> dict:
        """AI committee brief: the number-guarded CAM interpretation of the executive summary and recommendation."""
        app = self._require(application_id)
        step = self.wf.step(app["step_id"]) if app.get("step_id") else None
        if not step or step.id not in COMMITTEE_STEPS or app["status"] in TERMINAL:
            raise ConflictError("The committee brief is prepared at the review and committee steps")
        if not can_act(self.wf, session["user"]["id"], session["role"], step):
            raise ForbiddenError(f"This step belongs to the {self.wf.roles[step.role]} role")
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
    def _system_session(self, role: str, user_id: Optional[str] = None) -> dict:
        uid = user_id or self.wf.users_with_role(role)[0]["id"]
        user = self.wf.user(uid)
        return {"user": {k: user[k] for k in ("id", "name", "email", "branch", "roles")}, "role": role}

    def seed_demo(self, force: bool = False) -> int:
        """Seed the demo applications once (or again with force=True). Returns the number created."""
        if force:
            self.store.clear()
        elif self.store.count():
            return 0
        created = 0
        for entity_id, target, flag, days_ago, idle_days, note in DEMO_SEED:
            if entity_id not in self.companies:
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
                              related_parties=related_parties,
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
                holder = self._system_session(self.wf.step(target).role)
                self._force_assignee(app["application_id"], holder["user"]["id"])
                self.escalate(app["application_id"], holder, "Tranche timing depends on the borrower's "
                                                             "project milestones (demo note).")
            self._annotate(app["application_id"], note)
            self._seed_presentation_evidence(app["application_id"], entity_id, end)
        created += self._seed_exit_showcase()
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
            app["proposal"]["banking"] = prop_mod.normalise_banking(
                {"arrangement": "consortium", "lead_bank": "Demo Bank", "number_of_banks": 3,
                 "institution_share_pct": 42, "banks": [{"name": "Demo Bank", "share_pct": 42, "role": "Lead"},
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
            registry = app.setdefault("documents", dreg.initial_registry())
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
        app = self.create(rm, entity_id=DEMO_EXIT_ENTITY, at=now - timedelta(days=55), seeded=True,
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
        registry = app.setdefault("documents", dreg.initial_registry())
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
        dreg.register_generated(app.setdefault("documents", dreg.initial_registry()),
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
                                 "name": app.get("borrower_name"), "account_no": "3140101429000442", "bank": "Demo Bank",
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
        registry = app.setdefault("documents", dreg.initial_registry())
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

    def _replay_to(self, application_id: str, target: str, t0: datetime, end: datetime) -> None:
        """Walk the application forward to ``target`` with the default holders, spacing the events between
        ``t0`` and ``end`` (when it enters the target step)."""
        target_index = self.wf.step(target).index
        span = max(target_index, 1)
        for i in range(target_index):
            app = self.store.get(application_id)
            step = self.wf.step(app["step_id"])
            session = self._system_session(step.role, app.get("assignee_id"))
            action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                      "allocation": "allocate"}[step.kind]
            allocate_to = self._default_assignee(step.allocates_to) if step.kind == "allocation" else None
            at = t0 + (end - t0) * (i + 1) / span
            if step.id == "ps_maker":               # seeded history: due diligence was run and recorded
                self._seed_due_diligence(application_id, at)
                self._seed_stage_docs(application_id, "PS", at)
            if step.id == "pos_maker":               # seeded history: conditions satisfied, consent recorded
                app = self.store.get(application_id)
                for c in app.get("conditions") or []:
                    if c["type"] in ("PC", "CP", "CPS"):
                        c.update(status="satisfied", note="Satisfied (seeded demo history)", updated_by="Demo seed",
                                 updated_at=at.isoformat(timespec="seconds"))
                app["consent"] = {"acknowledged_by": "Customer authorisation (demo seed)", "consent_date": at.date().isoformat(),
                                  "remarks": "Sanction accepted (seeded demo history)",
                                  "facilities": [{"facility_id": f["facility_id"], "execution_status": "executed",
                                                   "agreement_date": at.date().isoformat()}
                                                  for f in (app.get("facilities") or [app.get("facility") or {}])],
                                  "by": "seed", "by_name": "Demo seed", "at": at.isoformat(timespec="seconds")}
                self.store.save(app)
                self.generate_letter(application_id, session, "sanction_letter", at=at)   # RUL-10: the letter is on file
                app = self.store.get(application_id)
                facmod.apply_execution(app.get("facilities") or [], app["consent"]["facilities"],
                                    at.isoformat(timespec="seconds"), "Demo seed")
                self._seed_stage_docs(application_id, "POS", at)
            if step.id == IP_NOTE_STEP:              # seeded history: the IP Note was prepared
                app = self.store.get(application_id)
                app["ip_note"] = build_ip_note(app, self.companies.get(app["entity_id"]), now=at) | {"seeded": True}
                self.store.save(app)
                self._seed_stage_docs(application_id, "IP", at)
            if step.id == "ap_risk_maker":           # seeded history: CMA recorded, pricing benchmark set
                self._seed_ap_workspace(application_id, at)
                self._seed_stage_docs(application_id, "AP", at)
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
        maker = self._system_session(self.wf.step(app["step_id"]).role, app.get("assignee_id"))
        self.act(application_id, maker, "submit", at=entered + (self.now() - entered) / 3,
                 comment="Assessment complete; submitted for review (seeded demo history).")
        app = self.store.get(application_id)
        reviewer = self._system_session(self.wf.step(app["step_id"]).role, app.get("assignee_id"))
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


def load_workflow() -> Workflow:
    from src.core.config_manager import config
    config.reload()
    return Workflow.from_config(config.get("los_workflow", default={}) or {})
