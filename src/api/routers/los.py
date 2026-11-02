"""Corporate LOS — demo sign-in, pipeline, applications and workflow actions.

The session token (demo sign-in, no passwords) is sent in the ``X-LOS-Session`` header.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.application.errors import ForbiddenError

router = APIRouter(prefix="/api/los", tags=["los"])


class SignIn(BaseModel):
    user_id: str
    role: str


class RoleSwitch(BaseModel):
    role: str


class FacilityInput(BaseModel):
    proposal_type: str = "Fresh"
    facility_nature: str = "fund_based"
    facility_type: str = "working_capital"
    amount_cr: float
    tenor_months: Optional[int] = None
    purpose: str = ""
    ad_hoc: bool = False
    # facility attributes (GAP-P0-04): product subtype, pricing, repayment, operational IDs
    product_subtype: Optional[str] = None
    benchmark: Optional[str] = None
    benchmark_rate: Optional[float] = None
    spread: Optional[float] = None
    interest_rate: Optional[float] = None
    reset_frequency: Optional[str] = None
    reset_date: Optional[str] = None
    penal_rate: Optional[float] = None
    effective_rate: Optional[float] = None
    repayment_type: Optional[str] = None
    repayment_frequency: Optional[str] = None
    moratorium_months: Optional[float] = None
    total_limit_id: Optional[str] = None
    fund_limit_id: Optional[str] = None
    non_fund_limit_id: Optional[str] = None
    limit_suffix: Optional[str] = None
    loan_account: Optional[str] = None
    next_review_date: Optional[str] = None


class RelatedPartyInput(BaseModel):
    name: str
    role: str
    party_type: str = "non_individual"
    ownership_pct: Optional[float] = None
    pan: Optional[str] = None
    cin: Optional[str] = None
    relationship: Optional[str] = None           # relationship to the borrowing entity
    sourced_address: Optional[str] = None        # address with its source noted
    key_person_role: Optional[str] = None        # for individual key persons (e.g. CFO, MD)
    party_status: str = "active"                 # active | inactive | withdrawn


class ProspectDiscussion(BaseModel):
    project_type: str = ""
    funding_type: str = ""
    brief_description: str = ""
    detailed_discussion: str = ""
    initial_remarks: str = ""


class SourcingDecision(BaseModel):
    decision: str = ""
    mandatory_remarks: str = ""
    conditional_remarks: str = ""


class CamStart(BaseModel):
    mode: str                                    # workspace | document | generate
    run_id: Optional[str] = None                 # workspace: a specific CAM run (default: the latest)
    staging_id: Optional[str] = None             # document: the staged CAM (read with /prospects/{id}/read)


class NewApplication(BaseModel):
    entity_id: str
    # ``facility`` remains accepted for backward compatibility with existing API clients.
    facility: Optional[dict] = None
    facilities: list[FacilityInput] = Field(default_factory=list)
    related_parties: list[RelatedPartyInput] = Field(default_factory=list)
    priority: str = "Normal"
    prospect_discussion: ProspectDiscussion = Field(default_factory=ProspectDiscussion)
    sourcing_decision: SourcingDecision = Field(default_factory=SourcingDecision)
    customer_id_selection: Optional[str] = None
    cam: Optional[CamStart] = None               # start from a CAM (S8)
    profile: Optional[str] = None                # institution profile for this application (default: active)
    product: Optional[str] = None                # product template (else inferred from the facility types)


class ProspectIdentity(BaseModel):
    company_name: str = ""
    cin: Optional[str] = None
    pan: Optional[str] = None
    gstin: Optional[str] = None
    date_of_incorporation: Optional[str] = None
    registered_address: Optional[str] = None
    registered_state: Optional[str] = None
    listed_exchange: Optional[str] = None
    external_rating: Optional[str] = None
    sector: str = ""
    subsector: Optional[str] = None


class NewProspect(BaseModel):
    staging_id: str
    identity: ProspectIdentity
    facilities: list[FacilityInput] = Field(default_factory=list)
    related_parties: list[RelatedPartyInput] = Field(default_factory=list)
    priority: str = "Normal"
    prospect_discussion: ProspectDiscussion = Field(default_factory=ProspectDiscussion)
    sourcing_decision: SourcingDecision = Field(default_factory=SourcingDecision)
    confirm_not_duplicate: bool = False
    cam: Optional[CamStart] = None
    product: Optional[str] = None                       # product template (else inferred from the facility types)


class Action(BaseModel):
    action: str
    comment: str = ""
    allocate_to: Optional[str] = None
    sanctioned_amount_cr: Optional[float] = None
    significant_changes: Optional[str] = None    # Disbursement VP Review: significant changes observed
    rework_to: Optional[str] = None              # return: a specific earlier step (reason-specific rework)
    decision_data: Optional[dict] = None         # the step's decision fields (e.g. material_information_date)
    deferred_until: Optional[str] = None         # defer: the date to take the application up again


class FieldReview(BaseModel):
    field_id: str
    status: str                  # confirmed | overridden | clear
    value: Optional[str] = None
    reason: Optional[str] = None


class FieldReviews(BaseModel):
    reviews: list[FieldReview]


class FieldDecision(BaseModel):
    field_id: str
    action: str                     # confirm | override | keep | reopen
    value: Optional[str] = None
    reason: str = ""


class FieldDecisions(BaseModel):
    decisions: list[FieldDecision]


class BulkConfirm(BaseModel):
    field_ids: Optional[list[str]] = None     # None = every pre-ticked field in the queue


class Reassign(BaseModel):
    user_id: str
    comment: str = ""


class Escalate(BaseModel):
    comment: str


def _session(svc: ServiceContainer, token: Optional[str]) -> dict:
    return svc.los.session(token)


def _admin_session(svc: ServiceContainer, token: Optional[str]) -> dict:
    sess = _session(svc, token)
    if not sess:
        raise ForbiddenError("A signed-in administrator session is required")
    return sess


@router.get("/directory")
async def directory(svc: ServiceContainer = Depends(get_container)):
    """Groups, roles and demo users (for the sign-in screen and allocation pickers),
    with the active institution profile's branding."""
    return svc.los.directory()


@router.get("/profiles")
async def profiles(svc: ServiceContainer = Depends(get_container)):
    """The available institution profiles (active / default)."""
    return svc.los.profiles_view()


@router.get("/profiles/{profile_id}")
async def profile_detail(profile_id: str, full: bool = False, svc: ServiceContainer = Depends(get_container)):
    """One institution profile resolved: branding, labels, modules, checks, documents, authority, outputs."""
    return svc.los.profile_detail(profile_id, full=full)


