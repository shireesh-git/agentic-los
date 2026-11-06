"""The agentic framework: parallel graph, fan-out, LLM concurrency cap, structured
output, tools, the agent loop and the critic."""

import threading
import time

import pytest

from src.agentic.graph import AgentGraph, GraphError, Node
from src.agentic.schema import parse_json_object, validate
from src.core.llm_provider import (BaseLLMProvider, LLMUnavailableError, MockLLMProvider, StructuredOutputError,
                                   _provider_semaphore)


def _sleep(value, seconds=0.2):
    def run(ctx):
        time.sleep(seconds)
        return value
    return run


# ── AgentGraph ───────────────────────────────────────────────────────────────

def test_independent_nodes_run_in_parallel():
    graph = AgentGraph([Node("a", run=_sleep("A")), Node("b", run=_sleep("B")), Node("c", run=_sleep("C"))])
    t = time.perf_counter()
    run = graph.run({})
    assert time.perf_counter() - t < 0.45            # sequential would be ≥ 0.6s
    assert run.max_concurrency == 3
    assert [run.data(n) for n in "abc"] == ["A", "B", "C"]


def test_dependencies_order_and_results_flow():
    seen = []

    def b(ctx):
        seen.append(ctx["results"]["a"])
        return ctx["results"]["a"] + 1

    run = AgentGraph([Node("b", run=b, requires=("a",)), Node("a", run=lambda ctx: 1)]).run({})
    assert seen == [1] and run.data("b") == 2
    assert [e["agent_name"] for e in run.log()] == ["b", "a"]      # log keeps declaration order


def test_failed_requirement_skips_dependent_but_not_independent():
    def boom(ctx):
        raise ValueError("no data")

    run = AgentGraph([Node("a", run=boom), Node("b", run=lambda c: 1, requires=("a",)),
                      Node("c", run=lambda c: 2, waits_for=("a",))]).run({})
    assert run.results["a"].status == "failed" and "no data" in run.results["a"].error
    assert run.results["b"].status == "failed" and "Missing results" in run.results["b"].error
    assert run.data("c") == 2                         # waits_for: runs without a's result


def test_critical_failure_stops_the_graph():
    def boom(ctx):
        raise ValueError("bad")

    graph = AgentGraph([Node("a", run=boom, critical=True), Node("b", run=lambda c: 1, requires=("a",))])
    with pytest.raises(RuntimeError, match="Critical agent 'a' failed"):
        graph.run({})
    assert "b" not in graph.last_run.results


def test_fan_out_runs_items_in_parallel_and_joins_in_item_order():
    def work(ctx, item):
        time.sleep(0.3 - item * 0.05)                 # later items finish first
        if item == 3:
            raise ValueError("unreadable page")
        return item * 10

    node = Node("pages", fan_out=lambda ctx: [1, 2, 3, 4], run_item=work, item_key=lambda i: f"p{i}")
    items = []
    t = time.perf_counter()
    run = AgentGraph([node], on_item=lambda n, k, r, done, total: items.append((k, done, total))).run({})
    assert time.perf_counter() - t < 0.5              # sequential would be ≈ 0.9s
    res = run.results["pages"]
    assert res.status == "completed"
    assert list(res.data) == ["p1", "p2", "p4"] and res.data["p4"] == 40      # item order, failed item dropped
    assert res.diagnostics["failed_keys"] == ["p3"] and res.diagnostics["fan_out"] == 4
    assert len(items) == 4 and items[-1][1:] == (4, 4)


def test_fan_out_with_custom_join_and_empty_items():
    graph = AgentGraph([
        Node("docs", fan_out=lambda ctx: ["x", "y"], run_item=lambda ctx, d: d.upper(),
             join=lambda ctx, pairs: "".join(r.data for _, r in pairs)),
        Node("none", fan_out=lambda ctx: [], run_item=lambda ctx, d: d),
        Node("after", run=lambda ctx: ctx["results"]["docs"] + "!", requires=("docs",)),
    ])
    run = graph.run({})
    assert run.data("docs") == "XY" and run.data("after") == "XY!"
    assert run.results["none"].status == "completed"


