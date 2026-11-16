"""Read each listed borrower's audited standalone statements from its latest annual reports into its data file.

    .venv/Scripts/python scripts/read_fy2026_statements.py [ENTITY ...]

Uses the same reader as the new-to-bank financials agent (src/flow/acquire/readers.read_financial_statements): our
layout reading of the statement pages and Gemini reading the pages themselves, both checked (the balance sheet
reconciles, revenue exceeds profit). The latest annual report (storage/documents/<id>/financials/annual_report_fy2026.pdf,
else fy2025) gives two years; the previous report on record adds one more when its figures agree. The statements
replace ``financials`` in data/borrowers/<id>.json, with their provenance in ``latest_statement_source``.

Run it when a new annual report is fetched (scripts/fetch_borrower_documents.py), then
scripts/refresh_demo_documents.py.
"""

import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _usable(s: dict) -> bool:
    it = s["items"]
    rev, pat = it.get("revenue_operating") or 0, it.get("pat")
    return all(c["ok"] for c in s.get("checks") or []) and rev > 0 and pat not in (None, 0) and abs(pat) < rev


def main(only: list[str]) -> int:
    from src.core import env_loader
    env_loader.load_local_env()                                  # the AI model key (.env.local), as the app does
    from src.application.container import build_container
    from src.data import borrowers
    from src.flow.acquire import readers
    from src.models.canonical_model import FinancialStatement

    llm = build_container().flow.llm_factory()
    for eid in borrowers.ids():
        if only and eid not in only:
            continue
        fin = ROOT / "storage" / "documents" / eid / "financials"
        latest = next((fin / f"annual_report_fy{y}.pdf" for y in (2026, 2025)
                       if (fin / f"annual_report_fy{y}.pdf").exists()
                       and (fin / f"annual_report_fy{y}.pdf").stat().st_size > 1_000_000), None)
        if latest is None:
            print(f"{eid}: no annual report on file — figures unchanged")
            continue
        t = time.time()
        try:
            r = readers.read_financial_statements(latest, llm)
        except Exception as e:                                       # noqa: BLE001 - reported; the record is kept
            print(f"{eid}: not read — {e}")
            continue
        statements = [dict(s, document=f"financials/{latest.name}") for s in r["statements"] if _usable(s)]
        year = int(latest.stem[-4:])
        older = fin / f"annual_report_fy{year - 1}.pdf"
        if older.exists() and older.stat().st_size > 1_000_000 and len(statements) == 2:
            try:
                r2 = readers.read_financial_statements(older, llm)
                a, b = statements[1]["items"].get("revenue_operating"), r2["statements"][0]["items"].get("revenue_operating")
                if _usable(r2["statements"][1]) and a and b and abs(a - b) <= 0.02 * a:
                    statements.append(dict(r2["statements"][1], document=f"financials/{older.name}"))
            except Exception as e:                                   # noqa: BLE001
                print(f"{eid}: {older.name} not read — {e}")
        if not statements or statements[0]["period"] != r["statements"][0]["period"]:
            print(f"{eid}: the latest year did not pass the checks — figures unchanged")
            continue
        rec = borrowers.load(eid)
        rec["financials"] = {s["period"]: FinancialStatement(
            entity_id=eid, period=s["period"], statement_type=s.get("basis") or "standalone", source="audited",
            as_of_date=date.fromisoformat(s["as_of"]), line_items=dict(s["items"])) for s in statements}
        rec["provisional"] = None
        # read from the audited statements: the CAM engine's document extraction must not overwrite them
        rec["verified_overrides"] = {**(rec.get("verified_overrides") or {}),
                                     "financials": [f"{s['period']}.{k}" for s in statements for k in s["items"]]}
        rec["latest_statement_source"] = {"period": statements[0]["period"], "document": statements[0]["document"],
                                          "pages": r["pages"], "method": r["method"], "unit": r["unit"],
                                          "cross_check": r.get("cross_check") or {},
                                          "filled_from_layout": r.get("filled_from_layout") or []}
        borrowers.save(eid, rec)
        print(f"{eid}: {', '.join(s['period'] for s in statements)} via {r['method']}"
              + (f" · differs {r['cross_check']}" if r.get("cross_check") else "")
              + f" · revenue {statements[0]['items'].get('revenue_operating')} · PAT {statements[0]['items'].get('pat')}"
              + f" ({time.time() - t:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
