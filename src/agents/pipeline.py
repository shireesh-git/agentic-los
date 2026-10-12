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
"""

import logging
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

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

    @staticmethod
    def _missing_requirements(agent: BaseAgent, results: dict) -> list[str]:
        return [name for name in agent.requires if name not in results]

    def execute_pipeline(self, company_data: dict, on_progress=None, stores=None) -> dict:
        context = {"company_data": company_data, "results": {}}
        # Agents running in parallel emit concurrently; serialize the listener.
        emit = self._serialized(on_progress)
        if emit:
            context["_on_progress"] = emit
        if stores:
            context["_stores"] = stores

        run = self._run_parallel if self.parallel else self._run_sequential
        entries: dict[int, dict] = {}
        try:
            run(context, emit, entries)
        finally:
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

    def _execute_one(self, step: int, agent: BaseAgent, context: dict, emit) -> AgentResult:
        total = len(self.agents)
        self._trace(f">>> Starting agent {step}/{total}: {agent.name}")
        if emit:
            emit({"type": "agent_start", "agent": agent.name, "description": agent.description,
                  "step": step, "total": total})

        missing = self._missing_requirements(agent, context["results"])
        if missing:
            return AgentResult(agent_name=agent.name, status="failed",
                               error=f"Missing results from required agent(s): {', '.join(missing)}",
                               diagnostics={"execution_mode": "skipped", "llm_invoked": False, "llm_calls": 0,
                                            "output_present": False, "skip_reason": "missing requirements"})
        return agent.execute(context)

    def _record(self, step: int, agent: BaseAgent, result: AgentResult, context: dict, emit,
                entries: dict[int, dict]) -> None:
        """Store an agent's outcome (on the orchestrator thread) and raise on a critical failure."""
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
                  "execution_mode": d.get("execution_mode"), "llm_invoked": d.get("llm_invoked", False)})

        if result.status == "completed" and result.data:
            context["results"][agent.name] = result.data
        elif result.status == "failed" and agent.critical:
            raise RuntimeError(f"Critical agent '{agent.name}' failed: {result.error}")

    # ── Schedulers ───────────────────────────────────────────────────────

    def _run_sequential(self, context: dict, emit, entries: dict[int, dict]) -> None:
        for step, agent in enumerate(self.agents, start=1):
            result = self._execute_one(step, agent, context, emit)
            self._record(step, agent, result, context, emit, entries)

    def _run_parallel(self, context: dict, emit, entries: dict[int, dict]) -> None:
        names = {agent.name for agent in self.agents}
        pending = list(enumerate(self.agents, start=1))
        finished: set[str] = set()

        def ready(agent: BaseAgent) -> bool:
            # A dependency that is not in this pipeline can never finish; let the
            # agent start so the missing-requirements check reports it.
            return all(dep in finished or dep not in names
                       for dep in (*agent.requires, *agent.waits_for))

        with ThreadPoolExecutor(max_workers=max(1, len(self.agents)),
                                thread_name_prefix="cam-agent") as pool:
            running = {}
            try:
                while pending or running:
                    for item in [item for item in pending if ready(item[1])]:
                        pending.remove(item)
                        step, agent = item
                        running[pool.submit(self._execute_one, step, agent, context, emit)] = item
                    if not running:
                        # Dependency cycle: nothing can start. Fail loudly rather than hang.
                        raise RuntimeError("Pipeline agents have circular requirements: "
                                           + ", ".join(agent.name for _, agent in pending))
                    done, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in sorted(done, key=lambda f: running[f][0]):
                        step, agent = running.pop(future)
                        finished.add(agent.name)
                        self._record(step, agent, future.result(), context, emit, entries)
            except BaseException:
                # Stop scheduling; agents already running finish (they cannot be
                # interrupted) and are recorded so the log shows what happened.
                for future, (step, agent) in list(running.items()):
                    try:
                        result = future.result()
                    except Exception as e:  # execute() catches agent errors; this is defensive
                        result = AgentResult(agent_name=agent.name, status="failed", error=str(e))
                    entries[step] = result.to_dict()
                raise

    def get_agent_list(self) -> list[dict]:
        return [agent.describe() for agent in self.agents]
