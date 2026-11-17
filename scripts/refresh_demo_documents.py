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
    _bank_book(store, only)                              # the bank's records first: the registry reads the conduct
    _registry_files(borrowers.load_all(), only, rebuild_real=True)   # a real company: clean, from its record
    return 0


def _bank_book(store: dict, only: list[str]) -> None:
    """The bank's own records about each borrower (src/data/demo_bank_book.py): for a real borrower they are
    rebuilt from its audited figures, clean (no invented events); a fictional borrower keeps its designed story
    and only gets the blocks it lacks. The charges register goes into its demo registry file."""
    import json
    from src.core.config_manager import config
    from src.data import borrowers, demo_bank_book, demo_registry
    cfg = dict(config.get("data_sources", "demo_data", "bank_book", default={}) or {})
    cfg["tier1_capital_cr"] = config.get("exposure", "bank", "tier1_capital_cr", default=None)
    policy = config.get("rules", "policy_thresholds", default={}) or {}
    for eid, rec in sorted(store.items()):
        if only and eid not in only:
            continue
        real = bool(rec.get("latest_statement_source"))
        reg_path = demo_registry.path_for(eid)
        reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path else {}
        status = (reg.get("bureau") or {}).get("dpd_status") or "Standard"
        blocks = demo_bank_book.build(rec, cfg, policy, "Standard" if real else status)
        rec = borrowers.load(eid)
        added = []
        for k in ("existing_exposure", "conduct", "covenants", "core_banking", "crilc"):
            # a real company: rebuilt (empty when new to the bank); a fictional one: only what it lacks
            if real or (not rec.get(k) and blocks[k]):
                rec[k] = blocks[k]
                added.append(k)
        borrowers.save(eid, rec)
        if reg_path and (real or not reg.get("charges")):
            reg["charges"] = blocks["charges"]
            reg_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
            added.append("charges")
        print(f"{eid}: bank records {', '.join(added) or 'kept'}")


def _registry_files(store: dict, only: list[str], rebuild_real: bool = False) -> None:
    """A demo registry file (bureau, MCA, regulatory lists) for every borrower on record that has none and no
    bureau data of its own, so its six mandatory data checks can run (round 9). Hand-made files are kept."""
    import json
    from datetime import date
    from src.core.config_manager import config
    from src.data import demo_registry
    by_rating = config.get("data_sources", "demo_data", "bureau_by_rating", default={}) or {}
    for eid, rec in sorted(store.items()):
        real = bool(rec.get("latest_statement_source"))
        if (only and eid not in only) or (rec.get("external_data") or {}).get("bureau_data")                 or (demo_registry.path_for(eid) and not (rebuild_real and real)):
            continue
        data = demo_registry.from_record(rec, by_rating, date.today().isoformat())
        old = demo_registry.load(eid) or {}
        if old.get("charges"):
            data["charges"] = old["charges"]             # written by _bank_book
        (demo_registry.ROOT / f"{eid}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10),
                                                        encoding="utf-8")
        print(f"{eid}: demo registry file written ({data['bureau'].get('cmr_rank') or 'no rank'})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
