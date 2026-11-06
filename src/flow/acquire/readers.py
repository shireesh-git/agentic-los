"""
Document readers: the fallback when a source's API is inactive. Each reader turns an
uploaded document into the same envelope the API connector would return
(``connectors.envelope``), with ``provenance.via = "document"`` and the page it read.

Reading is deterministic first (statement layouts, label: value forms, tables); the AI
model is used where the layout is unknown or the deterministic reading does not
reconcile, and its reading is accepted only if it passes the same checks.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from src.flow.acquire.connectors import envelope, name_score

log = logging.getLogger(__name__)

NUM = r"\(?-?[\d,]+(?:\.\d+)?\)?|-(?=\s*\|)"


# ── text ─────────────────────────────────────────────────────────────────────

def page_texts(path: Path) -> list[str]:
    import pymupdf
    with pymupdf.open(str(path)) as doc:
        return [p.get_text() for p in doc]


def joined(text: str) -> str:
    """A page as one line of cells: 'Label | 12 | 1,234 | 5,678 | Next label ...'."""
    return " | ".join(s for s in (re.sub(r"[\t ]+", " ", ln).strip() for ln in text.splitlines()) if s)


def to_num(tok: str) -> float:
    t = tok.strip()
    if t in ("-", ""):
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    v = float(t.strip("()").replace(",", ""))
    return -v if neg else v


def _doc(path: Path, page: Optional[int] = None, **extra) -> dict:
    return {"via": "document", "document": path.name, "page": page, **extra}


def identity_in(text: str) -> dict:
    """Identifiers printed in a document (to check it is about this borrower)."""
    cin = re.search(r"\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b", text)
    gstin = re.search(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", text)
    pan = re.search(r"\bPAN\b[^A-Z0-9]{0,12}([A-Z]{5}\d{4}[A-Z])\b", text) or \
        (re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", gstin.group(1)[2:12]) if gstin else None)
    return {"cin": cin.group(1) if cin else None, "gstin": gstin.group(1) if gstin else None,
            "pan": pan.group(1) if pan else None}


# ── Financial statements ─────────────────────────────────────────────────────

_UNIT = (("lakh", 0.01), ("crore", 1.0), ("million", 0.1), ("thousand", 0.0001))


def _unit(text: str) -> tuple[str, float]:
    low = text.lower()
    m = re.search(r"(?:₹|`|rs\.?|inr|h)\s*(?:/\s*)?(?:in\s*)?(lakhs?|crores?|millions?|thousands?)", low) or \
        re.search(r"\bin\s+(lakhs?|crores?|millions?|thousands?)\b", low) or \
        re.search(r"(lakhs?|crores?|millions?|thousands?)", low)
    word = m.group(1) if m else "crore"
    for k, f in _UNIT:
        if word.startswith(k):
            return k, f
    return "crore", 1.0


def _score(low_head: str, low: str, kind: str) -> int:
    need = {"bs": ("balance sheet", "total assets"),
            "pl": ("profit and loss", "revenue from operations"),
            "cf": ("cash flow", "operating activities")}[kind]
    if not all(n in low for n in need):
        return -99
    s = 0
    if kind == "bs" and ("total equity" in low or "equity and liabilities" in low):
        s += 3
    if kind == "pl" and "profit before tax" in low:
        s += 3
    if kind == "cf" and "investing activities" in low:
        s += 3
    s += 4 if "standalone" in low_head else 0
    s -= 8 if "consolidated" in low_head else 0
    s -= 5 if ("auditor" in low_head or "report on the audit" in low or "key audit matter" in low) else 0
    s -= 4 if "notes forming part" in low_head else 0
    title = {"bs": "balance sheet", "pl": "statement of profit and loss", "cf": "cash flow"}[kind]
    s += 3 if title in low_head else 0
    return s


def locate_statements(pages: list[str]) -> dict:
    """Pages of the standalone balance sheet, P&L and cash flow (0-based), by heading."""
    out = {}
    for kind in ("bs", "pl", "cf"):
        best, best_s = None, 0
        for i, t in enumerate(pages):
            low = re.sub(r"\s+", " ", t.lower())
            # the heading area: text before the first figure column; a statement may run onto the next page
            head = low[:900]
            nxt = re.sub(r"\s+", " ", pages[i + 1].lower())[:3000] if i + 1 < len(pages) else ""
            s = _score(head, low + " " + nxt, kind)
            if s > best_s:
                best, best_s = i, s
        if best is not None:
            out[kind] = best
    return out


def _grab(label: str, text: str, start: int = 0, end: Optional[int] = None) -> Optional[tuple[float, float, int]]:
    """(current, previous, position) for the first ``label`` in text[start:end] followed by two figures
    (an optional note number between them is skipped)."""
    pat = re.compile(r"(?:" + label + r")[^|]*(?:\|[^|\d(\-][^|]*){0,2}?\|\s*(?:\d{1,2}\s*\|\s*)?(" + NUM +
                     r")\s*\|\s*(" + NUM + r")\s*(?=\||$)", re.I)
    m = pat.search(text, start, end if end is not None else len(text))
    if not m:
        return None
    try:
        return to_num(m.group(1)), to_num(m.group(2)), m.start()
    except ValueError:
        return None


def _sections(t: str) -> dict:
    low = t.lower()

    def at(pattern, start=0):
        m = re.compile(pattern, re.I).search(low, start)
        return m.start() if m else None
    nca = at(r"non[- ]current assets")
    ca = at(r"(?<!non-)(?<!non )\bcurrent assets", (nca or 0) + 5)
    ta = at(r"total assets", ca or 0)
    ncl = at(r"non[- ]current liabilities", ta or 0)
    cl = at(r"(?<!non-)(?<!non )\bcurrent liabilities", (ncl or ta or 0) + 5)
    tel = at(r"total equity and liabilities", cl or 0)
    return {"nca": (nca or 0, ca or len(t)), "ca": (ca or 0, ta or len(t)), "eq": (ta or 0, ncl or len(t)),
            "ncl": (ncl or 0, cl or len(t)), "cl": (cl or 0, tel or len(t)), "all": (0, len(t))}


_BS = [  # key, section, label
    ("ppe", "nca", r"property,? plant (?:and|&) equipment"), ("cwip", "nca", r"capital work[- ]?in[- ]?progress"),
    ("intangibles", "nca", r"other intangible assets|intangible assets"), ("goodwill", "nca", r"goodwill"),
    ("rou", "nca", r"right[ -]*of[ -]*use assets"), ("nc_investments", "nca", r"investments"),
    ("inventory", "ca", r"inventories"), ("current_investments", "ca", r"investments"),
    ("trade_receivables", "ca", r"trade receivables"), ("cash", "ca", r"cash and cash equivalents"),
    ("other_bank", "ca", r"bank balances other than"),
    ("total_assets", "all", r"total assets"), ("share_capital", "eq", r"equity share capital|share capital"),
    ("other_equity", "eq", r"other equity"), ("total_equity", "eq", r"total equity(?! and)"),
    ("lt_borrowings", "ncl", r"borrowings"), ("nc_lease", "ncl", r"lease liabilities"),
    ("nc_provisions", "ncl", r"provisions"), ("dtl", "ncl", r"deferred tax liabilities"),
    ("other_ncl", "ncl", r"other non[- ]current liabilities"),
    ("st_borrowings", "cl", r"borrowings"), ("c_lease", "cl", r"lease liabilities"),
    ("payables_msme", "cl", r"micro and small enterprises"),
    ("payables_other", "cl", r"creditors other than micro"),
    ("trade_payables_single", "cl", r"trade payables"),
    ("total_liabilities", "all", r"total liabilities"), ("tel", "all", r"total equity and liabilities"),
]
_PL = [
    ("revenue_operating", r"revenue from operations"), ("other_income", r"other income"),
    ("total_income", r"total income"), ("materials", r"cost of materials consumed"),
    ("purchases", r"purchases? of stock[- ]in[- ]trade"), ("inventory_change", r"changes in inventories"),
    ("employee_cost", r"employee benefits? expenses?"), ("finance_cost", r"finance costs?"),
    ("depreciation", r"depreciation and amorti[sz]ation"), ("other_expenses", r"other expenses"),
    ("total_expenses", r"total expenses"), ("exceptional", r"exceptional items(?! and)"),
    ("pbt", r"profit\s*/?\s*(?:\(loss\)\s*)?before tax"), ("tax_expense", r"tax expenses?\s*(?:\(\d+\))"),
    ("pat", r"profit\s*/?\s*(?:\(loss\)\s*)?for the (?:year|period)"),
]
_CF = [("ocf", r"net cash (?:generated )?from\s*/?\s*\(?(?:used in)?\)?\s*operating activities|"
               r"net cash (?:flow )?(?:generated )?from operating activities"),
       ("capex", r"capital expenditure on property|purchase of property,? plant")]


def _years(text: str) -> list[int]:
    ys = []
    for m in re.finditer(r"31(?:st)?\s*march,?\s*(20\d\d)|march\s*31,?\s*(20\d\d)|31[-/.]0?3[-/.](20\d\d)", text, re.I):
        y = int(next(g for g in m.groups() if g))
        if y not in ys:
            ys.append(y)
    return ys[:2]


_ENDS = {"bs": "total equity and liabilities", "pl": "for the year", "cf": "investing activities"}


def statement_text(pages: list[str], loc: dict, kind: str) -> str:
    """The located statement's page, with the next page when the statement runs over."""
    if kind not in loc:
        return ""
    i = loc[kind]
    text = pages[i]
    if _ENDS[kind] not in re.sub(r"\s+", " ", text.lower()) and i + 1 < len(pages):
        text += "\n" + pages[i + 1]
    return joined(text)


