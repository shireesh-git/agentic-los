"""Write the POC demo document set (a fictional prospect) for the agentic LOS walkthrough.

    python scripts/make_demo_documents.py [output folder]     (default: demo_documents/)

Upload the files on New Application → "New prospect from documents" in the categories of
their folders (request, kyc, financials; cam for the bank's CAM), and the legal/ and drawdown
files at the Post Sanction and Disbursement steps. See docs/POC_DEMO_SCRIPT.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.devtools.demo_documents import write_set  # noqa: E402

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "demo_documents")
    for path in write_set(out, include_cam=True):
        print(path)
