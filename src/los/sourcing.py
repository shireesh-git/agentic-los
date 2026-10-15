"""
Prospect Sourcing document prefill (LOS Phase 4).

Reads the borrower's documents page by page and proposes values for the Prospect
Sourcing form, each with its source (document, page, snippet) and a confidence:

  extraction    labelled-field patterns over each page's text (deterministic);
  corroboration the same value found in several documents raises confidence,
                agreement with the borrower master / application raises it further,
                different values are a conflict the analyst must resolve;
  AI fallback   (optional) a configured LLM may propose values for fields the
                patterns did not find — accepted only when the value appears
                verbatim in the cited page, and labelled "ai".

Nothing is applied automatically: the analyst accepts or edits each value.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

PREFILL_VERSION = "los_prefill/v1"
_AMT = r"(?:₹|Rs\.?|INR|I)\s?([\d,]+(?:\.\d+)?)\s*(?:Cr|crore)"
_NUM = r"([\d,]+(?:\.\d+)?)"
MAX_PAGES = 12          # long filings (annual reports) are read for their opening pages only
_ANNUAL_ONLY = r"quarterly|unaudited|provisional"   # interim figures are not the latest audited year

# id, label, group, kind, patterns, application target
FIELDS: list[dict] = [
    {"id": "legal_name", "label": "Legal name", "group": "Borrower", "kind": "text",
     "patterns": [r"Legal Name:\s*(.+?)(?:\s+CIN:|\s+Incorporated:|$)",
                  r"Name of the (?:Borrower|Applicant):\s*(.+?)(?:\s+CIN:|\s+PAN:|\s+Constitution:|$)"]},
    {"id": "cin", "label": "CIN", "group": "Borrower", "kind": "id",
     "patterns": [r"CIN:\s*([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})"]},
    {"id": "pan", "label": "PAN", "group": "Borrower", "kind": "id",
     "patterns": [r"PAN:\s*([A-Z]{5}\d{4}[A-Z])"]},
    {"id": "gstin", "label": "GSTIN", "group": "Borrower", "kind": "id",
     "patterns": [r"GSTIN:?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d])"]},
    {"id": "date_of_incorporation", "label": "Date of incorporation", "group": "Borrower", "kind": "date",
     "patterns": [r"Incorporated(?: on)?:\s*(\d{1,2}[-/ ][A-Za-z]{3}[-/ ]\d{4})"]},
    {"id": "registered_address", "label": "Registered office", "group": "Borrower", "kind": "text",
     "patterns": [r"Registered Office:\s*(.+?\d{6})"]},
    {"id": "listed_exchange", "label": "Listed on", "group": "Borrower", "kind": "text",
     "patterns": [r"Listed Exchange:\s*([A-Z, ]+?)(?:\s+Corporate|\s+[A-Z][a-z]|$)"]},
    {"id": "authorised_signatory", "label": "Authorised signatory", "group": "Borrower", "kind": "text",
     "patterns": [r"Board authori[sz]es\s+(.+?)\s+to execute"]},
    {"id": "facility_type", "label": "Facility type", "group": "Proposal", "kind": "facility", "target": "facility_type",
     "patterns": [r"Facility (?:Requested|type):\s*([a-z_]+)", r"for the proposed\s+([a-z_]+)\.",
                  r"(?:Facility|Nature of Facility|Facility Type) ?(?:Proposed)?:\s*((?:Working Capital|Term Loan|Project Finance)[A-Za-z ]*?)(?=\s+[A-Z][A-Za-z ]{2,30}:|\.|$)"]},
    {"id": "case_type", "label": "Case type", "group": "Proposal", "kind": "code", "target": "case_type",
     "patterns": [r"Case Type:\s*(ETB|NTB)"]},
    {"id": "amount_cr", "label": "Proposed amount (₹ Cr)", "group": "Proposal", "kind": "amount", "target": "amount_cr",
     "patterns": [r"Amount Requested:\s*" + _AMT, r"Requested limit under review:\s*" + _AMT,
                  r"Proposed (?:Limit|Amount):\s*" + _AMT]},
    {"id": "tenor_months", "label": "Tenor (months)", "group": "Proposal", "kind": "int", "target": "tenor_months",
     "patterns": [r"Tenor:\s*(\d+)\s*months"]},
    {"id": "purpose", "label": "Purpose", "group": "Proposal", "kind": "text", "target": "purpose",
     "patterns": [r"(?<!Primary )Purpose:\s*(.+?)(?:\s+Latest Financial|\s+Credit View|\.\s|\.$|$)",
                  r"Primary purpose(?: stated by management)?:\s*(.+?)(?:\.\s|\.$|$)"]},
    {"id": "revenue_cr", "label": "Revenue — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Revenue from Operations\s+" + _NUM, r"Snapshot[^:]*:\s*Revenue\s+" + _AMT]},
    {"id": "ebitda_cr", "label": "EBITDA — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"\bEBITDA\s+" + _NUM + r"\s", r"Snapshot[^.]*?EBITDA\s+" + _AMT]},
    {"id": "pat_cr", "label": "PAT — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Profit After Tax\s+" + _NUM, r"Snapshot[^.]*?PAT\s+" + _AMT]},
    {"id": "net_worth_cr", "label": "Net worth — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Total Equity\s+" + _NUM]},
    {"id": "total_debt_cr", "label": "Total debt — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Total Debt\s+" + _NUM, r"Snapshot[^.]*?Debt\s+" + _AMT]},
    {"id": "external_rating", "label": "External rating", "group": "Rating & security", "kind": "text",
     "patterns": [r"(?:Assigned / Referenced )?Rating:\s*([A-Z]+ [A-Z+\-]+(?:/[A-Za-z]+)?)"]},
    {"id": "collateral_mv_cr", "label": "Collateral market value (₹ Cr)", "group": "Rating & security", "kind": "amount",
     "patterns": [r"collateral market value assessed at\s*" + _AMT]},
    {"id": "collateral_fsv_cr", "label": "Collateral forced-sale value (₹ Cr)", "group": "Rating & security",
     "kind": "amount", "patterns": [r"forced-sale value of\s*" + _AMT]},
]
FIELD_IDS = {f["id"] for f in FIELDS}
FACILITY_TARGETS = {f["id"]: f["target"] for f in FIELDS if f.get("target")}


# ─── Reading documents ──────────────────────────────────────────────────────

def read_documents(entity_dir: Path) -> list[dict]:
    """Each PDF under the borrower's folder: {document, category, pages: [text, ...]} (text normalised to one line)."""
    import fitz  # PyMuPDF

    docs = []
    if not entity_dir.exists():
        return docs
    for path in sorted(entity_dir.rglob("*.pdf")):
        try:
            with fitz.open(path) as pdf:
                pages = [re.sub(r"\s+", " ", pdf[i].get_text()).strip() for i in range(min(pdf.page_count, MAX_PAGES))]
        except Exception:
            continue
        docs.append({"document": path.relative_to(entity_dir).as_posix(), "category": path.parent.name,
                     "pages": pages})
    return docs


