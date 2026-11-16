"""UAT test packs for new-to-bank prospects (test-documents/<borrower>/).

Each pack has a ``prepare.py`` naming the borrower (name, CIN) and the public documents it downloads, a ``demo/``
folder of generated documents filed by category (mca, kyc, bureau, banking, gst) and a ``public/`` folder of the
borrower's real annual reports and rating rationale. The RM loads a pack into a prospect's proposal in one click,
instead of uploading each document. The packs are read as text: ``prepare.py`` is never imported or run here.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from src.flow.graph import norm_name

_NAME = re.compile(r'''(?:"name"\s*:|^NAME\s*=)\s*"([^"]+)"''', re.M)
_CIN = re.compile(r'''(?:"cin"\s*:|^CIN\s*=)\s*"([A-Z0-9]{21})"''', re.M)
_PUBLIC = re.compile(r'''"([\w.-]+\.pdf)"\s*:\s*"(https?://[^"]+)"''')


def packs(root: Optional[Path]) -> list[dict]:
    """Every pack under ``root``: folder, borrower name, CIN and the public documents it downloads."""
    if not root or not Path(root).is_dir():
        return []
    out = []
    for spec in sorted(Path(root).glob("*/prepare.py")):
        text = spec.read_text(encoding="utf-8", errors="ignore")
        name, cin = _NAME.search(text), _CIN.search(text)
        if not name:
            continue
        out.append({"dir": spec.parent, "id": spec.parent.name, "name": name.group(1),
                    "cin": cin.group(1) if cin else None, "public": dict(_PUBLIC.findall(text))})
    return out


def find(root: Optional[Path], cin: Optional[str], name: str) -> Optional[dict]:
    """The pack for this borrower: by CIN when both have one, else by registered name."""
    key = norm_name(name)
    for p in packs(root):
        if cin and p["cin"]:
            if p["cin"] == cin.strip().upper():
                return p
        elif key and norm_name(p["name"]) == key:
            return p
    return None


def _category(file_name: str) -> str:
    n = file_name.lower()
    if "rationale" in n or "rating" in n:
        return "ratings"
    return "financials"


def files(pack: dict) -> list[tuple[Path, str]]:
    """(document, category) for every PDF in the pack: demo/<category>/*.pdf and public/*.pdf."""
    out = []
    demo = pack["dir"] / "demo"
    if demo.is_dir():
        out += [(p, p.parent.name) for p in sorted(demo.glob("*/*.pdf"))]
    public = pack["dir"] / "public"
    if public.is_dir():
        out += [(p, _category(p.name)) for p in sorted(public.glob("*.pdf"))]
    return out


def copy_into(pack: dict, folder: Path) -> list[str]:
    """Copy the pack into a borrower's document folder; returns 'category/file' for each document."""
    done = []
    for src, cat in files(pack):
        dest = folder / cat
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest / src.name)
        done.append(f"{cat}/{src.name}")
    return done
