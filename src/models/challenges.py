"""
Credit Challenge model.

A challenge questions the proposed facility: it states what in the proposal is
in doubt, the figures behind the doubt, and what the RM must answer. Triggers,
figures and severity are deterministic (src/agents/challenge_agent.py); an LLM
may only reword the challenge (``ai_wording``). A challenge never approves or
declines anything — the analyst records how it was dealt with in ``status``.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ChallengeStatus(str, Enum):
    OPEN = "OPEN"               # not yet answered
    ADDRESSED = "ADDRESSED"     # RM has answered it with evidence
    ACCEPTED = "ACCEPTED"       # the risk is accepted (e.g. mitigated by a condition)
    OVERRIDDEN = "OVERRIDDEN"   # the analyst disagrees with the challenge


@dataclass
class CreditChallenge:
    challenge_id: str
    case_id: str
    category: str
    challenge: str
    supporting_metrics: list[dict]      # [{metric, label, value, unit, period, source}]
    rationale: str
    severity: str                       # CRITICAL | HIGH | MEDIUM | LOW
    required_response: list[str]
    status: str                         # ChallengeStatus value
    title: str = ""
    rule_id: str = ""
    proposal_reference: str = ""        # the part of the proposal being challenged
    linked_observation_ids: list[str] = field(default_factory=list)
    linked_investigation_ids: list[str] = field(default_factory=list)
    agent_reasoning: list[str] = field(default_factory=list)
    created_at: str = ""
    generated_by: str = ""
    review: dict = field(default_factory=dict)          # {response, updated_at, updated_by}
    ai_wording: Optional[dict] = None                   # {challenge, rationale, model, generated_at}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
