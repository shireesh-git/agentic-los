"""
AgentGraph — run agents in parallel wherever their dependencies allow.

Every agent workflow in the platform (the CAM pipeline, LOS stage preparation,
document intake, reconciliation) is a graph of nodes. A node declares

  requires    nodes that must finish *successfully* first (their results are needed);
  waits_for   nodes to wait for whose results are optional;
  critical    whether its failure stops the graph.

A node starts as soon as its dependencies have finished, so independent nodes run
side by side on one bounded thread pool. A **fan-out** node expands at run time
into one child per item (per document, page, party, check, field domain …); the
children run in parallel and are joined, in item order, into the node's result.

Determinism: results are keyed by node name and fan-out children are joined in
item order, so a graph's output never depends on which branch finished first.

Failure isolation: a failed node is recorded and the graph carries on; only a
failed *critical* node stops it. Nodes that ``require`` a failed node fail with
"missing results" instead of running on partial input. A failed fan-out child
fails only that item.

Concurrency: ``max_workers`` bounds the pool (``settings.agentic.max_workers``).
LLM calls are bounded separately per provider (``max_parallel_llm``), so a wide
fan-out cannot flood a model endpoint.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from src.agents.base_agent import AgentResult, describe_output

log = logging.getLogger(__name__)

DEFAULT_MAX_WORKERS = 16


def default_max_workers() -> int:
    try:
        from src.core.config_manager import config
        return int(config.get("settings", "agentic", "max_workers", default=DEFAULT_MAX_WORKERS))
    except Exception:  # config unavailable (isolated use): the built-in default
        return DEFAULT_MAX_WORKERS


def timed(name: str, fn: Callable[[], Any]) -> AgentResult:
    """Run ``fn`` and wrap its outcome (data or error) and timing in an AgentResult."""
    start, clock = datetime.now(), time.perf_counter()
    try:
        data, status, error = fn(), "completed", None
    except Exception as e:  # recorded on the result; the graph decides what a failure means
        log.debug("node %s failed", name, exc_info=True)
        data, status, error = None, "failed", f"{type(e).__name__}: {e}" if not str(e) else str(e)
    return AgentResult(agent_name=name, status=status, data=data, error=error,
                       started_at=start.isoformat(), completed_at=datetime.now().isoformat(),
                       duration_ms=round((time.perf_counter() - clock) * 1000, 3),
                       diagnostics={**describe_output(data), "execution_mode": "failed" if error else "deterministic"})


@dataclass
class Node:
    """One unit of work in an AgentGraph.

    Exactly one of ``run`` / ``execute`` / ``fan_out`` + ``run_item`` is used:

      run(ctx) -> data                plain function; timed and wrapped by the graph
      execute(ctx) -> AgentResult     returns its own result (e.g. BaseAgent.execute)
      fan_out(ctx) -> [items]         expand into parallel children, each
      run_item(ctx, item) -> data       processed by run_item and joined by
      join(ctx, [(key, result)])        join (default: {key: data} of the completed items)
    """
    name: str
    run: Optional[Callable[[dict], Any]] = None
    execute: Optional[Callable[[dict], AgentResult]] = None
    fan_out: Optional[Callable[[dict], list]] = None
    run_item: Optional[Callable[[dict, Any], Any]] = None
    item_key: Callable[[Any], str] = str
    join: Optional[Callable[[dict, list[tuple[str, AgentResult]]], Any]] = None
    requires: tuple[str, ...] = ()
    waits_for: tuple[str, ...] = ()
    critical: bool = False
    lane: str = ""                      # display group for progress views
    description: str = ""

    def __post_init__(self):
        modes = sum(bool(x) for x in (self.run, self.execute, self.fan_out))
        if modes != 1:
            raise ValueError(f"node {self.name}: give exactly one of run, execute or fan_out")
        if self.fan_out and not self.run_item:
            raise ValueError(f"node {self.name}: a fan-out node needs run_item")


@dataclass
class GraphRun:
    """The outcome of one graph run: a result per node, in declaration order."""
    results: dict[str, AgentResult] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    max_concurrency: int = 0            # most tasks observed running at once

    def log(self) -> list[dict]:
        return [self.results[n].to_dict() for n in self.order if n in self.results]

    def data(self, name: str, default=None):
        r = self.results.get(name)
        return r.data if r is not None and r.status == "completed" else default


class GraphError(RuntimeError):
    pass


class AgentGraph:
    """Runs a set of nodes in dependency order, in parallel where possible.

    Hooks (all optional, called on the scheduling thread so they need no locking):

      on_start(node, step)              a node (or the first child of a fan-out) starts
      on_result(node, step, result)     a node finished, before its result is stored
      on_item(node, key, result, done, total)   a fan-out child finished
    """

    def __init__(self, nodes: list[Node], *, max_workers: int | None = None, ordered: bool = False,
                 name: str = "graph", on_start=None, on_result=None, on_item=None):
        names = [n.name for n in nodes]
        if len(names) != len(set(names)):
            raise GraphError(f"{name}: duplicate node names")
        self.nodes = list(nodes)
        self.name = name
        # ordered=True runs one task at a time in declaration order (the sequential mode).
        self.ordered = ordered
        self.max_workers = 1 if ordered else max(1, max_workers or default_max_workers())
        self.on_start, self.on_result, self.on_item = on_start, on_result, on_item

    # ── public ───────────────────────────────────────────────────────────────

    def describe(self) -> list[dict]:
        return [{"name": n.name, "lane": n.lane, "description": n.description, "requires": list(n.requires),
                 "waits_for": list(n.waits_for), "critical": n.critical, "fan_out": bool(n.fan_out)}
                for n in self.nodes]

    def run(self, context: dict) -> GraphRun:
        """Run the graph against ``context``. Completed results are stored in
        ``context["results"][node]``; a failed critical node raises after the
        tasks already running have finished and been recorded."""
        context.setdefault("results", {})
        run = GraphRun(order=[n.name for n in self.nodes])
        self.last_run = run                 # readable even when the run raises
        clock = time.perf_counter()
        try:
            self._schedule(context, run)
        finally:
            run.duration_ms = round((time.perf_counter() - clock) * 1000, 3)
        return run

    # ── scheduling ───────────────────────────────────────────────────────────

    def _schedule(self, context: dict, run: GraphRun) -> None:
        names = {n.name for n in self.nodes}
        step_of = {n.name: i for i, n in enumerate(self.nodes, start=1)}
        pending = list(self.nodes)
        finished: set[str] = set()
        running: dict[Future, tuple[Node, Optional[str]]] = {}      # future → (node, fan-out key | None)
        fan_state: dict[str, dict] = {}                              # fan-out node → items, results

        def ready(node: Node) -> bool:
            # A dependency outside this graph can never finish: let the node start so
            # the missing-requirements check reports it.
            return all(d in finished or d not in names for d in (*node.requires, *node.waits_for))

        def missing(node: Node) -> list[str]:
            return [d for d in node.requires if d not in context["results"]]

        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix=self.name) as pool:
            def submit(node: Node, key: Optional[str], fn: Callable[[], AgentResult]) -> None:
                running[pool.submit(fn)] = (node, key)
                run.max_concurrency = max(run.max_concurrency, len(running))

            def finish(node: Node, result: AgentResult) -> None:
                finished.add(node.name)
                self._record(node, step_of[node.name], result, context, run)

            def start(node: Node) -> None:
                gap = missing(node)
                if self.on_start:
                    self.on_start(node, step_of[node.name])
                if gap:
                    finish(node, AgentResult(
                        agent_name=node.name, status="failed",
                        error=f"Missing results from required agent(s): {', '.join(gap)}",
                        diagnostics={"execution_mode": "skipped", "llm_invoked": False, "llm_calls": 0,
                                     "output_present": False, "skip_reason": "missing requirements"}))
                    return
                if node.fan_out:
                    try:
                        items = list(node.fan_out(context) or [])
                    except Exception as e:
                        finish(node, AgentResult(agent_name=node.name, status="failed", error=f"fan-out failed: {e}",
                                                 diagnostics={"execution_mode": "failed", "fan_out": 0}))
                        return
                    keys = [str(node.item_key(it)) for it in items]
                    fan_state[node.name] = {"items": items, "keys": keys, "results": {},
                                            "clock": time.perf_counter(), "start": datetime.now()}
                    if not items:
                        finish(node, self._join(node, context, fan_state.pop(node.name)))
                        return
                    for item, key in zip(items, keys):
                        submit(node, key, lambda it=item, k=key: timed(
                            f"{node.name}[{k}]", lambda: node.run_item(context, it)))
                elif node.execute:
                    submit(node, None, lambda: node.execute(context))
                else:
                    submit(node, None, lambda: timed(node.name, lambda: node.run(context)))

            try:
                while pending or running:
                    for node in [n for n in pending if ready(n)]:
                        if self.ordered and running:
                            break
                        pending.remove(node)
                        start(node)
                        if self.ordered and running:
                            break
                    if not running:
                        if pending and not any(ready(n) for n in pending):
                            raise GraphError(f"{self.name}: circular requirements: "
                                             + ", ".join(n.name for n in pending))
                        continue
                    done, _ = wait(running, return_when=FIRST_COMPLETED)
                    # Record in a stable order when several finish together.
                    for future in sorted(done, key=lambda f: (step_of[running[f][0].name], running[f][1] or "")):
                        node, key = running.pop(future)
                        result = self._result_of(future, node, key)
                        if key is None:
                            finish(node, result)
                            continue
                        state = fan_state[node.name]
                        state["results"][key] = result
                        if self.on_item:
                            self.on_item(node, key, result, len(state["results"]), len(state["items"]))
                        if len(state["results"]) == len(state["items"]):
                            finish(node, self._join(node, context, fan_state.pop(node.name)))
            except BaseException:
                # Stop scheduling. Tasks already running cannot be interrupted: let them
                # finish and record them, so the log shows what happened.
                for future, (node, key) in list(running.items()):
                    result = self._result_of(future, node, key)
                    if key is None and node.name not in run.results:
                        run.results[node.name] = result
                raise

    @staticmethod
    def _result_of(future: Future, node: Node, key: Optional[str]) -> AgentResult:
        try:
            return future.result()
        except Exception as e:  # node functions are wrapped; this is defensive
            name = f"{node.name}[{key}]" if key is not None else node.name
            return AgentResult(agent_name=name, status="failed", error=str(e))

    @staticmethod
    def _join(node: Node, context: dict, state: dict) -> AgentResult:
        """Combine a fan-out node's children, in item order, into the node's result."""
        pairs = [(k, state["results"][k]) for k in state["keys"]]
        failed = [k for k, r in pairs if r.status != "completed"]
        diagnostics = {"fan_out": len(pairs), "failed": len(failed), "failed_keys": failed[:20],
                       "children_ms": round(sum(r.duration_ms or 0 for _, r in pairs), 3)}
        try:
            data = (node.join(context, pairs) if node.join
                    else {k: r.data for k, r in pairs if r.status == "completed"})
            status = "failed" if pairs and len(failed) == len(pairs) else "completed"
            error = "every item failed: " + "; ".join(f"{k}: {r.error}" for k, r in pairs[:3]) if status == "failed" else None
        except Exception as e:
            data, status, error = None, "failed", f"join failed: {e}"
        diagnostics.update(describe_output(data))
        diagnostics["execution_mode"] = "failed" if status == "failed" else "parallel_fan_out"
        elapsed = (time.perf_counter() - state["clock"]) * 1000
        return AgentResult(agent_name=node.name, status=status, data=data, error=error,
                           started_at=state["start"].isoformat(), completed_at=datetime.now().isoformat(),
                           duration_ms=round(elapsed, 3), diagnostics=diagnostics)

    def _record(self, node: Node, step: int, result: AgentResult, context: dict, run: GraphRun) -> None:
        run.results[node.name] = result
        if self.on_result:
            self.on_result(node, step, result)
        if result.status == "completed" and result.data:
            context["results"][node.name] = result.data
        elif result.status == "failed" and node.critical:
            raise RuntimeError(f"Critical agent '{node.name}' failed: {result.error}")
