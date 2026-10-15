"""
The population graph: resolvers run in parallel, the critic checks their proposals
(fanned out per domain), and the result is one ordered list of proposals for the
single writer to merge.

    resolver A ─┐
    resolver B ─┼─► critic (fan-out per domain) ─► proposals
    resolver … ─┘

Sprint 2 has one resolver (the credit case via the Risk Maker view); document intake,
external sources and the per-domain reconciliation agents join the same graph later.
When two resolvers propose the same field, the one listed first in the registry wins
unless it has no value.
"""

from __future__ import annotations

from typing import Callable

from src.agentic.critic import CriticAgent
from src.agentic.graph import AgentGraph, Node
from src.los.fields.model import available
from src.los.fields.registry import FieldRegistry

Resolver = Callable[[dict], list]


def run_population(resolvers: dict[str, Resolver], registry: FieldRegistry, context: dict | None = None,
                   critic: CriticAgent | None = None) -> dict:
    """Run ``resolvers`` ({name: fn(ctx) -> proposals}) in parallel, critic-check the proposals,
    and return ``{"proposals": [...], "log": [...], "duration_ms", "max_concurrency"}``."""
    critic = critic or CriticAgent()
    names = list(resolvers)

    def combined(ctx: dict) -> list[dict]:
        chosen: dict[str, dict] = {}
        for name in names:                                  # registry order decides precedence
            for p in ctx["results"].get(name) or []:
                current = chosen.get(p["field_id"])
                if current is None or (not available(current.get("value"), current.get("provenance"))
                                       and available(p.get("value"), p.get("provenance"))):
                    chosen[p["field_id"]] = p
        return list(chosen.values())

    def domains(ctx: dict) -> list[str]:
        ctx["_combined"] = combined(ctx)
        return sorted({p["domain"] for p in ctx["_combined"]})

    def check_domain(ctx: dict, domain: str) -> list[dict]:
        batch = [dict(p) for p in ctx["_combined"] if p["domain"] == domain]
        to_check = [p for p in batch if available(p.get("value"), p.get("provenance"))]
        for p, verdict in zip(to_check, critic.review_proposals(to_check)):
            p["issues"] = list(p.get("issues") or []) + verdict.issues     # keep the resolver's own flags
        return batch

    def join(ctx: dict, pairs) -> list[dict]:
        return [p for _, r in pairs if r.status == "completed" for p in r.data]

    nodes = [Node(name, run=fn, lane="resolver", description=f"resolver: {name}") for name, fn in resolvers.items()]
    nodes.append(Node("critic", fan_out=domains, run_item=check_domain, join=join, waits_for=tuple(names),
                      lane="critic", description="critic: evidence and figures, per domain"))
    graph = AgentGraph(nodes, name="field-population")
    ctx = dict(context or {})
    run = graph.run(ctx)
    return {"proposals": run.data("critic", []) or [], "log": run.log(), "duration_ms": run.duration_ms,
            "max_concurrency": run.max_concurrency,
            "failed": [n for n, r in run.results.items() if r.status != "completed"]}
