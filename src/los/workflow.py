"""
LOS workflow definition and transition rules (deterministic, no I/O).

The definition (config/los_workflow.yaml) lists groups, roles, demo users and the
stages → steps an application moves through. ``transition`` decides where an
action takes an application; the service applies it, records the audit event
and assigns the next person.

Actions by step kind:
  maker       submit                      → next step
  checker     approve | return | reject   → next step | previous maker step | rejected
  vp_review   submit | return             → next step (endorse) | previous maker step (rework)
  allocation  allocate (to a user)        → next step, assigned to that user
  committee   sanction | return | reject  → next stage | previous maker step | rejected
Any active step can also be escalated (flag only) or reassigned (same step).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

STATUS_DRAFT = "DRAFT"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_UNDER_REVIEW = "UNDER_REVIEW"
STATUS_RETURNED = "RETURNED"
STATUS_APPROVED = "APPROVED"          # all stages complete (disbursed)
STATUS_REJECTED = "REJECTED"
STATUS_WITHDRAWN = "WITHDRAWN"        # the borrower / prospect withdraws the application
STATUS_DROPPED = "DROPPED"            # the bank drops / terminates the application
TERMINAL = (STATUS_APPROVED, STATUS_REJECTED, STATUS_WITHDRAWN, STATUS_DROPPED)

# Base actions per step kind. ``available_actions`` further narrows them per step
# (e.g. a modification can only be proposed at a post-sanction maker step).
ACTIONS_BY_KIND = {
    "maker": ("submit", "withdraw", "propose_modification"),
    "checker": ("approve", "return", "reject", "recommend_modification", "drop"),
    "vp_review": ("submit", "return"),
    "allocation": ("allocate",),
    "committee": ("sanction", "return", "reject", "drop"),
}
COMMENT_REQUIRED = ("return", "reject", "withdraw", "propose_modification", "recommend_modification", "drop")

# Actions that end the application (no next step).
TERMINATING_ACTIONS = {"withdraw": STATUS_WITHDRAWN, "drop": STATUS_DROPPED, "reject": STATUS_REJECTED}

# A modification to sanctioned terms must re-enter credit reassessment.
MODIFICATION_TARGET_STEP = "ap_risk_maker"
# Only post-sanction makers can propose a modification of sanctioned terms.
MODIFICATION_MAKER_STEPS = ("pos_maker", "dis_maker")


class WorkflowError(ValueError):
    """An action that the workflow does not allow."""


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    role: str
    kind: str
    sla_days: int
    stage_id: str
    stage_name: str
    index: int                      # position in the full ordered step list
    allocates_to: Optional[str] = None


@dataclass
class Workflow:
    groups: list[dict]
    roles: dict[str, str]
    users: list[dict]
    stages: list[dict]
    steps: list[Step] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: dict) -> "Workflow":
        if not cfg or not cfg.get("stages"):
            raise WorkflowError("LOS workflow configuration (config/los_workflow.yaml) is missing or empty")
        steps, index = [], 0
        for stage in cfg["stages"]:
            for s in stage["steps"]:
                steps.append(Step(id=s["id"], name=s["name"], role=s["role"], kind=s["kind"],
                                  sla_days=int(s.get("sla_days", 3)), stage_id=stage["id"], stage_name=stage["name"],
                                  index=index, allocates_to=s.get("allocates_to")))
                index += 1
        wf = cls(groups=cfg.get("groups", []), roles=cfg.get("roles", {}), users=cfg.get("users", []),
                 stages=cfg["stages"], steps=steps)
        wf._validate()
        return wf

    def _validate(self) -> None:
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise WorkflowError("duplicate step ids in the LOS workflow")
        for s in self.steps:
            if s.kind not in ACTIONS_BY_KIND:
                raise WorkflowError(f"step {s.id}: unknown kind {s.kind}")
            if s.role not in self.roles:
                raise WorkflowError(f"step {s.id}: unknown role {s.role}")
            if s.kind == "allocation" and s.allocates_to not in self.roles:
                raise WorkflowError(f"step {s.id}: allocation needs a valid allocates_to role")
        user_roles = {r for u in self.users for r in u.get("roles", [])}
        missing = sorted({s.role for s in self.steps} - user_roles)
        if missing:
            raise WorkflowError(f"no demo user holds role(s): {', '.join(missing)}")

    # ── lookups ──────────────────────────────────────────────────────────────
    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise WorkflowError(f"unknown step {step_id}")

    @property
    def first_step(self) -> Step:
        return self.steps[0]

    def next_step(self, step: Step) -> Optional[Step]:
        return self.steps[step.index + 1] if step.index + 1 < len(self.steps) else None

    def previous_maker(self, step: Step) -> Step:
        """The maker step a checker / committee returns work to (within the same stage)."""
        for s in reversed(self.steps[:step.index]):
            if s.stage_id == step.stage_id and s.kind == "maker":
                return s
        return self.steps[step.index - 1] if step.index > 0 else step

    def next_stage_first_step(self, step: Step) -> Optional[Step]:
        for s in self.steps[step.index + 1:]:
            if s.stage_id != step.stage_id:
                return s
        return None

    def user(self, user_id: str) -> dict:
        for u in self.users:
            if u["id"] == user_id:
                return u
        raise WorkflowError(f"unknown user {user_id}")

    def users_with_role(self, role: str) -> list[dict]:
        return [u for u in self.users if role in u.get("roles", [])]

    def group_of_role(self, role: str) -> Optional[dict]:
        return next((g for g in self.groups if role in g.get("roles", [])), None)

    def actions_for(self, step: Step) -> tuple[str, ...]:
        return ACTIONS_BY_KIND[step.kind]


def available_actions(wf: Workflow, step: Step) -> tuple[str, ...]:
    """The actions open at a step: the kind's base actions narrowed by step context.
    A modification of sanctioned terms can only be proposed at a post-sanction maker step;"""
    base = ACTIONS_BY_KIND[step.kind]
    if step.kind == "maker" and step.id not in MODIFICATION_MAKER_STEPS:
        base = tuple(a for a in base if a != "propose_modification")
    return base


def rework_destinations(wf: Workflow, step: Step) -> list[dict]:
    """The earlier steps a checker / committee / maker may rework to (reason-specific rework)."""
    return [{"id": s.id, "name": s.name, "stage": s.stage_name} for s in wf.steps if s.index < step.index]


@dataclass(frozen=True)
class Outcome:
    step_id: Optional[str]          # None when the application is finished
    status: str
    assign_role: Optional[str]      # role whose holder gets the work next
    assign_user: Optional[str] = None
    message: str = ""


def status_on_entry(step: Step, returned: bool = False) -> str:
    if returned:
        return STATUS_RETURNED
    return STATUS_UNDER_REVIEW if step.kind in ("checker", "committee", "vp_review") else STATUS_IN_PROGRESS


def transition(wf: Workflow, step: Step, action: str, *, comment: str = "", allocate_to: str | None = None,
               current_status: str = STATUS_IN_PROGRESS, rework_to: str | None = None) -> Outcome:
    """Where ``action`` on ``step`` takes the application. Raises WorkflowError if not allowed."""
    if current_status in TERMINAL:
        raise WorkflowError(f"application is {current_status.lower()}; no further actions")
    if action not in available_actions(wf, step):
        raise WorkflowError(f"'{action}' is not available at {step.name} ({step.kind} step)")
    if action in COMMENT_REQUIRED and not (comment or "").strip():
        raise WorkflowError(f"a comment is required to {action}")

    if action in TERMINATING_ACTIONS and action != "reject":
        # withdraw / drop: the application ends where it is. A reason is mandatory (COMMENT_REQUIRED).
        status = TERMINATING_ACTIONS[action]
        verb = "Withdrawn" if action == "withdraw" else "Dropped / terminated"
        return Outcome(step_id=None, status=status, assign_role=None, message=f"{verb} at {step.name}")
    if action == "reject":
        return Outcome(step_id=step.id, status=STATUS_REJECTED, assign_role=None, message=f"Rejected at {step.name}")
    if action in ("propose_modification", "recommend_modification"):
        # A maker proposes (or a read-only checker recommends) a modification of the sanctioned
        # terms: the application re-enters credit reassessment with a recorded request.
        target = wf.step(MODIFICATION_TARGET_STEP) if wf.step(MODIFICATION_TARGET_STEP).index < step.index else None
        back = target or wf.previous_maker(step)
        verb = "Modification proposed" if action == "propose_modification" else "Modification recommended"
        return Outcome(step_id=back.id, status=STATUS_RETURNED, assign_role=back.role,
                       message=f"{verb} at {step.name}; re-entering {back.name}")
    if action == "return":
        if rework_to:
            back = wf.step(rework_to)
            if back.index >= step.index:
                raise WorkflowError(f"a rework destination must be an earlier step (not {back.name})")
        else:
            back = wf.previous_maker(step)
        return Outcome(step_id=back.id, status=STATUS_RETURNED, assign_role=back.role,
                       message=f"Returned from {step.name} to {back.name}")
    if action == "allocate":
        if not allocate_to:
            raise WorkflowError("choose the person to allocate to")
        user = wf.user(allocate_to)
        if step.allocates_to not in user.get("roles", []):
            raise WorkflowError(f"{user['name']} does not hold the {wf.roles[step.allocates_to]} role")
        nxt = wf.next_step(step)
        return Outcome(step_id=nxt.id, status=status_on_entry(nxt), assign_role=nxt.role,
                       assign_user=allocate_to if nxt.role == step.allocates_to else None,
                       message=f"Allocated to {user['name']}")

    # submit / approve / sanction move forward
    nxt = wf.next_step(step)
    if nxt is None:
        return Outcome(step_id=None, status=STATUS_APPROVED, assign_role=None, message="Disbursement approved — complete")
    verb = {"submit": "Submitted", "approve": "Approved", "sanction": "Sanctioned"}[action]
    return Outcome(step_id=nxt.id, status=status_on_entry(nxt), assign_role=nxt.role,
                   message=f"{verb} at {step.name}; moved to {nxt.name}")


def can_act(wf: Workflow, user_id: str, active_role: str, step: Step) -> bool:
    """The acting user must hold the step's role and be acting in it."""
    user = wf.user(user_id)
    return active_role == step.role and step.role in user.get("roles", [])


