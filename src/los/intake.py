"""
Document intake agent: reads a borrower's documents in parallel and proposes the
Prospect Sourcing fields, each with its document, page, snippet and confidence.

    documents   fan-out per PDF: page text; a page with no text layer (a scan) is
                transcribed by the vision model when one is configured (pages in parallel)
    patterns    fan-out per document: labelled-field patterns (src/los/sourcing.py)
    ai_fallback fields the patterns missed: a schema-validated LLM extraction whose
                values must appear verbatim on the cited page
    resolve     corroboration across documents, conflicts, agreement with the record

The result has the shape of the sourcing prefill (the review screen is unchanged) plus
``intake`` (how the graph ran). ``proposals_from_prefill`` turns it into field-store
proposals so Prospect Sourcing counts in the populate / verify metrics.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.agentic.graph import AgentGraph, Node
from src.engines.data_provenance import NOT_AVAILABLE
from src.los import sourcing as src

log = logging.getLogger(__name__)

VISION_MIN_CHARS = 40          # a page with less text than this is treated as a scan
MAX_VISION_PAGES = 4           # per document: vision transcription is slow and costly
VISION_DPI = 110

_TRANSCRIBE = {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}
_EXTRACT = {"type": "object", "required": ["fields"], "properties": {"fields": {"type": "array", "maxItems": 30, "items": {
    "type": "object", "required": ["id", "value", "document", "page"],
    "properties": {"id": {"type": "string"}, "value": {"type": "string"}, "document": {"type": "string"},
                   "page": {"type": "integer"}}}}}}


def _vision_ready(llm) -> bool:
    return bool(llm is not None and getattr(llm, "supports_vision", False) and getattr(llm, "supports_structured", False))


def read_pdf(path: Path, root: Path, llm=None) -> dict:
    """One document: its page texts (scanned pages transcribed by the vision model when available)."""
    import fitz  # PyMuPDF

    with fitz.open(path) as pdf:
        n = min(pdf.page_count, src.MAX_PAGES)
        pages = [re.sub(r"\s+", " ", pdf[i].get_text()).strip() for i in range(n)]
        scanned = [i for i, t in enumerate(pages) if len(t) < VISION_MIN_CHARS]
        images = {i: pdf[i].get_pixmap(dpi=VISION_DPI).tobytes("png")
                  for i in scanned[:MAX_VISION_PAGES]} if _vision_ready(llm) else {}
    vision_pages, vision_errors = [], []

    def transcribe(i: int):
        out = llm.generate_structured(
            "Transcribe all the text on this page of a loan document exactly as written, in reading order.",
            _TRANSCRIBE, images=[{"mime": "image/png", "data": images[i]}], max_tokens=2000)
        return i, re.sub(r"\s+", " ", out["text"]).strip()

    if images:
        with ThreadPoolExecutor(max_workers=len(images), thread_name_prefix="intake-vision") as pool:
            for fut in [pool.submit(transcribe, i) for i in images]:
                try:
                    i, text = fut.result()
                    pages[i] = text
                    vision_pages.append(i + 1)
                except Exception as e:                    # the page stays unread; reported, never invented
                    vision_errors.append(str(e)[:200])
    return {"document": path.relative_to(root).as_posix(), "category": path.parent.name, "pages": pages,
            "scanned_pages": [i + 1 for i in scanned], "vision_pages": sorted(vision_pages),
            "vision_errors": vision_errors}


def _doc_hits(doc: dict, specs: Optional[list[dict]] = None) -> dict[str, dict]:
    """Pattern hits in one document: {field id: hit}."""
    out = {}
    for spec in specs or src.FIELDS:
        if spec["group"] == "Financials" and re.search(src._ANNUAL_ONLY, doc["document"], re.I):
            continue                                       # interim filings never feed annual figures
        hit = src._first_hit(spec, doc)
        if hit:
            out[spec["id"]] = hit
    return out


def _ai_hits(docs: list[dict], missing: list[dict], llm) -> dict[str, list[dict]]:
    """Schema-validated LLM extraction for the missing fields; a value is kept only when it
    appears verbatim on the page it cites."""
    pages = {(d["document"], i): t for d in docs for i, t in enumerate(d["pages"][:src.MAX_PAGES], start=1)}
    corpus = "\n\n".join(f"[{doc} p{pno}] {text[:1500]}" for (doc, pno), text in list(pages.items())[:40])
    wanted = [{"id": f["id"], "label": f["label"]} for f in missing]
    data = llm.generate_structured(f"Fields to find: {wanted}\n\nPages:\n{corpus}", _EXTRACT,
                                   system_prompt=src.AI_SYSTEM_PROMPT, max_tokens=900)
    kinds = {f["id"]: f["kind"] for f in missing}
    out: dict[str, list[dict]] = {}
    for item in data.get("fields") or []:
        fid, raw = item.get("id"), str(item.get("value") or "").strip()
        text = pages.get((str(item.get("document")), int(item.get("page") or 0)))
        if fid not in kinds or not raw or not text or raw not in text:          # verbatim check
            continue
        value = src._norm(kinds[fid], re.sub(r"^(?:₹|Rs\.?|INR)\s?|\s*(?:Cr|crore)$", "", raw))
        if value in (None, ""):
            continue
        i = text.index(raw)
        out.setdefault(fid, []).append({"value": value, "document": item["document"], "page": int(item["page"]),
                                        "method": "ai", "category": str(item["document"]).split("/")[0],
                                        "snippet": src._snippet(text, i, i + len(raw))})
    return out


def run_intake(root: Path, master: dict, llm=None, now: Optional[datetime] = None,
               specs: Optional[list[dict]] = None) -> dict:
    """Read every PDF under ``root`` and propose the fields in ``specs`` (default: the Prospect
    Sourcing fields; see the module docstring)."""
    root = Path(root)
    specs = specs or src.FIELDS
    paths = sorted(root.rglob("*.pdf")) if root.exists() else []

    def read_one(ctx, path):
        return read_pdf(path, root, llm)

    def docs_of(ctx) -> list[dict]:
        return list((ctx["results"].get("documents") or {}).values())

    def ai_fallback(ctx):
        hits = ctx["results"].get("patterns") or {}
        found = {fid for per_doc in hits.values() for fid in per_doc}
        missing = [f for f in specs if f["id"] not in found]
        if not missing or not docs_of(ctx):
            return {"status": "not_needed", "hits": {}}
        if llm is None or not getattr(llm, "supports_structured", False):
            return {"status": "skipped (no model output configured)", "hits": {}}
        return {"status": "ok", "hits": _ai_hits(docs_of(ctx), missing, llm),
                "model": getattr(llm, "model_id", None) or getattr(llm, "name", "llm")}

    nodes = [
        Node("documents", fan_out=lambda ctx: paths, run_item=read_one,
             item_key=lambda p: p.relative_to(root).as_posix(), lane="read", description="read each document"),
        Node("patterns", fan_out=docs_of, run_item=lambda ctx, d: _doc_hits(d, specs), item_key=lambda d: d["document"],
             requires=("documents",), lane="extract", description="labelled-field extraction per document"),
        Node("ai_fallback", run=ai_fallback, requires=("documents",), waits_for=("patterns",), lane="llm",
             description="schema-validated AI extraction of missing fields (verbatim-checked)"),
    ]
    graph = AgentGraph(nodes, name="document-intake")
    ctx: dict = {}
    run = graph.run(ctx)
    docs = docs_of(ctx)
    hits: dict[str, list[dict]] = {f["id"]: [] for f in specs}
    for per_doc in (run.data("patterns") or {}).values():
        for fid, hit in per_doc.items():
            hits[fid].append(hit)
    ai_result = run.data("ai_fallback") or {"status": "failed", "hits": {}}
    if run.results.get("ai_fallback") and run.results["ai_fallback"].status == "failed":
        ai_result = {"status": f"failed: {run.results['ai_fallback'].error}", "hits": {}}
    for fid, extra in (ai_result.get("hits") or {}).items():
        hits[fid].extend(extra)
    ai = {"used": bool(ai_result.get("hits")), "status": ai_result["status"], "model": ai_result.get("model")}
    vision = [p for d in docs for p in d.get("vision_pages", [])]
    engine = ("Document intake agent: parallel reading and extraction with cross-document corroboration"
              + (" + vision transcription of scanned pages" if vision else "") + (" + AI fallback" if ai["used"] else ""))
    prefill = src.finish_prefill(docs, hits, master, ai, engine, now, specs)
    unread = [f"{d['document']} p{p}" for d in docs for p in d["scanned_pages"] if p not in d["vision_pages"]]
    prefill["intake"] = {
        "documents": len(paths), "duration_ms": run.duration_ms, "max_concurrency": run.max_concurrency,
        "lanes": [{"node": e["agent_name"], "status": e["status"], "ms": e["duration_ms"],
                   "parallel": (e["diagnostics"] or {}).get("fan_out")} for e in run.log()],
        "scanned_pages": sum(len(d["scanned_pages"]) for d in docs), "vision_pages": len(vision),
        "unread_pages": unread[:20],
        "note": (None if not unread else
                 "Some scanned pages could not be read automatically — check them yourself (to read them, "
                 "turn on a vision model or install OCR)"),
    }
    return prefill


# ── field store ──────────────────────────────────────────────────────────────

def field_id(spec_or_field: dict, domain: str = "sourcing") -> str:
    group = re.sub(r"[^a-z0-9]+", "_", spec_or_field["group"].lower()).strip("_")
    return f"{domain}.{group}.{spec_or_field['id']}"


def proposals_from_prefill(prefill: dict, domain: str = "sourcing") -> list[dict]:
    """The prefill's fields as field-store proposals (domain ``sourcing`` by default, verified at
    Prospect Sourcing; ``post_sanction`` / ``disbursement`` for the later-stage documents)."""
    out = []
    for f in prefill.get("fields") or []:
        base = {"field_id": field_id(f, domain), "domain": domain, "label": f["label"], "resolver": "document_intake",
                "run_id": prefill.get("generated_at")}
        if f["status"] == "not_found":
            out.append(base | {"value": NOT_AVAILABLE, "provenance": "unavailable", "source": "record",
                               "evidence": {"path": "documents on file"}, "confidence": 0.0})
            continue
        first = (f.get("sources") or [{}])[0]
        issues = ([f"Documents disagree: {', '.join(a['value'] + ' (' + str(a['document']) + ')' for a in f['alternatives'][:3])}"]
                  if f["status"] == "conflict" else [])
        out.append(base | {"value": f["display"], "provenance": "ai" if f.get("method") == "ai" else "source",
                           "source": "document", "confidence": f["confidence"], "issues": issues,
                           "evidence": {"document": first.get("document"), "page": first.get("page"),
                                        "snippet": first.get("snippet"), "category": first.get("category"),
                                        "corroborating_documents": len({s["document"] for s in f.get("sources") or []})}})
    return out
