"""
LLM-Powered CAM Renderer — Section-by-Section Generation
Pass 2 per IDEA.MD: LLM converts approved factual JSON into credit narrative.
Each section is generated independently (several at once when the provider
allows it) and checkpointed as soon as it is written; a failed run resumes
from the completed sections. An LLM failure stops the run (no silent template
fallback).
Golden Rule: LLM only writes from approved fact-pack, never invents facts.
"""

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable, Protocol

# Prompt data lives in cam_sections; PROMPT_VERSION is re-exported for cam_checkpoints.
from src.engines.cam_sections import CAM_SECTIONS, PROMPT_VERSION, SYSTEM_PROMPT  # noqa: F401

log = logging.getLogger(__name__)


class SectionCheckpoints(Protocol):
    """Storage for CAM sections already generated, so a failed run can resume."""

    def load(self, section_id: str, input_hash: str) -> str | None: ...

    def save(self, section_id: str, input_hash: str, content: str) -> None: ...


def model_identity(llm_provider) -> str:
    model = getattr(llm_provider, "model", None) or getattr(llm_provider, "model_name", None) or ""
    return f"{getattr(llm_provider, 'name', 'unknown')}:{model}"


def section_input_hash(prompt: str, system_prompt: str, model_id: str,
                       temperature: float, max_tokens: int) -> str:
    """Fingerprint of everything that determines a section's LLM output."""
    material = json.dumps(
        {"v": PROMPT_VERSION, "prompt": prompt, "system": system_prompt, "model": model_id,
         "temperature": temperature, "max_tokens": max_tokens},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_FENCED = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", flags=re.DOTALL)


def clean_section_output(text: str) -> str:
    """Strip reasoning blocks (e.g. qwen3 <think>) and a wrapping code fence."""
    text = _THINK_BLOCK.sub("", text or "")
    if "</think>" in text.lower():  # reasoning without an opening tag
        text = text[text.lower().rindex("</think>") + len("</think>"):]
    text = text.strip()
    fenced = _FENCED.match(text)
    return fenced.group(1).strip() if fenced else text


def _sanitize_llm_markdown(text: str) -> str:
    """Clean up common LLM markdown defects before PDF rendering."""
    import re as _re

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()

        # ── Fix 1: Truncate absurdly long separator rows ──
        # LLM sometimes produces separator rows with hundreds of dashes
        if stripped.startswith("|") and len(stripped) > 200:
            dash_ratio = (stripped.count("-") + stripped.count(":")) / len(stripped)
            if dash_ratio > 0.7:
                # Reconstruct a proper separator based on pipe count in the header
                pipes = stripped.count("|")
                ncols = max(pipes - 1, 1)
                line = "| " + " | ".join(["---"] * ncols) + " |"

        # ── Fix 2: Fix table rows that don't end with | ──
        stripped2 = line.strip()
        if stripped2.startswith("|") and not stripped2.endswith("|"):
            # Check if it's a mostly-dash separator that lost its trailing pipe
            if len(stripped2) > 50 and stripped2.count("-") / len(stripped2) > 0.5:
                pipes = stripped2.count("|")
                ncols = max(pipes, 2)
                line = "| " + " | ".join(["---"] * ncols) + " |"
            else:
                line = stripped2 + " |"

        # ── Fix 3: Remove header-only tables ──
        # (handled in a second pass below)

        cleaned.append(line)

    # ── Second pass: Remove header-only tables (header + separator, no data rows) ──
    result = []
    i = 0
    while i < len(cleaned):
        line = cleaned[i].strip()
        # Detect start of a table (pipe-delimited row)
        if line.startswith("|") and line.endswith("|") and "---" not in line:
            # Collect the full table
            tbl_start = i
            tbl_lines = [cleaned[i]]
            i += 1
            while i < len(cleaned) and cleaned[i].strip().startswith("|") and cleaned[i].strip().endswith("|"):
                tbl_lines.append(cleaned[i])
                i += 1
            # Count non-separator rows
            data_rows = [r for r in tbl_lines if not _re.match(r"^\s*\|[\s\-:|]+\|\s*$", r)]
            if len(data_rows) <= 1:
                # Header-only table — skip it (don't add to result)
                continue
            else:
                result.extend(tbl_lines)
        else:
            result.append(cleaned[i])
            i += 1

    return "\n".join(result)


def _compact_for_prompt(key: str, value):
    """Prompt form of a fact-pack section: same facts, less repetition."""
    if key == "ratio_analysis" and isinstance(value, dict):
        # The formula text repeated for every period roughly doubled this section; send each once.
        values = {p: {r: (v or {}).get("value") for r, v in ratios.items()} for p, ratios in value.items()}
        formulas = {}
        for ratios in value.values():
            for r, v in ratios.items():
                formulas.setdefault(r, (v or {}).get("formula"))
        return {"values_by_period": values, "formulas": formulas}
    return value


def _slice_fact_pack(fact_pack: dict, keys: list) -> dict:
    """The fact-pack sections a CAM section uses, with each section's data provenance label."""
    data = {k: _compact_for_prompt(k, fact_pack.get(k, {})) for k in keys}
    provenance = fact_pack.get("data_provenance") or {}
    labels = {k: provenance[k]["label"] + (f" ({provenance[k]['note']})" if provenance[k].get("note") else "")
              for k in keys if k in provenance}
    if labels:
        data["_provenance"] = labels
    return data


def _has_meaningful_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_value(item) for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _should_render_section(section: dict, fact_pack: dict) -> bool:
    sid = section.get("id")
    if sid == "social_media":
        return _has_meaningful_value(fact_pack.get("social_media_analysis"))
    return True


def render_cam_template_only(fact_pack: dict, on_section_progress: Callable = None) -> str:
    """Render a complete CAM using template functions only (no LLM)."""
    from src.engines.cam_renderer_v2 import (
        render_cover_page, render_toc, render_data_sources, render_disclaimer,
        render_annexure_a_document_checklist, render_annexure_b_quarterly_performance,
        render_annexure_c_glossary,
    )

    _struct_map = {
        "cover_page": render_cover_page,
        "toc": render_toc,
        "annexure_a": render_annexure_a_document_checklist,
        "annexure_b": render_annexure_b_quarterly_performance,
        "annexure_c": render_annexure_c_glossary,
        "data_sources": render_data_sources,
        "disclaimer": render_disclaimer,
    }

    rendered_sections = []
    section_results = {}
    content_sections = [s for s in CAM_SECTIONS if not s.get("skip_llm") and _should_render_section(s, fact_pack)]
    total = len(content_sections)
    idx = 0

    for section in CAM_SECTIONS:
        sid = section["id"]

        if section.get("skip_llm"):
            fn = _struct_map.get(sid)
            if fn:
                rendered_sections.append(fn(fact_pack))
            continue

        if not _should_render_section(section, fact_pack):
            section_results[sid] = "skipped"
            continue

        idx += 1
        if on_section_progress:
            on_section_progress({"type": "section_start", "section": sid,
                                 "title": section["title"], "step": idx, "total": total})

        text = _get_template_fallback(sid, fact_pack)
        if text and len(text.strip()) >= 10:
            rendered_sections.append(text.strip())
            section_results[sid] = "template"
        else:
            section_results[sid] = "skipped"

        if on_section_progress:
            on_section_progress({"type": "section_complete", "section": sid, "title": section["title"],
                                 "mode": "template", "step": idx, "total": total, "completed": idx})

    meta = _generation_metadata(section_results)
    rendered_sections.append(meta)

    raw = "\n\n---\n\n".join(rendered_sections)
    return _sanitize_llm_markdown(raw)


def render_cam_with_llm(
    fact_pack: dict,
    llm_provider,
    template_renderer_fn: Callable = None,
    temperature: float = 0.1,
    max_tokens_per_section: int = 1500,
    on_section_progress: Callable = None,
    checkpoints: SectionCheckpoints | None = None,
    max_parallel_sections: int = 1,
    section_max_tokens: dict[str, int] | None = None,
    section_models: dict[str, str] | None = None,
    verify_figures: bool = True,
) -> str:
    """
    Render a complete CAM using LLM for narrative sections.

    Each section is saved to ``checkpoints`` as soon as it is generated, and a
    section whose inputs are unchanged is reused instead of regenerated, so a
    re-run after a failure resumes where the last run stopped.
    Up to ``max_parallel_sections`` sections are generated at once; the CAM is
    always assembled in document order. ``section_max_tokens`` ({section id: limit},
    from config) overrides a section's output limit, which otherwise is the
    section's own ``max_tokens`` or ``max_tokens_per_section``.

    ``section_models`` ({section id: model}) routes sections to other models of the same
    provider (e.g. a small local model for table-led sections). Routed models run first,
    grouped, then the main model, so a run switches model once; a routed local model is
    unloaded before the main one loads. With ``verify_figures``, a routed section whose
    figures are not all found in its data is rewritten by the main model.
    Raises on LLM failure — no template fallback.
    """
    from src.engines.cam_renderer_v2 import (
        render_cover_page, render_toc, render_data_sources, render_disclaimer,
        render_annexure_a_document_checklist, render_annexure_b_quarterly_performance,
        render_annexure_c_glossary,
    )

    # Template map for structural sections only (cover, toc, annexures)
    _template_map = {
        "cover_page": render_cover_page,
        "toc": render_toc,
        "annexure_a": render_annexure_a_document_checklist,
        "annexure_b": render_annexure_b_quarterly_performance,
        "annexure_c": render_annexure_c_glossary,
        "data_sources": render_data_sources,
        "disclaimer": render_disclaimer,
    }

    # Verify LLM connection upfront — fail fast, no silent fallback
    test_result = llm_provider.test_connection()
    if test_result.get("status") != "ok":
        raise RuntimeError(
            f"LLM connection failed: {test_result.get('message', 'unknown error')}. "
            f"Provider: {test_result.get('provider', 'unknown')}"
        )

    # Plan in document order: structural sections render now; each narrative
    # section gets a slot that its LLM job fills (possibly out of order).
    main_model = getattr(llm_provider, getattr(llm_provider, "_model_attr", "model"), None)
    providers = {main_model: llm_provider}

    def provider_for(model):
        if model not in providers:
            providers[model] = llm_provider.with_model(model)
        return providers[model]

    slots: list[str | None] = []
    section_results = {}
    jobs: list[_SectionJob] = []
    for section in CAM_SECTIONS:
        sid = section["id"]
        # Structural sections (cover, toc, annexures) use template — these genuinely don't need LLM
        if section.get("skip_llm"):
            fn = _template_map.get(sid)
            if fn:
                slots.append(fn(fact_pack))
            continue
        if not _should_render_section(section, fact_pack):
            section_results[sid] = "skipped"
            continue
        prompt, data_json = _section_prompt(section, fact_pack)
        max_tokens = int((section_max_tokens or {}).get(sid)
                         or section.get("max_tokens", max_tokens_per_section))
        model = (section_models or {}).get(sid) or main_model
        job = _SectionJob(slot=len(slots), step=len(jobs) + 1, section=section, prompt=prompt,
                          data_json=data_json, max_tokens=max_tokens, model=model,
                          routed=model != main_model)
        _prepare(job, provider_for(model), temperature, checkpoints)
        section_results[sid] = "pending"
        jobs.append(job)
        slots.append(None)

    # Fail fast if a routed model is unavailable (e.g. not pulled into Ollama).
    for model in dict.fromkeys(job.model for job in jobs if job.routed and job.cached is None):
        check = provider_for(model).test_connection()
        if check.get("status") != "ok":
            raise RuntimeError(f"Routed model '{model}' unavailable: {check.get('message', 'unknown error')}")

    llm_total = len(jobs)
    progress_lock = threading.Lock()
    completed = 0
    deferred: list[_SectionJob] = []  # routed sections that failed the figures check

    def notify(event: dict) -> None:
        if on_section_progress:
            with progress_lock:
                on_section_progress(event)

    def write_section(job: _SectionJob) -> str | None:
        """Write one section; None means it was deferred to the main model."""
        nonlocal completed
        sid = job.section["id"]
        notify({"type": "section_start", "section": sid, "title": job.section["title"],
                "step": job.step, "total": llm_total, "model": job.model})
        resumed = job.cached is not None
        if resumed:
            log.info("LLM section %d/%d: %s resumed from checkpoint", job.step, llm_total, sid)
            text = job.cached
        else:
            text = _generate_section(job, llm_total, provider_for(job.model), temperature)
            unsupported = _unsupported_figures(text, job.data_json) if (job.routed and verify_figures) else []
            if unsupported:
                # Not sent to the main model now: that would swap models mid-group. It
                # joins the main model's group, which runs next.
                log.warning("Section %s (%s): figures not in its data %s — rewriting with %s",
                            sid, job.model, unsupported[:5], main_model)
                with progress_lock:
                    deferred.append(job)
                return None
            if not job.routed:
                # Main model: report only (there is no stronger model to hand it to), so
                # figures the reviewer should check are visible in the log.
                flagged = _unsupported_figures(text, job.data_json)
                if flagged:
                    log.warning("Section %s (%s): %d figure(s) not found in its data — review: %s",
                                sid, job.model, len(flagged), flagged[:8])
            if checkpoints:
                checkpoints.save(sid, job.input_hash, text)
        with progress_lock:
            completed += 1
            done = completed
        # step = position in the CAM; completed = sections finished so far (they can finish out of order)
        notify({"type": "section_complete", "section": sid, "title": job.section["title"], "mode": "llm",
                "resumed": resumed, "step": job.step, "total": llm_total, "completed": done,
                "model": job.model})
        section_models_used[sid] = job.model
        return text

    def run_group(model, group: list[_SectionJob]) -> None:
        provider = provider_for(model)
        # A provider whose context size is chosen per prompt (Ollama) reloads the model
        # whenever it changes; let it fix one size for every section this group still writes.
        to_generate = [(SYSTEM_PROMPT, job.prompt, job.max_tokens) for job in group if job.cached is None]
        fix_window = getattr(provider, "fixed_context_window", None)
        window_scope = fix_window(to_generate) if (callable(fix_window) and to_generate) else nullcontext()
        workers = max(1, min(int(max_parallel_sections or 1), len(group) or 1))
        log.info("CAM narrative: %s — %d section(s) (%d to generate), %d at a time",
                 model, len(group), len(to_generate), workers)
        with window_scope:
            if workers == 1:
                for job in group:
                    text = write_section(job)
                    if text is not None:
                        slots[job.slot] = text
                        section_results[job.section["id"]] = "llm"
            else:
                # Sections only read the fact pack, so they are independent. On the first
                # failure, queued sections are cancelled; ones already running finish and
                # are checkpointed, so a re-run resumes from them.
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cam-section") as pool:
                    futures = {pool.submit(write_section, job): job for job in group}
                    try:
                        for future in as_completed(futures):
                            job = futures[future]
                            text = future.result()
                            if text is not None:
                                slots[job.slot] = text
                                section_results[job.section["id"]] = "llm"
                    except BaseException:
                        for future in futures:
                            future.cancel()
                        raise

    # Routed models first, the main model last: one model switch per run, and sections
    # deferred by the figures check join the main group instead of forcing extra swaps.
    section_models_used: dict[str, str] = {}
    routed_models = list(dict.fromkeys(job.model for job in jobs if job.routed))
    for model in routed_models:
        run_group(model, [job for job in jobs if job.model == model])
        release = getattr(provider_for(model), "release", None)
        if callable(release) and any(job.cached is None for job in jobs if job.model == model):
            release()  # free its RAM before the main model loads
    for job in deferred:
        job.model, job.routed = main_model, False
        _prepare(job, llm_provider, temperature, checkpoints)
    main_jobs = sorted([job for job in jobs if job.model == main_model], key=lambda j: j.step)
    if main_jobs:
        run_group(main_model, main_jobs)

    rendered_sections = [text for text in slots if text is not None]

    # Add generation metadata
    meta = _generation_metadata(section_results, section_models_used)
    rendered_sections.append(meta)

    raw = "\n\n---\n\n".join(rendered_sections)
    return _sanitize_llm_markdown(raw)


@dataclass
class _SectionJob:
    """One narrative section of a CAM run: its place, prompt, model and any checkpointed text."""

    slot: int            # position among the CAM's rendered parts
    step: int            # 1-based position among the narrative sections
    section: dict
    prompt: str
    data_json: str       # the data given to the model (for the figures check)
    max_tokens: int
    model: str           # model that writes it (the main model unless routed)
    routed: bool         # written by a routed (usually smaller) model
    input_hash: str = ""
    cached: str | None = None  # checkpointed text from an earlier run, if the inputs are unchanged


def _prepare(job: _SectionJob, provider, temperature: float, checkpoints: SectionCheckpoints | None) -> None:
    """Key the section by everything that determines its output (incl. the model) and load
    its checkpoint, if any."""
    job.input_hash = section_input_hash(job.prompt, SYSTEM_PROMPT, model_identity(provider),
                                        temperature, job.max_tokens)
    job.cached = checkpoints.load(job.section["id"], job.input_hash) if checkpoints else None


def _section_prompt(section: dict, fact_pack: dict) -> tuple[str, str]:
    """The section's prompt, and the data JSON embedded in it."""
    # Compact JSON: indentation carries no information for the model but adds
    # roughly a fifth to a third more prompt tokens, which a local CPU model
    # must read before it writes anything.
    data_slice = _slice_fact_pack(fact_pack, section.get("data_keys", []))
    data_json = json.dumps(data_slice, separators=(",", ":"), ensure_ascii=False, default=str)
    prompt = (
        f"## Section: {section['title']}\n\n"
        f"### Instructions:\n{section['instruction']}\n\n"
        f"### Data (use ONLY this data):\n```json\n"
        f"{data_json}\n```\n\n"
        f"Write the section now. Output ONLY the section content in markdown format. "
        f"Start with the heading: ## {section['title']}"
    )
    return prompt, data_json


def _generate_section(job: _SectionJob, total: int, llm_provider, temperature: float) -> str:
    """Generate one narrative section (the caller checkpoints it once accepted).

    LLM generation — no fallback: raises if the model returns too little text.
    """
    sid = job.section["id"]
    started = time.time()
    log.info("LLM generating section %d/%d: %s with %s (prompt ~%d chars)",
             job.step, total, sid, job.model, len(job.prompt))
    text = clean_section_output(llm_provider.generate(
        prompt=job.prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=temperature,
        max_tokens=job.max_tokens,
    ))
    elapsed = time.time() - started
    log.info("LLM section %s: %d chars in %.1fs", sid, len(text), elapsed)
    if len(text) < 50:
        raise RuntimeError(
            f"LLM produced empty/insufficient output for section '{sid}' "
            f"({len(text)} chars in {elapsed:.1f}s)"
        )
    return text


# ── Figures check for routed (smaller) models ────────────────────────────────

_NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w])")
_DATA_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _unsupported_figures(text: str, data_json: str) -> list[str]:
    """Figures in a section's text that do not appear in the data it was given.

    A smaller model is more likely to invent or miscopy numbers; in a credit memo that
    matters more than speed. A figure counts as supported if some data value equals it
    after rounding to the figure's precision, also as a fraction shown in percent (0.125
    → 12.5) or the reverse. Headings, years, and small whole numbers (counts, list
    numbering) are ignored.
    """
    values = [float(v) for v in _DATA_NUMBER.findall(data_json)]
    unsupported: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for match in _NUMBER.finditer(line):
            token = match.group(0)
            try:
                value = float(token.replace(",", ""))
            except ValueError:
                continue
            decimals = len(token.split(".", 1)[1]) if "." in token else 0
            if decimals == 0 and (abs(value) <= 31 or 1900 <= value <= 2100):
                continue  # counts, list numbers, days, years
            # "(9.1)" style sub-section numbers
            if decimals and abs(value) < 30 and line[max(0, match.start() - 1):match.start()] == "(":
                continue
            tolerance = 0.5 * 10 ** -decimals + 1e-9
            if any(abs(v - value) <= tolerance or abs(v * 100 - value) <= tolerance
                   or abs(v / 100 - value) <= tolerance for v in values):
                continue
            unsupported.append(token)
    return list(dict.fromkeys(unsupported))


