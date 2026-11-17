"""Rebuild each listed borrower's identity facts from its own annual report (round 9 data revalidation).

    .venv/Scripts/python scripts/read_identity_from_reports.py [ENTITY ...]

The data files had identity facts that no public document supports (PANs, director DINs, personal net worth,
auditors, a few CINs). This replaces them with what the latest annual report on file states:

    CIN                 the company's CIN as printed in the report (the most frequent one)
    registered office   "Registered Office: …" in the report
    statutory auditor   the firm signing the Independent Auditor's Report
    board of directors  Gemini reads the pages listing the directors and their DINs; a director is kept only
                        if the name and the 8-digit DIN appear in the report text. Other listed directorships
                        are kept only if the company name appears in the report.
    PAN / GSTIN         not printed in any annual report: cleared (collected at KYC by the bank)
    personal data       a director's net worth or PAN is not public: cleared
    group companies     kept only if the report names them

Run scripts/validate_test_data.py afterwards; it checks every fact against the report.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CIN = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}(?:PLC|GOI|PTC|SGC)\d{6}\b")
DIN = re.compile(r"\b\d{8}\b")


def _pages(pdf: Path) -> list[str]:
    import fitz
    with fitz.open(pdf) as d:
        return [" ".join(p.get_text().split()) for p in d]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _cin(text: str, current: str) -> str:
    found = Counter(CIN.findall(text))
    if current in found:
        return current
    return found.most_common(1)[0][0] if found else current


def _office(text: str) -> str | None:
    m = re.search(r"Registered Office\s*[:\-–]?\s*(.{15,220}?\b\d{3}\s?\d{3}\b)", text)
    if not m:
        return None
    office = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;")
    office = re.sub(r"^(?:is located at|of the Company (?:is )?situated at|situated at|at)\s+", "", office, flags=re.I)
    return re.sub(r"\b([A-Z]) ([a-z]{3,})", r"\1\2", office)          # "C hennai" -> "Chennai"


def _auditor(text: str) -> str | None:
    """The statutory auditor: the firm in the signature line "For <firm> … Chartered Accountants"."""
    hits = re.findall(r"(?:For|from|auditor)\s+([A-Z][^,;()]{2,70}?)\s*(?:\([^)]{0,80}\))?\s*,?\s*Chartered Accountants",
                      text)
    firm = lambda h: (re.match(r"(.+?(?:&\s*CO\.?\s*LLP|&\s*Associates\s*LLP|LLP|&\s*Co\.?(?![\w])|&\s*Associates|Associates))", h, re.I)  # noqa: E731
                      or [None, None])[1]
    c = Counter(f.strip() for f in map(firm, hits) if f)
    return c.most_common(1)[0][0] if c else None


_PROMPT = """These are pages of {name}'s annual report that list its Board of Directors.
Return JSON only: {{"board": [{{"name": "...", "din": "8 digits", "designation": "...", "promoter": true|false,
"other_listed_directorships": ["company name", ...]}}]}}
Rules: only directors on the Board at the date of the report (not those who ceased); the DIN exactly as printed;
designation as printed (e.g. Chairman, Managing Director, Independent Director); promoter true only if the report
says promoter / promoter group; other listed directorships only if the report lists them for that director.
Do not add anyone or anything the pages do not state.

PAGES:
{pages}"""


def _board(pages: list[str], name: str, llm) -> list[dict]:
    scored = sorted(range(len(pages)), key=lambda i: -len(re.findall(r"\bDIN\b", pages[i])))[:4]
    chosen = [pages[i][:9000] for i in sorted(scored) if re.search(r"\bDIN\b", pages[i])]
    if not chosen or llm is None:
        return []
    raw = llm.generate(prompt=_PROMPT.format(name=name, pages="\n\n---\n\n".join(chosen)),
                       system_prompt="You extract facts from annual reports. JSON only.", temperature=0.0,
                       max_tokens=4000)
    m = re.search(r"\{.*\}", raw or "", re.S)
    board = (json.loads(m.group(0)).get("board") if m else None) or []
    text = " ".join(pages)
    nt = _norm(text)
    out, seen = [], set()
    for d in board:
        din = re.sub(r"\D", "", str(d.get("din") or ""))
        nm = str(d.get("name") or "").strip()
        if len(din) != 8 or din in seen or din not in text or not nm:
            continue
        last = nm.replace(".", " ").split()[-1]
        if _norm(nm) not in nt and _norm(last) not in nt:
            continue
        seen.add(din)
        others = [o for o in d.get("other_listed_directorships") or [] if _norm(o)[:14] in nt]
        out.append({"din": din, "name": nm, "designation": d.get("designation") or None,
                    "is_promoter": bool(d.get("promoter")), "other_directorships": others})
    return out


_HOLD = """These are pages of {name}'s annual report with its shareholding pattern (distribution by category of
shareholder) at the end of the financial year. Return JSON only:
{{"promoter_pct": number, "institutional_pct": number, "public_pct": number}}
promoter = promoter and promoter group; institutional = all institutions (mutual funds, insurers, banks, foreign
portfolio investors, alternative investment funds); public = everyone else (non-institutions). Percentages of total
shares exactly as printed; null for any figure the pages do not state.