# ─── Normalising and comparing ──────────────────────────────────────────────

_FACILITY_CODES = (("working capital", "working_capital"), ("term loan", "term_loan"),
                   ("project financ", "project_finance"))


def _norm(kind: str, raw: str):
    raw = raw.strip().strip(".,;")
    if kind == "facility":                     # a CAM says "Working Capital Term Loan"; the form wants a code
        low = raw.lower().replace("_", " ")
        return next((code for words, code in _FACILITY_CODES if words in low), re.sub(r"[^a-z0-9]+", "_", low).strip("_"))
    if kind in ("amount", "int"):
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            return None
        return int(v) if kind == "int" else v
    if kind == "date":
        for fmt in ("%d-%b-%Y", "%d/%b/%Y", "%d %b %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
        return None
    return raw


def _same(kind: str, a, b) -> bool:
    if a is None or b is None:
        return False
    if kind == "amount":
        a, b = float(a), float(b)
        return abs(a - b) <= max(1.0, 0.01 * max(abs(a), abs(b)))
    if kind == "int":
        return int(a) == int(b)
    key = (lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower().replace("&", "and"))) if kind == "text" else \
        (lambda s: str(s).strip().lower())
    return key(a) == key(b)


def _display(kind: str, v) -> str:
    if v is None:
        return ""
    if kind == "amount":
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def _snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return ("…" if s else "") + text[s:e].strip() + ("…" if e < len(text) else "")


