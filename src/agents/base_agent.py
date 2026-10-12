"""
Base Agent Framework
Common interface and result contract for all pipeline agents.
"""

import time
from datetime import datetime
from typing import Any, Callable


class AgentResult:
    """Standardized result from an agent execution."""

    __slots__ = ("agent_name", "status", "data", "error",
                 "started_at", "completed_at", "duration_ms", "diagnostics")

    def __init__(self, agent_name: str, status: str, data: Any = None,
                 error: str = None, started_at: str = None,
                 completed_at: str = None, duration_ms: float = 0, diagnostics: dict | None = None):
        self.agent_name = agent_name
        self.status = status
        self.data = data
        self.error = error
        self.started_at = started_at
        self.completed_at = completed_at
        self.duration_ms = duration_ms
        # How the agent ran (see describe_output): execution_mode, llm_invoked, output_present, ...
        self.diagnostics = diagnostics or {"execution_mode": "skipped" if status == "failed" else "unknown"}

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "diagnostics": self.diagnostics,
        }


def _meaningful(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple, set)):
        return any(_meaningful(v) for v in (value.values() if isinstance(value, dict) else value))
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return True   # objects (dataclasses, engine results) count as content


def describe_output(data: Any) -> dict:
    """What an agent returned: whether there is content, and which keys are empty."""
    if isinstance(data, dict):
        empty = sorted(k for k, v in data.items() if not _meaningful(v))
        return {"output_present": any(_meaningful(v) for v in data.values()),
                "output_keys": sorted(data), "empty_output_keys": empty}
    return {"output_present": _meaningful(data), "output_keys": [], "empty_output_keys": []}


class BaseAgent:
    """All pipeline agents inherit from this.

    Contract:
      * ``requires`` — agents that must finish *successfully* first: their results
        (``context["results"]``) or their changes to ``company_data`` are needed.
        The orchestrator starts an agent only after these finish, and fails it
        if one of them produced no result, so a broken order fails loudly.
      * ``waits_for`` — agents to wait for whose results are optional: the agent
        starts after them and uses their result when present, but runs anyway if
        they failed (e.g. reuse a non-critical agent's output instead of
        recomputing it).
      * ``critical`` — when True, a failure stops the pipeline.
      * ``run(context)`` returns this agent's result payload, stored under
        ``context["results"][name]``.

    Agents without a dependency between them may run at the same time (see
    ``src/agents/pipeline.py``), so an agent must not write to ``company_data``
    keys that another independent agent reads.
    """

    name: str = "base"
    description: str = ""
    critical: bool = True
    uses_llm: bool = False   # True only for agents that may call an LLM
    requires: tuple[str, ...] = ()
    waits_for: tuple[str, ...] = ()

    def execute(self, context: dict) -> AgentResult:
        # An agent may record how it ran in self.diagnostics during run() (e.g. the
        # narrative counts LLM calls); everything else is derived from its output.
        self.diagnostics = {}
        start, clock = datetime.now(), time.perf_counter()
        try:
            data = self.run(context)
            status, error = "completed", None
        except Exception as e:
            data, status, error = None, "failed", str(e)
        elapsed_ms = (time.perf_counter() - clock) * 1000   # wall-clock datetime is too coarse for fast agents
        end = datetime.now()
        diagnostics = {**describe_output(data), "llm_invoked": False, "llm_calls": 0, **self.diagnostics}
        diagnostics.setdefault("execution_mode", "failed" if status == "failed" else
                               "deterministic" if diagnostics["output_present"] else "empty")
        return AgentResult(
            agent_name=self.name, status=status, data=data, error=error,
            started_at=start.isoformat(), completed_at=end.isoformat(),
            duration_ms=round(elapsed_ms, 3),
            diagnostics=diagnostics,
        )

    def run(self, context: dict) -> Any:
        raise NotImplementedError

    @staticmethod
    def emitter(context: dict) -> Callable[[str], None]:
        """Progress callback that forwards info messages to the pipeline listener."""
        on_progress = context.get("_on_progress")

        def emit(message: str) -> None:
            if on_progress:
                on_progress({"type": "info", "message": message})

        return emit

    def describe(self) -> dict:
        return {"name": self.name, "description": self.description,
                "critical": self.critical, "uses_llm": self.uses_llm, "requires": list(self.requires),
                "waits_for": list(self.waits_for)}
