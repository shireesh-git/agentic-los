"""
Tools: the only way an agent touches data or the engines.

A tool is a plain Python function with a JSON-schema for its arguments and a
permission:

  read       reads the record, documents or engine output — no side effects
  propose    writes a *proposal* (a field value, conflict or deviation) for a person to verify
  external   calls an outside source (bureau, registry, screening) — may cost or be slow

An agent is given the permissions it may use; anything else is refused. Every
call is validated against the tool's schema and audited (who, what, outcome,
duration), and a failing tool returns an error result instead of raising, so the
agent can observe the failure and adapt.

Agents propose; people decide. No tool submits, approves or changes the workflow.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from src.agentic.schema import validate

log = logging.getLogger(__name__)

PERMISSIONS = ("read", "propose", "external")


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    permission: str = "read"

    def spec(self) -> dict:
        """The tool as an agent sees it."""
        return {"name": self.name, "description": self.description, "permission": self.permission,
                "parameters": self.parameters}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._lock = threading.Lock()

    def register(self, tool: Tool, replace: bool = False) -> Tool:
        if tool.permission not in PERMISSIONS:
            raise ToolError(f"tool {tool.name}: unknown permission {tool.permission}")
        with self._lock:
            if tool.name in self._tools and not replace:
                raise ToolError(f"tool {tool.name} is already registered")
            self._tools[tool.name] = tool
        return tool

    def tool(self, name: str, description: str, parameters: dict | None = None, permission: str = "read",
             replace: bool = False):
        """Decorator: register a function as a tool."""
        def wrap(fn):
            self.register(Tool(name=name, description=description, fn=fn,
                               parameters=parameters or {"type": "object", "properties": {}},
                               permission=permission), replace=replace)
            return fn
        return wrap

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if not tool:
            raise ToolError(f"unknown tool {name}")
        return tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self, names: Iterable[str] | None = None, permissions: Iterable[str] = PERMISSIONS) -> list[dict]:
        allowed = set(permissions)
        chosen = sorted(names) if names is not None else self.names()
        return [self._tools[n].spec() for n in chosen if n in self._tools and self._tools[n].permission in allowed]

    def call(self, name: str, args: dict | None = None, *, caller: str = "system",
             permissions: Iterable[str] = ("read",), audit: list | None = None) -> dict:
        """Call a tool. Returns ``{"tool", "ok", "result" | "error", "duration_ms", ...}``;
        never raises for a tool failure (the caller observes it)."""
        args = dict(args or {})
        record = {"tool": name, "caller": caller, "args": _summarise(args),
                  "at": datetime.now().isoformat(timespec="seconds")}
        clock = time.perf_counter()
        try:
            tool = self.get(name)
            record["permission"] = tool.permission
            if tool.permission not in set(permissions):
                raise ToolError(f"{caller} may not use {tool.permission} tool {name}")
            problems = validate(args, tool.parameters)
            if problems:
                raise ToolError("invalid arguments: " + "; ".join(problems[:5]))
            record.update(ok=True, result=tool.fn(**args))
        except Exception as e:
            record.update(ok=False, error=str(e))
            log.info("tool %s (%s) failed: %s", name, caller, e)
        record["duration_ms"] = round((time.perf_counter() - clock) * 1000, 3)
        if audit is not None:
            audit.append({k: v for k, v in record.items() if k != "result"} | {"result": _summarise(record.get("result"))})
        return record


def _summarise(value: Any, limit: int = 300) -> Any:
    """A short, JSON-safe rendering of arguments/results for the audit trail."""
    text = repr(value)
    return value if len(text) <= limit and isinstance(value, (str, int, float, bool, type(None), dict, list)) \
        else text[:limit] + ("…" if len(text) > limit else "")


# The platform-wide registry; modules register their tools on import.
registry = ToolRegistry()