def parse_statements(pages: list[str], loc: dict) -> dict:
    """Deterministic reading of the located statement pages: {"years": [cur, prev], "raw": {key: (cur, prev)}}."""
    raw: dict[str, tuple[float, float]] = {}
    bs = statement_text(pages, loc, "bs")
    if bs:
        sec = _sections(bs)
        for key, s, label in _BS:
            a, b = sec[s]
            g = _grab(label, bs, a, b)
            if g:
                raw[key] = (g[0], g[1])
        m = re.search(r"\|\s*(" + NUM + r")\s*\|\s*(" + NUM + r")\s*\|\s*total assets", bs, re.I)
        if m:
            raw["current_assets_subtotal"] = (to_num(m.group(1)), to_num(m.group(2)))
    pl = statement_text(pages, loc, "pl")
    if pl:
        start = re.search(r"statement of profit and loss", pl, re.I)
        s0 = start.start() if start else 0
        for key, label in _PL:
            g = _grab(label, pl, s0)
            if g:
                raw[key] = (g[0], g[1])
    if "cf" in loc:
        cf = joined(" \n".join(pages[loc["cf"]:loc["cf"] + 2]))
        for key, label in _CF:
            g = _grab(label, cf)
            if g:
                raw[key] = (g[0], g[1])
    years = _years(bs or pl)
    return {"years": years, "raw": raw}


