"""
LLMAgent — a bounded reason → act → observe loop.

Each turn the model returns one JSON object (validated, provider-agnostic, so it
works on any configured model, including OpenAI-compatible endpoints without
native tool calling):

    {"thought": "...", "action": "tools", "calls": [{"tool": "...", "args": {...}}, ...]}
    {"thought": "...", "action": "final", "final": {...matches the agent's output schema...}}

Several tool calls in one turn run **in parallel**. Observations are fed back
and the loop continues until the agent answers or a budget is hit (steps, tool
calls, wall-clock). Every model turn and tool call is kept in the run's trace.

When no model is available (mock provider) the run ends with status
``unavailable`` and the caller uses its deterministic fallback.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from src.agentic.schema import validate
from src.agentic.tools import ToolRegistry, registry as default_registry
from src.core.llm_provider import LLMUnavailableError, StructuredOutputError

log = logging.getLogger(__name__)


@dataclass
class AgentSpec:
    name: str
    instructions: str                       # the agent's role, rules and what a good answer is
    output_schema: dict                     # schema of the final answer
    tools: list[str] = field(default_factory=list)
    permissions: tuple[str, ...] = ("read",)
    max_steps: int = 6
    max_tool_calls: int = 20
    max_seconds: float = 300.0
    max_tokens: int = 2000


@dataclass
class AgentRun:
    agent: str
    status: str = "running"                 # completed | failed | unavailable
    output: Any = None
    error: str | None = None
    steps: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {"agent": self.agent, "status": self.status, "output": self.output, "error": self.error,
                "steps": self.steps, "tool_calls": self.tool_calls, "llm_calls": self.llm_calls,
                "duration_ms": self.duration_ms}


def _turn_schema(spec: AgentSpec) -> dict:
    return {
        "type": "object",
        "required": ["action"],
        "properties": {
            "thought": {"type": "string"},
            "action": {"type": "string", "enum": ["tools", "final"]},
            "calls": {"type": "array", "maxItems": 8, "items": {
                "type": "object", "required": ["tool"],
                "properties": {"tool": {"type": "string", "enum": spec.tools or ["none"]},
                               "args": {"type": "object"}}}},
            "final": spec.output_schema,
        },
    }


def _clip(value: Any, limit: int = 4000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"… (truncated, {len(text)} chars)"


class LLMAgent:
    def __init__(self, spec: AgentSpec, llm, tools: ToolRegistry | None = None):
        self.spec, self.llm = spec, llm
        self.tools = tools or default_registry

    def _system(self) -> str:
        specs = self.tools.specs(self.spec.tools, self.spec.permissions)
        return (f"{self.spec.instructions.strip()}\n\n"
                "You work step by step. Each reply is ONE JSON object:\n"
                '- to use tools: {"thought": "...", "action": "tools", "calls": [{"tool": name, "args": {...}}]} '
                "(independent calls in one reply run in parallel);\n"
                '- to answer: {"thought": "...", "action": "final", "final": <answer matching the output schema>}.\n'
                "Use only facts from tool results or the task. Never invent figures.\n\n"
                f"Tools:\n{json.dumps(specs, ensure_ascii=False)}\n\n"
                f"Output schema for 'final':\n{json.dumps(self.spec.output_schema, ensure_ascii=False)}")

    def run(self, task: str, context: dict | None = None) -> AgentRun:
        spec, run = self.spec, AgentRun(agent=self.spec.name)
        clock = time.perf_counter()
        transcript: list[str] = [f"Task:\n{task}"]
        if context:
            transcript.append(f"Context (JSON):\n{_clip(context, 12000)}")
        system, schema = self._system(), _turn_schema(spec)
        try:
            for step in range(1, spec.max_steps + 1):
                if time.perf_counter() - clock > spec.max_seconds:
                    raise TimeoutError(f"time budget of {spec.max_seconds}s exhausted")
                last = step == spec.max_steps
                prompt = "\n\n".join(transcript) + (
                    "\n\nThis is your last step: answer now with action 'final'." if last else "")
                turn = self.llm.generate_structured(prompt, schema, system_prompt=system, max_tokens=spec.max_tokens)
                run.llm_calls += 1
                entry = {"step": step, "thought": turn.get("thought"), "action": turn["action"]}
                if turn["action"] == "final":
                    problems = validate(turn.get("final"), spec.output_schema)
                    if not problems:
                        run.steps.append(entry)
                        run.status, run.output = "completed", turn["final"]
                        return run
                    entry["rejected"] = problems[:5]
                    run.steps.append(entry)
                    transcript.append(f"Your answer was rejected: {'; '.join(problems[:5])}. Correct it.")
                    continue
                calls = (turn.get("calls") or [])[:8]
                if not calls:
                    entry["note"] = "no calls given"
                    run.steps.append(entry)
                    transcript.append("You chose 'tools' but gave no calls. Call a tool or answer.")
                    continue
                if len(run.tool_calls) + len(calls) > spec.max_tool_calls:
                    raise RuntimeError(f"tool-call budget of {spec.max_tool_calls} exhausted")
                results = self._call_parallel(calls)
                run.tool_calls.extend(results["audit"])
                entry["calls"] = [c.get("tool") for c in calls]
                run.steps.append(entry)
                transcript.append(f"Step {step} tool results:\n{_clip(results['observations'])}")
            raise RuntimeError(f"no final answer within {spec.max_steps} steps")
        except LLMUnavailableError as e:
            run.status, run.error = "unavailable", str(e)
        except (StructuredOutputError, RuntimeError, TimeoutError) as e:
            run.status, run.error = "failed", str(e)
            log.info("agent %s failed: %s", spec.name, e)
        finally:
            run.duration_ms = round((time.perf_counter() - clock) * 1000, 3)
        return run

    def _call_parallel(self, calls: list[dict]) -> dict:
        audit: list[dict] = []

        def one(call):
            return self.tools.call(call.get("tool", ""), call.get("args") or {}, caller=self.spec.name,
                                   permissions=self.spec.permissions, audit=audit)

        with ThreadPoolExecutor(max_workers=max(1, len(calls)), thread_name_prefix=f"{self.spec.name}-tool") as pool:
            records = list(pool.map(one, calls))           # map keeps call order
        observations = [{"tool": r["tool"], "ok": r["ok"], **({"result": r["result"]} if r["ok"] else {"error": r["error"]})}
                        for r in records]
        return {"observations": observations, "audit": audit}
