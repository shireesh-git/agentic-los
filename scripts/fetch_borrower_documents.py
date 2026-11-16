"""Download the latest public filings of the listed borrowers (config/borrower_documents.yaml, ``fetch:``).

    python3 scripts/fetch_borrower_documents.py            # what is missing
    python3 scripts/fetch_borrower_documents.py --force    # everything again

Annual reports (FY2026) and the results for the quarter to 30 September 2026 are large public files, so they are
not committed: this script puts them in storage/documents/<entity>/<file>. deploy_gcp.sh runs it in Cloud Shell
before each build. Standard library only; one request at a time, a few seconds apart; a file that does not
download as a PDF is reported and skipped.
"""

import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "borrower_documents.yaml"
DOCS = ROOT / "storage" / "documents"
UA = "CorporateCreditOrigination-UAT/1.0 (public filings for testing; one-time download)"


def manifest() -> list[tuple[str, str, str]]:
    """(entity, relative file, url) for every ``fetch:`` entry — read as text, so PyYAML is not needed."""
    out, entity, in_fetch = [], None, False
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^  ([A-Z0-9]+):\s*$", line)
        if m:
            entity, in_fetch = m.group(1), False
            continue
        if re.match(r"^    fetch:\s*$", line):
            in_fetch = True
            continue
        if re.match(r"^    \S", line):
            in_fetch = False
        m = re.match(r"^      ([\w./-]+\.pdf):\s*(https?://\S+)\s*$", line)
        if entity and in_fetch and m:
            out.append((entity, m.group(1), m.group(2)))
    return out


def main(force: bool = False) -> int:
    missing = 0
    for entity, rel, url in manifest():
        target = DOCS / entity / rel
        if target.exists() and target.stat().st_size > 10_000 and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if not data.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            target.write_bytes(data)
            print(f"saved {entity}/{rel} ({len(data) / 1e6:.1f} MB)")
        except Exception as e:                              # noqa: BLE001 - report and carry on
            missing += 1
            print(f"skip  {entity}/{rel}: {e}", file=sys.stderr)
        time.sleep(3)
    print("Borrower documents ready" + (f" ({missing} could not be fetched)" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