def build_statements(raw: dict, factor: float) -> list[dict]:
    """Canonical line items (₹ crore) for the two columns, in the engine's vocabulary."""
    out = []
    for col in (0, 1):
        def v(k, default=0.0):
            return round(raw[k][col] * factor, 2) if k in raw else default
        it = {}
        it["revenue_operating"] = v("revenue_operating")
        it["other_income"] = v("other_income")
        it["total_income"] = v("total_income") or round(it["revenue_operating"] + it["other_income"], 2)
        it["raw_material_cost"] = round(v("materials") + v("purchases") + v("inventory_change"), 2)
        it["employee_cost"] = v("employee_cost")
        it["other_expenses"] = v("other_expenses")
        it["finance_cost"] = v("finance_cost")
        it["depreciation"] = v("depreciation")
        it["exceptional_items"] = v("exceptional")
        it["pbt"] = v("pbt")
        it["pat"] = v("pat")
        it["tax_expense"] = v("tax_expense") or round(it["pbt"] - it["pat"], 2)
        it["ebitda"] = round(it["total_income"] - it["raw_material_cost"] - it["employee_cost"]
                             - it["other_expenses"], 2)
        it["ebit"] = round(it["ebitda"] - it["depreciation"], 2)
        it["fixed_assets"] = round(v("ppe") + v("cwip") + v("intangibles") + v("goodwill") + v("rou"), 2)
        it["investments"] = round(v("nc_investments") + v("current_investments"), 2)
        it["inventory"] = v("inventory")
        it["trade_receivables"] = v("trade_receivables")
        it["cash_equivalents"] = round(v("cash") + v("other_bank"), 2)
        it["total_assets"] = v("total_assets")
        it["current_assets"] = v("current_assets_subtotal") or round(
            it["inventory"] + it["trade_receivables"] + it["cash_equivalents"] + v("current_investments"), 2)
        it["total_equity"] = v("total_equity") or round(v("share_capital") + v("other_equity"), 2)
        it["share_capital"] = v("share_capital")
        it["long_term_debt"] = v("lt_borrowings")
        it["short_term_debt"] = v("st_borrowings")
        it["total_debt"] = round(it["long_term_debt"] + it["short_term_debt"], 2)
        it["lease_liabilities"] = round(v("nc_lease") + v("c_lease"), 2)
        ncl = round(v("lt_borrowings") + v("nc_lease") + v("nc_provisions") + v("dtl") + v("other_ncl"), 2)
        it["non_current_liabilities"] = ncl
        tel = v("tel") or it["total_assets"]
        it["current_liabilities"] = round(tel - it["total_equity"] - ncl, 2) if tel else 0.0
        it["trade_payables"] = round(v("payables_msme") + v("payables_other"), 2) or v("trade_payables_single")
        it["working_capital"] = round(it["current_assets"] - it["current_liabilities"], 2)
        it["ocf"] = v("ocf")
        it["capex"] = -abs(v("capex")) if "capex" in raw else 0.0
        it["fcff"] = round(it["ocf"] + it["capex"], 2) if "ocf" in raw else 0.0
        out.append({k: x for k, x in it.items() if x not in (None,)})
    return out


