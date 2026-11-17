"""Check every borrower's test data against its own public documents, and report what does not hold up.

    .venv/Scripts/python scripts/validate_test_data.py [ENTITY ...]

For a borrower with its annual report on file (storage/documents/<id>/financials/annual_report_fy2026.pdf, else
fy2025) the data file's identity facts must appear in that report: CIN, registered name, PAN, each director's
name and DIN, the statutory auditor, the registered office PIN code. The external rating must match the rating
rationale on file. Every borrower is also checked for internal consistency: CIN format and incorporation year,
PAN format (and that its 5th letter is the first letter of the name, as for every company PAN), the demo
registry file naming the same company, and no other company's name in its generated demo documents.

Synthetic borrowers (no annual report) are checked for consistency only. Nothing is changed: the report says
what to fix.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PAN = re.compile(r"^[A-Z]{3}C[A-Z]\d{4}[A-Z]$")
CIN = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}(PLC|PTC|GOI|NPL|SGC|FLC|GAP|GAT|ULL|ULT|OPC)\d{6}$")


def _text(pdf: Path) -> str:
    import fitz
    with fitz.open(pdf) as d:
        return " ".join(" ".join(p.get_text().split()) for p in d)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _first_word(name: str) -> str:
    w = [x for x in re.split(r"\W+", name.upper()) if x and x not in ("THE", "M/S")]
    return w[0] if w else ""


def check(eid: str, rec: dict) -> list[tuple[str, str]]:
    from src.data import demo_registry
    out = []
    b = rec["borrower"]
    g = (lambda k: b.get(k)) if isinstance(b, dict) else (lambda k: getattr(b, k, None))   # noqa: E731
    name, cin = g("company_name") or "", g("cin") or ""
    pan = (rec.get("identifiers") or {}).get("pan") or g("pan") or ""
    inc = g("date_of_incorporation")
    inc = inc.isoformat() if hasattr(inc, "isoformat") else str(inc or "")

    # consistency
    if not CIN.match(cin):
        out.append(("error", f"CIN {cin!r} is not a valid CIN"))
    elif inc and inc[:4] != cin[8:12]:
        out.append(("error", f"incorporation {inc} disagrees with the CIN year {cin[8:12]}"))
    if pan and not PAN.match(pan):
        out.append(("error", f"PAN {pan!r} is not a company PAN (AAACx9999x)"))
    elif pan and pan[4] != _first_word(name)[:1]:
        out.append(("error", f"PAN {pan} — 5th letter should be {_first_word(name)[:1]!r}, the first letter of the name"))
    reg = demo_registry.load(eid, cin)
    if reg and (_norm((reg.get("mca") or {}).get("company_name")) != _norm(name) or reg.get("cin") != cin):
        out.append(("error", f"demo registry names {(reg.get('mca') or {}).get('company_name')!r} / {reg.get('cin')}"))

    # generated demo documents must name this borrower only
    docs = ROOT / "storage" / "documents" / eid
    for f in sorted(docs.rglob("*.pdf")) if docs.exists() else []:
        if f.parent.name in ("financials", "exchange", "ratings") or f.stat().st_size > 2_000_000:
            continue                                       # public filings: they name group companies freely
        t = _text(f)[:4000]
        if _norm(name)[:12] not in _norm(t):
            out.append(("warn", f"{f.relative_to(docs)} does not name {name}"))
        for c in set(re.findall(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", t)) - {cin}:
            out.append(("error", f"{f.relative_to(docs)} prints CIN {c}, not the borrower's {cin}"))
        for p in set(re.findall(r"\b[A-Z]{3}C[A-Z]\d{4}[A-Z]\b", t)) - ({pan} if pan else set()):
            out.append(("error", f"{f.relative_to(docs)} prints PAN {p}, not on the borrower's record"))

    # against the annual report
    ar = next((docs / "financials" / f"annual_report_fy{y}.pdf" for y in (2026, 2025)
               if (docs / "financials" / f"annual_report_fy{y}.pdf").exists()
               and (docs / "financials" / f"annual_report_fy{y}.pdf").stat().st_size > 1_000_000), None)
    if ar is None:
        out.append(("info", "no annual report on file — identity not checked against a public document"))
        return out
    # a real borrower carries no news, quarterly figures or operating KPIs without a document behind them
    for k in ("market_signals", "exchange_filing", "sector_kpis", "infra_metrics"):
        if rec.get(k) and not (isinstance(rec[k], dict) and rec[k].get("document")):
            out.append(("error", f"{k} on record with no source document — real news comes from the live feed"))
    t = _text(ar)
    T = t.upper()
    if cin not in T:
        out.append(("error", f"CIN {cin} not found in {ar.name}"))
    if _norm(name) not in _norm(t[:400000]):
        out.append(("warn", f"name {name!r} not found as written in {ar.name}"))
    if pan and pan not in T:
        out.append(("error", f"PAN {pan} not found in {ar.name} — not from a public source"))
    for d in rec.get("directors") or []:
        d = d if isinstance(d, dict) else vars(d)
        dn, din = d.get("name") or "", str(d.get("din") or "")
        surname = dn.split()[-1] if dn.split() else ""
        if din and din not in t:
            out.append(("error", f"director {dn} — DIN {din} not in {ar.name}"))
        if dn and _norm(dn) not in _norm(t) and not re.search(re.escape(dn.split()[0]) + r"\W+(?:\w\.?\W+){0,2}" +
                                                              re.escape(surname), t, re.I):
            out.append(("error", f"director {dn!r} not named in {ar.name}"))
        for k in ("net_worth_cr", "pan"):
            if d.get(k) not in (None, "", 0):
                out.append(("error", f"director {dn}: personal {k} on record — not public; remove"))
    aud = (rec.get("profile") or {}).get("auditor")
    if aud and _norm(aud.split("&")[0].split(" LLP")[0])[:10] not in _norm(t):
        out.append(("error", f"auditor {aud!r} not found in {ar.name}"))
    pin = re.search(r"\b\d{6}\b", g("registered_address") or "")
    if pin and pin.group(0) not in t:
        out.append(("warn", f"registered office PIN {pin.group(0)} not in {ar.name}"))

    rs = rec.get("rating_source") or {}
    rf = docs / (rs.get("document") or "-")
    rating = g("credit_rating") or ""
    if rs.get("document") and rf.exists():
        squash = lambda s: re.sub(r"[\[\]\s]", "", s.upper())                         # noqa: E731 - "[ICRA]AA+"
        rt = squash(_text(rf))
        grade = squash(re.sub(r"\s*[/(].*", "", rating))
        if grade and grade not in rt:
            out.append(("error", f"rating {rating!r} not in {rs['document']}"))
    elif rating:
        out.append(("error", f"rating {rating!r} has no rationale on file"))
    return out


def main(only: list[str]) -> int:
    from src.data import borrowers
    bad = 0
    for eid in borrowers.ids():
        if only and eid not in only:
            continue
        issues = check(eid, borrowers.load(eid))
        errs = [i for i in issues if i[0] == "error"]
        bad += bool(errs)
        print(f"\n{eid}: {'OK' if not errs else str(len(errs)) + ' problem(s)'}")
        for level, msg in issues:
            print(f"  [{level}] {msg}")
    print(f"\n{bad} borrower(s) with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