@router.post("/profiles/active")
async def set_active_profile(body: dict, x_los_session: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    """Administrator-only: switch the institution profile for new work (the journey, modules,
    checks, documents, authority and outputs it carries). Existing applications keep their own
    profile. Body: {profile_id, reseed?} — reseed recreates the profile's demo applications."""
    profile_id = str((body or {}).get("profile_id") or "").strip()
    if not profile_id:
        raise ForbiddenError("Send {profile_id: <id>}")
    return svc.los.admin_switch_profile(_admin_session(svc, x_los_session), profile_id,
                                        reseed=bool((body or {}).get("reseed")))


@router.get("/admin/overview")
async def admin_overview(x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Administrator: read-only configuration summary — institution profiles, product templates,
    seeded demo applications and the available reset scopes."""
    return svc.los.admin_overview(_admin_session(svc, x_los_session))


@router.post("/admin/demo-reset")
async def admin_demo_reset(body: dict, x_los_session: Optional[str] = Header(None),
                           svc: ServiceContainer = Depends(get_container)):
    """Administrator: controlled demo-data reset (scope: 'active_profile' or 'all_demo').
    Removes the seeded demo applications and recreates them deterministically; user-created
    applications are never touched. Audit-logged."""
    scope = str((body or {}).get("scope") or "active_profile")
    return svc.los.admin_reset_demo(_admin_session(svc, x_los_session), scope)


@router.get("/admin/audit")
async def admin_audit(limit: int = 100, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    """Administrator: the recent audit trail (workflow actions and system/admin events)."""
    _admin_session(svc, x_los_session)
    return {"events": svc.los.audit(limit=min(max(limit, 1), 500))}


@router.get("/demo-scenarios")
async def demo_scenarios(profile_id: Optional[str] = None, svc: ServiceContainer = Depends(get_container)):
    """The guided demo scenarios for the institution profile (or 'all')."""
    return svc.los.demo_scenarios(profile_id)


@router.get("/demo-packages")
async def demo_packages(profile_id: Optional[str] = None, svc: ServiceContainer = Depends(get_container)):
    """R22: the bank-focused demo packages (executive / functional walkthroughs of the 22
    enhancements), enriched with their live demo applications (or 'all' profiles)."""
    return svc.los.demo_packages(profile_id)


@router.get("/branding")
async def branding(svc: ServiceContainer = Depends(get_container)):
    """The active institution profile's branding and labels (for the portal shell and papers)."""
    return svc.los.branding_view()


@router.get("/products")
async def products(svc: ServiceContainer = Depends(get_container)):
    """The reusable product templates and which ones the active institution profile runs."""
    return {"products": svc.los.products_view()}


@router.get("/products/{product_id}")
async def product_detail(product_id: str, profile_id: Optional[str] = None, profile: Optional[str] = None,
                         svc: ServiceContainer = Depends(get_container)):
    """One product template resolved against an institution profile (its fields, limits, checks,
    documents, workflow/modules, approval matrix and output templates)."""
    return svc.los.product_detail(product_id, profile_id or profile)


@router.post("/session")
async def sign_in(body: SignIn, svc: ServiceContainer = Depends(get_container)):
    return svc.los.sign_in(body.user_id, body.role)


@router.get("/session")
async def me(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    return _session(svc, x_los_session)


@router.post("/session/role")
async def switch_role(body: RoleSwitch, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    return svc.los.switch_role(x_los_session, body.role)


@router.delete("/session")
async def sign_out(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    svc.los.sign_out(x_los_session)
    return {"signed_out": True}


@router.get("/dashboard")
async def dashboard(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    return svc.los.dashboard(_session(svc, x_los_session))


@router.get("/applications")
async def list_applications(status: str = "", stage: str = "", mine: bool = False, q: str = "",
                            x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    session = _session(svc, x_los_session)
    return {"applications": svc.los.list(session, status=status, stage=stage, mine=mine, query=q)}


@router.post("/applications")
async def create_application(body: NewApplication, x_los_session: Optional[str] = Header(None),
                             idempotency_key: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    session = _session(svc, x_los_session)
    app = await asyncio.to_thread(               # starting from a CAM populates the fields: off the event loop
        svc.los.create,
        session,
        entity_id=body.entity_id,
        facility=body.facility,
        facilities=[item.model_dump(exclude_none=True) for item in body.facilities],
        related_parties=[item.model_dump() for item in body.related_parties],
        priority=body.priority,
        prospect_discussion=body.prospect_discussion.model_dump(),
        sourcing_decision=body.sourcing_decision.model_dump(),
        customer_id_selection=body.customer_id_selection,
        cam=body.cam.model_dump() if body.cam else None,
        profile=body.profile,
        product=body.product,
        idempotency_key=idempotency_key,
    )
    return svc.los.get(app["application_id"], session)


@router.get("/applications/{application_id}")
async def get_application(application_id: str, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    return svc.los.get(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/actions")
async def act(application_id: str, body: Action, x_los_session: Optional[str] = Header(None),
              idempotency_key: Optional[str] = Header(None),
              svc: ServiceContainer = Depends(get_container)):
    return svc.los.act(application_id, _session(svc, x_los_session), body.action, comment=body.comment,
                       allocate_to=body.allocate_to, sanctioned_amount_cr=body.sanctioned_amount_cr,
                       significant_changes=body.significant_changes, rework_to=body.rework_to,
                       decision_data=body.decision_data, deferred_until=body.deferred_until,
                       idempotency_key=idempotency_key)


@router.get("/applications/{application_id}/assessment")
async def get_assessment(application_id: str, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Risk Maker workspace: the running job (if any) and the tabs built from the latest credit case."""
    return svc.los.assessment(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/assessment")
async def run_assessment(application_id: str, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Start the credit assessment (the credit-intelligence pipeline) from the Risk Maker step."""
    return svc.los.start_assessment(application_id, _session(svc, x_los_session))


class PrefillItem(BaseModel):
    field_id: str
    status: str = "accepted"          # accepted | clear
    value: Optional[str] = None       # set to edit the proposed value
    reason: Optional[str] = None


class PrefillApply(BaseModel):
    items: list[PrefillItem]


class NoteRequest(BaseModel):
    with_ai: bool = True


@router.get("/applications/{application_id}/sourcing")
async def sourcing(application_id: str, x_los_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    """Prospect Sourcing: documents on file and the document prefill."""
    return svc.los.sourcing(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/documents")
async def upload_document(application_id: str, file: UploadFile = File(...), category: str = Form(...),
                          link_to: Optional[str] = Form(None),
                          x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Upload a PDF to the borrower's documents; a new version is added under the logical name
    (never overwritten), optionally linked to a checklist document (link_to = doc_id)."""
    content = await file.read()
    return svc.los.upload_document(application_id, _session(svc, x_los_session), category, file.filename, content,
                                   link_to=link_to)


@router.post("/applications/{application_id}/prefill")
async def run_prefill(application_id: str, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    """Read the documents and propose values with source page and confidence."""
    return await asyncio.to_thread(svc.los.run_prefill, application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/prepare")
async def prepare_application(application_id: str, x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """Preparation agent: identity & dedupe, document intake and the API checks in parallel lanes."""
    return svc.los.prepare_application(application_id, _session(svc, x_los_session))


# ── New prospect sourced from its documents ──────────────────────────────────

@router.post("/prospects/documents")
async def stage_prospect_document(file: UploadFile = File(...), category: str = Form(...),
                                  staging_id: Optional[str] = Form(None),
                                  x_los_session: Optional[str] = Header(None),
                                  svc: ServiceContainer = Depends(get_container)):
    """Stage a document for a new prospect (before the borrower exists); returns the staging set."""
    content = await file.read()
    return svc.los.stage_document(_session(svc, x_los_session), category, file.filename, content, staging_id)


@router.post("/prospects/{staging_id}/read")
async def read_prospect_documents(staging_id: str, x_los_session: Optional[str] = Header(None),
                                  svc: ServiceContainer = Depends(get_container)):
    """The intake agent reads the staged documents: proposed identity, facility and duplicate matches."""
    return await asyncio.to_thread(svc.los.read_staged, _session(svc, x_los_session), staging_id)


@router.post("/prospects")
async def create_prospect(body: NewProspect, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Register the new prospect from its documents, create its application and start the preparation agent."""
    return await asyncio.to_thread(
        lambda: svc.los.create_prospect(
            _session(svc, x_los_session), staging_id=body.staging_id, identity=body.identity.model_dump(),
            facilities=[f.model_dump() for f in body.facilities],
            related_parties=[p.model_dump() for p in body.related_parties], priority=body.priority,
            prospect_discussion=body.prospect_discussion.model_dump(),
            sourcing_decision=body.sourcing_decision.model_dump(),
            confirm_not_duplicate=body.confirm_not_duplicate,
            cam=body.cam.model_dump() if body.cam else None,
            product=body.product))


@router.post("/applications/{application_id}/prefill/apply")
async def apply_prefill(application_id: str, body: PrefillApply, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    return svc.los.apply_prefill(application_id, _session(svc, x_los_session),
                                 [i.model_dump() for i in body.items])


@router.get("/applications/{application_id}/ip-note")
async def ip_note(application_id: str, x_los_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    return svc.los.ip_note(application_id, _session(svc, x_los_session))


# ── governed due-diligence workspace (Client One GAP-P0-05/06) ─────────────────

@router.get("/applications/{application_id}/due-diligence")
async def due_diligence(application_id: str, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """The fifteen-check due-diligence workspace: statuses, retrigger history, comments, exceptions."""
    return svc.los.due_diligence(application_id, _session(svc, x_los_session))


class CheckId(BaseModel):
    check_id: str
    remarks: str = ""
    to: Optional[str] = None          # an exception request: the Compliance VP it is addressed to


@router.post("/applications/{application_id}/due-diligence/run")
async def run_due_diligence(application_id: str, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    """Run every API check that has no clear result yet."""
    return await asyncio.to_thread(svc.los.run_due_diligence, application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/due-diligence/trigger")
async def trigger_check(application_id: str, body: CheckId, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Run (or re-run) one API check; the previous result is preserved in its history."""
    return svc.los.trigger_check(application_id, _session(svc, x_los_session), body.check_id)


class CheckRecord(BaseModel):
    check_id: str
    result: str                  # clear | matched | failed
    remarks: str = ""


@router.post("/applications/{application_id}/due-diligence/record")
async def record_check(application_id: str, body: CheckRecord, x_los_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    """Record one manual check (a non-clear result needs a remark)."""
    return svc.los.record_check(application_id, _session(svc, x_los_session), body.check_id, body.result, body.remarks)


@router.post("/applications/{application_id}/due-diligence/comment")
async def comment_check(application_id: str, body: CheckId, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    return svc.los.comment_check(application_id, _session(svc, x_los_session), body.check_id, body.remarks)


@router.post("/applications/{application_id}/due-diligence/exception")
async def exception_check(application_id: str, body: CheckId, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Compliance VP only: the recorded exception that releases a mandatory match/failure block."""
    return svc.los.exception_check(application_id, _session(svc, x_los_session), body.check_id, body.remarks)


@router.post("/applications/{application_id}/due-diligence/exception-request")
async def request_exception(application_id: str, body: CheckId, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    """The step holder asks the Compliance VP for an exception (it appears in the Compliance VP's queue)."""
    return svc.los.request_exception(application_id, _session(svc, x_los_session), body.check_id, body.remarks,
                                     to=body.to)


@router.post("/applications/{application_id}/due-diligence/exception-decline")
async def decline_exception(application_id: str, body: CheckId, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    """Compliance VP only: decline a requested exception, with the reason the step holder sees."""
    return svc.los.decline_exception(application_id, _session(svc, x_los_session), body.check_id, body.remarks)


class CheckEvidence(BaseModel):
    check_id: str
    name: str
    note: str = ""


@router.post("/applications/{application_id}/due-diligence/evidence")
async def add_check_evidence(application_id: str, body: CheckEvidence, x_los_session: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    """Attach an evidence reference to one check (UAT-P1-8); also registered in the document registry."""
    return svc.los.add_check_evidence(application_id, _session(svc, x_los_session), body.check_id, body.name, body.note)


class CheckGridRow(BaseModel):
    document: str
    udin_code: str
    status: str                  # verified | not_verified | pending


class CheckGrid(BaseModel):
    check_id: str
    rows: list[CheckGridRow] = Field(default_factory=list)


@router.post("/applications/{application_id}/due-diligence/grid")
async def save_check_grid(application_id: str, body: CheckGrid, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Record the detailed grid for a manual check (UDIN) (UAT-P1-8)."""
    return svc.los.save_check_grid(application_id, _session(svc, x_los_session), body.check_id,
                                   [r.model_dump() for r in body.rows])


@router.post("/applications/{application_id}/ip-note")
async def generate_ip_note(application_id: str, body: NoteRequest = NoteRequest(),
                           x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    return await asyncio.to_thread(svc.los.generate_ip_note, application_id, _session(svc, x_los_session),
                                   body.with_ai)


@router.post("/applications/{application_id}/ip-note/assignments")
async def save_ip_assignments(application_id: str, body: WorkspacePayload,
                              x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """LPFG Analyst / Senior Analyst assignments and the CRAC recommendation (UAT-P1-6)."""
    return svc.los.save_ip_assignments(application_id, _session(svc, x_los_session), body.payload)


@router.get("/applications/{application_id}/ip-note.html", response_class=HTMLResponse)
async def ip_note_html(application_id: str, x_los_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    _session(svc, x_los_session)
    return HTMLResponse(svc.los.ip_note_html(application_id))


class ConditionUpdate(BaseModel):
    id: str
    status: str
    note: Optional[str] = None
    evidence: Optional[str] = None
    due: Optional[str] = None


class ConditionUpdates(BaseModel):
    updates: list[ConditionUpdate]


class ChecklistItem(BaseModel):
    id: str
    done: bool
    note: Optional[str] = None


class Checklist(BaseModel):
    items: list[ChecklistItem]


class Tranche(BaseModel):
    amount_cr: float
    value_date: str
    purpose: str = ""
    facility_id: Optional[str] = None


class ConsentFacility(BaseModel):
    facility_id: str
    execution_status: str        # executed | partial | not_executed
    agreement_date: Optional[str] = None


class Consent(BaseModel):
    acknowledged_by: str
    consent_date: str
    remarks: str = ""
    facilities: list[ConsentFacility] = Field(default_factory=list)


@router.post("/applications/{application_id}/post-sanction/consent")
async def record_consent(application_id: str, body: Consent, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Customer's sanction consent and per-facility execution (Post-Sanction Maker; gates the submission)."""
    return svc.los.record_consent(application_id, _session(svc, x_los_session),
                                  acknowledged_by=body.acknowledged_by, consent_date=body.consent_date,
                                  remarks=body.remarks, facilities=[f.model_dump() for f in body.facilities])


@router.get("/applications/{application_id}/post-sanction")
async def post_sanction(application_id: str, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Conditions tracker, deviation register, IP → AP comparison and disbursement."""
    return svc.los.post_sanction(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/conditions")
async def update_conditions(application_id: str, body: ConditionUpdates, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    return svc.los.update_conditions(application_id, _session(svc, x_los_session),
                                     [u.model_dump() for u in body.updates])


class CovenantAction(BaseModel):
    condition_id: str
    action: str                     # test | cure
    result: str = ""                # pass | fail (for test)
    remarks: str = ""


@router.post("/applications/{application_id}/covenants")
async def record_covenant(application_id: str, body: CovenantAction, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Recurring covenant monitoring (UAT-P2-11): test a covenant (pass/fail) or record a cure."""
    return svc.los.record_covenant(application_id, _session(svc, x_los_session), body.condition_id,
                                   body.action, body.result, body.remarks)


@router.post("/applications/{application_id}/disbursement/checklist")
async def update_checklist(application_id: str, body: Checklist, x_los_session: Optional[str] = Header(None),
                           svc: ServiceContainer = Depends(get_container)):
    return svc.los.update_checklist(application_id, _session(svc, x_los_session), [i.model_dump() for i in body.items])


# ── R7: governed modifications of sanctioned terms ─────────────────────────
@router.post("/applications/{application_id}/modifications")
async def propose_modification(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                               svc: ServiceContainer = Depends(get_container)):
    """Propose a modification of sanctioned terms (payload: amount_cr / tenor_months /
    interest_rate / facility_type / reason). Materiality is assessed against the profile's
    thresholds; the sanctioned terms stay in force until it is decided."""
    return svc.los.propose_modification_request(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/modifications/recommend")
async def recommend_modification(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                                 svc: ServiceContainer = Depends(get_container)):
    """The checker's recommendation on the open modification (payload: decision, remarks)."""
    return svc.los.recommend_modification_request(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/modifications/decide")
async def decide_modification(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """The committee's decision on a recommended modification (payload: outcome, minutes).
    A material approval re-enters credit reassessment with the recalculated route."""
    return svc.los.decide_modification_request(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/disbursement/tranche")
async def request_tranche(application_id: str, body: Tranche, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    return svc.los.request_tranche(application_id, _session(svc, x_los_session), body.amount_cr, body.value_date,
                                   body.purpose, facility_id=body.facility_id)


class SubsequentTranche(BaseModel):
    reason: str


@router.post("/applications/{application_id}/disbursement/subsequent-tranche")
async def request_subsequent_tranche(application_id: str, body: SubsequentTranche,
                                     x_los_session: Optional[str] = Header(None),
                                     svc: ServiceContainer = Depends(get_container)):
    """Repeat-tranche re-entry after Exit (UAT-P2-12): re-opens at the Disbursement Maker."""
    return svc.los.request_subsequent_tranche(application_id, _session(svc, x_los_session), body.reason)


class CopilotRun(BaseModel):
    tool: str


class CopilotDraft(BaseModel):
    kind: str


class CopilotAsk(BaseModel):
    question: str


@router.get("/mis")
async def mis(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Management MIS from the applications and the audit trail."""
    _session(svc, x_los_session)
    return await asyncio.to_thread(svc.los.mis)


@router.get("/applications/{application_id}/letters")
async def letters(application_id: str, x_los_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    """Term sheet and sanction letter: availability and issued versions."""
    return svc.los.letters(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/letters/{kind}")
async def generate_letter(application_id: str, kind: str, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    return await asyncio.to_thread(svc.los.generate_letter, application_id, _session(svc, x_los_session), kind)


@router.get("/applications/{application_id}/letters/{kind}.html", response_class=HTMLResponse)
async def letter_html(application_id: str, kind: str, version: Optional[int] = None,
                      x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    _session(svc, x_los_session)
    return HTMLResponse(svc.los.letter_html(application_id, kind, version))


@router.get("/copilot/digest")
async def copilot_digest(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """The copilot's view of the signed-in user's queue."""
    return svc.los.copilot_digest(_session(svc, x_los_session))


@router.get("/applications/{application_id}/copilot")
async def copilot(application_id: str, x_los_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    """Next best actions for this application."""
    return await asyncio.to_thread(svc.los.copilot, application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/copilot/run")
async def copilot_run(application_id: str, body: CopilotRun, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    return await asyncio.to_thread(svc.los.copilot_run, application_id, _session(svc, x_los_session), body.tool)


@router.post("/applications/{application_id}/copilot/draft")
async def copilot_draft(application_id: str, body: CopilotDraft, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    return await asyncio.to_thread(svc.los.copilot_draft, application_id, _session(svc, x_los_session), body.kind)


@router.post("/applications/{application_id}/copilot/ask")
async def copilot_ask(application_id: str, body: CopilotAsk, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    return await asyncio.to_thread(svc.los.copilot_ask, application_id, _session(svc, x_los_session), body.question)


@router.get("/applications/{application_id}/committee-pack")
async def committee_pack(application_id: str, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Review & committee pack for the Risk Reviewer, EVP and Sanction Committee."""
    return svc.los.committee_pack(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/committee-brief")
async def committee_brief(application_id: str, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Generate the AI committee brief (number-guarded CAM interpretation), then return the pack."""
    return await asyncio.to_thread(svc.los.committee_brief, application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/field-reviews")
async def review_fields(application_id: str, body: FieldReviews, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Risk Maker: confirm or override assessment fields (override needs a value and a reason)."""
    return svc.los.review_fields(application_id, _session(svc, x_los_session),
                                 [r.model_dump() for r in body.reviews])


@router.post("/applications/{application_id}/fields/verify")
async def verify_fields(application_id: str, body: FieldDecisions, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Verify populated fields: confirm, override (value + reason), keep a decided value over a
    conflicting new proposal (reason), or reopen. Returns the refreshed Risk Maker workspace."""
    return await asyncio.to_thread(svc.los.verify_fields, application_id, _session(svc, x_los_session),
                                   [d.model_dump() for d in body.decisions])


@router.post("/applications/{application_id}/fields/bulk-confirm")
async def bulk_confirm_fields(application_id: str, body: BulkConfirm, x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """Confirm the given fields, or every pre-ticked field in the verify queue, in one decision."""
    return await asyncio.to_thread(svc.los.bulk_confirm, application_id, _session(svc, x_los_session),
                                   body.field_ids)


@router.post("/applications/{application_id}/reassign")
async def reassign(application_id: str, body: Reassign, x_los_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    return svc.los.reassign(application_id, _session(svc, x_los_session), body.user_id, body.comment)


@router.post("/applications/{application_id}/escalate")
async def escalate(application_id: str, body: Escalate, x_los_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    return svc.los.escalate(application_id, _session(svc, x_los_session), body.comment)


@router.get("/borrowers")
async def borrowers(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Borrowers in the platform that a new application can be opened for."""
    _session(svc, x_los_session)
    out = []
    for eid, company in sorted(svc.state.companies.items()):
        b, f = company.get("borrower"), company.get("facility")
        out.append({"entity_id": eid, "name": getattr(b, "company_name", eid),
                    "sector": getattr(getattr(b, "sector", None), "value", None),
                    "facility_type": getattr(getattr(f, "facility_type", None), "value", None),
                    "amount_cr": getattr(f, "amount_requested_cr", None),
                    "has_credit_case": eid in svc.state.cases})
    return {"borrowers": out}


@router.get("/borrowers/{entity_id}/identity")
async def borrower_identity(entity_id: str, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    """Customer identity & deduplication for the New Application screen: NTB/ETB, identifiers,
    CBS customer search and potential existing LOS applications."""
    _session(svc, x_los_session)
    return svc.los.borrower_identity(entity_id)


@router.get("/borrowers/{entity_id}/cam")
async def borrower_cam(entity_id: str, x_los_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    """What a new application can start from: the latest CAM in the CAM workspace, or generating one."""
    _session(svc, x_los_session)
    return svc.los.cam_options(entity_id)


@router.get("/audit")
async def audit(limit: int = 200, x_los_session: Optional[str] = Header(None),
                svc: ServiceContainer = Depends(get_container)):
    _session(svc, x_los_session)
    return {"events": svc.los.audit(limit)}


@router.post("/demo/reset")
async def reset_demo(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Admin only: clear LOS applications and re-seed the demo pipeline."""
    session = _session(svc, x_los_session)
    if session["role"] != "los_admin":
        raise ForbiddenError("Only the LOS System Admin can reset the demo")
    return {"seeded": svc.los.seed_demo(force=True)}


# ── governance workspaces (Client One GAP-P0/P1) ─────────────────────────────

class WorkspacePayload(BaseModel):
    payload: dict = Field(default_factory=dict)


@router.post("/applications/{application_id}/parties")
async def save_party(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    """Add/edit a related party; a PAN change re-evaluates identity, reruns dedupe and invalidates PAN-dependent checks."""
    return svc.los.save_party(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/parties/{party_id}/evidence")
async def save_party_evidence(application_id: str, party_id: str, body: WorkspacePayload,
                              x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """Party-level evidence (UAT-P0-3): link one party separately to KYC, bureau checks,
    name screening, ratings, financial records, documents and exceptions."""
    return svc.los.save_party_verification(application_id, _session(svc, x_los_session), party_id, body.payload)


@router.post("/applications/{application_id}/entity")
async def save_entity(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    """Entity-level prospect fields (UAT-P1-4/5): incorporated flag and latest material information date."""
    return svc.los.save_entity_flags(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/invalidations/{invalidation_id}/resolve")
async def resolve_invalidation(application_id: str, invalidation_id: str, body: WorkspacePayload,
                               x_los_session: Optional[str] = Header(None),
                               svc: ServiceContainer = Depends(get_container)):
    """Close a dependency invalidation after the re-evaluation (UAT-P2-10)."""
    return svc.los.resolve_invalidation(application_id, _session(svc, x_los_session),
                                        invalidation_id, str((body.payload or {}).get("resolution") or ""))


@router.post("/applications/{application_id}/facilities/{facility_id}")
async def update_facility(application_id: str, facility_id: str, body: WorkspacePayload,
                          x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Edit a proposed facility (amount, tenor, pricing, repayment, operational IDs); changes are attributed."""
    return svc.los.update_facility(application_id, _session(svc, x_los_session), facility_id, body.payload)


@router.post("/applications/{application_id}/securities")
async def save_security(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Add/update a security (master + lifecycle); changes re-evaluate cover and flag revalidation."""
    return svc.los.save_security(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/projects")
async def save_project(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    """Add/update a project (TEV, cost, means of finance, risk register, DCCO)."""
    return svc.los.save_project(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/projects/{project_id}/change")
async def record_project_change(application_id: str, project_id: str, body: WorkspacePayload,
                                x_los_session: Optional[str] = Header(None),
                                svc: ServiceContainer = Depends(get_container)):
    """Record a project cost/DCCO/scope change — flags the project for reappraisal."""
    return svc.los.record_project_change(application_id, _session(svc, x_los_session), project_id, body.payload)


@router.post("/applications/{application_id}/esms")
async def update_esms(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    """ESMS screening: excluded-activity checklist (remarks mandatory for Yes/Not Available), category, ESDD."""
    return svc.los.update_esms(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/esms/exception-request")
async def request_esms_exception(application_id: str, body: CheckId, x_los_session: Optional[str] = Header(None),
                                 svc: ServiceContainer = Depends(get_container)):
    """R5: the step holder asks the institution's configured E&S authority for an exception
    to the excluded-activity screen."""
    return svc.los.request_esms_exception(application_id, _session(svc, x_los_session), body.remarks)


@router.post("/applications/{application_id}/esms/exception-decision")
async def decide_esms_exception(application_id: str, body: EsmsExceptionDecision,
                                x_los_session: Optional[str] = Header(None),
                                svc: ServiceContainer = Depends(get_container)):
    """R5: the configured E&S authority approves (with a TTL) or declines the E&S exception."""
    return svc.los.decide_esms_exception(application_id, _session(svc, x_los_session),
                                         body.outcome, body.reason)


class EsmsExceptionDecision(BaseModel):
    outcome: str
    reason: str


@router.get("/applications/{application_id}/decision")
async def get_decision(application_id: str, x_los_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    """The decision tab: the computed committee, deviations (automatic and manual), the decision records
    and the remarks history."""
    return svc.los.decision_view(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/letters/{kind}/signed-copy")
async def post_signed_copy(application_id: str, kind: str, filename: str,
                           content: bytes = b"",
                           x_los_session: Optional[str] = Header(None),
                           svc: ServiceContainer = Depends(get_container)):
    """R8: upload the customer's signed copy of the letter (against the letter's current version)."""
    return svc.los.upload_signed_letter(application_id, _session(svc, x_los_session), kind,
                                        filename or "signed.pdf", content or b"")


@router.post("/applications/{application_id}/letters/{kind}/signed-copy/review")
async def post_signed_copy_review(application_id: str, kind: str, body: dict,
                                  x_los_session: Optional[str] = Header(None),
                                  svc: ServiceContainer = Depends(get_container)):
    """R8: the reviewer's verification of the signed copy (verified / rejected)."""
    return svc.los.review_signed_letter(application_id, _session(svc, x_los_session), kind,
                                        (body or {}).get("outcome", ""), (body or {}).get("note", ""))


@router.get("/applications/{application_id}/conditions/indicators")
async def get_condition_indicators(application_id: str, x_los_session: Optional[str] = Header(None),
                                   svc: ServiceContainer = Depends(get_container)):
    """R10: the condition / covenant indicators (open, overdue, breached, waived, pending)."""
    return svc.los.condition_indicators(application_id)


@router.get("/applications/{application_id}/group-exposure")
async def get_group_exposure(application_id: str, x_los_session: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    """R12: the group / connected-party exposure with norm, headroom and breach."""
    return svc.los.group_exposure(application_id, _session(svc, x_los_session))


@router.get("/applications/{application_id}/facilities/hierarchy")
async def get_facility_hierarchy(application_id: str, x_los_session: Optional[str] = Header(None),
                                 svc: ServiceContainer = Depends(get_container)):
    """R6: the facility hierarchy (parent/sublimits, currencies, utilisation) with validation."""
    return svc.los.facility_hierarchy(application_id, _session(svc, x_los_session))


@router.get("/applications/{application_id}/field-permissions")
async def get_field_permissions(application_id: str, x_los_session: Optional[str] = Header(None),
                                svc: ServiceContainer = Depends(get_container)):
    """R17: the effective field-level edit policy for this application — the same policy
    the API enforces, so the UI disables exactly the fields a role may not edit."""
    return svc.los.field_permissions(application_id, _session(svc, x_los_session))


# ── R9 committee governance: the meeting record for a committee step ─────────────────
@router.get("/applications/{application_id}/committees/{step_id}")
async def get_committee_meeting(application_id: str, step_id: str,
                                x_los_session: Optional[str] = Header(None),
                                svc: ServiceContainer = Depends(get_container)):
    """R9: the committee's meeting record — roster, attendance (with conflicts of interest),
    the vote, the structured minutes, the quorum position and the version history."""
    return svc.los.committee_meeting(application_id, _session(svc, x_los_session), step_id)


@router.post("/applications/{application_id}/committees/{step_id}/attendance")
async def post_committee_attendance(application_id: str, step_id: str, body: dict,
                                    x_los_session: Optional[str] = Header(None),
                                    svc: ServiceContainer = Depends(get_container)):
    """R9: record the committee's attendance (present / absent / excused) with conflict-of-
    interest declarations."""
    return svc.los.record_committee_attendance(application_id, _session(svc, x_los_session),
                                               step_id, (body or {}).get("members"))


@router.post("/applications/{application_id}/committees/{step_id}/votes")
async def post_committee_votes(application_id: str, step_id: str, body: dict,
                               x_los_session: Optional[str] = Header(None),
                               svc: ServiceContainer = Depends(get_container)):
    """R9: record the committee's vote (approve / abstain / dissent, per member)."""
    return svc.los.record_committee_votes(application_id, _session(svc, x_los_session),
                                          step_id, (body or {}).get("votes"))


@router.post("/applications/{application_id}/committees/{step_id}/minutes")
async def post_committee_minutes(application_id: str, step_id: str, body: dict,
                                 x_los_session: Optional[str] = Header(None),
                                 svc: ServiceContainer = Depends(get_container)):
    """R9: record the structured minutes (agenda, discussion, resolution)."""
    b = body or {}
    return svc.los.record_committee_minutes(application_id, _session(svc, x_los_session), step_id,
                                            agenda=b.get("agenda"), discussion=b.get("discussion"),
                                            resolution=b.get("resolution"))


@router.put("/applications/{application_id}/prospect")
async def put_prospect(application_id: str, body: dict,
                       x_los_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    """R4: the RM's prospect fields (currency, infra qualification, lead source, status,
    next follow-up)."""
    return svc.los.update_prospect(_session(svc, x_los_session), application_id, body or {})


@router.post("/applications/{application_id}/prospect/discussions")
async def post_prospect_discussion(application_id: str, body: dict,
                                   x_los_session: Optional[str] = Header(None),
                                   svc: ServiceContainer = Depends(get_container)):
    """R4: record a dated prospect discussion (participants, status, notes)."""
    return svc.los.add_prospect_discussion(_session(svc, x_los_session), application_id, body or {})


@router.get("/applications/{application_id}/notifications")
async def get_notifications(application_id: str, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    """R19: the case's current notifications (assignment, rework, deferral due, SLA,
    condition due, covenant breach, pending approval, document rejection)."""
    return {"application_id": application_id,
            "notifications": svc.los.notifications_for(application_id)}


@router.post("/applications/{application_id}/notifications/{notification_id}/acknowledge")
async def acknowledge_notification(application_id: str, notification_id: str,
                                   body: dict, x_los_session: Optional[str] = Header(None),
                                   svc: ServiceContainer = Depends(get_container)):
    """R19: acknowledge a notification (seen; the case state is unchanged)."""
    return svc.los.acknowledge_notification(application_id, _session(svc, x_los_session),
                                            notification_id, (body or {}).get("note", ""))


@router.get("/applications/{application_id}/audit")
async def get_audit(application_id: str, x_los_session: Optional[str] = Header(None),
                    svc: ServiceContainer = Depends(get_container)):
    """R18: the application's audit trail with the hash-chain verification result."""
    from src.los.audit import verify_audit
    events = svc.los.store.events(application_id, limit=100000, asc=True)
    return {"application_id": application_id, "events": events,
            "verification": verify_audit(events)}


@router.get("/applications/{application_id}/reports")
async def get_reports_catalog(application_id: str, x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """R14: the report types available for this case."""
    from src.los import reports
    return {"reports": [{"id": k, "name": v["name"], "description": v["description"]}
                         for k, v in reports.CATALOG.items()]}


@router.get("/applications/{application_id}/reports/{report}")
async def get_report(application_id: str, report: str, fmt: str = "csv",
                     x_los_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    """R14: a downloadable case report (csv or html), derived from the stored record."""
    from src.los import reports
    from src.application.errors import InvalidRequestError
    if fmt not in ("csv", "html"):
        raise InvalidRequestError("fmt must be csv or html")
    if report not in reports.CATALOG:
        raise InvalidRequestError(f"Unknown report '{report}' — available: "
                                  + ", ".join(reports.CATALOG))
    built = reports.build_report(svc.los, application_id, report, fmt=fmt)
    media = "text/csv" if fmt == "csv" else "text/html"
    from fastapi.responses import Response
    filename = f"{application_id}_{report}.{fmt}"
    return Response(content=built[fmt], media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/applications/{application_id}/re_recommendation")
async def post_re_recommendation(application_id: str, x_los_session: Optional[str] = Header(None),
                                 svc: ServiceContainer = Depends(get_container)):
    """R9: the Risk Maker re-submits the revised recommendation after the committee sent the case
    back for re-consideration."""
    return svc.los.re_recommend(application_id, _session(svc, x_los_session))


@router.get("/applications/{application_id}/summary")
async def get_summary(application_id: str, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    """R13: the case summary - the position at each stage, the open risks and the recent decisions,
    so an approver can see where the case stands without opening the documents."""
    return svc.los.summary(application_id=application_id)


@router.get("/applications/{application_id}/routing")
async def get_routing(application_id: str, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    """R1: the calculated route — the authority, the included / excluded conditional steps with the
    basis for each, the required concurrences and their state, and the reapproval flag."""
    app = svc.los.get(application_id, _session(svc, x_los_session))
    v = svc.los.concurrences_view(application_id, _session(svc, x_los_session))
    return {**v, "route_full": app.get("routing") or {}}


@router.post("/applications/{application_id}/concurrences")
async def record_concurrence(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    """Record a concurrence required by the calculated authority (payload {concurrence_id, remarks, evidence?}).
    Only the role the profile assigns to that concurrence may record it."""
    return svc.los.record_concurrence(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/routing/reapprove")
async def reapprove_route(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """The sanction committee's reapproval after a material route change (payload {remarks})."""
    return svc.los.acknowledge_route(application_id, _session(svc, x_los_session),
                                     str(body.payload.get("remarks") or ""))


@router.post("/applications/{application_id}/deviations")
async def save_deviation(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Add a manual deviation (payload {type, description, justification}) or remove one
    (payload {action: remove, id, reason}). At the IP / AP Note and the Risk Maker steps."""
    return svc.los.save_deviation(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/unit-visits")
async def save_unit_visit(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Unit Visit Details: payload {entity_name?, address_visited, date_of_visit, place, officials: [{name,
    designation}], observation, report?, remarks?} or {action: remove, visit_id}. At the AP makers."""
    return svc.los.save_unit_visit(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/sourcing-details")
async def save_sourcing_details(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                                svc: ServiceContainer = Depends(get_container)):
    """Sourcing details: received_date, source, sourcing_branch, owner_primary / secondary, sol_id,
    sub_sub_sector, lpfg_analyst, lpfg_senior_analyst. At Prospect Sourcing and IP Note Processing."""
    return svc.los.save_sourcing_details(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/security-notes")
async def save_security_notes(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                              svc: ServiceContainer = Depends(get_container)):
    """The AP security remarks: creation_status, change_since_last_sanction, security_trustee."""
    return svc.los.save_security_notes(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/decision-notes")
async def save_decision_note(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    """A decision-tab narrative: payload {key, text} (policy_compliance, previous_relaxations, other_matters,
    ip_observations)."""
    return svc.los.save_decision_note(application_id, _session(svc, x_los_session), body.payload.get("key"),
                                      body.payload.get("text"))


@router.get("/applications/{application_id}/terms")
async def get_terms(application_id: str, x_los_session: Optional[str] = Header(None),
                    svc: ServiceContainer = Depends(get_container)):
    """Terms & conditions authored at AP (drafted by the T&C agent), with each draft's field status and evidence."""
    return svc.los.terms(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/terms")
async def save_term(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                    svc: ServiceContainer = Depends(get_container)):
    """Author a term & condition: payload {action: add|update|remove|restore, term_id?, category, text,
    facility_id?, stipulated_value?, frequency?, reason?}. Editing an agent's text needs a reason."""
    return svc.los.save_term(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/ewps")
async def save_ewp(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    """External work parties: LIA, LIE, Security Trustee, ESDD provider, Legal Loan Counsel."""
    return svc.los.save_ewp(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/ratings")
async def record_rating(application_id: str, kind: str, body: WorkspacePayload,
                        x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Record an external / internal rating or an adverse-event review (kind: external|internal|adverse_event)."""
    return svc.los.record_rating(application_id, _session(svc, x_los_session), kind, body.payload)


@router.post("/applications/{application_id}/raroc")
async def compute_raroc(application_id: str, body: WorkspacePayload,
                        x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Compute the facility-wise RAROC from its recorded inputs (labelled demo model)."""
    return svc.los.compute_raroc(application_id, _session(svc, x_los_session), body.payload.get("facility_id"))


@router.post("/applications/{application_id}/crp-notes")
async def save_crp_note(application_id: str, body: WorkspacePayload, review: bool = False,
                        x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """Upload or review LPF Note / Rating Report / CRP Note / risk observations."""
    return svc.los.save_crp_note(application_id, _session(svc, x_los_session), body.payload, review=review)


@router.post("/applications/{application_id}/cma")
async def record_cma(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    """Record CMA rows for a subject (borrower/promoter/sponsor/spv/parent) with audited/provisional/projected class."""
    p = body.payload
    return svc.los.record_cma(application_id, _session(svc, x_los_session), p.get("subject", ""),
                              p.get("rows") or {}, p.get("value_class", "audited"))


@router.post("/applications/{application_id}/cma/review")
async def review_cma(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    """Maker-checker review of the CMA (approve or return)."""
    p = body.payload
    return svc.los.review_cma(application_id, _session(svc, x_los_session), bool(p.get("approve")), p.get("remarks", ""))


@router.post("/applications/{application_id}/proposal")
async def update_proposal(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Proposal / exposure / banking / conduct / compliance / inter-firm sections (section + payload)."""
    p = body.payload
    return svc.los.update_proposal(application_id, _session(svc, x_los_session), p.get("section", ""), p.get("data") or {})


@router.post("/applications/{application_id}/proposal/fetch-exposure")
async def fetch_exposure(application_id: str, kind: str, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Fetch Bond / Loan Exposure — labelled demo source (FT not connected: yields unavailable)."""
    return svc.los.fetch_exposure(application_id, _session(svc, x_los_session), kind)


@router.post("/applications/{application_id}/pricing")
async def record_pricing(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    """Facility pricing record: recommended vs proposed benchmark/rate/spread, comparison and justification."""
    return svc.los.record_pricing(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/pricing/fees")
async def record_fee(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    return svc.los.record_fee(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/pricing/schedule")
async def record_tentative_schedule(application_id: str, body: WorkspacePayload,
                                    x_los_session: Optional[str] = Header(None),
                                    svc: ServiceContainer = Depends(get_container)):
    """The tentative term-loan schedule — kept distinct from the final disbursement terms."""
    return svc.los.record_tentative_schedule(application_id, _session(svc, x_los_session), body.payload)


@router.post("/applications/{application_id}/disops")
async def update_disops(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Disbursement Maker operational record: cif, limits, loan_accounts, security_refs, beneficiaries,
    fees, non_fund_charges, repayment_final, interest_terms, arrears, drawdown, sop, exposure, missing_info."""
    p = body.payload
    return svc.los.update_disops(application_id, _session(svc, x_los_session), p.get("section", ""), p.get("data") or {})


@router.post("/applications/{application_id}/disops/memo")
async def generate_memo(application_id: str, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """Generate the Disbursement Memo (freezes the operational record; RUL-13)."""
    return svc.los.generate_memo(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/disops/memo/review")
async def review_memo(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    p = body.payload
    return svc.los.review_memo(application_id, _session(svc, x_los_session), bool(p.get("approve")), p.get("remarks", ""))


@router.post("/applications/{application_id}/disops/review")
async def update_dis_review(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                            svc: ServiceContainer = Depends(get_container)):
    """Read-only review checklists of the Disbursement Checker / Final Approver (stage: checker|final)."""
    p = body.payload
    return svc.los.update_dis_review(application_id, _session(svc, x_los_session), p.get("stage", "checker"),
                                     p.get("items") or [])


@router.post("/applications/{application_id}/documents/review")
async def review_document(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Reviewed / accepted / rejected / rework status with the reviewer (GAP-P0-12)."""
    p = body.payload
    return svc.los.review_document(application_id, _session(svc, x_los_session), p.get("doc_id", ""),
                                   p.get("status", ""), p.get("remarks", ""))


@router.get("/applications/{application_id}/documents")
async def documents(application_id: str, x_los_session: Optional[str] = Header(None),
                    svc: ServiceContainer = Depends(get_container)):
    """The logical document registry: checklist, versions, statuses and the stage gate."""
    return svc.los.documents(application_id, _session(svc, x_los_session))


@router.post("/applications/{application_id}/material-changes/review")
async def review_material_changes(application_id: str, body: WorkspacePayload, x_los_session: Optional[str] = Header(None),
                                  svc: ServiceContainer = Depends(get_container)):
    """Accept or reject the material change(s) since the approval snapshot (remarks mandatory)."""
    p = body.payload
    return svc.los.review_material_changes(application_id, _session(svc, x_los_session),
                                           p.get("decision", ""), p.get("remarks", ""))


@router.get("/applications/{application_id}/snapshot")
async def snapshot_view(application_id: str, x_los_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    """The approval snapshot(s) and material-change state (GAP-P0-11)."""
    return svc.los.snapshot_view(application_id, _session(svc, x_los_session))


@router.get("/applications/{application_id}/rules")
async def rules_view(application_id: str, x_los_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    """The mandatory rule catalog with live status (GAP-P2-01) and the dependency matrix (GAP-P2-02)."""
    return svc.los.rules_view(application_id, _session(svc, x_los_session))


@router.get("/integrations")
async def integrations(x_los_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    """The integration adapter registry with the honest state of every source (GAP-P0-17)."""
    _session(svc, x_los_session)
    return svc.los.integrations()


@router.post("/applications/{application_id}/outputs/{kind}")
async def generate_output(application_id: str, kind: str, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Generated outputs: executive_summary, due_diligence_report, esms_approval_note,
    committee_minutes, cma_download, disbursement_memo (GAP-P1-06)."""
    return svc.los.generate_output(application_id, _session(svc, x_los_session), kind)


@router.get("/applications/{application_id}/outputs/{kind}.html", response_class=HTMLResponse)
async def download_output(application_id: str, kind: str, x_los_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    """Downloadable demo output as a self-contained HTML page (UAT-P1-7): MCA/CIBIL/CRIF reports,
    CEIB Proforma A, UDIN response, Drawdown Request & Schedule and Annexures I/III/IV/VI/IX/XI/XIII/XIV."""
    _session(svc, x_los_session)
    return HTMLResponse(svc.los.output_html(application_id, kind))