def master_values(company: Optional[dict], app: Optional[dict]) -> dict:
    """Values already on record (borrower master / the application) that extracted values are checked against."""
    out: dict = {}
    b = (company or {}).get("borrower")
    if b is not None:
        doi = getattr(b, "date_of_incorporation", None)
        out.update({"legal_name": getattr(b, "company_name", None), "cin": getattr(b, "cin", None),
                    "pan": getattr(b, "pan", None), "registered_address": getattr(b, "registered_address", None),
                    "listed_exchange": getattr(b, "listed_exchange", None),
                    "date_of_incorporation": doi.isoformat() if doi else None,
                    "external_rating": getattr(b, "credit_rating", None)})
    fins = (company or {}).get("financials") or {}
    audited = [fs for fs in fins.values() if getattr(fs, "source", "") == "audited"]
    if audited:
        li = max(audited, key=lambda fs: fs.period).line_items
        out.update({"revenue_cr": li.get("revenue_operating"), "ebitda_cr": li.get("ebitda"), "pat_cr": li.get("pat"),
                    "net_worth_cr": li.get("total_equity"), "total_debt_cr": li.get("total_debt")})
    fac = (app or {}).get("facility") or {}
    for fid, key in FACILITY_TARGETS.items():
        if fac.get(key) not in (None, ""):
            out[fid] = fac[key]
    return {k: v for k, v in out.items() if v not in (None, "")}


# ─── Prefill ────────────────────────────────────────────────────────────────

def _band(conf: float) -> str:
    return "high" if conf >= 0.85 else "medium" if conf >= 0.65 else "low" if conf > 0 else "none"


def _resolve(spec: dict, hits: list[dict], master) -> dict:
    """Choose a value from the hits and score it."""
    kind = spec["kind"]
    out = {"id": spec["id"], "label": spec["label"], "group": spec["group"], "kind": kind,
           "target": spec.get("target"), "master": _display(kind, master) if master is not None else None}
    if not hits:
        return out | {"value": None, "display": "", "confidence": 0.0, "band": "none", "status": "not_found",
                      "sources": [], "alternatives": [], "method": None,
                      "note": "Not found in the documents on file"}
    clusters: list[list[dict]] = []
    for h in hits:
        for c in clusters:
            if _same(kind, c[0]["value"], h["value"]):
                c.append(h)
                break
        else:
            clusters.append([h])
    # most documents first; on a tie, the primary source (the field's first pattern, e.g. the request note)
    clusters.sort(key=lambda c: (-len({x["document"] for x in c}), min(x.get("rank", 9) for x in c)))
    best = clusters[0]
    docs = len({h["document"] for h in best})
    value = best[0]["value"]
    method = "ai" if all(h.get("method") == "ai" for h in best) else "pattern"
    conf = min(0.92, 0.72 + 0.12 * (docs - 1)) if method == "pattern" else 0.6
    alternatives = [{"value": _display(kind, c[0]["value"]), "document": c[0]["document"], "page": c[0]["page"]}
                    for c in clusters[1:]]
    if master is not None and not _same(kind, master, value):
        alternatives.append({"value": _display(kind, master), "document": "Borrower master / application", "page": None})
    if alternatives:
        status, conf = "conflict", min(conf, 0.45)
        note = "Documents disagree — confirm the correct value"
    elif master is not None:
        status, conf = "matches_record", min(0.98, conf + 0.06 + (0.1 if docs == 1 else 0))
        note = "Matches the borrower master / application"
    elif docs > 1:
        status, note = "corroborated", f"Found consistently in {docs} documents"
    else:
        status, note = "single_source", "Single document — confirm before use"
    if method == "ai":
        note = "AI-proposed (value verified verbatim in the cited page) — " + note[0].lower() + note[1:]
    return out | {"value": value, "display": _display(kind, value), "confidence": round(conf, 2),
                  "band": _band(conf), "status": status, "method": method, "note": note,
                  "sources": [{k: h[k] for k in ("document", "category", "page", "snippet")} for h in best],
                  "alternatives": alternatives}


def extract_hits(docs: list[dict]) -> dict[str, list[dict]]:
    hits: dict[str, list[dict]] = {f["id"]: [] for f in FIELDS}
    for spec in FIELDS:
        for doc in docs:
            if spec["group"] == "Financials" and re.search(_ANNUAL_ONLY, doc["document"], re.I):
                continue
            hit = _first_hit(spec, doc)
            if hit:
                hits[spec["id"]].append(hit)
    return hits


def _first_hit(spec: dict, doc: dict) -> Optional[dict]:
    """The first labelled value for the field in the document (one per document)."""
    for pno, text in enumerate(doc["pages"][:MAX_PAGES], start=1):
        for rank, pat in enumerate(spec["patterns"]):
            m = re.search(pat, text)
            value = _norm(spec["kind"], m.group(1)) if m else None
            if value not in (None, ""):
                return {"value": value, "document": doc["document"], "category": doc["category"], "page": pno,
                        "snippet": _snippet(text, m.start(), m.end()), "method": "pattern", "rank": rank}
    return None


