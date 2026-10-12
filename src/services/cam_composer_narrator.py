"""
On-demand AI interpretation of a composed CAM section (M7).

The composer has already laid out the section's facts, tables and findings with
their provenance. The LLM writes a short credit-officer interpretation of that
content only; it may not add facts, compute figures or change the
recommendation, and any figure not in the section's content rejects the text.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from src.services.observation_narrator import _parse_json_object, unsupported_figures

PROMPT_VERSION = "final_cam_interpret_v1"

SYSTEM_PROMPT = """You are a senior credit officer at an Indian bank writing the interpretation paragraph for one section
of a Credit Appraisal Memorandum. You are given the section's content exactly as the bank's systems produced it:
statements, facts, tables and findings, each with a provenance label.

Rules:
- Interpret and connect the content for a credit committee; do NOT add facts, events or opinions about the
  borrower that are not in the content, and do NOT change the recommendation or any grade.
- Do NOT calculate, derive, round or estimate any number; quote only figures that appear in the content exactly.
- Content labelled synthetic demo data must be described as demo data that is not verified; content labelled
  not available must be described as not available.
- 80-140 words, one paragraph, formal Indian banking usage.

Return ONLY a JSON object, no markdown fences: {"interpretation": "<paragraph>"}"""


def section_content(section: dict) -> dict:
    """The section's content as given to the model (no drill-down text)."""
    return {
        "title": section["title"],
        "statements": [{"text": s["text"], "provenance": s["provenance"]} for s in section.get("statements") or []],
        "facts": [{"label": f["label"], "value": f["value"], "provenance": f["provenance"]} for f in section.get("facts") or []],
        "tables": [{"title": t["title"], "columns": t["columns"], "rows": t["rows"][:15], "provenance": t["provenance"],
                    "note": t.get("note", "")} for t in section.get("tables") or [] if t.get("rows")],
        "findings": [f"{f['severity']}: {f['text']}" for f in section.get("findings") or []],
    }


def interpret_section(section: dict, llm_provider, company_name: str, max_tokens: int = 700) -> dict:
    content_json = json.dumps(section_content(section), ensure_ascii=False, default=str)
    prompt = f"Borrower: {company_name}\n\nSection content (JSON):\n{content_json}\n\nWrite the JSON object."
    data = _parse_json_object(llm_provider.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT, temperature=0.2,
                                                    max_tokens=max_tokens))
    text = str(data.get("interpretation") or "").strip()
    if len(text) < 40:
        raise ValueError("model response is missing the interpretation")
    bad = unsupported_figures(text, content_json)
    if bad:
        raise ValueError(f"interpretation quoted figures not in the section: {', '.join(bad[:5])}")
    return {"text": text, "model": getattr(llm_provider, "model", None) or getattr(llm_provider, "name", "llm"),
            "prompt_version": PROMPT_VERSION, "provenance": "ai",
            "generated_at": datetime.now().isoformat(timespec="seconds")}


def interpret_sections(sections: list[dict], llm_provider, company_name: str, max_workers: int = 4) -> dict[str, dict]:
    """{section id: {"status": "ok", "ai_interpretation": {...}} | {"status": "rejected", "reason": str}}."""
    def one(section):
        try:
            return section["id"], {"status": "ok", "ai_interpretation": interpret_section(section, llm_provider, company_name)}
        except Exception as e:
            return section["id"], {"status": "rejected", "reason": str(e)}

    if not sections:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(sections))), thread_name_prefix="cam-interpret") as pool:
        return dict(pool.map(one, sections))