# Working-day / holiday SLA calendar (UAT-P2-9). The holiday list is a labelled demo set — the
# bank's official holiday calendar is confirmation-required, so no real dates are asserted.
HOLIDAYS: set[str] = {
    "2026-01-26", "2026-03-04", "2026-03-21", "2026-03-31", "2026-05-01",
    "2026-08-15", "2026-10-02", "2026-10-20", "2026-11-08", "2026-12-25",
}
# An SLA breach that has aged beyond this many (calendar) days escalates.
ESCALATION_AGE_DAYS = 2


def is_working_day(d: datetime) -> bool:
    """A weekday that is not a listed holiday."""
    return d.weekday() < 5 and d.date().isoformat() not in HOLIDAYS


def add_working_days(start: datetime, days: int) -> datetime:
    """Advance ``days`` working days from ``start`` (weekends and holidays excluded)."""
    if days <= 0:
        return start
    cur = start
    added = 0
    while added < days:
        cur = cur + timedelta(days=1)
        if is_working_day(cur):
            added += 1
    return cur


def due_at(entered_at: datetime, step: Step) -> datetime:
    """SLA due date in working days (weekends + holidays excluded) (UAT-P2-9)."""
    return add_working_days(entered_at, step.sla_days)


def sla_state(entered_at: datetime, step: Step, now: datetime) -> dict:
    due = due_at(entered_at, step)
    remaining = (due - now).total_seconds() / 86400
    breached = remaining < 0
    aged_days = round(-remaining, 1) if breached else 0.0
    return {"due_at": due.isoformat(timespec="seconds"), "days_remaining": round(remaining, 1),
            "breached": breached,
            # ageing escalation (UAT-P2-9): a breach that has aged beyond the threshold escalates
            "escalated": breached and aged_days >= ESCALATION_AGE_DAYS,
            "age_days": aged_days}