def _get_template_fallback(section_id: str, fact_pack: dict) -> str:
    """Get template-rendered fallback from V2 renderer for a section."""
    from src.engines.cam_renderer_v2 import (
        render_section_1_executive_summary,
        render_section_2_borrower_profile,
        render_section_3_industry_analysis,
        render_section_4_financial_analysis,
        render_section_5_facility_details,
        render_section_6_security_collateral,
        render_section_7_risk_assessment,
        render_section_8_compliance,
        render_section_8b_social_media,
        render_section_9_covenants,
        render_section_10_conduct,
        render_section_11_benchmarking,
        render_section_12_operational_kpis,
        render_section_13_financial_projections,
        render_section_15_recommendation,
        render_section_8a_core_banking,
    )
    _map = {
        "executive_summary": render_section_1_executive_summary,
        "borrower_profile": render_section_2_borrower_profile,
        "industry_analysis": render_section_3_industry_analysis,
        "financial_analysis": render_section_4_financial_analysis,
        "facility_assessment": render_section_5_facility_details,
        "security_collateral": render_section_6_security_collateral,
        "risk_assessment": render_section_7_risk_assessment,
        "compliance": render_section_8_compliance,
        "social_media": render_section_8b_social_media,
        "covenants": render_section_9_covenants,
        "conduct": render_section_10_conduct,
        "benchmarking": render_section_11_benchmarking,
        "operational_kpis": render_section_12_operational_kpis,
        "financial_projections": render_section_13_financial_projections,
        "recommendation": render_section_15_recommendation,
        "core_banking": render_section_8a_core_banking,
    }
    fn = _map.get(section_id)
    return fn(fact_pack) if fn else ""


