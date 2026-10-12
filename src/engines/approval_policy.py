"""
Approval policy: the delegation-of-powers matrix and the case workflow state
machine. Pure and deterministic — persistence and actors live in the
application layer.
"""

from dataclasses import dataclass
from enum import Enum


class CaseStatus(str, Enum):
    DRAFT = "draft"                      # pipeline has run; maker is preparing
    SUBMITTED = "submitted"              # with the approving authority
    RETURNED = "returned_for_rework"     # authority sent it back to the maker
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkflowAction(str, Enum):
    SUBMIT = "submit"
    RECALL = "recall"
    APPROVE = "approve"
    REJECT = "reject"
    RETURN = "return"


# (from_status, action) -> to_status
TRANSITIONS: dict[tuple[CaseStatus, WorkflowAction], CaseStatus] = {
    (CaseStatus.DRAFT, WorkflowAction.SUBMIT): CaseStatus.SUBMITTED,
    (CaseStatus.RETURNED, WorkflowAction.SUBMIT): CaseStatus.SUBMITTED,
    (CaseStatus.SUBMITTED, WorkflowAction.RECALL): CaseStatus.DRAFT,
    (CaseStatus.SUBMITTED, WorkflowAction.APPROVE): CaseStatus.APPROVED,
    (CaseStatus.SUBMITTED, WorkflowAction.REJECT): CaseStatus.REJECTED,
    (CaseStatus.SUBMITTED, WorkflowAction.RETURN): CaseStatus.RETURNED,
}

MAKER_ACTIONS = {WorkflowAction.SUBMIT, WorkflowAction.RECALL}
CHECKER_ACTIONS = {WorkflowAction.APPROVE, WorkflowAction.REJECT, WorkflowAction.RETURN}
FINAL_STATUSES = {CaseStatus.APPROVED, CaseStatus.REJECTED}


class WorkflowError(ValueError):
    """An action that the workflow rules do not allow."""


@dataclass(frozen=True)
class AuthorityLevel:
    id: str
    name: str
    rank: int
    max_amount_cr: float | None
    allowed_risk_grades: tuple[str, ...]

    def covers(self, amount_cr: float, risk_grade: str) -> bool:
        within_limit = self.max_amount_cr is None or amount_cr <= self.max_amount_cr
        return within_limit and risk_grade in self.allowed_risk_grades


class AuthorityMatrix:
    def __init__(self, levels: list[AuthorityLevel], deviation_escalation_levels: int = 1,
                 maker_roles: tuple[str, ...] = ()):
        if not levels:
            raise ValueError("Approval matrix has no authority levels")
        self.levels = sorted(levels, key=lambda level: level.rank)
        self.deviation_escalation_levels = deviation_escalation_levels
        self.maker_roles = maker_roles

    @classmethod
    def from_config(cls, cfg: dict) -> "AuthorityMatrix":
        levels = [
            AuthorityLevel(
                id=item["id"],
                name=item.get("name", item["id"]),
                rank=rank,
                max_amount_cr=item.get("max_amount_cr"),
                allowed_risk_grades=tuple(item.get("allowed_risk_grades") or ()),
            )
            for rank, item in enumerate(cfg.get("authority_levels") or [])
        ]
        return cls(levels,
                   deviation_escalation_levels=int(cfg.get("deviation_escalation_levels", 1)),
                   maker_roles=tuple(cfg.get("maker_roles") or ()))

    def level(self, level_id: str) -> AuthorityLevel | None:
        return next((level for level in self.levels if level.id == level_id), None)

    def required_authority(self, amount_cr: float, risk_grade: str, system_recommendation: str) -> AuthorityLevel:
        """Lowest level that may decide this case; higher when approving would be a deviation."""
        base = next((level for level in self.levels if level.covers(amount_cr, risk_grade)), self.levels[-1])
        if system_recommendation == "decline":
            index = min(self.levels.index(base) + self.deviation_escalation_levels, len(self.levels) - 1)
            return self.levels[index]
        return base

    def can_decide(self, actor_level_id: str, required: AuthorityLevel) -> bool:
        """An authority may decide cases at its own level or below."""
        actor_level = self.level(actor_level_id)
        return actor_level is not None and actor_level.rank >= required.rank


def next_status(current: CaseStatus, action: WorkflowAction) -> CaseStatus:
    target = TRANSITIONS.get((current, action))
    if target is None:
        raise WorkflowError(f"Cannot {action.value} a case that is {current.value.replace('_', ' ')}")
    return target


def allowed_actions(current: CaseStatus) -> list[str]:
    return [action.value for (status, action) in TRANSITIONS if status == current]
