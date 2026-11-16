"""Save each listed borrower's latest rating rationale (config/borrower_documents.yaml, ``rating:``) as a PDF.

    .venv/Scripts/python scripts/save_rating_rationales.py

A rationale published as a PDF is saved as it is. One published as a web page (CRISIL, ICRA, India Ratings) is
saved as a text PDF: the page's text, headed by the agency, date and source URL. The files are small and are
committed, so this runs once when the manifest changes, not at deploy.
"""

import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "storage" / "documents"
UA = "CorporateCreditOrigination-UAT/1.0 (public rating rationale for testing; one-time download)"


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "head", "nav", "footer", "svg"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("p", "br", "tr", "li", "h1", "h2", "h3", "h4", "div", "table"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in ("td", "th"):
            self.parts.append("  ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        t = re.sub(r"[ \t\xa0]+", " ", "".join(self.parts))
        return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _pdf_from_text(title: str, text: str) -> bytes:
    """A plain A4 text PDF: lines wrapped at 105 characters, 68 lines a page."""
    import textwrap

    import fitz
    ascii_ = str.maketrans({"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
                            "₹": "Rs.", "•": "-", " ": " "})        # the built-in font is Latin-1
    lines = []
    for para in (title + "\n\n" + text).translate(ascii_).split("\n"):
        lines += textwrap.wrap(para, 105) or [""]
    doc = fitz.open()
    for i in range(0, len(lines), 68):
        page = doc.new_page()
        for j, line in enumerate(lines[i:i + 68]):
            page.insert_text((48, 60 + j * 11), line, fontsize=8.5, fontname="helv")
    out = doc.tobytes()
    doc.close()
    return out


def main() -> int:
    m = yaml.safe_load((ROOT / "config" / "borrower_documents.yaml").read_text(encoding="utf-8"))
    bad = 0
    for entity, spec in (m.get("borrowers") or {}).items():
        r = (spec or {}).get("rating")
        if not r:
            continue
        agency = re.sub(r"[^a-z]+", "_", str(r["agency"]).lower()).strip("_")
        target = DOCS / entity / "ratings" / f"rating_rationale_{agency}_{r['date']}.pdf"
        if target.exists():
            continue
        try:
            req = urllib.request.Request(r["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            if not data.startswith(b"%PDF"):
                p = _Text()
                p.feed(data.decode("utf-8", errors="ignore"))
                text = p.text()
                if len(text) < 400:
                    raise ValueError("the page has no rationale text")
                data = _pdf_from_text(f"RATING RATIONALE - {r['agency']}, {r['date']}\nSource: {r['url']}", text)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f"saved {entity}: {target.name} ({len(data) / 1e3:.0f} KB)")
        except Exception as e:                              # noqa: BLE001
            bad += 1
            print(f"skip  {entity}: {e}", file=sys.stderr)
        time.sleep(2)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
