"""Delegation-of-powers routing and workflow transitions."""

import pytest

from src.engines.approval_policy import (
    AuthorityMatrix, CaseStatus, WorkflowAction, WorkflowError, allowed_actions, next_status,
)

MATRIX = AuthorityMatrix.from_config({
    "authority_levels": [
        {"id": "branch", "max_amount_cr": 25, "allowed_risk_grades": ["A", "B"]},
        {"id": "zonal", "max_amount_cr": 100, "allowed_risk_grades": ["A", "B", "C"]},
        {"id": "head_office", "max_amount_cr": 500, "allowed_risk_grades": ["A", "B", "C", "D"]},
        {"id": "board", "max_amount_cr": None, "allowed_risk_grades": ["A", "B", "C", "D", "E"]},
    ],
    "deviation_escalation_levels": 1,
    "maker_roles": ["relationship_manager"],
})


@pytest.mark.parametrize("amount, grade, recommendation, expected", [
    (10, "A", "approve", "branch"),
    (10, "C", "refer", "zonal"),          # grade outside branch powers
    (80, "B", "approve", "zonal"),        # amount above branch limit
    (400, "D", "refer", "head_office"),
    (2000, "A", "approve", "board"),      # no level below has the limit
    (10, "A", "decline", "zonal"),        # approving a decline is a deviation: one level up
    (2000, "E", "decline", "board"),      # escalation is capped at the top level
])
def test_required_authority(amount, grade, recommendation, expected):
    assert MATRIX.required_authority(amount, grade, recommendation).id == expected


def test_higher_authority_can_decide_lower_cases():
    zonal = MATRIX.level("zonal")
    assert MATRIX.can_decide("head_office", zonal)
    assert MATRIX.can_decide("zonal", zonal)
    assert not MATRIX.can_decide("branch", zonal)
    assert not MATRIX.can_decide("unknown", zonal)


def test_transitions():
    assert next_status(CaseStatus.DRAFT, WorkflowAction.SUBMIT) is CaseStatus.SUBMITTED
    assert next_status(CaseStatus.SUBMITTED, WorkflowAction.RETURN) is CaseStatus.RETURNED
    assert next_status(CaseStatus.RETURNED, WorkflowAction.SUBMIT) is CaseStatus.SUBMITTED
    with pytest.raises(WorkflowError):
        next_status(CaseStatus.DRAFT, WorkflowAction.APPROVE)
    with pytest.raises(WorkflowError):
        next_status(CaseStatus.APPROVED, WorkflowAction.SUBMIT)
    assert allowed_actions(CaseStatus.APPROVED) == []
    assert set(allowed_actions(CaseStatus.SUBMITTED)) == {"recall", "approve", "reject", "return"}
