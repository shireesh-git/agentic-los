"""Shareholding by category (promoter / institutions / public) from the annual report's own pages, read as printed.

    .venv/Scripts/python scripts/read_shareholding.py [ENTITY ...]

Many annual reports print the shareholding pattern as a chart or a table the text layer does not carry, so
scripts/read_identity_from_reports.py cannot confirm it from the text. This sends those pages to Gemini as a PDF
(the pages themselves, like the statement reading) and keeps the three figures only when they add up to 100% (±2).
The source — document, pages, "read from the page image" — goes into ``shareholding_source``. Only borrowers with a
figure still missing are read.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_PROMPT = """These pages of {name}'s annual report contain its shareholding pattern at the end of the financial year
(often a chart or table by category of shareholder). Return JSON only:
{{"promoter_pct": number|null, "institutional_pct": number|null, "public_pct": number|null, "as_of": "date as printed",
"page": page number within these pages}}
promoter = promoter and promoter group; institutional = all institutions together (mutual funds, insurers, banks,
foreign portfolio investors, alternative investment funds; add them if listed separately); public = all others.
Percentages of total shares as printed; null for anything the pages do not show."""


def main(only: list[str]) -> int:
    from src.core import env_loader
    env_loader.load_local_env()
    from src.application.container import build_container
    from src.data import borrowers
    from src.flow.acquire import readers

    llm = build_container().flow.llm_factory()
    if not getattr(llm, "supports_vision", False):
        print("The configured model cannot read page images — nothing done")
        return 1
    for eid in borrowers.ids():
        if only and eid not in only:
            continue
        rec = borrowers.load(eid)
        g = rec.get("group")
        if not rec.get("latest_statement_source") or g is None or all(
                getattr(g, k) is not None for k in ("promoter_holding_pct", "institutional_holding_pct", "public_holding_pct")):
            continue
        fin = ROOT / "storage" / "documents" / eid / "financials"
        ar = next((fin / f"annual_report_fy{y}.pdf" for y in (2026, 2025) if (fin / f"annual_report_fy{y}.pdf").exists()), None)
        if ar is None:
            continue
        import fitz
        with fitz.open(ar) as d:
            texts = [p.get_text() for p in d]
        score = lambda t: (3 * bool(re.search(r"(?i)shareholding pattern|categor(?:y|ies) of share|shareholding by categor|"
                                              r"distribution of shareholding", t))
                           + len(re.findall(r"(?i)promoter", t)) + 2 * bool(re.search(r"(?i)\bFPI|foreign portfolio|mutual fund", t)))
        best = sorted(range(len(texts)), key=lambda i: -score(texts[i]))[:3]
        idx = sorted({j for i in best for j in (i, i + 1) if j < len(texts)})[:6]
        raw = llm.generate(prompt=_PROMPT.format(name=rec["borrower"].company_name),
                           system_prompt="You read annual report pages for a bank. JSON only.", temperature=0.0,
                           max_tokens=1200, images=[{"mime": "application/pdf", "data": readers.pages_pdf(ar, idx)}])
        m = re.search(r"\{.*\}", raw or "", re.S)
        got = json.loads(m.group(0)) if m else {}
        vals = [got.get(k) for k in ("promoter_pct", "institutional_pct", "public_pct")]
        if not all(isinstance(v, (int, float)) and 0 <= v <= 100 for v in vals) or abs(sum(vals) - 100) > 2:
            print(f"{eid}: not read ({vals}) — stays not on record")
            continue
        g.promoter_holding_pct, g.institutional_holding_pct, g.public_holding_pct = (round(float(v), 2) for v in vals)
        page = got.get("page")
        rec["shareholding_source"] = {"document": f"financials/{ar.name}", "pages": [i + 1 for i in idx],
                                      "page": idx[page - 1] + 1 if isinstance(page, int) and 0 < page <= len(idx) else None,
                                      "as_of": got.get("as_of"), "method": "ai (page image)"}
        borrowers.save(eid, rec)
        print(f"{eid}: promoter {vals[0]} · institutions {vals[1]} · public {vals[2]} (as of {got.get('as_of')}, "
              f"pages {[i + 1 for i in idx]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
