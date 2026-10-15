"""
CAM intake agent: reads a Credit Appraisal Memorandum (the bank's own CAM, uploaded as a PDF)
and proposes the IP-stage fields it covers, each with the CAM section, page and the text it
was read from.

    identity / facility   handled by the document intake agent: the CAM is read with the
                          borrower's other documents, so CAM-vs-document disagreements are
                          ordinary conflicts (src/los/intake.py)
    sections              the CAM's headings (numbered or not) mapped to the proposal
                          narratives, security, key terms, covenants, deviations and the
                          recommendation; headings the patterns do not know can be mapped by
                          the LLM, accepted only for headings that exist in the document
    labels                "Sector:", "Banking Arrangement:", "Internal Rating:",
                          "Recommended Limit:", "Pricing:" and the financial highlights

``resolver`` turns a stored reading into field-store proposals for the population graph,
checking the CAM's figures against the borrower record so a CAM that disagrees with the
audited statements is flagged instead of silently accepted.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from src.los import sourcing as src

log = logging.getLogger(__name__)

CAM_CATEGORY = "cam"
RESOLVER = "cam_document"

# section key → heading patterns (matched against a whole heading line, numbering removed)
SECTIONS: dict[str, list[str]] = {
    "borrower_and_business": [r"borrower and business(?: background)?", r"business background",
                              r"background of the (?:borrower|company)", r"(?:company|borrower) (?:background|profile|overview)",
                              r"about the (?:company|borrower)"],
    "industry_outlook": [r"industry (?:outlook|analysis|overview|scenario)", r"sector outlook"],
    "marketing_arrangements": [r"(?:details of )?marketing arrangements?"],
    "corporate_governance": [r"corporate governance(?: and management)?", r"management(?: profile)?(?: and corporate governance)?",
                             r"promoters? and management"],
    "strengths": [r"(?:key )?strengths(?: and weaknesses)?"],
    "weaknesses": [r"(?:key )?weaknesses"],
    "key_risks": [r"(?:key )?risks?(?: and mitigants)?", r"risk factors", r"risk analysis"],
    "financial_highlights": [r"financial (?:highlights|performance|analysis)"],
    "security": [r"security(?: details| offered| proposed| and collateral)?", r"collateral(?: security)?"],
    "key_terms": [r"(?:key |major )?terms (?:and|&) conditions", r"key terms"],
    "covenants": [r"(?:financial )?covenants"],
    "deviations": [r"(?:policy )?deviations?(?: from (?:the )?policy)?"],
    "recommendation": [r"(?:final )?recommendations?"],
}
NARRATIVE_KEYS = ("borrower_and_business", "industry_outlook", "marketing_arrangements", "corporate_governance",
                  "strengths", "weaknesses", "key_risks")
NARRATIVE_LABELS = {"borrower_and_business": "Borrower and business", "industry_outlook": "Industry outlook",
                    "marketing_arrangements": "Marketing arrangements", "corporate_governance": "Corporate governance",
                    "strengths": "Strengths", "weaknesses": "Weaknesses", "key_risks": "Key risks"}
# other sections → (field id, label)
SECTION_FIELDS = {"security": ("cam.security.summary", "Security (as in the CAM)"),
                  "key_terms": ("cam.terms.key_terms", "Key terms and conditions (as in the CAM)"),
                  "covenants": ("cam.terms.covenants", "Covenants (as in the CAM)"),
                  "deviations": ("cam.decision.deviations", "Deviations (as in the CAM)"),
                  "recommendation": ("cam.decision.recommendation", "Recommendation (as in the CAM)")}

_VALUE = r"\s*[:\-]\s*(.+?)(?=\s{2,}|\s+[A-Z][A-Za-z()/\- ]{2,40}:|$)"
LABELS: list[dict] = [
    {"id": "cam.profile.sector", "label": "Sector (as in the CAM)", "kind": "text", "pattern": r"(?<![-\w])Sector" + _VALUE},
    {"id": "cam.profile.subsector", "label": "Sub-sector (as in the CAM)", "kind": "text", "pattern": r"Sub-?\s?sector" + _VALUE},
    {"id": "cam.profile.constitution", "label": "Constitution (as in the CAM)", "kind": "text", "pattern": r"Constitution" + _VALUE},
    {"id": "cam.profile.banking_arrangement", "label": "Banking arrangement (as in the CAM)", "kind": "text",
     "pattern": r"Banking Arrangement" + _VALUE},
    {"id": "cam.rating.internal_rating", "label": "Internal rating (as in the CAM)", "kind": "text",
     "pattern": r"Internal (?:Risk )?Rating(?: \([^)]*\))?" + _VALUE},
    {"id": "cam.rating.external_rating", "label": "External rating (as in the CAM)", "kind": "text",
     "pattern": r"External (?:Credit )?Rating" + _VALUE},
    {"id": "cam.proposal.recommended_cr", "label": "Recommended limit (₹ Cr, as in the CAM)", "kind": "amount",
     "pattern": r"Recommended (?:Limit|Amount)\s*:\s*" + src._AMT},
    {"id": "cam.pricing.pricing", "label": "Pricing (as in the CAM)", "kind": "text",
     "pattern": r"(?:Pricing|Proposed (?:ROI|Rate of Interest))" + _VALUE},
]
# the financial highlights the CAM states, compared with the borrower record by the resolver
FINANCIALS = {"revenue_cr": ("Revenue", "revenue_operating"), "ebitda_cr": ("EBITDA", "ebitda"),
              "pat_cr": ("PAT", "pat"), "net_worth_cr": ("Net worth", "total_equity"),
              "total_debt_cr": ("Total debt", "total_debt")}

_HEADING_SCHEMA = {"type": "object", "required": ["map"], "properties": {"map": {"type": "array", "maxItems": 30, "items": {
    "type": "object", "required": ["heading", "key"],
    "properties": {"heading": {"type": "string"}, "key": {"type": "string", "enum": [*SECTIONS, "none"]}}}}}}


# ── reading ──────────────────────────────────────────────────────────────────

def _strip_heading(line: str) -> str:
    s = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)]|[IVXivx]+[.)])\s+", "", line.strip())
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)                       # "Financial Highlights (Rs Crore)"
    return s.strip(" :-–").strip()


def _match_section(line: str) -> Optional[str]:
    s = _strip_heading(line)
    if not s or len(s) > 70:
        return None
    for key, patterns in SECTIONS.items():
        if any(re.fullmatch(p, s, re.I) for p in patterns):
            return key
    return None


def _candidate_heading(line: str) -> bool:
    """A short line that looks like a heading (numbered or Title Case, no label value)."""
    s = line.strip()
    if not (3 <= len(s) <= 70) or s.endswith((".", ",")) or (":" in s and not s.endswith(":")):
        return False
    return bool(re.match(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?[A-Z]", s)) and len(s.split()) <= 9


def _join(lines: list[str]) -> str:
    out: list[str] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and not re.match(r"^(?:[•\-–*]|\d+[.)])\s", ln):
            out[-1] = out[-1] + " " + ln
        else:
            out.append(ln)
    return "\n".join(out).strip()


def read_lines(path: Path) -> list[list[str]]:
    import fitz  # PyMuPDF

    with fitz.open(path) as pdf:
        return [pdf[i].get_text().splitlines() for i in range(min(pdf.page_count, 40))]


def read_cam(path: Path, root: Optional[Path] = None, llm=None) -> dict:
    """One CAM document → its sections and labelled values, with page references."""
    path = Path(path)
    pages = read_lines(path)
    document = path.relative_to(root).as_posix() if root else path.name
    lines = [(pno, ln) for pno, page in enumerate(pages, start=1) for ln in page]

    heads = [(i, key) for i, (_, ln) in enumerate(lines) if (key := _match_section(ln))]
    ai = {"used": False, "status": "not_needed"}
    known = {k for _, k in heads}
    missing = [k for k in SECTIONS if k not in known]
    if missing and llm is not None and getattr(llm, "supports_structured", False):
        cands = [(i, ln.strip()) for i, (_, ln) in enumerate(lines) if _candidate_heading(ln)
                 and i not in {h for h, _ in heads}]
        if cands:
            try:
                out = llm.generate_structured(
                    "These are headings from a bank's Credit Appraisal Memorandum. Map each to the section it "
                    f"introduces, one of {list(SECTIONS)}, or 'none'.\n\nHeadings:\n"
                    + "\n".join(h for _, h in cands[:60]), _HEADING_SCHEMA, max_tokens=800)
                by_text = {h: i for i, h in cands}
                for item in out.get("map") or []:
                    i = by_text.get(str(item.get("heading") or "").strip())     # only headings that exist
                    if i is not None and item.get("key") in missing:
                        heads.append((i, item["key"]))
                        missing.remove(item["key"])
                ai = {"used": True, "status": "ok", "model": getattr(llm, "model_id", None)}
            except Exception as e:                       # headings stay unmapped; never guessed
                ai = {"used": False, "status": f"failed: {str(e)[:120]}"}
    heads.sort()
    sections: dict[str, dict] = {}
    for n, (i, key) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        body = _join([ln for _, ln in lines[i + 1:end]])
        if key in sections or not body:
            continue
        sections[key] = {"heading": lines[i][1].strip(), "page": lines[i][0], "text": body}

    flat = [re.sub(r"\s+", " ", " ".join(p)).strip() for p in pages]
    labels: dict[str, dict] = {}
    for spec in LABELS:
        for pno, (page_lines, text) in enumerate(zip(pages, flat), start=1):
            m = next((m for ln in page_lines if (m := re.search(spec["pattern"], ln.strip(), re.I))), None)
            if not m:
                continue
            value = src._norm(spec["kind"], m.group(1))
            if value in (None, ""):
                continue
            labels[spec["id"]] = {"value": value, "page": pno, "snippet": m.group(0).strip()[:200]}
            break
    doc = {"document": document, "category": CAM_CATEGORY, "pages": flat}
    for fid in FINANCIALS:
        spec = next(s for s in src.FIELDS if s["id"] == fid)
        hit = src._first_hit(spec, doc)
        if hit:
            labels[f"cam.financials.{fid}"] = {"value": hit["value"], "page": hit["page"], "snippet": hit["snippet"]}
    return {"document": document, "pages": len(pages), "sections": sections, "labels": labels, "ai": ai,
            "summary": {"sections": len(sections), "narratives": sum(1 for k in NARRATIVE_KEYS if k in sections),
                        "labels": len(labels)}}


def read_cams(root: Path, llm=None) -> Optional[dict]:
    """The CAM among a borrower's (or a staging set's) documents: the PDFs filed under ``cam/``."""
    root = Path(root)
    paths = sorted((root / CAM_CATEGORY).glob("*.pdf")) if (root / CAM_CATEGORY).exists() else []
    if not paths:
        return None
    reading = read_cam(paths[-1], root, llm)                     # the latest CAM filed wins
    reading["cams_on_file"] = [p.relative_to(root).as_posix() for p in paths]
    return reading


# ── field-store proposals ────────────────────────────────────────────────────

def _evidence(reading: dict, page: int, snippet: str, section: Optional[str] = None) -> dict:
    return {"document": reading["document"], "page": page, "snippet": snippet[:240], "section": section,
            "category": CAM_CATEGORY}


def proposals(reading: Optional[dict], run_id: Optional[str] = None) -> list[dict]:
    """The reading as field-store proposals: narratives into the proposal workspace, the rest into
    the ``cam`` domain (verified at the IP / AP Note)."""
    if not reading:
        return []
    out = []
    base = {"provenance": "source", "source": "document", "resolver": RESOLVER, "run_id": run_id, "issues": []}
    for key in NARRATIVE_KEYS:
        s = (reading.get("sections") or {}).get(key)
        if s:
            out.append(base | {"field_id": f"narrative.background.{key}", "domain": "narrative",
                               "label": NARRATIVE_LABELS[key], "value": s["text"], "confidence": 0.9,
                               "target": ["proposal", "background", key], "value_type": "text",
                               "evidence": _evidence(reading, s["page"], s["text"], s["heading"])})
    for key, (fid, label) in SECTION_FIELDS.items():
        s = (reading.get("sections") or {}).get(key)
        if s:
            out.append(base | {"field_id": fid, "domain": "cam", "label": label, "value": s["text"], "confidence": 0.9,
                               "evidence": _evidence(reading, s["page"], s["text"], s["heading"])})
    labels = {**{s["id"]: s["label"] for s in LABELS},
              **{f"cam.financials.{k}": f"{v[0]} — latest year (₹ Cr, as in the CAM)" for k, v in FINANCIALS.items()}}
    for fid, hit in (reading.get("labels") or {}).items():
        out.append(base | {"field_id": fid, "domain": "cam", "label": labels.get(fid, fid), "value": hit["value"],
                           "confidence": 0.9, "value_type": "number" if isinstance(hit["value"], float) else "text",
                           "evidence": _evidence(reading, hit["page"], hit["snippet"])})
    return out


def resolver(reading: Optional[dict], ctx: dict) -> list[dict]:
    """Population-graph resolver: the stored CAM reading, its figures checked against the record
    (the latest audited statements and the requested facility). A disagreement is an issue on the
    proposal, so it is never pre-ticked and the verifier sees both values."""
    props = proposals(reading, (reading or {}).get("read_at"))
    if not props:
        return []
    fins = (ctx.get("company") or {}).get("financials") or {}
    audited = [fs for fs in fins.values() if getattr(fs, "source", "") == "audited"]
    record = max(audited, key=lambda fs: fs.period).line_items if audited else {}
    for p in props:
        key = p["field_id"].rsplit(".", 1)[-1]
        if p["domain"] == "cam" and key in FINANCIALS and isinstance(p["value"], (int, float)):
            rec = record.get(FINANCIALS[key][1])
            if isinstance(rec, (int, float)) and not src._same("amount", p["value"], rec):
                p["issues"].append(f"The CAM states {p['value']:,.2f}; the borrower's audited statements show "
                                   f"{rec:,.2f} — confirm which is right")
    return props
