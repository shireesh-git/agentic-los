"""
On-demand LLM explanation of the repayment assessment.

The repayment analysis (src/engines/repayment_analysis.py) has already graded
capacity and risk and listed the factors. The LLM only explains that
assessment in credit language; it must not change the grades or calculate
anything, and any figure not in the assessment rejects the response.
"""

from __future__ import annotations

import json
from datetime import datetime

from src.services.observation_narrator import _parse_json_object, unsupported_figures

PROMPT_VERSION = "repayment_explain_v1"

SYSTEM_PROMPT = """You are a senior corporate credit analyst at an Indian bank writing the cash-flow and repayment
section of a credit note. You are given a repayment assessment that the bank's rules engine has ALREADY made:
repayment capacity, repayment risk, primary and secondary repayment sources, key metrics by year, positive
factors and concerns.

Rules:
- Explain the assessment; do NOT change or second-guess the capacity or risk grades.
- Do NOT calculate, derive, estimate or round any number; quote only figures that appear in the facts exactly as given.
- Do NOT forecast future years and do NOT recommend approval or decline.
- Formal, concise credit language (Indian banking usage, amounts in Rs Crore).

Return ONLY a JSON object, no markdown fences:
{"narrative": "<one paragraph, 5-7 sentences: what the cash flow shows, how it changed in the latest year, and what that means for repayment>",
 "primary_source": "<1-2 sentences on the primary repayment source>",
 "secondary_source": "<1-2 sentences on the secondary repayment source>"}"""


def _facts(assessment: dict) -> dict:
    return {
        "period": assessment.get("period"), "prior_period": assessment.get("prior_period"),
        "repayment_capacity": assessment.get("repayment_capacity"),
        "capacity_by_period": assessment.get("capacity_by_period"),
        "repayment_risk": assessment.get("repayment_risk"),
        "engine_summary": assessment.get("summary"),
        "primary_repayment_source": assessment.get("primary_repayment_source"),
        "secondary_repayment_source": assessment.get("secondary_repayment_source"),
        "key_metrics": [{"label": m["label"], "by_period": m["by_period"], "grade": m.get("grade")}
                        for m in assessment.get("key_metrics") or []],
        "positive_factors": assessment.get("positive_factors"),
        "concerns": [{"concern": c["concern"], "evidence": c["evidence"]} for c in assessment.get("concerns") or []],
    }


def explain_repayment(assessment: dict, llm_provider, company_name: str, max_tokens: int = 1200) -> dict:
    """LLM explanation of the assessment. Raises ValueError when the response is unusable."""
    facts_json = json.dumps(_facts(assessment), ensure_ascii=False, default=str)
    prompt = f"Borrower: {company_name}\n\nRepayment assessment (JSON):\n{facts_json}\n\nWrite the JSON object."
    data = _parse_json_object(llm_provider.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT,
                                                    temperature=0.2, max_tokens=max_tokens))
    parts = {k: str(data.get(k) or "").strip() for k in ("narrative", "primary_source", "secondary_source")}
    if not parts["narrative"]:
        raise ValueError("model response is missing the narrative")
    unsupported = unsupported_figures("\n".join(parts.values()), facts_json)
    if unsupported:
        raise ValueError(f"response quoted figures not in the assessment: {', '.join(unsupported[:5])}")
    return {**parts, "model": getattr(llm_provider, "model", None) or getattr(llm_provider, "name", "llm"),
            "prompt_version": PROMPT_VERSION, "generated_at": datetime.now().isoformat(timespec="seconds")}
