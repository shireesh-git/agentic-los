"""
Critic — checks agent output before a person sees it.

Two deterministic checks, also registered as tools so other agents can self-check:

  check_figures   every figure in a text must appear in the facts it was written from
                  (the platform's number guard: observation_narrator.unsupported_figures);
  check_evidence  every field proposal must carry its basis: a document + page, or the
                  tool / engine / external source that produced it.

A proposal or text that fails is rejected with its issues; the producing agent may
revise it, otherwise it never reaches the verify queue. An optional LLM review
(``llm_review=True``) adds a model's judgement on unsupported *claims*; it can only
add issues, never clear a deterministic failure.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from src.agentic.tools import registry

# Where a proposed value came from, and what evidence that kind of source must carry.
SOURCE_EVIDENCE = {
    "document": ("document", "page"),       # extracted from a page of an uploaded document
    "external": ("system",),                # an external record (MCA, bureau, screening …)
    "engine": ("engine",),                  # a deterministic engine output (ratio, policy, RAROC …)
    "template": ("engine",),                # a bank template or rate card (labelled; not borrower-specific)
    "record": ("path",),                    # already on the application / borrower master
    "ai_draft": ("facts",),                 # an AI-written draft; facts it was written from
}


@dataclass
class Verdict:
    passed: bool
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "issues": self.issues}


def _facts_json(facts: Any) -> str:
    return facts if isinstance(facts, str) else json.dumps(facts, ensure_ascii=False, default=str)


@registry.tool("check_figures",
               "Figures in a text that are NOT supported by the given facts (empty list = all supported).",
               {"type": "object", "required": ["text", "facts"],
                "properties": {"text": {"type": "string"}, "facts": {}}})
def check_figures(text: str, facts: Any) -> list[str]:
    from src.services.observation_narrator import unsupported_figures
    return unsupported_figures(text or "", _facts_json(facts))


@registry.tool("check_evidence",
               "Problems with a field proposal's evidence (empty list = the proposal shows its basis).",
               {"type": "object", "required": ["proposal"], "properties": {"proposal": {"type": "object"}}})
def check_evidence(proposal: dict) -> list[str]:
    issues = []
    fid = proposal.get("field_id") or "?"
    if "value" not in proposal:
        issues.append(f"{fid}: no value")
    source = proposal.get("source")
    if source not in SOURCE_EVIDENCE:
        return issues + [f"{fid}: unknown source '{source}' (expected one of {', '.join(SOURCE_EVIDENCE)})"]
    evidence = proposal.get("evidence") or {}
    missing = [k for k in SOURCE_EVIDENCE[source] if evidence.get(k) in (None, "", [])]
    if missing:
        issues.append(f"{fid}: {source} value without {', '.join(missing)}")
    conf = proposal.get("confidence")
    if conf is not None and not (isinstance(conf, (int, float)) and 0 <= conf <= 1):
        issues.append(f"{fid}: confidence must be between 0 and 1")
    if source == "ai_draft" and isinstance(proposal.get("value"), str):
        bad = check_figures(proposal["value"], evidence.get("facts"))
        if bad:
            issues.append(f"{fid}: figures not in the facts: {', '.join(bad[:6])}")
    return issues


_REVIEW_SCHEMA = {"type": "object", "required": ["issues"],
                  "properties": {"issues": {"type": "array", "items": {"type": "string"}, "maxItems": 10}}}


class CriticAgent:
    """Reviews texts and field proposals. Deterministic checks always run; an LLM review is optional."""

    def __init__(self, llm=None, llm_review: bool = False, max_workers: int = 8):
        self.llm, self.llm_review, self.max_workers = llm, llm_review, max_workers

    def review_text(self, text: str, facts: Any) -> Verdict:
        issues = [f"figure not in the facts: {f}" for f in check_figures(text, facts)]
        if self.llm_review and self.llm is not None and getattr(self.llm, "supports_structured", False):
            issues += self._llm_issues(text, facts)
        return Verdict(passed=not issues, issues=issues)

    def review_proposals(self, proposals: list[dict]) -> list[Verdict]:
        """One verdict per proposal, in order. AI drafts (which may need an LLM review)
        are reviewed in parallel; everything else is a fast deterministic check."""
        def one(p):
            issues = check_evidence(p)
            if not issues and p.get("source") == "ai_draft" and self.llm_review and self.llm is not None \
                    and getattr(self.llm, "supports_structured", False):
                issues = self._llm_issues(str(p.get("value")), (p.get("evidence") or {}).get("facts"))
            return Verdict(passed=not issues, issues=issues)

        if not any(p.get("source") == "ai_draft" for p in proposals):
            return [one(p) for p in proposals]
        with ThreadPoolExecutor(max_workers=max(1, min(self.max_workers, len(proposals))),
                                thread_name_prefix="critic") as pool:
            return list(pool.map(one, proposals))

    def _llm_issues(self, text: str, facts: Any) -> list[str]:
        try:
            out = self.llm.generate_structured(
                f"Facts (JSON):\n{_facts_json(facts)[:12000]}\n\nText to check:\n{text[:6000]}",
                _REVIEW_SCHEMA,
                system_prompt=("You are a credit-risk reviewer. List each statement in the text that is not "
                               "supported by the facts, or that contradicts them. Return an empty list if "
                               "everything is supported."),
                max_tokens=800)
            return [f"reviewer: {i}" for i in out.get("issues", [])]
        except Exception:   # the deterministic checks stand on their own
            return []