AI_SYSTEM_PROMPT = """You extract fields from Indian bank loan documents. You are given page texts, each tagged with
its document and page number, and a list of fields to find. For each field you can find, copy the value EXACTLY as it
appears in the text (no reformatting, no calculation) and cite the document and page. Omit fields you cannot find.
Return ONLY a JSON object: {"fields": [{"id": "...", "value": "...", "document": "...", "page": 1}]}"""


def ai_hits(docs: list[dict], missing: list[dict], llm) -> dict[str, list[dict]]:
    """LLM proposals for fields the patterns missed; each must appear verbatim in the cited page."""
    from src.services.observation_narrator import _parse_json_object

    pages = {(d["document"], i): t for d in docs for i, t in enumerate(d["pages"][:MAX_PAGES], start=1)}
    corpus = "\n\n".join(f"[{doc} p{pno}] {text[:1500]}" for (doc, pno), text in list(pages.items())[:40])
    wanted = [{"id": f["id"], "label": f["label"]} for f in missing]
    data = _parse_json_object(llm.generate(prompt=f"Fields: {json.dumps(wanted)}\n\nPages:\n{corpus}",
                                           system_prompt=AI_SYSTEM_PROMPT, temperature=0.0, max_tokens=800))
    kinds = {f["id"]: f["kind"] for f in missing}
    out: dict[str, list[dict]] = {}
    for item in data.get("fields") or []:
        fid, raw = item.get("id"), str(item.get("value") or "").strip()
        try:
            key = (str(item.get("document")), int(item.get("page")))
        except (TypeError, ValueError):
            continue
        text = pages.get(key)
        if fid not in kinds or not raw or not text or raw not in text:      # verbatim check
            continue
        value = _norm(kinds[fid], re.sub(r"^(?:₹|Rs\.?|INR)\s?|\s*(?:Cr|crore)$", "", raw))
        if value in (None, ""):
            continue
        i = text.index(raw)
        out.setdefault(fid, []).append({"value": value, "document": key[0], "page": key[1], "method": "ai",
                                        "category": key[0].split("/")[0], "snippet": _snippet(text, i, i + len(raw))})
    return out


def build_prefill(docs: list[dict], master: dict, llm_factory: Optional[Callable] = None,
                  now: Optional[datetime] = None) -> dict:
    hits = extract_hits(docs)
    ai = {"used": False, "status": "not_configured", "model": None}
    missing = [f for f in FIELDS if not hits[f["id"]]]
    if llm_factory and missing and docs:
        llm = llm_factory()
        if getattr(llm, "name", "") == "mock":
            ai["status"] = "skipped (the active LLM provider is 'mock')"
        else:
            try:
                for fid, found in ai_hits(docs, missing, llm).items():
                    hits[fid].extend(found)
                ai.update(used=True, status="ok", model=getattr(llm, "model", None) or getattr(llm, "name", "llm"))
            except Exception as e:                                         # the deterministic prefill stands
                ai.update(status=f"failed: {e}")
    engine = "Pattern extraction with cross-document corroboration" + (" + AI fallback" if ai["used"] else "")
    return finish_prefill(docs, hits, master, ai, engine, now)


def finish_prefill(docs: list[dict], hits: dict[str, list[dict]], master: dict, ai: dict, engine: str,
                   now: Optional[datetime] = None, specs: Optional[list[dict]] = None) -> dict:
    """Resolve every field from its hits (corroboration, conflicts, record match) into the prefill
    record the Prospect Sourcing screen shows. Shared by build_prefill and the intake agent
    (``specs``: another field set, e.g. the post-sanction and disbursement documents)."""
    fields = [_resolve(spec, hits.get(spec["id"]) or [], master.get(spec["id"])) for spec in (specs or FIELDS)]
    per_doc: dict[str, int] = {}
    for f in fields:
        for s in f["sources"]:
            per_doc[s["document"]] = per_doc.get(s["document"], 0) + 1
    count = lambda pred: sum(1 for f in fields if pred(f))
    return {
        "version": PREFILL_VERSION,
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "engine": engine,
        "ai": ai,
        "documents": [{"document": d["document"], "category": d["category"], "pages": len(d["pages"]),
                       "fields_found": per_doc.get(d["document"], 0)} for d in docs],
        "fields": fields,
        "summary": {"total": len(fields), "found": count(lambda f: f["status"] != "not_found"),
                    "high": count(lambda f: f["band"] == "high"), "medium": count(lambda f: f["band"] == "medium"),
                    "low": count(lambda f: f["band"] == "low"), "conflicts": count(lambda f: f["status"] == "conflict"),
                    "not_found": count(lambda f: f["status"] == "not_found")},
    }
