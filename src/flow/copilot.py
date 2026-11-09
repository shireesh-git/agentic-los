"""Credit Copilot's answers: a question about one proposal, answered from that proposal's record only.

    ask            with an LLM: the model answers from the record (JSON in, JSON out); every figure it quotes
                   is checked against the record, and an answer that quotes anything else is rejected
    lookup_answer  without an LLM (or when the answer is rejected): the record lines that match the question

Next steps and the amount check are not written by the model — see src/flow/risk.py (plan, amount_text).
"""

from __future__ import annotations

import json
import re
from typing import Optional

ASK_SYSTEM_PROMPT = """You are the credit copilot in a bank's loan origination system. Answer the user's question about
ONE application using ONLY the application record given as JSON. Rules: if the record does not contain the answer,
say it is not available in the record; do not add outside facts; do NOT calculate, round or estimate any number —
quote figures exactly as they appear in the record; values labelled synthetic or demo must be described as demo data;
be concise (at most 120 words). Return ONLY a JSON object: {"answer": "<text>", "fields_used": ["<record key>", ...]}"""

ADVISE_SYSTEM_PROMPT = """You are the Credit Copilot in a bank's loan origination system, assisting the officer named in
"asked_by". Answer using ONLY the application record given as JSON. When the question asks what to do, whether to change
something, or how to address a risk, give concrete numbered next steps that use only the actions listed in
asked_by.actions_available_on_screen and the suggested_actions of the key risk challenges; say which challenge or
policy breach each step addresses. Base the view on risk_assessment (the CAM engine's recommendation, hard rules and
ratios against policy) — never call a proposal sound when the engine recommends Decline or a hard rule failed. Rules:
do not add outside facts; do NOT calculate, round or estimate any number — quote figures exactly as they appear in the
record; if the record does not hold the answer, say so; be concise (at most 150 words). Return ONLY a JSON object:
{"answer": "<text>", "fields_used": ["<record key>", ...]}"""


# ── the record as people read it (fix list E6, E9) ─────────────────────────────
# The model quotes what it is given: format figures, dates and rule names before it sees them, and drop
# empty values, so no answer says "null", "None", "HR_…" or "₹153670.0 Cr".

_RULE = re.compile(r"\bHR_[A-Z_]+\b")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?$")
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
_DROP_KEYS = {"code", "run_id", "v", "_field_sources"}


def indian(n: float, decimals: int = 0) -> str:
    """1,53,670 — Indian digit grouping."""
    neg = n < 0
    whole, _, frac = f"{abs(n):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + whole + (f".{frac}" if decimals else "")


def crore(v: float) -> str:
    v = float(v)
    if abs(v) >= 1000 or v == int(v):
        return f"₹{indian(round(v))} Cr"
    return f"₹{indian(v, 2).rstrip('0').rstrip('.')} Cr"


def _date(v: str) -> str:
    m = _ISO_DATE.match(v.strip())
    if not m:
        return v
    y, mo, d, hh, mm = m.groups()
    out = f"{int(d)} {_MONTHS[int(mo) - 1]} {y}"
    return out + (f", {hh}:{mm}" if hh else "")


def _amount_key(key: str) -> bool:
    k = key.lower()
    return k.endswith("_cr") or k.endswith("(₹ cr)") or k in ("amount", "limit")


def clean(obj, key: str = ""):
    """A copy of the record with figures formatted for people and empty values removed."""
    from src.flow.checks import plain

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _DROP_KEYS:
                continue
            c = clean(v, str(k))
            if c not in (None, "", [], {}):
                out[k] = c
        return out
    if isinstance(obj, list):
        return [c for c in (clean(v, key) for v in obj) if c not in (None, "", [], {})]
    if isinstance(obj, bool):
        return "yes" if obj else "no"
    if isinstance(obj, (int, float)):
        if _amount_key(key):
            return crore(obj)
        if isinstance(obj, float):
            return indian(obj, 2).rstrip("0").rstrip(".") if abs(obj) < 1e6 else indian(round(obj))
        return indian(obj) if abs(obj) >= 1000 else obj
    if isinstance(obj, str):
        t = obj.strip()
        if t.lower() in ("none", "null", "nan"):
            return None
        t = _RULE.sub(lambda m: plain(m.group(0)).lower(), t)
        return _date(t)
    return obj


def flatten(obj, prefix="") -> list[tuple[str, str]]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        if all(not isinstance(x, (dict, list)) for x in obj):
            if obj:
                out.append((prefix, ", ".join(str(x) for x in obj)))
        else:
            for i, v in enumerate(obj[:20]):
                out += flatten(v, f"{prefix}[{i}]")
    elif obj not in (None, ""):
        out.append((prefix, str(obj)))
    return out


def lookup_answer(question: str, record: dict, limit: int = 8) -> dict:
    """No LLM: the record lines that share the most words with the question."""
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2} - {
        "what", "the", "is", "are", "was", "how", "much", "for", "this", "application", "does", "and", "which", "why"}
    scored = []
    for key, value in flatten(record):
        hay = (key.replace("_", " ") + " " + value).lower()
        score = sum(1 for w in words if w in hay)
        if score:
            scored.append((score, key, value))
    scored.sort(key=lambda x: -x[0])
    lines = [f"{k.replace('_', ' ')}: {v}" for _, k, v in scored[:limit]]
    return {"answer": ("From the record:\n" + "\n".join(lines)) if lines else
            "Nothing in the application record matches the question.", "provenance": "record",
            "mode": "lookup", "fields_used": [k for _, k, _ in scored[:limit]]}


def ask(question: str, record: dict, llm=None, system_prompt: Optional[str] = None) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Ask a question")
    if llm is None or getattr(llm, "name", "") == "mock":
        out = lookup_answer(question, record)
        out["note"] = "AI is not configured (mock provider) — showing the matching record lines."
        return out
    from src.services.observation_narrator import _parse_json_object, unsupported_figures

    content = json.dumps(record, ensure_ascii=False, default=str)
    try:
        raw = llm.generate(prompt=f"Application record (JSON):\n{content}\n\nQuestion: {question}",
                           system_prompt=system_prompt or ASK_SYSTEM_PROMPT, temperature=0.1, max_tokens=600)
        try:
            data = _parse_json_object(raw)
        except Exception:
            # with a long record some models answer in plain text instead of the JSON asked for: the
            # answer is still used, and checked against the record like any other
            plain = str(raw or "").strip()
            if not plain or plain.startswith(("{", "[")):
                raise
            data = {"answer": plain, "fields_used": []}
        text = str(data.get("answer") or "").strip()
        if not text:
            raise ValueError("the model returned no answer")
        bad = unsupported_figures(text, content)
        if bad:
            raise ValueError(f"quoted figures not in the record: {', '.join(bad[:4])}")
    except Exception as e:                                      # never pass an unchecked answer through
        out = lookup_answer(question, record)
        out["note"] = f"The AI answer was rejected ({e}) — showing the matching record lines instead."
        return out
    return {"answer": text, "provenance": "ai", "mode": "ai",
            "model": getattr(llm, "model", None) or getattr(llm, "name", "llm"),
            "fields_used": [str(f) for f in data.get("fields_used") or []][:10],
            "note": "AI answer from this application's record; figures checked against the record."}
