"""Read each listed borrower's operating KPIs (capacity, volumes, customers, employees …) from its annual report.

    .venv/Scripts/python scripts/read_sector_kpis.py [ENTITY ...]

The CAM's "Operating profile" (section 2) shows the borrower's operating measures. They are read from the latest
annual report on file: the pages richest in operating terms are given to Gemini, which lists up to eight measures
the pages state for the latest year, with the page number. A measure is kept only if its number is printed on
that page. The result goes into ``sector_kpis`` with the document and page as its source — nothing is estimated.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# words that mark an operating-highlights page (any sector)
_TERMS = re.compile(r"(?i)\b(capacity|volume|throughput|production|sales volume|units sold|customers|clients|employees|"
                    r"headcount|stores|outlets|beds|occupancy|ARR|RevPAR|tonnes|MTPA|MMT|MW|GW|TEU|cargo|plants?|"
                    r"dealers?|distribution|order book|market share|utili[sz]ation|footfall|patients|launches)\b")

_PROMPT = """These are pages of {name}'s annual report for {year}. List the company's main OPERATING measures for
{year} that these pages state (capacity, production or sales volumes, customers, employees, stores, beds,
occupancy, order book, market share — not financial figures such as revenue, profit, EBITDA or ratios,
not CSR or community programmes, not employee gender or diversity splits).
Return JSON only: {{"kpis": [{{"measure": "...", "value": "number as printed", "unit": "...", "page": n}}]}}
At most 8; the value exactly as printed on that page; only the company's own figures for {year}; nothing the pages
do not state.

{pages}"""


def _pages(pdf: Path) -> list[str]:
    import fitz
    with fitz.open(pdf) as d:
        return [" ".join(p.get_text().split()) for p in d]


def main(only: list[str]) -> int:
    from src.core import env_loader
    env_loader.load_local_env()
    from src.application.container import build_container
    from src.data import borrowers

    llm = build_container().flow.llm_factory()
    for eid in borrowers.ids():
        if only and eid not in only:
            continue
        rec = borrowers.load(eid)
        if not rec.get("latest_statement_source"):
            continue                                     # fictional borrowers keep their designed profile
        fin = ROOT / "storage" / "documents" / eid / "financials"
        ar = next((fin / f"annual_report_fy{y}.pdf" for y in (2026, 2025)
                   if (fin / f"annual_report_fy{y}.pdf").exists()), None)
        if ar is None:
            continue
        year = f"FY{ar.stem[-4:]}"
        pages = _pages(ar)
        best = sorted(range(min(len(pages), 160)), key=lambda i: -len(_TERMS.findall(pages[i])))[:5]
        chunk = "\n\n".join(f"[page {i + 1}]\n{pages[i][:6000]}" for i in sorted(best))
        raw = llm.generate(prompt=_PROMPT.format(name=rec["borrower"].company_name, year=year, pages=chunk),
                           system_prompt="You extract facts from annual reports. JSON only.", temperature=0.0,
                           max_tokens=1200)
        m = re.search(r"\{.*\}", raw or "", re.S)
        kpis = (json.loads(m.group(0)).get("kpis") if m else None) or []
        kept = {}
        for k in kpis:
            page, value = k.get("page"), str(k.get("value") or "").strip()
            if not isinstance(page, int) or not 1 <= page <= len(pages) or not value:
                continue
            if value.replace(" ", "") not in pages[page - 1].replace(" ", ""):
                continue                                 # the number must be printed on the cited page
            if re.search(r"(?i)CSR|programme|beneficiar|upskill|community|male|female|women", str(k.get('measure'))):
                continue                                 # not an operating measure
            label = f"{k.get('measure')}" + (f" ({k['unit']})" if k.get("unit") else "")
            kept[label[:80]] = f"{value} [p.{page}]"
        if kept:
            rec["sector_kpis"] = {"document": f"financials/{ar.name}",
                                  f"Operating highlights {year}": {**kept, "source": f"Annual report {year}"}}
        else:
            rec["sector_kpis"] = {}
        borrowers.save(eid, rec)
        print(f"{eid}: {len(kept)} of {len(kpis)} measures kept" + (" — " + "; ".join(f"{a}: {b}" for a, b in
                                                                        list(kept.items())[:3]) if kept else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
