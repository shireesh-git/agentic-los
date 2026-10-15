"""
Pipeline orchestrator: runs the agents, records a log entry per agent, streams
progress events, and stops on a critical failure.

Agents declare what they depend on in ``requires`` (must succeed first) and
``waits_for`` (wait, but the result is optional). In parallel mode (the default,
``settings.pipeline.parallel_agents``) an agent starts as soon as those have
finished, so independent agents run side by side:

    data_ingestion ─┬─ financial_analysis ── benchmark ─┐
                    └─ validation ──────────────────────┴─ policy ─┐
    pep_screening ─────────────────────────────────────────────────┴─ narrative
                                              (narrative waits_for pep_screening)

In sequential mode they run one at a time in list order. Either way the
pipeline log is kept in list order, so its shape does not depend on timing.

Scheduling is done by the platform's AgentGraph (src/agentic/graph.py), the same
engine every other agent workflow runs on.
"""

import logging
import threading

from src.agentic.graph import AgentGraph, Node
from src.agents.analysis_agents import BenchmarkAgent, FinancialAnalysisAgent, PolicyAgent, ValidationAgent
from src.agents.base_agent import AgentResult, BaseAgent
from src.agents.ingestion_agent import DataIngestionAgent
from src.agents.narrative_agent import NarrativeAgent
from src.agents.screening_agent import PEPScreeningAgent

log = logging.getLogger(__name__)


def default_agents(llm_provider=None, checkpoint_factory=None) -> list[BaseAgent]:
    return [
        DataIngestionAgent(),
        PEPScreeningAgent(),
        FinancialAnalysisAgent(),
        ValidationAgent(),
        BenchmarkAgent(),
        PolicyAgent(),
        NarrativeAgent(llm_provider=llm_provider, checkpoint_factory=checkpoint_factory),
    ]


def _parallel_from_config() -> bool:
    from src.core.config_manager import config
    return bool(config.get("settings", "pipeline", "parallel_agents", default=True))


class SuperAgent:
    """Orchestrates the full CAM pipeline by delegating to sub-agents."""

    def __init__(self, llm_provider=None, agents: list[BaseAgent] | None = None, checkpoint_factory=None,
                 parallel: bool | None = None):
        self.llm_provider = llm_provider
        self.agents: list[BaseAgent] = (agents if agents is not None
                                        else default_agents(llm_provider, checkpoint_factory))
        self.parallel = _parallel_from_config() if parallel is None else parallel
        self.pipeline_log: list[dict] = []

    @staticmethod
    def _trace(message: str) -> None:
        log.info("[PIPELINE] %s", message)

    def graph(self, emit=None, entries: dict[int, dict] | None = None) -> AgentGraph:
        """The pipeline as an AgentGraph: one node per agent, with the agent's own
        dependencies. ``parallel=False`` runs it one agent at a time in list order."""
        entries = {} if entries is None else entries
        by_name = {agent.name: agent for agent in self.agents}

        def on_start(node: Node, step: int) -> None:
            agent = by_name[node.name]
            self._trace(f">>> Starting agent {step}/{len(self.agents)}: {agent.name}")
            if emit:
                emit({"type": "agent_start", "agent": agent.name, "description": agent.description,
                      "step": step, "total": len(self.agents), "lane": node.lane})

        def on_result(node: Node, step: int, result: AgentResult) -> None:
            self._record(step, by_name[node.name], result, emit, entries)

        nodes = [Node(name=agent.name, execute=agent.execute, requires=tuple(agent.requires),
                      waits_for=tuple(agent.waits_for), critical=agent.critical,
                      lane="llm" if agent.uses_llm else "deterministic", description=agent.description)
                 for agent in self.agents]
        return AgentGraph(nodes, max_workers=max(1, len(self.agents)), ordered=not self.parallel,
                          name="cam-agent", on_start=on_start, on_result=on_result)

    def execute_pipeline(self, company_data: dict, on_progress=None, stores=None) -> dict:
        context = {"company_data": company_data, "results": {}}
        # Agents running in parallel emit concurrently; serialize the listener.
        emit = self._serialized(on_progress)
        if emit:
            context["_on_progress"] = emit
        if stores:
            context["_stores"] = stores

        entries: dict[int, dict] = {}
        graph = self.graph(emit, entries)
        try:
            graph.run(context)
        finally:
            # Agents still running when a critical failure stopped the run are logged too.
            for step, agent in enumerate(self.agents, start=1):
                result = getattr(graph, "last_run", None) and graph.last_run.results.get(agent.name)
                if result is not None and step not in entries:
                    entries[step] = result.to_dict()
            self.pipeline_log = [entries[i] for i in sorted(entries)]
        return context

    @staticmethod
    def _serialized(on_progress):
        if not on_progress:
            return None
        lock = threading.Lock()

        def emit(event: dict) -> None:
            with lock:
                on_progress(event)

        return emit

    # ── One agent ────────────────────────────────────────────────────────

    def _record(self, step: int, agent: BaseAgent, result: AgentResult, emit, entries: dict[int, dict]) -> None:
        """Log and announce an agent's outcome (on the scheduling thread). The graph then
        stores the result and stops the pipeline on a critical failure."""
        self._trace(f"<<< Agent {agent.name}: {result.status} ({result.duration_ms}ms)")
        d = result.diagnostics or {}
        # One line per agent that tells a fast deterministic agent from a skipped or empty one.
        log.info("[AGENT] %s status=%s execution_mode=%s llm_invoked=%s llm_calls=%s output_present=%s "
                 "duration_ms=%s%s", agent.name, result.status, d.get("execution_mode"),
                 str(d.get("llm_invoked", False)).lower(), d.get("llm_calls", 0),
                 str(d.get("output_present", False)).lower(), result.duration_ms,
                 f" empty_outputs={','.join(d['empty_output_keys'])}" if d.get("empty_output_keys") else "")
        entries[step] = result.to_dict()
        if emit:
            # step = position in the pipeline; completed = how many agents have finished,
            # which is what a progress bar should use when agents finish out of order.
            emit({"type": "agent_complete", "agent": agent.name, "status": result.status,
                  "duration_ms": result.duration_ms, "error": result.error,
                  "step": step, "total": len(self.agents), "completed": len(entries),
                  "execution_mode": d.get("execution_mode"), "llm_invoked": d.get("llm_invoked", False),
                  "lane": "llm" if agent.uses_llm else "deterministic"})

    def get_agent_list(self) -> list[dict]:
        return [agent.describe() for agent in self.agents]
