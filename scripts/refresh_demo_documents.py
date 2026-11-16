"""Regenerate the demo (non-public) documents of the listed borrowers from their latest figures (round 8).

    .venv/Scripts/python scripts/refresh_demo_documents.py [ENTITY ...]

Also writes a demo registry file (storage/demo_registry/) for each borrower that has none — see _registry_files.

The bank statement, GST returns summary, bureau report and KYC pack of a listed borrower are not public, so they are
generated stand-ins, labelled as synthetic. After the latest audited years were read from the annual reports
(scripts/read_fy2026_statements.py), they are regenerated from the latest year — so they agree with the figures the CAM
uses. Only borrowers whose statements were read from an annual report (``latest_statement_source``) are refreshed.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(only: list[str]) -> int:
    from src.data import borrowers
    from src.engines import document_downloader as dd

    store = borrowers.load_all()
    for eid in sorted(e for e, r in store.items() if r.get("latest_statement_source")):
        if only and eid not in only:
            continue
        data = dd._build_company_data_from_registry(eid)
        if not data:
            print(f"{eid}: no registry record")
            continue
        out = ROOT / "storage" / "documents" / eid
        files = (dd._generate_kyc_documents(eid, data, out) + dd._generate_gst_summaries(eid, data, out)
                 + dd._generate_bureau_documents(eid, data, out) + dd._generate_banking_documents(eid, data, out))
        print(f"{eid}: {dd._latest_year_key(data['financials'])} · {len(files)} documents")
    _registry_files(store, only)
    return 0


def _registry_files(store: dict, only: list[str]) -> None:
    """A demo registry file (bureau, MCA, regulatory lists) for every borrower on record that has none and no
    bureau data of its own, so its six mandatory data checks can run (round 9). Hand-made files are kept."""
    import json
    from datetime import date
    from src.core.config_manager import config
    from src.data import demo_registry
    by_rating = config.get("data_sources", "demo_data", "bureau_by_rating", default={}) or {}
    for eid, rec in sorted(store.items()):
        if (only and eid not in only) or demo_registry.path_for(eid) or (rec.get("external_data") or {}).get("bureau_data"):
            continue
        data = demo_registry.from_record(rec, by_rating, date.today().isoformat())
        (demo_registry.ROOT / f"{eid}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10),
                                                        encoding="utf-8")
        print(f"{eid}: demo registry file written ({data['bureau'].get('cmr_rank') or 'no rank'})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