def test_ordered_mode_runs_one_at_a_time():
    active, peak = [0], [0]
    lock = threading.Lock()

    def work(ctx):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return 1

    AgentGraph([Node(n, run=work) for n in "abc"], ordered=True).run({})
    assert peak[0] == 1


def test_cycle_is_reported():
    with pytest.raises(GraphError, match="circular"):
        AgentGraph([Node("a", run=lambda c: 1, requires=("b",)), Node("b", run=lambda c: 1, requires=("a",))]).run({})


def test_node_needs_exactly_one_mode():
    with pytest.raises(ValueError):
        Node("x")
    with pytest.raises(ValueError):
        Node("x", fan_out=lambda c: [])


# ── Schema & structured output ───────────────────────────────────────────────

SCHEMA = {"type": "object", "required": ["value", "confidence"], "additionalProperties": False,
          "properties": {"value": {"type": "number"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                         "tags": {"type": "array", "items": {"type": "string"}}}}


def test_validate_reports_problems():
    assert validate({"value": 1.5, "confidence": 0.9, "tags": ["a"]}, SCHEMA) == []
    errors = validate({"value": "x", "confidence": 2, "extra": 1, "tags": [3]}, SCHEMA)
    assert any("value" in e for e in errors) and any("maximum" in e for e in errors)
    assert any("unexpected property 'extra'" in e for e in errors) and any("tags[0]" in e for e in errors)


def test_parse_json_object_tolerates_fences_and_thinking():
    assert parse_json_object('<think>hmm</think>```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json_object("no json here")


class ScriptedLLM(BaseLLMProvider):
    """Replies with the given texts in turn; records prompts and concurrency."""
    name = "scripted"
    supports_vision = True

    def __init__(self, replies, delay=0.0):
        self.replies, self.delay, self.prompts = list(replies), delay, []
        self.in_flight = self.peak = 0
        self._lock = threading.Lock()

    def generate(self, prompt, system_prompt="", temperature=None, max_tokens=None, images=None):
        with self._lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            self.prompts.append(prompt)
            reply = self.replies.pop(0) if self.replies else '{"action": "final", "final": {}}'
        time.sleep(self.delay)
        with self._lock:
            self.in_flight -= 1
        return reply

    def test_connection(self):
        return {"status": "ok"}


def test_generate_structured_retries_with_the_errors():
    llm = ScriptedLLM(['{"value": "high"}', '{"value": 4.2, "confidence": 0.8}'])
    assert llm.generate_structured("extract", SCHEMA) == {"value": 4.2, "confidence": 0.8}
    assert "previous reply was invalid" in llm.prompts[1]


def test_generate_structured_gives_up():
    with pytest.raises(StructuredOutputError):
        ScriptedLLM(["nope", "still nope"]).generate_structured("x", SCHEMA)


def test_mock_provider_has_no_structured_output():
    with pytest.raises(LLMUnavailableError):
        MockLLMProvider().generate_structured("x", SCHEMA)


def test_max_parallel_llm_caps_calls_in_flight():
    llm = ScriptedLLM(["ok"] * 8, delay=0.1)
    llm._llm_semaphore = _provider_semaphore({"type": "scripted-test", "max_parallel_llm": 2})
    graph = AgentGraph([Node("calls", fan_out=lambda c: list(range(8)),
                             run_item=lambda c, i: llm.generate("p"))], max_workers=8)
    run = graph.run({})
    assert run.max_concurrency == 8                    # the graph ran all 8 branches at once …
    assert llm.peak == 2                               # … but only 2 model calls were in flight
    clone = llm.with_model("other")
    assert clone._llm_semaphore is llm._llm_semaphore  # a routed model shares the provider's cap
