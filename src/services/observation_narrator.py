"""
On-demand AI wording for credit observations.

The observation engine has already decided that an observation exists, its
severity, metrics and trigger. The LLM is given those facts for ONE
observation and may only:
  * explain it in credit-analyst language,
  * write a concise summary,
  * suggest areas to investigate.

It never sees an instruction to assess risk, and nothing it returns is used
for detection or severity. Any figure in its text that is not in the facts it
was given rejects the response (same check the CAM renderer uses), and the
deterministic wording stays in place.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

log = logging.getLogger(__name__)

PROMPT_VERSION = "obs_narrative_v1"

SYSTEM_PROMPT = """You are a senior corporate credit analyst at an Indian bank writing for a credit committee.
You are given ONE credit observation that a deterministic rules engine has ALREADY detected,
with its severity, metrics and trigger. Your job is wording only.

Rules:
- Do NOT decide whether the risk exists and do NOT change or comment on the severity.
- Do NOT calculate, derive, estimate or round any new number. Quote only figures that appear
  in the facts exactly as given. If you are unsure of a figure, describe it in words instead.
- Use formal, concise credit language (Indian banking usage, amounts in Rs Crore).
- Do not invent facts about the company, its clients, management or industry.

Return ONLY a JSON object, no markdown fences:
{"summary": "<1-2 sentences>",
 "detailed_explanation": "<one paragraph, 3-5 sentences: what the numbers show and why it matters for repayment>",
 "recommended_investigation": ["<specific check>", "<specific check>", "<specific check>"]}"""


def _facts(obs: dict) -> dict:
    """The deterministic facts the LLM may draw on — and the only source of figures."""
    return {
        "title": obs.get("title"),
        "category": obs.get("category"),
        "severity": obs.get("severity"),
        "engine_summary": obs.get("summary"),
        "metrics": obs.get("metrics"),
        "period_comparison": obs.get("period_comparison"),
        "trigger": obs.get("trigger"),
        "evidence": [e.get("description") for e in obs.get("evidence_references") or []],
        "engine_investigation_checklist": obs.get("recommended_investigation"),
    }


def build_prompt(obs: dict, company_name: str) -> tuple[str, str]:
    facts_json = json.dumps(_facts(obs), ensure_ascii=False, default=str)
    prompt = (f"Borrower: {company_name}\n\nObservation facts (JSON):\n{facts_json}\n\n"
              f"Write the JSON object described in your instructions.")
    return prompt, facts_json


def allowed_figures(facts_json: str) -> str:
    """The facts as the figure check should read them.

    Changes are stored signed (-76.3) but written as magnitudes ("fell 76.3%"), and
    amounts in engine text carry thousands separators ("₹1,100.00 Cr"): allow both forms.
    """
    unsigned = facts_json.replace("-", " ")
    return " ".join((facts_json, unsigned, re.sub(r"(?<=\d),(?=\d{3})", "", unsigned)))


def unsupported_figures(text: str, facts_json: str) -> list[str]:
    """Figures in model text that are not in the facts (the CAM renderer's check, made stricter).

    The CAM check skips a number glued to a letter, so ratios written "1.19x" would go
    unchecked; the multiplier sign is split off first so every ratio is verified.
    """
    from src.engines.cam_llm_renderer import _unsupported_figures

    return _unsupported_figures(re.sub(r"(?<=\d)(?=[xX]\b)", " ", text), allowed_figures(facts_json))


def _parse_json_object(text: str) -> dict:
    """The JSON object in a model reply (tolerates markdown fences and surrounding text)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model did not return a JSON object")
    return json.loads(text[start:end + 1])


def _parse(text: str) -> dict:
    data = _parse_json_object(text)
    summary = str(data.get("summary") or "").strip()
    explanation = str(data.get("detailed_explanation") or "").strip()
    steps = [str(s).strip() for s in (data.get("recommended_investigation") or []) if str(s).strip()]
    if not summary or not explanation:
        raise ValueError("model response is missing summary or explanation")
    return {"summary": summary, "detailed_explanation": explanation, "recommended_investigation": steps[:6]}


def explain_observation(obs: dict, llm_provider, company_name: str, max_tokens: int = 900) -> dict:
    """AI wording for one observation. Raises ValueError when the response is unusable."""
    prompt, facts_json = build_prompt(obs, company_name)
    raw = llm_provider.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT, temperature=0.2, max_tokens=max_tokens)
    wording = _parse(raw)
    text = "\n".join([wording["summary"], wording["detailed_explanation"], *wording["recommended_investigation"]])
    unsupported = unsupported_figures(text, facts_json)
    if unsupported:
        raise ValueError(f"response quoted figures not in the observation: {', '.join(unsupported[:5])}")
    return {
        **wording,
        "model": getattr(llm_provider, "model", None) or getattr(llm_provider, "name", "llm"),
        "prompt_version": PROMPT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def explain_observations(observations: list[dict], llm_provider, company_name: str,
                         max_workers: int = 4) -> dict[str, dict]:
    """{observation_id: {"status": "ok", "ai_explanation": {...}} | {"status": "rejected", "reason": str}}.

    One small call per observation, a few at a time, so one slow or bad answer
    does not hold up or spoil the others.
    """
    def one(obs: dict) -> tuple[str, dict]:
        try:
            return obs["observation_id"], {"status": "ok",
                                           "ai_explanation": explain_observation(obs, llm_provider, company_name)}
        except Exception as e:
            log.warning("AI explanation rejected for %s: %s", obs.get("observation_id"), e)
            return obs["observation_id"], {"status": "rejected", "reason": str(e)}

    if not observations:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(observations))),
                            thread_name_prefix="obs-narrator") as pool:
        return dict(pool.map(one, observations))
