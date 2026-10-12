"""Agent diagnostics (development): what each pipeline agent does, and running agents on a cached case."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_container
from src.application.container import ServiceContainer

router = APIRouter(prefix="/api/diagnostics/agents", tags=["diagnostics"])


class AgentRunRequest(BaseModel):
    agent: str = "all"
    cases: list[str]
    stop_after: str | None = None
    narrative_mode: str = "plan"          # plan | template | llm | full
    sections: list[str] | None = None
    refresh_snapshot: bool = False
    include_output: bool = False


@router.get("")
async def list_agents():
    """The 7 agents with their contracts as derived from the code (purpose, processing, outputs, consumers)."""
    from src.devtools.agent_contracts import AGENT_ORDER, CONTRACTS, NARRATIVE_OWN_ANALYSIS, PROMPT_COMPUTE_REQUESTS
    return {"agents": [{"name": n, **CONTRACTS[n]} for n in AGENT_ORDER],
            "narrative_own_analysis": NARRATIVE_OWN_ANALYSIS, "prompt_compute_requests": PROMPT_COMPUTE_REQUESTS}


@router.post("/run")
async def run_agents(body: AgentRunRequest, svc: ServiceContainer = Depends(get_container)):
    """Run agent(s) for one or more cases from cached snapshots and return the evaluation reports."""
    from src.devtools import agent_harness as h

    def work():
        results, reports = [], []
        for case in body.cases:
            result = h.run_case(case, agents=body.agent, stop_after=body.stop_after,
                                narrative_mode=body.narrative_mode, sections=body.sections,
                                refresh_snapshot=body.refresh_snapshot, loader=svc.companies.get)
            path = h.save_run(result)
            reps = result["reports"] if body.include_output else [h.strip_heavy(r) for r in result["reports"]]
            reports += result["reports"]
            results.append({**{k: v for k, v in result.items() if k != "reports"}, "reports": reps,
                            "saved_to": str(path)})
        return {"results": results, "comparison": h.comparison_rows(reports)}

    return await asyncio.to_thread(work)