PAGES:
{pages}"""


def _holdings(pages: list[str], name: str, llm) -> dict:
    """Promoter / institutional / public shareholding from the report's shareholding pattern; a figure is kept only
    if the report prints it (to two decimals or as printed)."""
    scored = sorted(range(len(pages)), key=lambda i: -(len(re.findall(r"(?i)promoter", pages[i]))
                                                       * bool(re.search(r"(?i)shareholding|category of share", pages[i]))))[:3]
    chosen = [pages[i][:9000] for i in sorted(scored)]
    if llm is None or not chosen:
        return {}
    raw = llm.generate(prompt=_HOLD.format(name=name, pages="\n\n---\n\n".join(chosen)),
                       system_prompt="You extract facts from annual reports. JSON only.", temperature=0.0, max_tokens=300)
    m = re.search(r"\{.*\}", raw or "", re.S)
    got = json.loads(m.group(0)) if m else {}
    text = " ".join(chosen)
    out = {}
    for k in ("promoter_pct", "institutional_pct", "public_pct"):
        v = got.get(k)
        if isinstance(v, (int, float)) and 0 <= v <= 100 and (f"{v:.2f}" in text or f"{v:g}" in text):
            out[k] = round(float(v), 2)
    return out


def main(only: list[str]) -> int:
    from src.core import env_loader
    env_loader.load_local_env()
    from src.application.container import build_container
    from src.data import borrowers
    from src.models.canonical_model import DirectorPromoter as Director

    llm = build_container().flow.llm_factory()
    for eid in borrowers.ids():
        if only and eid not in only:
            continue
        fin = ROOT / "storage" / "documents" / eid / "financials"
        ar = next((fin / f"annual_report_fy{y}.pdf" for y in (2026, 2025)
                   if (fin / f"annual_report_fy{y}.pdf").exists()
                   and (fin / f"annual_report_fy{y}.pdf").stat().st_size > 1_000_000), None)
        if ar is None:
            continue                                       # synthetic borrowers: fictional, left as they are
        rec = borrowers.load(eid)
        b = rec["borrower"]
        pages = _pages(ar)
        text = " ".join(pages)
        changes = []
        cin = _cin(text, b.cin)
        if cin != b.cin:
            changes.append(f"CIN {b.cin} → {cin}")
            b.cin = cin
            if b.date_of_incorporation and str(b.date_of_incorporation.year) != cin[8:12]:
                b.date_of_incorporation = b.date_of_incorporation.replace(year=int(cin[8:12]))
        office = _office(text)
        if office and office != b.registered_address:
            changes.append(f"office → {office[:60]}")
            b.registered_address = office
        if b.pan:
            changes.append(f"PAN {b.pan} cleared")
            b.pan = None
        ids = dict(rec.get("identifiers") or {})
        if ids.get("pan") or ids.get("gstin"):
            ids.pop("pan", None)
            ids.pop("gstin", None)
            rec["identifiers"] = ids
        prof = dict(rec.get("profile") or {})
        aud = _auditor(text)
        if aud and aud != prof.get("auditor"):
            changes.append(f"auditor {prof.get('auditor')} → {aud}")
            prof["auditor"] = aud
        elif not aud and prof.get("auditor") and _norm(prof["auditor"])[:10] not in _norm(text):
            changes.append(f"auditor {prof['auditor']} cleared (not in the report)")
            prof.pop("auditor")
        if prof.pop("narrative", None) is not None:
            changes.append("invented narrative removed")
        rec["profile"] = prof
        board = _board(pages, b.company_name, llm)
        if board:
            rec["directors"] = [Director(entity_id=eid, din=d["din"], name=d["name"], designation=d["designation"] or "Director",
                                         is_promoter=d["is_promoter"], other_directorships=d["other_directorships"],
                                         pan=None, net_worth_cr=None, date_of_appointment=None) for d in board]
            changes.append(f"board read: {len(board)} directors")
        else:
            for d in rec.get("directors") or []:
                d.net_worth_cr, d.pan = None, None
            changes.append("board NOT read — directors kept, personal data cleared")
        grp = rec.get("group")
        if grp is not None:
            h = _holdings(pages, b.company_name, llm)
            for attr, k in (("promoter_holding_pct", "promoter_pct"), ("institutional_holding_pct", "institutional_pct"),
                            ("public_holding_pct", "public_pct")):
                new = h.get(k)
                if new != getattr(grp, attr, None):
                    changes.append(f"{attr} {getattr(grp, attr, None)} → {new if new is not None else 'cleared (not read)'}")
                    setattr(grp, attr, new)                     # None: not on record, never 0%
        if grp is not None and getattr(grp, "entities", None):
            keep = [e for e in grp.entities if e == eid or _norm(e)[:12] in _norm(text)]
            if keep != grp.entities:
                changes.append(f"group: {len(grp.entities) - len(keep)} company(ies) not in the report removed")
                grp.entities = keep
        borrowers.save(eid, rec)
        print(f"{eid}: " + "; ".join(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