def statement_checks(it: dict) -> list[dict]:
    checks = []
    ta, te, ncl, cl = it.get("total_assets", 0), it.get("total_equity", 0), \
        it.get("non_current_liabilities", 0), it.get("current_liabilities", 0)
    if ta:
        gap = abs(ta - (te + ncl + cl))
        checks.append({"check": "Assets = equity + liabilities", "ok": gap <= max(1.0, ta * 0.002),
                       "detail": f"{ta:,.2f} vs {te + ncl + cl:,.2f}"})
    if it.get("pbt") or it.get("pat"):
        gap = abs(it.get("pbt", 0) - it.get("tax_expense", 0) - it.get("pat", 0))
        checks.append({"check": "PBT − tax = PAT", "ok": gap <= 1.0,
                       "detail": f"{it.get('pbt', 0):,.2f} − {it.get('tax_expense', 0):,.2f} vs {it.get('pat', 0):,.2f}"})
    if it.get("revenue_operating"):
        ok = 0 < it["revenue_operating"] <= it.get("total_income", 0) + 0.01
        checks.append({"check": "Revenue ≤ total income", "ok": ok,
                       "detail": f"{it['revenue_operating']:,.2f} / {it.get('total_income', 0):,.2f}"})
    core = ("revenue_operating", "pat", "total_assets", "total_equity")
    checks.append({"check": "Core figures present", "ok": all(it.get(k) for k in core),
                   "detail": ", ".join(k for k in core if not it.get(k)) or "all present"})
    return checks


_FS_SYSTEM = (
    "You read Indian audited financial statements. Return ONLY a JSON object, no prose. Figures exactly as "
    "printed (no unit conversion), negative numbers for figures in brackets.")
_FS_KEYS = ["revenue_operating", "other_income", "total_income", "materials", "purchases", "inventory_change",
            "employee_cost", "finance_cost", "depreciation", "other_expenses", "exceptional", "pbt", "tax_expense",
            "pat", "ppe", "cwip", "intangibles", "rou", "nc_investments", "current_investments", "inventory",
            "trade_receivables", "cash", "other_bank", "current_assets_subtotal", "total_assets", "share_capital",
            "other_equity", "total_equity", "lt_borrowings", "nc_lease", "nc_provisions", "dtl", "other_ncl",
            "st_borrowings", "c_lease", "payables_msme", "payables_other", "total_liabilities", "tel", "ocf",
            "capex"]


def llm_statements(pages: list[str], loc: dict, llm) -> Optional[dict]:
    """The AI model reads the same pages into the same keys (used when the layout reading does not reconcile)."""
    if llm is None or getattr(llm, "name", "") == "mock":
        return None
    from src.services.observation_narrator import _parse_json_object
    text = "\n\n".join(f"[{k.upper()} page {i + 1}]\n{pages[i][:6000]}" for k, i in loc.items())
    prompt = ("From the statements below return {\"years\": [current_year_end_YYYY, previous_year_end_YYYY], "
              "\"values\": {key: [current, previous]}} for these keys (omit a key that is not printed): "
              + ", ".join(_FS_KEYS) + ". 'tel' is total equity and liabilities; 'lt_' non-current, 'st_' current; "
              "'current_assets_subtotal' is the total of current assets.\n\n" + text)
    try:
        raw = llm.generate(prompt=prompt, system_prompt=_FS_SYSTEM, temperature=0.0, max_tokens=1800)
        data = _parse_json_object(raw)
        vals = {k: (float(v[0]), float(v[1])) for k, v in (data.get("values") or {}).items()
                if k in _FS_KEYS and isinstance(v, (list, tuple)) and len(v) == 2}
        years = [int(str(y)[:4]) for y in (data.get("years") or [])][:2]
        return {"years": years, "raw": vals} if vals else None
    except Exception:
        log.warning("AI reading of the financial statements failed", exc_info=True)
        return None


