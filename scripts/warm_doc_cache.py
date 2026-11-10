"""Read every catalogue borrower's documents once, so the extraction cache is built ahead of the first CAM.

Run while the cloud image is built (see the Dockerfile): the cache is written for the image's own paths and
OCR setup, so the first CAM run for a borrower reuses it instead of reading hundreds of pages on one CPU.
New prospects (folders starting with "P") are read when their documents are uploaded, not here.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CAM_GEMINI_OCR", "off")       # no cloud credentials while the image is built

from src.core.runtime_paths import DOCUMENTS_ROOT  # noqa: E402
from src.engines import notes_reader  # noqa: E402
from src.services.document_extractor import extract_all_documents  # noqa: E402


def main() -> None:
    started = time.time()
    for folder in sorted(p for p in DOCUMENTS_ROOT.iterdir() if p.is_dir() and not p.name.startswith(("P", "_"))):
        t = time.time()
        res = extract_all_documents(folder.name, DOCUMENTS_ROOT)
        notes = notes_reader.for_entity(folder.name, use_model=False)   # the rules reading; the AI reads on the first CAM
        print(f"{folder.name}: {res.get('document_count', 0)} document(s) in {time.time() - t:.0f}s"
              + (f"; notes: {notes.get('red_flags', 0)} red flag(s)" if notes.get("available") else ""), flush=True)
    print(f"Document cache ready in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
