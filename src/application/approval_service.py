"""
Approval workflow: maker-checker review of a credit case against the
delegation-of-powers matrix, with an append-only decision audit trail.
"""

from dataclasses import dataclass

from src.application.case_service import CaseService
from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.engines.approval_policy import (
    CHECKER_ACTIONS, MAKER_ACTIONS, AuthorityMatrix, CaseStatus, WorkflowAction, WorkflowError,
    allowed_actions, next_status,
)


@dataclass(frozen=True)
class Actor:
    """Who is acting. Supplied by the caller until real authentication exists."""

    user_id: str
    role: str  # a maker role, or an authority level id from config/approval.yaml


class ApprovalService:
    def __init__(self, persistence, cases: CaseService, matrix_loader):
        self.persistence = persistence
        self.cases = cases
        self._matrix_loader = matrix_loader

    @property
    def matrix(self) -> AuthorityMatrix:
        return self._matrix_loader()

    # ── Queries ──────────────────────────────────────────────────────────

    def _current(self, entity_id: str) -> tuple[dict, dict]:
        """The latest case and its workflow row (a fresh draft if the run is new)."""
        case = self.cases.require(entity_id)
        workflow = self.persistence.get_workflow(entity_id)
        if not workflow or workflow["case_run_id"] != case.get("run_id"):
            workflow = {"entity_id": entity_id, "case_run_id": case.get("run_id"),
                        "status": CaseStatus.DRAFT.value, "required_authority": None, "submitted_by": None}
        return case, workflow

    def required_authority(self, case: dict):
        return self.matrix.required_authority(
            float(case.get("requested_amount_cr") or 0),
            str(case.get("risk_grade") or "E"),
            str(case.get("recommendation") or ""),
        )

    def status(self, entity_id: str) -> dict:
        case, workflow = self._current(entity_id)
        required = self.required_authority(case)
        return {
            "entity_id": entity_id,
            "case_run_id": workflow["case_run_id"],
            "status": workflow["status"],
            "submitted_by": workflow.get("submitted_by"),
            "system_recommendation": case.get("recommendation"),
            "risk_grade": case.get("risk_grade"),
            "requested_amount_cr": case.get("requested_amount_cr"),
            "required_authority": {"id": required.id, "name": required.name},
            "is_deviation_route": case.get("recommendation") == "decline",
            "allowed_actions": allowed_actions(CaseStatus(workflow["status"])),
            "history": self.persistence.list_case_decisions(entity_id),
        }

    def queue(self, authority_level_id: str) -> list[dict]:
        """Submitted cases this authority level may decide."""
        level = self.matrix.level(authority_level_id)
        if level is None:
            raise InvalidRequestError(f"Unknown authority level '{authority_level_id}'")
        pending = []
        for workflow in self.persistence.list_workflows(CaseStatus.SUBMITTED.value):
            required = self.matrix.level(workflow.get("required_authority") or "")
            if required and self.matrix.can_decide(level.id, required):
                case = self.cases.get(workflow["entity_id"]) or {}
                pending.append({**workflow, "company_name": case.get("company_name"),
                                "requested_amount_cr": case.get("requested_amount_cr"),
                                "risk_grade": case.get("risk_grade"),
                                "system_recommendation": case.get("recommendation")})
        return pending

    def authority_matrix(self) -> list[dict]:
        return [{"id": level.id, "name": level.name, "rank": level.rank,
                 "max_amount_cr": level.max_amount_cr, "allowed_risk_grades": list(level.allowed_risk_grades)}
                for level in self.matrix.levels]

    def is_locked_for_rerun(self, entity_id: str) -> bool:
        workflow = self.persistence.get_workflow(entity_id)
        return bool(workflow and workflow["status"] == CaseStatus.SUBMITTED.value)

    # ── Commands ─────────────────────────────────────────────────────────

    def act(self, entity_id: str, action: str, actor: Actor, comments: str = "",
            conditions: list[str] | None = None) -> dict:
        try:
            action_enum = WorkflowAction(action)
        except ValueError:
            raise InvalidRequestError(f"Unknown action '{action}'. Use one of: "
                                      f"{', '.join(a.value for a in WorkflowAction)}")
        if not actor.user_id or not actor.role:
            raise ForbiddenError("Identify the actor with X-User-Id and X-User-Role headers")

        case, workflow = self._current(entity_id)
        current = CaseStatus(workflow["status"])
        try:
            target = next_status(current, action_enum)
        except WorkflowError as e:
            raise ConflictError(str(e))

        required = self.required_authority(case)
        comments = (comments or "").strip()
        submitted_by = workflow.get("submitted_by")

        if action_enum in MAKER_ACTIONS:
            if actor.role not in self.matrix.maker_roles:
                raise ForbiddenError(f"Role '{actor.role}' cannot {action_enum.value} cases")
            if action_enum is WorkflowAction.RECALL and actor.user_id != submitted_by:
                raise ForbiddenError("Only the user who submitted the case can recall it")
            if action_enum is WorkflowAction.SUBMIT:
                submitted_by = actor.user_id

        if action_enum in CHECKER_ACTIONS:
            if self.matrix.level(actor.role) is None:
                raise ForbiddenError(f"Role '{actor.role}' is not an approving authority")
            if not self.matrix.can_decide(actor.role, required):
                raise ForbiddenError(f"This case requires {required.name} or above")
            if actor.user_id == submitted_by:
                raise ForbiddenError("Maker-checker: the submitter cannot decide their own case")
            if action_enum in (WorkflowAction.REJECT, WorkflowAction.RETURN) and not comments:
                raise InvalidRequestError(f"Comments are required to {action_enum.value} a case")
            if (action_enum is WorkflowAction.APPROVE and case.get("recommendation") == "decline"
                    and not comments):
                raise InvalidRequestError("Approving against a system DECLINE needs a justification in comments")

        self.persistence.record_workflow_transition(
            entity_id=entity_id, case_run_id=workflow["case_run_id"], action=action_enum.value,
            from_status=current.value, to_status=target.value, actor_id=actor.user_id, actor_role=actor.role,
            required_authority=required.id, system_recommendation=case.get("recommendation"),
            submitted_by=submitted_by, comments=comments, conditions=conditions,
        )
        return self.status(entity_id)
