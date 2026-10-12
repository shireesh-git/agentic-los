"""
Reorganise test-documents/ into the CAM document model (core CAM pack / conditional / additional evidence).

REORGANISE, DON'T DELETE:
  * every move is a same-volume rename of an existing file into a new folder, filename unchanged
    (plain filesystem move, so the git index is not touched; git shows it as a rename once staged);
  * nothing is copied, deleted, renamed or edited;
  * a move is skipped (file left in place) if its target already exists;
  * before/after inventories with SHA-256 are compared and the run fails loudly on any difference.

Runtime ingestion reads storage/documents/{entity}/{category}/ (src/services/document_extractor.py,
src/agents/ingestion_agent.py), never test-documents/, so these moves do not affect the pipeline.
storage/documents/ is hashed before and after to prove it is untouched.

Usage:
  python scripts/rationalise_test_documents.py --plan      # show the plan, change nothing
  python scripts/rationalise_test_documents.py --apply     # move, verify, write the inventory
  python scripts/rationalise_test_documents.py --verify    # re-check the inventory against the disk
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "test-documents"
STORAGE = ROOT / "storage" / "documents"
INVENTORY = DOCS / "document_inventory.json"
NEW_FILES = {"document_inventory.json", "CAM_DOCUMENT_MODEL.md"}   # written by this script; not part of the corpus

BORROWER_DIRS = ["APOL001_Apollo_Hospitals", "IHCL001_IHCL", "INFY001_Infosys", "MFL001_Madras_Fertilisers",
                 "MRF001_MRF", "PNCR001_PNC_Roads"]

CORE, CONDITIONAL, ADDITIONAL = "CORE", "CONDITIONAL", "ADDITIONAL"

# Who reads a storage/documents/{entity}/<category>/ folder today (document_extractor.py, ingestion_agent.py).
# Categories with no reader are listed as such; nothing is claimed beyond the current code.
CATEGORY_CONSUMERS = {
    "financials": ["data_ingestion: document extraction (audited / provisional / debt schedule)",
                   "financial_analysis", "repayment assessment (M4)", "resilience assessment (M5)", "CAM"],
    "request": ["data_ingestion: request note / site visit extraction"],
    "banking": ["data_ingestion: bank statement extraction"],
    "ratings": ["data_ingestion: rating report extraction"],
    "kyc": ["data_ingestion: KYC text", "validation: NTB document checklist (document inventory)"],
    "collateral": ["data_ingestion: valuation report extraction", "validation: NTB document checklist"],
    "gst": ["data_ingestion: GST document"],
    "exchange": ["data_ingestion: exchange filing"],
    "bureau": [], "mca": [], "legal": [], "misc": [],
}

# platform-document-pack/<category>/<file> → target folder (relative to the borrower), role.
PACK_RULES = {
    "financials": ("core-cam/financials", CORE),
    "request": ("core-cam/credit-request", CORE),
    "banking": ("core-cam/banking-debt", CORE),
    "bureau": ("core-cam/credit-history", CORE),
    "ratings": ("core-cam/credit-history", CORE),
    "kyc": ("core-cam/borrower-corporate", CORE),
    "mca": ("core-cam/borrower-corporate", CORE),
    "collateral": ("conditional/security", CONDITIONAL),
    "gst": ("additional-evidence/compliance", ADDITIONAL),
    "legal": ("additional-evidence/legal", ADDITIONAL),
    "misc": ("additional-evidence/other", ADDITIONAL),
}
# File-level exceptions within the pack (more specific than the category).
PACK_FILE_RULES = {
    "debt_schedule": ("core-cam/banking-debt", CORE),                  # existing debt position
    "itr_auto_fetch.json": ("additional-evidence/compliance", ADDITIONAL),
    "board_resolution_borrowing.pdf": ("additional-evidence/legal", ADDITIONAL),
    "quarterly_results": ("core-cam/financials", CORE),               # latest unaudited results
    "corporate_governance_report.pdf": ("core-cam/borrower-corporate", CORE),   # shareholding / promoters
    "nse_live_quote.json": ("additional-evidence/other", ADDITIONAL),
    "epfo": ("additional-evidence/compliance", ADDITIONAL),
    "probe42_epfo_details.json": ("additional-evidence/compliance", ADDITIONAL),
}
# optional-inputs/<file> → target, role, the storage category it would be uploaded to (None = no category).
OPTIONAL_RULES = {
    "synthetic_bank_statements.pdf": ("core-cam/banking-debt", CORE, "banking"),
    "synthetic_credit_facility_details.pdf": ("core-cam/banking-debt", CORE, "banking"),   # existing exposure summary
    "synthetic_cma_projection.pdf": ("additional-evidence/projections", ADDITIONAL, None),
    "cma_projection_enhanced.pdf": ("additional-evidence/projections", ADDITIONAL, None),
    "road_construction_projections.pdf": ("additional-evidence/projections", ADDITIONAL, None),
    "synthetic_valuation_report.pdf": ("additional-evidence/valuation", ADDITIONAL, "collateral"),
    "synthetic_property_documents.pdf": ("additional-evidence/legal", ADDITIONAL, None),
    "synthetic_cersai_search.pdf": ("additional-evidence/legal", ADDITIONAL, None),
    "synthetic_board_resolution_borrowing.pdf": ("additional-evidence/legal", ADDITIONAL, "kyc"),
    "synthetic_undertakings.pdf": ("additional-evidence/legal", ADDITIONAL, None),
    "synthetic_site_visit_report.pdf": ("additional-evidence/site-visit", ADDITIONAL, "request"),
    "synthetic_insurance_policies.pdf": ("additional-evidence/insurance", ADDITIONAL, None),
    "synthetic_internal_credit_notes.pdf": ("additional-evidence/other", ADDITIONAL, None),
}

# Folders kept where they are (already match the model, or not borrower inputs).
KEEP_REASONS = {
    "annual-reports": "Real annual reports and unaudited results; the model keeps annual-reports/ as the source folder.",
    "annual-reports-real": "Second set of real PNC annual reports; kept beside annual-reports/ as the source folder.",
    "metadata.json": "Platform pack manifest (categories of the original storage pack); kept with platform-document-pack/.",
    "optional-inputs.zip": "Archive of the optional inputs; kept as-is at the borrower root.",
    "TVS_Motors": "Real annual reports for a company without an entity id yet; nothing to classify.",
    "reference-cams": "Reference CAM documents (not borrower inputs).",
    "etb-overlays": "ETB overlay JSON (not a borrower document).",
    "README.md": "Corpus guide (documentation, not a test document).",
}

WORKFLOW_MAP = {
    "core-cam/financials": "Audited / provisional financials → financial analysis → repayment assessment → resilience "
                           "assessment → CAM",
    "core-cam/credit-request": "Credit request → credit assessment (facility details) → credit challenge → credit decision → CAM",
    "core-cam/banking-debt": "Banking / existing debt → repayment assessment, credit history → credit decision",
    "core-cam/credit-history": "Bureau / CRILC / rating → credit history (CAM section 5) → risk identification",
    "core-cam/borrower-corporate": "KYC / MCA / shareholding → validation document checklist → borrower profile",
    "conditional/security": "Security / valuation → security cover (repayment secondary source) → facility structure → "
                            "recommendation",
    "conditional/working-capital": "Debtor / creditor ageing → risk identification → due diligence → credit challenge → "
                                   "repayment assessment",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(base: Path, skip_new: bool = True) -> dict[str, dict]:
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_file() and not (skip_new and p.parent == DOCS and p.name in NEW_FILES):
            out[p.relative_to(ROOT).as_posix()] = {"size": p.stat().st_size, "sha256": sha256(p)}
    return out


def entity_of(borrower_dir: str) -> str:
    return borrower_dir.split("_", 1)[0]


def plan() -> tuple[list[dict], list[dict]]:
    """(moves, kept) for every file under the borrower folders."""
    moves, kept = [], []
    for bdir in BORROWER_DIRS:
        base = DOCS / bdir
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(base).parts
            target = role = storage_cat = None
            provenance = "synthetic" if p.name.startswith("synthetic_") else None
            if rel[0] == "platform-document-pack" and len(rel) == 3:
                storage_cat = rel[1]
                target, role = PACK_RULES.get(rel[1], (None, None))
                for key, rule in PACK_FILE_RULES.items():
                    if p.name == key or p.name.startswith(key):
                        target, role = rule
                provenance = provenance or "platform-generated pack"
            elif rel[0] == "optional-inputs" and len(rel) == 2:
                target, role, storage_cat = OPTIONAL_RULES.get(p.name, (None, None, None))
                provenance = provenance or "synthetic"
            entry = {"borrower": entity_of(bdir), "filename": p.name,
                     "original_path": p.relative_to(ROOT).as_posix(), "storage_category": storage_cat,
                     "provenance": provenance}
            if target:
                dest = base / target / p.name
                if dest.exists():
                    kept.append({**entry, "reason": f"target {dest.relative_to(ROOT).as_posix()} already exists"})
                else:
                    moves.append({**entry, "new_path": dest.relative_to(ROOT).as_posix(), "folder": target, "role": role})
            else:
                key = rel[0] if rel[0] in KEEP_REASONS else p.name
                kept.append({**entry, "reason": KEEP_REASONS.get(key, "no rule; left in place")})
    # Two sources must never land on the same target.
    seen: dict[str, str] = {}
    for m in moves:
        if m["new_path"] in seen:
            raise SystemExit(f"COLLISION: {m['original_path']} and {seen[m['new_path']]} → {m['new_path']}")
        seen[m["new_path"]] = m["original_path"]
    return moves, kept


def classify_kept(entry: dict) -> tuple[str, str]:
    """(folder, role) for a file left in place."""
    path = entry["original_path"]
    if "/annual-reports" in path:
        return "annual-reports", CORE
    if path.endswith("platform-document-pack/metadata.json"):
        return "platform-document-pack", ADDITIONAL
    return "other", ADDITIONAL


def build_inventory(moves, kept, before) -> dict:
    docs = []
    for m in moves:
        cat = m["storage_category"]
        docs.append({"borrower": m["borrower"], "filename": m["filename"], "original_path": m["original_path"],
                     "current_path": m["new_path"], "moved": True, "document_category": m["folder"],
                     "cam_role": m["role"], "upload_as_storage_category": cat, "provenance": m["provenance"],
                     "likely_consumers": CATEGORY_CONSUMERS.get(cat, []) if cat else [],
                     "sha256": before[m["original_path"]]["sha256"], "size": before[m["original_path"]]["size"],
                     "preserved": True})
    for k in kept:
        folder, role = classify_kept(k)
        is_report = folder == "annual-reports"
        docs.append({"borrower": k["borrower"], "filename": k["filename"], "original_path": k["original_path"],
                     "current_path": k["original_path"], "moved": False, "document_category": folder, "cam_role": role,
                     "upload_as_storage_category": "financials" if is_report else k["storage_category"],
                     "provenance": "real (public annual report / results)" if is_report else k["provenance"],
                     "likely_consumers": CATEGORY_CONSUMERS["financials"] if is_report else [],
                     "kept_reason": k["reason"], "sha256": before[k["original_path"]]["sha256"],
                     "size": before[k["original_path"]]["size"], "preserved": True})
    borrower_paths = {d["original_path"] for d in docs}
    for path, meta in before.items():          # non-borrower files under test-documents/
        if path.startswith("test-documents/") and path not in borrower_paths:
            top = Path(path).relative_to("test-documents").parts[0]
            docs.append({"borrower": None, "filename": Path(path).name, "original_path": path, "current_path": path,
                         "moved": False, "document_category": "non-borrower", "cam_role": None,
                         "kept_reason": KEEP_REASONS.get(top, "not a borrower input"), "sha256": meta["sha256"],
                         "size": meta["size"], "preserved": True})
    docs.sort(key=lambda d: d["original_path"])
    abce = sorted(p for p in before if p.startswith("storage/documents/ABCE001/"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_by": "scripts/rationalise_test_documents.py",
        "principle": "Reorganised, not deleted: every original file is present (same name and SHA-256).",
        "counts": {"documents": len(docs), "moved": sum(d["moved"] for d in docs),
                   "left_in_place": sum(not d["moved"] for d in docs)},
        "cam_document_model": {
            "CORE": ["core-cam/financials", "core-cam/credit-request", "core-cam/banking-debt", "core-cam/credit-history",
                     "core-cam/borrower-corporate", "annual-reports"],
            "CONDITIONAL": ["conditional/working-capital", "conditional/security"],
            "ADDITIONAL": ["additional-evidence/projections", "additional-evidence/valuation", "additional-evidence/legal",
                           "additional-evidence/compliance", "additional-evidence/site-visit",
                           "additional-evidence/insurance", "additional-evidence/other"],
        },
        "workflow_mapping": WORKFLOW_MAP,
        "runtime_note": ("The pipeline reads storage/documents/{entity}/{category}/, not test-documents/. "
                         "'upload_as_storage_category' is the category a test file is uploaded into. ABCE001 is an "
                         "in-code demo borrower: its files exist only under storage/documents/ABCE001/ and were not moved."),
        "abce001_storage_documents": abce,
        "documents": docs,
    }


def verify(before: dict, after: dict, moves: list[dict]) -> list[str]:
    errors = []
    if len(before) != len(after):
        errors.append(f"count changed: {len(before)} → {len(after)}")
    key = lambda snap: sorted((Path(p).name, m["sha256"]) for p, m in snap.items())
    if key(before) != key(after):
        errors.append("the multiset of (filename, sha256) changed")
    moved_from = {m["original_path"]: m["new_path"] for m in moves}
    for path, meta in before.items():
        now = moved_from.get(path, path)
        if now not in after:
            errors.append(f"missing: {path} (expected at {now})")
        elif after[now]["sha256"] != meta["sha256"]:
            errors.append(f"content changed: {now}")
    return errors


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if args.verify:
        inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
        bad = [d["current_path"] for d in inv["documents"]
               if not (ROOT / d["current_path"]).is_file() or sha256(ROOT / d["current_path"]) != d["sha256"]]
        print(f"{len(inv['documents'])} documents in inventory; {len(bad)} missing or changed")
        for b in bad:
            print("  ", b)
        sys.exit(1 if bad else 0)

    before_docs, before_storage = snapshot(DOCS), snapshot(STORAGE)
    moves, kept = plan()
    print(f"test-documents files: {len(before_docs)}; storage/documents files: {len(before_storage)}")
    print(f"planned moves: {len(moves)}; left in place: {len(kept)}")
    if args.plan:
        for m in moves:
            print(f"  MOVE {m['original_path']}  →  {m['new_path']}  [{m['role']}]")
        for k in kept:
            print(f"  KEEP {k['original_path']}  ({k['reason']})")
        return

    for m in moves:
        dest = ROOT / m["new_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = ROOT / m["original_path"]
        if dest.exists():
            raise SystemExit(f"target appeared during the run, stopping: {m['new_path']}")
        src.rename(dest)          # same-volume rename: a move, never a copy; the git index is not touched
    for d in sorted((p for p in DOCS.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()                       # only empty source folders left behind by the moves

    after_docs, after_storage = snapshot(DOCS), snapshot(STORAGE)
    errors = verify(before_docs, after_docs, moves)
    if before_storage != after_storage:
        errors.append("storage/documents changed")
    inventory = build_inventory(moves, kept, {**before_docs, **before_storage})
    INVENTORY.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"after: test-documents files {len(after_docs)}; storage/documents files {len(after_storage)}")
    print("VERIFY:", "PASS" if not errors else "FAIL")
    for e in errors:
        print("  ", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