def _generate_toc(section_results: dict) -> str:
    """Generate a table of contents."""
    lines = ["## Table of Contents\n"]
    for i, section in enumerate(CAM_SECTIONS):
        if section.get("skip_llm") and section["id"] in ("cover_page",):
            continue
        if section_results.get(section["id"]) == "skipped":
            continue
        mode = section_results.get(section["id"], "template")
        indicator = "🤖" if mode == "llm" else "📋"
        lines.append(f"{i}. {section['title']} {indicator}")
    lines.append("\n*🤖 = LLM-generated narrative | 📋 = Template-rendered*")
    return "\n".join(lines)


def _generation_metadata(section_results: dict, section_models: dict[str, str] | None = None) -> str:
    """Add metadata about how each section was generated (and by which model, when routed)."""
    llm_count = sum(1 for v in section_results.values() if v == "llm")
    template_count = sum(1 for v in section_results.values() if v == "template_fallback")
    total = llm_count + template_count

    lines = [
        "## Generation Metadata",
        f"- **Total narrative sections**: {total}",
        f"- **LLM-generated**: {llm_count}",
        f"- **Template fallback**: {template_count}",
        f"- **LLM coverage**: {round(llm_count/total*100) if total > 0 else 0}%",
    ]
    models = {}
    for model in (section_models or {}).values():
        models[model] = models.get(model, 0) + 1
    if len(models) > 1:
        lines.append("- **Models**: " + ", ".join(f"{m} ({n} sections)" for m, n in models.items()))
    return "\n".join(lines)
