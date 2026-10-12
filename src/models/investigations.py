"""
Investigation model.

An investigation is a follow-up task the Investigation Agent opens for one or
more credit observations: what must be checked next, why, which evidence is
needed and how urgently. Routing, reason, evidence and priority are
deterministic; an LLM may only phrase the request (``request_text``).
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class InvestigationStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"


class InvestigationPriority(str, Enum):
    P1 = "P1"   # resolve before the case goes to credit committee
    P2 = "P2"   # resolve before sanction
    P3 = "P3"   # may be carried as a pre-disbursement condition


PRIORITY_ORDER = {p.value: i for i, p in enumerate(InvestigationPriority)}


@dataclass
class Investigation:
    investigation_id: str
    case_id: str
    observation_id: str                 # originating (most severe) observation
    title: str
    reason: str
    priority: str                       # InvestigationPriority value
    required_evidence: list[dict]       # [{item, description, purpose, source}]
    status: str                         # InvestigationStatus value
    agent_reasoning: list[str]          # routing / priority steps, in order
    investigation_type: str = ""
    related_observation_ids: list[str] = field(default_factory=list)
    observation_title: str = ""
    observation_severity: str = ""
    created_at: str = ""
    generated_by: str = ""
    review: dict = field(default_factory=dict)          # {note, updated_at, updated_by}
    request_text: Optional[dict] = None                 # optional LLM phrasing {text, model, generated_at}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
