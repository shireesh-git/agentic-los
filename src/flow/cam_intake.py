"""
CAM intake agent: reads a Credit Appraisal Memorandum (the bank's own CAM, uploaded as a PDF) — its
sections and labelled values, each with the page and the text it was read from. The LOS turns the reading
into credit data fields (src/flow/datapoints.py, from_reading).

    sections   the CAM's headings (numbered or not) mapped to the narratives, security, key terms, covenants,
               deviations and the recommendation; headings the patterns do not know can be mapped by the
               LLM, accepted only for headings that exist in the document
    labels     "Sector:", "Banking Arrangement:", "Internal Rating:", "Recommended Limit:", "Pricing:" and the
               financial highlights
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from src.flow import doc_patterns as src

CAM_CATEGORY = "cam"

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

# the financial-highlights table: row labels, and the year columns (the latest actual year is taken)
_ROW = {"revenue_cr": r"(?:revenue from operations|net (?:sales|revenue)|total (?:operating )?income|"
                      r"operating income|revenue|turnover|net sales)",
        "ebitda_cr": r"(?:ebitda|pbdit|operating profit(?: \(ebitda\))?)",
        "pat_cr": r"(?:profit after tax|pat|net profit)",
        "net_worth_cr": r"(?:(?:tangible |adjusted )?net worth|tnw)",
        "total_debt_cr": r"(?:total (?:debt|borrowings?)|borrowings|total outside debt)"}
_NUM = r"\(?-?[\d,]+(?:\.\d+)?\)?"
_YEAR = re.compile(r"\b(?:FY\s?'?(\d{2,4})(?:\s?-\s?\d{2})?|(20\d{2})\s?-\s?(\d{2,4})|(?:Mar(?:ch)?|31[.\-/ ]0?3[.\-/ ])\s?'?-?(\d{2,4}))"
                   r"(\s*\((?:P|E|Proj|Est|Projected|Estimated|B|Budget)\)|\s+(?:Projected|Estimated|Proj|Est))?", re.I)


def _year(m: re.Match) -> Optional[int]:
    y = m.group(1) or m.group(3) or m.group(4)
    if m.group(2) and not m.group(3):
        y = m.group(2)
    if not y:
        return None
    y = int(y)
    return y + 2000 if y < 100 else y


def _num(s: str) -> Optional[float]:
    neg = s.startswith("(") or s.startswith("-")
    try:
        v = float(s.strip("()-").replace(",", ""))
    except ValueError:
        return None
    return -v if neg else v


def read_financial_table(pages: list[list[str]]) -> dict[str, dict]:
    """The latest actual year's figures from a CAM's financial-highlights table, whether the PDF text puts a row
    on one line ("Revenue 5,121.74 6,051.88 5,666.68") or each cell on its own line. Projected / estimated
    columns are skipped; a row whose cell count does not match the year header is not read (never guessed)."""
    out: dict[str, dict] = {}
    for pno, lines in enumerate(pages, start=1):
        cells = [ln.strip() for ln in lines if ln.strip()]
        i = 0
        while i < len(cells):
            # a year header: consecutive year cells, or one line holding several years
            years, j = [], i
            on_line = list(_YEAR.finditer(cells[i]))
            if len(on_line) >= 2:
                years, j = on_line, i + 1
            else:
                while j < len(cells) and (m := _YEAR.fullmatch(cells[j])):
                    years.append(m)
                    j += 1
            if len(years) < 2:
                i += 1
                continue
            cols = [(_year(m), bool(m.group(5))) for m in years]
            actual = [n for n, (y, proj) in enumerate(cols) if y and not proj]
            if not actual:
                i = j
                continue
            pick = max(actual, key=lambda n: cols[n][0])
            head = " ".join(cells[max(i - 3, 0):j]).lower()
            scale = (0.01 if re.search(r"lakhs?|lacs?", head) else 0.1 if re.search(r"millions?|\bmn\b", head)
                     else 1.0)
            k = j
            while k < len(cells) and not (len(list(_YEAR.finditer(cells[k]))) >= 2 or _YEAR.fullmatch(cells[k])):
                label = re.sub(r"\s*\((?:rs|₹|inr)[^)]*\)|\s*\(%\)|\s*\(x\)", "", cells[k], flags=re.I)
                m = re.match(rf"^\s*([A-Za-z][A-Za-z ()/&.\-]*?)\s*((?:{_NUM}\s*)*)$", label)
                if not m:
                    k += 1
                    continue
                name, nums = m.group(1).strip(), re.findall(_NUM, m.group(2))
                n = k + 1
                while len(nums) < len(cols) and n < len(cells) and re.fullmatch(_NUM, cells[n]):
                    nums.append(cells[n])
                    n += 1
                fid = next((f for f, p in _ROW.items() if re.fullmatch(p, name, re.I)), None)
                if fid and fid not in out and len(nums) == len(cols):
                    v = _num(nums[pick])
                    if v is not None:
                        out[fid] = {"value": round(v * scale, 2), "page": pno, "year": f"FY{cols[pick][0]}",
                                    "snippet": f"{name}: {' | '.join(nums)} (FY{cols[pick][0]} column)"}
                k = n if n > k + 1 else k + 1
            i = k
    return out


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
    table = read_financial_table(pages)
    for fid in FINANCIALS:
        spec = next(s for s in src.FIELDS if s["id"] == fid)
        hit = table.get(fid) or src._first_hit(spec, doc)
        if hit:
            labels[f"cam.financials.{fid}"] = {"value": hit["value"], "page": hit["page"], "snippet": hit["snippet"]}
    return {"document": document, "pages": len(pages), "sections": sections, "labels": labels, "ai": ai,
            "summary": {"sections": len(sections), "narratives": sum(1 for k in NARRATIVE_KEYS if k in sections),
                        "labels": len(labels)}}
