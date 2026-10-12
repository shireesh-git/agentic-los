"""
Populate synthetic document packs for listed real-company profiles.

This script uses the generalized document downloader to:
  1. Pull live NSE quote data when available
  2. Scrape lightweight public company profile context
  3. Generate synthetic-but-credible financial PDFs/Excel/JSON documents
  4. Backfill sparse folders under storage/documents/{entity_id}/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engines.document_downloader import populate_supported_company_documents


def main(force_refresh: bool = False) -> int:
    result = populate_supported_company_documents(force_refresh=force_refresh)
    generated = [(item["entity_id"], item["files_generated"]) for item in result["generated"]]
    skipped = result["skipped"]
    failed = [(item["entity_id"], item["message"]) for item in result["failed"]]

    print("Generated:")
    for entity_id, count in generated:
        print(f"  {entity_id}: {count} files")

    print("Skipped:")
    for entity_id in skipped:
        print(f"  {entity_id}")

    if failed:
        print("Failed:")
        for entity_id, message in failed:
            print(f"  {entity_id}: {message}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(force_refresh="--force" in sys.argv))