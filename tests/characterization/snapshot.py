"""
Characterization snapshots: a date-free summary of what the pipeline produces
for each seeded company. Used to prove that refactoring does not change
behaviour; intentional behaviour changes regenerate the golden file.

Regenerate:  python -m tests.characterization.snapshot --write
"""

import copy
import json
import re
import sys
from pathlib import Path

GOLDEN_PATH = Path(__file__).with_name("golden_pipeline.json")


def _value(obj):
    return getattr(obj, "value", obj)


def summarize_pipeline(context: dict, pipeline_log: list[dict]) -> dict:
    results = context["results"]
    policy = results.get("policy", {})
    rec = policy.get("recommendation")
    score = policy.get("risk_score")
    narrative = results.get("narrative", {})
    fact_pack = narrative.get("fact_pack", {})
    fp_rec = (fact_pack.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    cam_text = narrative.get("cam_text", "")

    return {
        "agents": {entry["agent_name"]: entry["status"] for entry in pipeline_log},
        "recommendation": _value(rec.recommendation) if rec else None,
        "risk_grade": score.risk_grade if score else None,
        "composite_score": score.composite_score if score else None,
        "component_scores": [score.financial_score, score.conduct_score,
                             score.governance_score, score.market_score] if score else None,
        "conditions": list(rec.conditions) if rec else None,
        "tier1": sorted(f"{d.rule_code}:{d.result}" for d in policy.get("tier1_decisions", [])),
        "exceptions": sorted(e.exception_code for e in results.get("validation", {}).get("exceptions", [])),
        "fact_pack_keys": sorted(fact_pack.keys()),
        "fact_pack_recommendation": _value(fp_rec.get("recommendation")),
        "fact_pack_risk_grade": fp_rec.get("risk_grade"),
        "narrative_mode": narrative.get("narrative_mode"),
        "cam_headings": re.findall(r"^#{1,2} .+$", cam_text, flags=re.MULTILINE),
    }


def run_all_seeded() -> dict:
    from src.agents.pipeline import SuperAgent
    from src.core.config_manager import config
    from src.core.llm_provider import create_llm_provider
    from src.data.company_catalog import seed_company_store

    store = seed_company_store()
    snapshots = {}
    for entity_id in sorted(store):
        agent = SuperAgent(llm_provider=create_llm_provider(config.get_active_llm_provider()))
        context = agent.execute_pipeline(copy.deepcopy(store[entity_id]),
                                         stores={"extraction": {}, "etb": {}})
        snapshots[entity_id] = summarize_pipeline(context, agent.pipeline_log)
    return snapshots


if __name__ == "__main__":
    import tests.conftest  # noqa: F401  (isolates runtime paths, forces mock LLM)

    data = run_all_seeded()
    if "--write" in sys.argv:
        GOLDEN_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
                               encoding="utf-8")
        print(f"Wrote {GOLDEN_PATH}")
    else:
        print(json.dumps(data, indent=2, default=str))