def read_financial_statements(path: Path, llm=None, pages: Optional[list[str]] = None) -> dict:
    """Both year columns of the standalone statements in an annual report / audited accounts."""
    pages = pages or page_texts(path)
    loc = locate_statements(pages)
    if "bs" not in loc or "pl" not in loc:
        raise ValueError(f"{path.name}: no balance sheet and statement of profit and loss found")
    unit, factor = _unit(" ".join(pages[i][:1500] for i in loc.values()))
    head = " ".join(pages[i][:900].lower() for i in loc.values())
    basis = "standalone" if "standalone" in head else ("consolidated" if "consolidated" in head else "standalone")
    parsed = parse_statements(pages, loc)
    method = "layout"
    years_items = build_statements(parsed["raw"], factor)
    ok = all(c["ok"] for it in years_items for c in statement_checks(it))
    if not ok:
        alt = llm_statements(pages, loc, llm)
        if alt:
            alt_items = build_statements(alt["raw"], factor)
            if all(c["ok"] for it in alt_items for c in statement_checks(it)):
                parsed, years_items, method = {"years": alt["years"] or parsed["years"], "raw": alt["raw"]}, \
                    alt_items, "ai"
    years = parsed["years"]
    if len(years) < 2:
        raise ValueError(f"{path.name}: the statement dates could not be read")
    whole = "\n".join(pages[:6]) + "\n" + "\n".join(pages[i] for i in loc.values())
    statements = []
    for col, y in enumerate(years[:2]):
        it = years_items[col]
        statements.append({"period": f"FY{y}", "as_of": f"{y}-03-31", "basis": basis, "items": it,
                           "checks": statement_checks(it)})
    first = "\n".join(pages[:3])
    name = re.search(r"([A-Z][A-Za-z&().\- ]{3,80}(?:LIMITED|Limited|LTD|Ltd\.?))", first)
    return {"document": path.name, "pages": {k: i + 1 for k, i in loc.items()}, "unit": unit, "basis": basis,
            "method": method, "statements": statements, "identity": identity_in(whole),
            "name_found": name.group(1).strip() if name else None}


# ── Rating rationale (ICRA / CRISIL / CARE / India Ratings) ──────────────────

_RATING = r"(\[ICRA\]\s?[A-D]{1,3}[+-]?|CRISIL\s?[A-D]{1,3}[+-]?|CARE\s?[A-D]{1,3}[+-]?|IND\s?[A-D]{1,3}[+-]?)"


def read_rating(path: Path, pages: Optional[list[str]] = None) -> dict:
    pages = pages or page_texts(path)
    text = "\n".join(pages)
    flat = re.sub(r"\s+", " ", text)
    agency = next((a for a in ("ICRA", "CRISIL", "CARE", "India Ratings") if a.lower() in flat.lower()[:3000]), None)
    d = re.search(r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
                  r"\s+\d{1,2},\s+20\d\d)", flat)
    lt = re.search(_RATING + r"\s*\((Stable|Positive|Negative|Developing)\)", flat)
    st = re.search(r"(\[ICRA\]\s?A1\+?|CRISIL\s?A1\+?|CARE\s?A1\+?|IND\s?A1\+?)", flat)
    action = re.search(r"(reaffirmed|upgraded|downgraded|assigned|withdrawn)", flat[:2500], re.I)
    total = re.search(r"Total\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", flat)
    facilities = []
    for m in re.finditer(r"(Long[- ]term|Short[- ]term|Long[- ]term\s*/\s*Short[- ]term)\s*[–-]\s*([A-Za-z \-–]+?)\s+"
                         r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})", flat[:4000]):
        facilities.append({"tenure": m.group(1), "instrument": m.group(2).strip(" –-"),
                           "previous_cr": to_num(m.group(3)), "current_cr": to_num(m.group(4))})
    strengths = _headings(flat, "Credit strengths", "Credit challenges")
    challenges = _headings(flat, "Credit challenges", "Environmental and social risks|Liquidity position")
    liquidity = re.search(r"Liquidity position:\s*(\w+)", flat)
    payload = {"rating_agency": agency, "long_term_rating": f"{lt.group(1)} ({lt.group(2)})" if lt else None,
               "outlook": lt.group(2) if lt else None, "short_term_rating": st.group(1) if st else None,
               "last_action": (action.group(1).capitalize() if action else None), "action_date": d.group(1) if d else None,
               "total_rated_cr": to_num(total.group(2)) if total else None, "rated_facilities": facilities,
               "key_strengths": strengths, "key_challenges": challenges,
               "liquidity": liquidity.group(1) if liquidity else None}
    return {"payload": payload, "identity": identity_in(text), "page": 1,
            "name_found": (re.search(r"\n?([A-Z][A-Za-z&().\- ]{3,80}Limited)\s*:", flat) or [None, None])[1]}


