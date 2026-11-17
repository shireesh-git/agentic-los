"""Read every catalogue borrower's documents once, so the extraction cache is built ahead of the first CAM.

Run while the cloud image is built (see the Dockerfile): the cache is written for the image's own paths and
OCR setup, so the first CAM run for a borrower reuses it instead of reading hundreds of pages on one CPU.
New prospects (folders P<NAME><4 hex>) are read when their documents are uploaded, not here.
"""

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CAM_GEMINI_OCR", "off")       # no cloud credentials while the image is built

from src.core.runtime_paths import DOCUMENTS_ROOT  # noqa: E402
from src.engines import notes_reader  # noqa: E402
from src.services.document_extractor import extract_all_documents  # noqa: E402


def _warm(eid: str) -> str:
    t = time.time()
    res = extract_all_documents(eid, DOCUMENTS_ROOT)
    notes = notes_reader.for_entity(eid, use_model=False)   # the rules reading; the AI reads on the first CAM
    return (f"{eid}: {res.get('document_count', 0)} document(s) in {time.time() - t:.0f}s"
            + (f"; notes: {notes.get('red_flags', 0)} red flag(s)" if notes.get("available") else ""))


def main() -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    started = time.time()
    # catalogue borrowers are AAAA999 (PNCR001 and PINF001 start with P too); prospects are P<NAME><4 hex>
    ids = sorted(p.name for p in DOCUMENTS_ROOT.iterdir() if p.is_dir() and re.fullmatch(r"[A-Z]{4}\d{3}", p.name))
    # one borrower per CPU (the build machine has several; cache files are written atomically)
    with ProcessPoolExecutor(max_workers=max(1, os.cpu_count() or 1)) as pool:
        for fut in as_completed([pool.submit(_warm, eid) for eid in ids]):
            print(fut.result(), flush=True)
    print(f"Document cache ready in {time.time() - started:.0f}s on {os.cpu_count()} CPU(s)", flush=True)


if __name__ == "__main__":
    main()
