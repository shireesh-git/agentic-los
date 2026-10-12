"""
On-demand LLM phrasing of an investigation request.

The Investigation Agent has already decided the investigation, its reason,
evidence list and priority. The LLM only turns that into a short, courteous
information request an RM can send to the borrower. As with observation
wording, any figure not present in the task's facts rejects the response.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from src.services.observation_narrator import _parse_json_object, unsupported_figures

log = logging.getLogger(__name__)

PROMPT_VERSION = "inv_request_v1"

SYSTEM_PROMPT = """You are a relationship manager at an Indian bank drafting an information request to a corporate borrower.
You are given ONE investigation task that the bank's rules engine has ALREADY opened, with its reason and
the list of documents needed. Your job is wording only.

Rules:
- Do NOT add, drop or change the documents requested, and do NOT change the priority or the reason.
- Do NOT calculate or invent any number; quote only figures that appear in the facts exactly as given.
- Formal, courteous, concise (120-200 words). Address the borrower's finance team.
- This goes to the borrower: never mention internal priorities, rule or exception codes, or the bank's
  credit process. No placeholders such as [Your Name]; sign off as "Relationship Manager, Corporate Credit".
- List the documents as numbered points in the same order.

Return ONLY a JSON object, no markdown fences: {"request_text": "<the request>"}"""


def _facts(task: dict) -> dict:
    # Borrower-facing: internal priority and rule codes (e.g. "(XSRC_...)") are not passed to the model.
    def plain(text):
        return re.sub(r"\s*\([A-Z][A-Z0-9_]{3,}\)|\s*\b[A-Z]{2,}_[A-Z0-9_]+\b|\s*\([a-z]+(?:_[a-z]+)+\)",
                      "", text or "").strip()

    return {"title": task.get("title"), "reason": plain(task.get("reason")),
            "documents": [{"item": plain(e.get("item")), "description": plain(e.get("description"))}
                          for e in task.get("required_evidence") or []]}


def phrase_request(task: dict, llm_provider, company_name: str, max_tokens: int = 900) -> dict:
    """LLM wording for one task. Raises ValueError when the response is unusable."""
    facts_json = json.dumps(_facts(task), ensure_ascii=False)
    prompt = f"Borrower: {company_name}\n\nInvestigation facts (JSON):\n{facts_json}\n\nWrite the JSON object."
    data = _parse_json_object(llm_provider.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT,
                                                    temperature=0.2, max_tokens=max_tokens))
    text = str(data.get("request_text") or "").strip()
    if len(text) < 40:
        raise ValueError("model response is missing the request text")
    unsupported = unsupported_figures(text, facts_json)
    if unsupported:
        raise ValueError(f"response quoted figures not in the task: {', '.join(unsupported[:5])}")
    return {"text": text, "model": getattr(llm_provider, "model", None) or getattr(llm_provider, "name", "llm"),
            "prompt_version": PROMPT_VERSION, "generated_at": datetime.now().isoformat(timespec="seconds")}


def phrase_requests(tasks: list[dict], llm_provider, company_name: str, max_workers: int = 4) -> dict[str, dict]:
    """{investigation_id: {"status": "ok", "request_text": {...}} | {"status": "rejected", "reason": str}}."""
    def one(task: dict) -> tuple[str, dict]:
        try:
            return task["investigation_id"], {"status": "ok",
                                              "request_text": phrase_request(task, llm_provider, company_name)}
        except Exception as e:
            log.warning("Investigation request phrasing rejected for %s: %s", task.get("investigation_id"), e)
            return task["investigation_id"], {"status": "rejected", "reason": str(e)}

    if not tasks:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks))),
                            thread_name_prefix="inv-narrator") as pool:
        return dict(pool.map(one, tasks))
