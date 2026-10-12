"""
Credit Risk Observation model.

An observation is a structured credit finding derived deterministically from
the analytical engines' outputs (ratios, benchmarks, validations, policy). The
observation engine alone decides whether an observation exists, its severity,
its metrics and the threshold comparison; an LLM may later add explanatory
wording in ``ai_explanation`` but never changes those fields.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ObservationSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ObservationStatus(str, Enum):
    NEW = "NEW"
    INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED"
    EXPLAINED = "EXPLAINED"
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"


SEVERITY_ORDER = {s.value: i for i, s in enumerate(ObservationSeverity)}


@dataclass
class CreditObservation:
    observation_id: str
    case_id: str
    category: str
    title: str
    severity: str                       # ObservationSeverity value
    status: str                         # ObservationStatus value
    summary: str
    detailed_explanation: str
    metrics: list[dict]                 # [{metric, label, period, value, unit, source}]
    period_comparison: Optional[dict]   # {from_period, to_period, changes: [{metric, label, from, to, change, change_unit}]}
    trigger: dict                       # {rule_id, condition, thresholds, observed}
    evidence_references: list[dict]     # [{type, ref, description}]
    recommended_investigation: list[str]
    source_type: str                    # financial_trend | ratio_threshold | validation | benchmark | policy
    generated_by: str                   # e.g. "observation_engine/obs_v1"
    created_at: str
    # Analyst review and optional AI wording; never affect detection.
    review: dict = field(default_factory=dict)          # {note, updated_at, updated_by}
    ai_explanation: Optional[dict] = None               # {summary, detailed_explanation, recommended_investigation, model, generated_at}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