def _headings(flat: str, start: str, end: str) -> list[str]:
    s = re.search(start, flat)
    if not s:
        return []
    e = re.search(end, flat[s.end():])
    block = flat[s.end(): s.end() + (e.start() if e else 4000)].strip()
    heads = re.findall(r"(?:^|[.:]\s+)([A-Z][A-Za-z ,/&'()\-]{12,140}?)\s+–\s+(?=[A-Z])", block)
    return [h.strip() for h in heads][:6]


# ── Structured forms: label: value ───────────────────────────────────────────

def form_fields(text: str) -> dict:
    out = {}
    for ln in text.splitlines():
        m = re.match(r"\s*([A-Za-z][A-Za-z0-9 ()/&.,'\-]{2,70}?)\s*:\s*(.+?)\s*$", ln)
        if m and m.group(1).strip().lower() not in out:
            out[m.group(1).strip().lower()] = m.group(2).strip()
    return out


def pdf_tables(path: Path) -> list[list[list[str]]]:
    """Ruled tables in a PDF (PyMuPDF table finder), each as rows of cell strings."""
    import pymupdf
    out = []
    with pymupdf.open(str(path)) as doc:
        for page in doc:
            try:
                found = page.find_tables()
            except Exception:
                continue
            for t in found.tables:
                rows = [[re.sub(r"\s+", " ", str(c or "")).strip() for c in r] for r in t.extract()]
                if rows:
                    out.append(rows)
    return out


def table_rows(tables: list, header_words: tuple[str, ...], ncols: int) -> list[list[str]]:
    """The data rows of the first table whose header row contains all ``header_words``."""
    for t in tables:
        head = " ".join(t[0]).lower()
        if all(w in head for w in header_words):
            return [r[:ncols] for r in t[1:] if len(r) >= ncols and any(c for c in r)
                    and not r[0].lower().startswith(("total", "note", "source"))]
    return []


def _f(fields: dict, *keys, num=False):
    for k in keys:
        for fk, v in fields.items():
            if fk.startswith(k):
                if num:
                    m = re.search(r"-?[\d,]+(?:\.\d+)?", v)
                    return to_num(m.group(0)) if m else None
                return v
    return None


def _score_num(v):
    """A numeric bureau score (e.g. 300–900); a rank such as CMR-2 is not a score."""
    m = re.fullmatch(r"\s*(\d{3})\s*", str(v or ""))
    return int(m.group(1)) if m else None


def llm_fields(text: str, spec: dict, llm, what: str) -> dict:
    """The AI model reads a document of unknown layout into ``spec`` ({field: description})."""
    if llm is None or getattr(llm, "name", "") == "mock":
        return {}
    from src.services.observation_narrator import _parse_json_object
    prompt = (f"Document: {what}. Return ONLY a JSON object with these keys (null when not stated):\n"
              + json.dumps(spec, indent=1) + "\n\nDocument text:\n" + text[:14000])
    try:
        return _parse_json_object(llm.generate(prompt=prompt, system_prompt="You extract facts from banking "
                                               "documents. Never guess a value that is not printed.",
                                               temperature=0.0, max_tokens=1500)) or {}
    except Exception:
        log.warning("AI reading of %s failed", what, exc_info=True)
        return {}


