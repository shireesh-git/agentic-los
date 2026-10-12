"""
On-demand LLM wording for credit challenges.

The Credit Challenge Agent has already decided the challenge, its figures,
severity and the response required. The LLM only rewrites the challenge and
its rationale in credit-committee language. It must not approve, decline or
recommend, and any figure not in the challenge's facts rejects the response.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from src.services.observation_narrator import _parse_json_object, unsupported_figures

log = logging.getLogger(__name__)

PROMPT_VERSION = "chl_wording_v1"

SYSTEM_PROMPT = """You are a sceptical senior credit officer on an Indian bank's credit committee.
You are given ONE challenge to a proposed credit facility that the bank's rules engine has ALREADY raised,
with its figures. Your job is wording only: put the challenge to the relationship manager sharply and fairly.

Rules:
- Do NOT approve, decline, recommend or predict a credit decision, and do NOT change the severity.
- Do NOT calculate, estimate or invent any number; quote only figures that appear in the facts exactly as given.
- Do not add new concerns that are not in the facts.
- "challenge": 2-3 sentences, direct, in the voice of the committee questioning the proposal.
- "rationale": 2-3 sentences on why it matters for the bank's exposure.

Return ONLY a JSON object, no markdown fences: {"challenge": "...", "rationale": "..."}"""


def _facts(ch: dict) -> dict:
    return {"category": ch.get("category"), "title": ch.get("title"), "proposal": ch.get("proposal_reference"),
            "engine_challenge": ch.get("challenge"), "engine_rationale": ch.get("rationale"),
            "supporting_metrics": [{"label": m.get("label"), "value": m.get("value"), "period": m.get("period")}
                                   for m in ch.get("supporting_metrics") or []],
            "required_response": ch.get("required_response")}


def word_challenge(ch: dict, llm_provider, company_name: str, max_tokens: int = 700) -> dict:
    """LLM wording for one challenge. Raises ValueError when the response is unusable."""
    facts_json = json.dumps(_facts(ch), ensure_ascii=False, default=str)
    prompt = f"Borrower: {company_name}\n\nChallenge facts (JSON):\n{facts_json}\n\nWrite the JSON object."
    data = _parse_json_object(llm_provider.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT,
                                                    temperature=0.2, max_tokens=max_tokens))
    challenge, rationale = str(data.get("challenge") or "").strip(), str(data.get("rationale") or "").strip()
    if not challenge or not rationale:
        raise ValueError("model response is missing the challenge or rationale")
    unsupported = unsupported_figures(f"{challenge}\n{rationale}", facts_json)
    if unsupported:
        raise ValueError(f"response quoted figures not in the challenge: {', '.join(unsupported[:5])}")
    return {"challenge": challenge, "rationale": rationale,
            "model": getattr(llm_provider, "model", None) or getattr(llm_provider, "name", "llm"),
            "prompt_version": PROMPT_VERSION, "generated_at": datetime.now().isoformat(timespec="seconds")}


def word_challenges(challenges: list[dict], llm_provider, company_name: str, max_workers: int = 4) -> dict[str, dict]:
    """{challenge_id: {"status": "ok", "ai_wording": {...}} | {"status": "rejected", "reason": str}}."""
    def one(ch: dict) -> tuple[str, dict]:
        try:
            return ch["challenge_id"], {"status": "ok", "ai_wording": word_challenge(ch, llm_provider, company_name)}
        except Exception as e:
            log.warning("Challenge wording rejected for %s: %s", ch.get("challenge_id"), e)
            return ch["challenge_id"], {"status": "rejected", "reason": str(e)}

    if not challenges:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(challenges))),
                            thread_name_prefix="chl-narrator") as pool:
        return dict(pool.map(one, challenges))
