"""Download the public documents of the UAT test packs (test-documents/*/public/) where they are missing.

    python3 scripts/fetch_test_packs.py

The annual reports and rating rationales are public filings but are not committed (size), so a fresh clone (Cloud
Shell) has only the demo documents. deploy_gcp.sh runs this before building, so "Load test pack" works in the cloud.
Standard library only; one request at a time, a few seconds apart. A failed download is reported and skipped.
"""

import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "test-documents"
PUBLIC = re.compile(r'''"([\w.-]+\.pdf)"\s*:\s*"(https?://[^"]+)"''')
UA = "CorporateCreditOrigination-UAT/1.0 (test data, one-time download)"


def main() -> int:
    missing = 0
    for spec in sorted(ROOT.glob("*/prepare.py")):
        out = spec.parent / "public"
        for name, url in PUBLIC.findall(spec.read_text(encoding="utf-8", errors="ignore")):
            target = out / name
            if target.exists() and target.stat().st_size > 1000:
                continue
            out.mkdir(exist_ok=True)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = r.read()
                if not data.startswith(b"%PDF"):
                    raise ValueError("not a PDF")
                target.write_bytes(data)
                print(f"saved {spec.parent.name}/{name} ({len(data) / 1e6:.1f} MB)")
            except Exception as e:                          # noqa: BLE001 - report and carry on
                missing += 1
                print(f"skip  {spec.parent.name}/{name}: {e}", file=sys.stderr)
            time.sleep(3)
    print("Test packs ready" + (f" ({missing} public document(s) missing)" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