def read_mca(path: Path, llm=None) -> dict:
    text = "\n".join(page_texts(path))
    tables = pdf_tables(path)
    f = form_fields(text)
    directors = [{"din": r[0], "name": r[1].title(), "designation": r[2]}
                 for r in table_rows(tables, ("din", "name", "designation"), 3) if r[1]]
    charges = [{"charge_id": r[0], "charge_holder": r[1], "amount_cr": to_num(r[2]), "created_on": r[3],
                "status": r[4]} for r in table_rows(tables, ("charge id", "charge holder", "amount"), 5)]
    payload = {"cin": _f(f, "cin"), "company_name": _f(f, "company name"), "roc": _f(f, "roc"),
               "company_class": _f(f, "class of company"), "company_category": _f(f, "company category"),
               "date_of_incorporation": _f(f, "date of incorporation"),
               "registered_office": _f(f, "registered address", "registered office"),
               "registered_state": _f(f, "state"), "email": _f(f, "email"),
               "listing_status": _f(f, "whether listed", "listing status"),
               "status": _f(f, "company status", "status"), "nic_code": _f(f, "main division", "nic"),
               "industrial_class": _f(f, "industrial class", "activity description"),
               "paid_up_capital_inr": _f(f, "paid up capital", num=True),
               "authorized_capital_inr": _f(f, "authorised capital", "authorized capital", num=True),
               "last_agm_date": _f(f, "date of last agm"), "last_balance_sheet_date": _f(f, "date of balance sheet"),
               "directors": directors, "charges": charges}
    if not payload["cin"] and llm is not None:
        payload.update({k: v for k, v in llm_fields(text, {
            "cin": "Corporate Identification Number", "company_name": "registered name",
            "date_of_incorporation": "date of incorporation", "registered_office": "registered office address",
            "status": "company status", "listing_status": "Listed / Unlisted"}, llm, "MCA master data").items() if v})
    return {"payload": payload, "identity": identity_in(text), "name_found": payload["company_name"], "page": 1}


def read_kyc(path: Path, llm=None) -> dict:
    text = "\n".join(page_texts(path))
    tables = pdf_tables(path)
    f = form_fields(text)
    signatories = [{"name": r[0], "designation": r[1], "id_verified": r[2], "status": r[3]}
                   for r in table_rows(tables, ("name", "designation", "verified", "status"), 4)]
    owners = [{"name": r[0], "holding_pct": to_num(r[1].rstrip("%")), "basis": r[2]}
              for r in table_rows(tables, ("beneficial owner", "holding", "basis"), 3)]
    payload = {"pan": _f(f, "pan"), "cin": _f(f, "cin"), "gstin": _f(f, "gstin"),
               "company_name": _f(f, "company name", "name of entity"),
               "incorporation_certificate": _f(f, "certificate of incorporation"),
               "registered_office": _f(f, "registered office", "address"),
               "kyc_status": _f(f, "kyc status"), "verified_on": _f(f, "verified on", "date of verification"),
               "risk_category": _f(f, "risk category", "customer risk"),
               "authorised_signatories": signatories, "beneficial_owners": owners}
    if not payload["pan"] and llm is not None:
        payload.update({k: v for k, v in llm_fields(text, {
            "pan": "PAN of the company", "cin": "CIN", "company_name": "name", "kyc_status": "KYC status",
            "registered_office": "registered office"}, llm, "KYC pack").items() if v})
    return {"payload": payload, "identity": identity_in(text), "name_found": payload["company_name"], "page": 1}


def read_bureau(path: Path, llm=None) -> dict:
    text = "\n".join(page_texts(path))
    tables = pdf_tables(path)
    f = form_fields(text)
    facilities = []
    for r in table_rows(tables, ("lender", "facility", "sanctioned", "outstanding"), 7):
        facilities.append({"lender": r[0], "type": r[1], "limit_cr": to_num(r[2]), "outstanding_cr": to_num(r[3]),
                           "overdue_cr": to_num(r[4]), "dpd": int(to_num(r[5])), "classification": r[6]})
    payload = {"bureau": _f(f, "bureau"), "report_date": _f(f, "report date", "date of report"),
               "entity_name": _f(f, "borrower name", "entity name", "name"), "pan": _f(f, "pan"),
               "cmr_rank": _f(f, "cmr rank", "rank"),
               "credit_score": _score_num(_f(f, "credit score", "commercial score", "score")),
               "score_band": _f(f, "cmr rank", "rank"), "score_description": _f(f, "rank description", "description"),
               "total_lenders": len({x["lender"] for x in facilities}) or _f(f, "number of lenders", num=True),
               "total_exposure_cr": round(sum(x["limit_cr"] for x in facilities), 2) or _f(f, "total sanctioned", num=True),
               "total_outstanding_cr": round(sum(x["outstanding_cr"] for x in facilities), 2),
               "dpd_status": "Standard" if facilities and all(x["dpd"] == 0 for x in facilities) else
               (_f(f, "dpd status") or ("Overdue" if facilities else None)),
               "max_dpd_last_12m": max((x["dpd"] for x in facilities), default=0) if facilities else
               _f(f, "max dpd", num=True),
               "worst_status_12m": _f(f, "worst status"), "suit_filed_amount_cr": _f(f, "suit filed", num=True) or 0.0,
               "wilful_defaulter": str(_f(f, "wilful defaulter") or "No").strip().lower().startswith("y"),
               "enquiries_last_6m": _f(f, "enquiries", num=True), "facilities": facilities}
    if not facilities and llm is not None:
        payload.update({k: v for k, v in llm_fields(text, {
            "credit_score": "CMR rank or score", "total_exposure_cr": "total sanctioned (Rs crore)",
            "dpd_status": "worst delinquency status", "wilful_defaulter": "true/false",
            "suit_filed_amount_cr": "suit-filed amount (Rs crore)"}, llm, "commercial bureau report").items() if v})
    return {"payload": payload, "identity": identity_in(text), "name_found": payload["entity_name"], "page": 1}


def read_bank_statement(path: Path, llm=None) -> dict:
    text = "\n".join(page_texts(path))
    tables = pdf_tables(path)
    f = form_fields(text)
    months = []
    for r in table_rows(tables, ("month", "opening", "credits", "debits", "closing"), 7):
        months.append({"month": r[0], "opening_cr": to_num(r[1]), "credits_cr": to_num(r[2]),
                       "debits_cr": to_num(r[3]), "closing_cr": to_num(r[4]), "credit_count": int(to_num(r[5])),
                       "returns": int(to_num(r[6]))})
    payload = {"bank": _f(f, "bank"), "account_type": _f(f, "account type"), "account_holder": _f(f, "account holder"),
               "period": _f(f, "statement period", "period"), "months": months,
               "total_credits_cr": round(sum(m["credits_cr"] for m in months), 2),
               "total_debits_cr": round(sum(m["debits_cr"] for m in months), 2),
               "avg_balance_cr": round(sum(m["closing_cr"] for m in months) / len(months), 2) if months else None,
               "returns": sum(m["returns"] for m in months), "limit_cr": _f(f, "sanctioned limit", "limit", num=True),
               "avg_utilisation_pct": _f(f, "average utilisation", num=True)}
    return {"payload": payload, "identity": identity_in(text), "name_found": payload["account_holder"], "page": 1}


def read_gst(path: Path, llm=None) -> dict:
    text = "\n".join(page_texts(path))
    tables = pdf_tables(path)
    f = form_fields(text)
    returns = [{"period": r[0], "taxable_value_cr": to_num(r[1]), "tax_paid_cr": to_num(r[2]), "filed_on": r[3],
                "status": r[4]} for r in table_rows(tables, ("return period", "taxable", "tax", "filed"), 5)]
    turnover = {}
    for m in re.finditer(r"Aggregate turnover\s*(?:FY|F\.Y\.)\s*(20\d\d)-?(\d\d)\s*\(.*?\)\s*:\s*([\d,]+(?:\.\d+)?)",
                         text, re.I):
        turnover[f"aggregate_turnover_fy{2000 + int(m.group(2))}_cr"] = to_num(m.group(3))
    late = sum(1 for r in returns if r["status"].lower() != "filed on time")
    payload = {"gstin": _f(f, "gstin"), "legal_name": _f(f, "legal name"), "registration_status": _f(f, "status"),
               "registration_date": _f(f, "date of registration"), "nature_of_business": _f(f, "nature of business"),
               **turnover, "returns": returns,
               "filing_status": ("Regular" if returns and not late else "Delayed" if returns else _f(f, "filing status")),
               "filing_detail": f"{len(returns) - late} of {len(returns)} returns filed on time" if returns else None,
               "last_return_filed": f"GSTR-3B {returns[-1]['period']}" if returns else _f(f, "last return"),
               "pending_returns": late}
    return {"payload": payload, "identity": identity_in(text), "name_found": payload["legal_name"], "page": 1}


READERS = {"mca": read_mca, "kyc": read_kyc, "bureau": read_bureau, "bank_statements": read_bank_statement,
           "gst": read_gst}


def read_source_document(source_id: str, path: Path, llm=None) -> dict:
    """An uploaded document for one source → the source's envelope (as an API would return it)."""
    rtype = {"mca": ("mca", "company_master"), "kyc": ("ckyc", "kyc_record"), "bureau": ("bureau", "commercial_report"),
             "bank_statements": ("account_aggregator", "bank_statement"), "gst": ("gst", "turnover_summary"),
             "rating": ("rating", "rating_action")}[source_id]
    r = read_rating(path) if source_id == "rating" else READERS[source_id](path, llm)
    key = r["identity"].get("cin") or r["identity"].get("pan") or path.stem
    env = envelope(rtype[0], rtype[1], key, r["payload"], provenance=_doc(path, r.get("page")))
    env["identity"], env["name_found"] = r["identity"], r.get("name_found")
    return env


def fy_of(d: date) -> int:
    return d.year + 1 if d.month > 3 else d.year
