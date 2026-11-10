"""Notes-to-accounts reader (roadmap P3): what the auditor and the notes say that officers rarely read.

The latest annual report (or audited accounts) is searched page by page for the sections where trouble is
first written down, and only those pages are read:

    auditor      the independent auditor's report: the opinion (unmodified / qualified / adverse / disclaimer),
                 its basis, emphasis of matter, key audit matters, material uncertainty on going concern
    caro         the CARO annexure: defaults to lenders, wilful-defaulter declaration, short-term funds used for
                 long-term purposes, undisputed statutory dues, fraud, cash losses
    contingent   contingent liabilities and guarantees given
    related      related-party transactions
    flagged      any other page that names a modified opinion, an emphasis of matter or a going-concern doubt

The AI model reads those pages into findings (topic, severity, finding, a verbatim quote, the page). A finding
whose quote is not on the page it names is dropped: nothing reaches the CAM that the document does not say.
Without a model (mock provider, no key, an error) the same pages are read by rules that look for the standard
CARO and audit-report wording, labelled "read by rules".

Results are cached per file and mode under the extraction cache, so a document is read once.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

VERSION = 5
TOPICS = ["audit_opinion", "ifc_opinion", "emphasis_of_matter", "going_concern", "key_audit_matter", "caro_default",
          "caro_wilful_defaulter", "caro_diversion", "caro_statutory_dues", "caro_fraud", "caro_other",
          "contingent_liabilities", "related_party", "other"]
TOPIC_LABEL = {"audit_opinion": "Audit opinion", "ifc_opinion": "Internal financial controls opinion", "emphasis_of_matter": "Emphasis of matter",
               "going_concern": "Going concern", "key_audit_matter": "Key audit matter",
               "caro_default": "CARO: default to lenders", "caro_wilful_defaulter": "CARO: wilful defaulter",
               "caro_diversion": "CARO: short-term funds used long-term", "caro_statutory_dues": "CARO: statutory dues",
               "caro_fraud": "CARO: fraud", "caro_other": "CARO: other", "contingent_liabilities": "Contingent liabilities",
               "related_party": "Related-party transactions", "other": "Other"}
SEVERITIES = ["high", "medium", "low", "info"]
PAGE_CHARS = 3200

SCHEMA = {
    "type": "object", "required": ["opinion", "findings"],
    "properties": {
        "opinion": {"type": "string", "enum": ["unmodified", "qualified", "adverse", "disclaimer", "not_found"]},
        "findings": {"type": "array", "items": {
            "type": "object", "required": ["topic", "severity", "finding", "quote", "page"],
            "properties": {"topic": {"type": "string", "enum": TOPICS},
                           "severity": {"type": "string", "enum": SEVERITIES},
                           "finding": {"type": "string"}, "quote": {"type": "string"},
                           "page": {"type": "integer"}}}}}}

SYSTEM = ("You are a credit analyst at an Indian bank reading the auditor's report, the CARO annexure and the notes "
          "to accounts of a borrower's annual report. You report only what the pages say, each with a verbatim "
          "quote and its page number.")

PROMPT = """Read the pages below (each starts with [p.N], N being the PDF page) and return a JSON object:
{{"opinion": "unmodified|qualified|adverse|disclaimer|not_found", "findings": [{{"topic", "severity", "finding", "quote", "page"}}]}}

Topics: {topics}.
Severity:
- high: a qualified, adverse or disclaimer opinion ON THE FINANCIAL STATEMENTS (topic audit_opinion); a material
  uncertainty related to going concern; CARO reports a default in repaying lenders, a wilful-defaulter declaration, or
  short-term funds used for long-term purposes
- medium: a qualified or adverse opinion on INTERNAL FINANCIAL CONTROLS, or a material weakness in them (topic
  ifc_opinion — not audit_opinion: it is a separate report on controls, not on the accounts)
- medium: an emphasis of matter; undisputed statutory dues outstanding more than six months; fraud noticed or
  reported; cash losses; contingent liabilities or guarantees above 25% of net worth (net worth: {net_worth});
  material loans or guarantees to related parties
- low: other points a credit officer should know
- info: the clean result of a check (e.g. "CARO (ix): no default in repayment to lenders"), and each key audit matter

Rules: the auditor's standard wording about its own responsibilities (e.g. that it evaluates management's use of
the going concern basis, or that fraud may involve collusion) is NOT a finding. "opinion" is the opinion on the
financial statements, not on internal financial controls. "finding" is one plain sentence for a credit officer. "quote" is copied word for word from the page (at most
300 characters, no ellipsis inside). "page" is the N of the page the quote is on. Do not report anything the pages
do not say. Report each CARO check you can see (as info when clean). At most 20 findings.

{pages}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[‘’“”]", "'", str(s or ""))).strip().lower()


# ── finding the sections ────────────────────────────────────────────────────

_AUD = re.compile(r"independent auditor.?s'? report", re.I)
_CARO = re.compile(r"companies \(auditor.?s'? report\) order", re.I)
_FLAG = re.compile(r"qualified opinion|adverse opinion|disclaimer of opinion|emphasis of matter|"
                   r"material uncertainty related to going concern", re.I)
_FS_START = re.compile(r"balance sheet as at", re.I)


def locate(pages: list[str]) -> dict[str, list[int]]:
    """0-based page indexes per section."""
    low = [p.lower() for p in pages]
    out: dict[str, list[int]] = {}
    aud = next((i for i, t in enumerate(low) if _AUD.search(t) and "opinion" in t), None)
    if aud is not None:
        block = []
        for i in range(aud, min(aud + 12, len(pages))):
            if i > aud and _FS_START.search(low[i]) and not _AUD.search(low[i]):
                break
            block.append(i)
        keep = [i for i in block if re.search(r"opinion|emphasis|key audit|going concern|material uncertainty", low[i])]
        out["auditor"] = (keep or block)[:6]
    caro = next((i for i, t in enumerate(low) if _CARO.search(t) and (aud is None or i >= aud)
                 and re.search(r"\(i+\)|clause|annexure", t)), None)
    if caro is not None:
        out["caro"] = list(range(caro, min(caro + 5, len(pages))))
    after = aud or 0
    cont = [i for i, t in enumerate(low) if i >= after and "contingent liabilit" in t
            and re.search(r"not acknowledged|claims against|guarantees? (given|issued)", t)]
    if cont:
        out["contingent"] = cont[:2]
    rpt = [i for i, t in enumerate(low) if i >= after and "related part" in t
           and re.search(r"key management personnel|nature of relationship|transactions with related", t)]
    if rpt:
        out["related"] = rpt[:2]
    seen = {i for v in out.values() for i in v}
    flagged = [i for i, t in enumerate(low) if _FLAG.search(t) and i not in seen]
    if flagged:
        out["flagged"] = flagged[:4]
    return out


# ── reading with rules (no model) ───────────────────────────────────────────

def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(])", flat) if len(s.strip()) > 8]


def _hit(pages: list[str], idx: list[int], pattern: str) -> Optional[tuple[int, str]]:
    for i in idx:
        ss = _sentences(pages[i])
        for k, s in enumerate(ss):
            if re.search(pattern, s, re.I):
                j = k + 1
                while len(s) < 90 and j < len(ss):          # a heading ("Emphasis of Matter: a.") needs its text
                    s, j = s + " " + ss[j], j + 1
                return i, s[:300]
    return None


_RULES = [
    # topic, section(s), pattern, clean pattern (a "no / not" form), severity when not clean
    ("audit_opinion", ("auditor", "flagged", "caro"), r"\b(qualified|adverse) opinion\b|disclaimer of opinion", None, "high"),
    ("going_concern", ("auditor", "flagged", "caro"), r"material uncertainty related to going concern", None, "high"),
    ("emphasis_of_matter", ("auditor", "flagged", "caro"), r"emphasis of matter", None, "medium"),
    ("caro_default", ("caro",), r"default(ed)? in (the )?repayment", r"\b(not|no)\b[^.]{0,40}default", "high"),
    ("caro_wilful_defaulter", ("caro",), r"wilful defaulter", r"\bnot\b[^.]{0,40}(declared|been)", "high"),
    ("caro_diversion", ("caro",), r"short[- ]term basis[^.]{0,80}long[- ]term", r"\bnot\b|\bno\b", "high"),
    ("caro_statutory_dues", ("caro",), r"undisputed[^.]{0,120}(outstanding|arrears)", r"\bno\b|\bnil\b|\bnot\b", "medium"),
    ("caro_fraud", ("caro",), r"fraud (by|on) the company|fraud[^.]{0,80}(noticed|reported)",
     r"\bno\b[^.]{0,30}fraud|\bnot\b[^.]{0,40}(noticed|reported)", "medium"),
    ("caro_other", ("caro",), r"cash loss", r"\bnot\b|\bno\b", "medium"),
]


def read_by_rules(pages: list[str], sections: dict) -> dict:
    findings = []
    for topic, secs, pat, clean, sev in _RULES:
        idx = [i for s in secs for i in sections.get(s, [])]
        got = _hit(pages, idx, pat)
        if not got:
            continue
        i, quote = got
        if topic == "audit_opinion" and re.search(r"internal financial control", pages[i], re.I):
            topic, sev = "ifc_opinion", "medium"           # the report on controls, not on the accounts
        ok = bool(clean and re.search(clean, quote, re.I))
        findings.append({"topic": topic, "severity": "info" if ok else sev, "quote": quote, "page": i + 1,
                         "finding": (f"{TOPIC_LABEL[topic]}: clean." if ok else f"{TOPIC_LABEL[topic]} reported.")})
    for topic, sec in (("contingent_liabilities", "contingent"), ("related_party", "related")):
        if sections.get(sec):
            i = sections[sec][0]
            s = _hit(pages, [i], r"contingent liabilit|related part")
            findings.append({"topic": topic, "severity": "info", "page": i + 1, "quote": (s or (i, ""))[1],
                             "finding": f"{TOPIC_LABEL[topic]} disclosed: read the note before sanction."})
    modified = next((f for f in findings if f["topic"] == "audit_opinion" and f["severity"] == "high"), None)
    opinion = ("not_found" if "auditor" not in sections else
               ("adverse" if modified and "adverse" in modified["quote"].lower() else
                "disclaimer" if modified and "disclaimer" in modified["quote"].lower() else
                "qualified" if modified else "unmodified"))
    return {"opinion": opinion, "findings": findings}


# ── reading with the model ──────────────────────────────────────────────────

def read_by_model(pages: list[str], sections: dict, llm, net_worth_cr: Optional[float]) -> dict:
    idx = sorted({i for v in sections.values() for i in v})
    text = "\n\n".join(f"[p.{i + 1}]\n{pages[i][:PAGE_CHARS]}" for i in idx)
    prompt = PROMPT.format(topics=", ".join(TOPICS), pages=text,
                           net_worth=f"₹{net_worth_cr:,.0f} Cr" if net_worth_cr else "not given")
    from src.agentic.schema import validate
    raw = llm.generate(prompt=prompt, system_prompt=SYSTEM, temperature=0.0, max_tokens=3000)
    s, e = raw.find("{"), raw.rfind("}")
    if s < 0 or e <= s:
        raise ValueError("no JSON object in the reply")
    # quotes copied from a page carry its line breaks: allow control characters inside strings
    body = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", raw[s:e + 1])   # a stray backslash from a PDF glyph
    data = json.loads(body, strict=False)
    for f in data.get("findings") or []:                    # "p.299" / "299" → 299
        if isinstance(f, dict) and not isinstance(f.get("page"), int):
            m = re.search(r"\d+", str(f.get("page") or ""))
            f["page"] = int(m.group()) if m else 0
        if isinstance(f, dict):
            f["severity"] = str(f.get("severity") or "").lower()
    problems = validate(data, SCHEMA)
    if problems:
        raise ValueError("; ".join(problems[:4]))
    return data


def _key(s: str) -> str:
    """Letters and digits only: PDF text splits words ("ex planations"), uses ligatures and hyphenates."""
    import unicodedata
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", str(s or "")).lower())


def _on_page(quote: str, page_key: str) -> bool:
    q = _key(quote)
    if len(q) < 20:
        return False
    probes = [q[:60], q[len(q) // 2 - 25:len(q) // 2 + 25] if len(q) >= 80 else q[-50:]]
    return any(p in page_key for p in probes)


# a finding's topic must be borne out by its own quote (a model can attach a red-flag topic to the wrong sentence)
_TOPIC_WORDS = {"audit_opinion": r"qualified|adverse|disclaimer", "ifc_opinion": r"internal financial control|material weakness",
                "going_concern": r"going concern", "caro_default": r"default", "caro_wilful_defaulter": r"wilful",
                "caro_diversion": r"short.?term", "emphasis_of_matter": r"emphasis|draw attention|attention is drawn"}


def _sane(f: dict, pages: list[str]) -> dict:
    quote, page = f.get("quote") or "", pages[f["page"] - 1] if 0 < f.get("page", 0) <= len(pages) else ""
    if f["topic"] == "audit_opinion" and re.search(r"internal financial control", page, re.I) \
            and not re.search(r"true and fair", quote, re.I):
        return {**f, "topic": "ifc_opinion", "severity": "medium" if f["severity"] == "high" else f["severity"]}
    words = _TOPIC_WORDS.get(f["topic"])
    if words and f["severity"] in ("high", "medium") and not re.search(words, quote, re.I):
        # a red flag must be in its own quote; a point to note may take its context from the page
        if f["severity"] == "high" or not re.search(words, page, re.I):
            return {**f, "topic": "other", "severity": "low"}
    return f


def _dedupe(findings: list[dict], per_topic: int = 3) -> list[dict]:
    out, seen, count = [], set(), {}
    for f in findings:
        k = (f["topic"], _key(f.get("finding"))[:80])
        if k in seen or count.get(f["topic"], 0) >= per_topic:
            continue
        seen.add(k)
        count[f["topic"]] = count.get(f["topic"], 0) + 1
        out.append(f)
    return out


def ground(result: dict, pages: list[str], allowed: set[int]) -> tuple[list[dict], int]:
    """Keep findings whose quote is on the page they name (a page that was read)."""
    kept, dropped = [], 0
    keys = {i: _key(pages[i]) for i in allowed}
    for f in result.get("findings") or []:
        page, quote = int(f.get("page") or 0), f.get("quote") or ""
        ok = page - 1 in keys and _on_page(quote, keys[page - 1])
        if not ok:                                   # the model sometimes names the neighbouring page
            alt = next((i for i in sorted(keys) if _on_page(quote, keys[i])), None)
            if alt is not None:
                f, ok = {**f, "page": alt + 1}, True
        if ok:
            kept.append({k: f[k] for k in ("topic", "severity", "finding", "quote", "page")})
        else:
            dropped += 1
    return kept, dropped


# ── the document and the cache ──────────────────────────────────────────────

def _year(name: str) -> int:
    m = re.search(r"(?:fy|20)(\d{2,4})", name.lower())
    return int(m.group(1)[-2:]) if m else 0


def find_reports(entity_dir: Path, max_year: Optional[int] = None) -> list[Path]:
    """Annual reports (then audited accounts) in a borrower's folder, latest first; with ``max_year`` (e.g. 2024)
    only those for that year or earlier (a back-test must not read a later report)."""
    if not entity_dir.exists():
        return []
    pdfs = [p for p in entity_dir.rglob("*.pdf") if re.search(r"annual[_ ]?report|(?<!un)audited", p.name, re.I)]
    if max_year:
        pdfs = [p for p in pdfs if _year(p.name) and _year(p.name) <= max_year % 100]
    return sorted(pdfs, key=lambda p: (bool(re.search(r"annual", p.name, re.I)), _year(p.name), p.stat().st_size),
                  reverse=True)


def find_report(entity_dir: Path, max_year: Optional[int] = None) -> Optional[Path]:
    found = find_reports(entity_dir, max_year)
    return found[0] if found else None


def _cache_file(path: Path, mode: str) -> Path:
    from src.core.runtime_paths import CACHE_ROOT
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return CACHE_ROOT / "extractions" / f"notes_v{VERSION}_{mode}_{h.hexdigest()[:24]}.json"


def read(path: Path, llm=None, net_worth_cr: Optional[float] = None, use_model: bool = True) -> dict:
    """Findings from one annual report: {"available", "mode", "document", "opinion", "findings", ...}."""
    model = use_model and llm is not None and getattr(llm, "name", "") != "mock"
    mode = "ai" if model else "rules"
    cache = _cache_file(path, mode)
    if cache.exists():
        try:
            return {**json.loads(cache.read_text(encoding="utf-8")), "cached": True}
        except Exception:
            pass
    from src.flow.acquire.readers import page_texts
    pages = page_texts(path)
    sections = locate(pages)
    if not sections.get("auditor") and not sections.get("caro"):
        return {"available": False, "document": path.name,
                "reason": f"{path.name}: no auditor's report or CARO annexure found in {len(pages)} pages"}
    allowed = {i for v in sections.values() for i in v}
    dropped, how = 0, "rules"
    raw = None
    if model:
        try:
            raw = read_by_model(pages, sections, llm, net_worth_cr)
            how = "ai"
        except Exception as e:
            log.warning("Notes reader: the model failed on %s (%s) — reading by rules", path.name, e)
    rules = read_by_rules(pages, sections)
    if raw is None:
        raw, how = rules, "rules"
    findings, dropped = ground(raw, pages, allowed)
    if how == "ai":
        findings = [_sane(f, pages) for f in findings]
        if not any(f["topic"] == "audit_opinion" and f["severity"] == "high" for f in findings):
            raw["opinion"] = rules.get("opinion") or raw.get("opinion")
        # the rules back the model up: a modified opinion, a going-concern doubt or a CARO default the rules
        # can see is never lost because the model worded or placed it differently
        have = {f["topic"] for f in findings if f["severity"] in ("high", "medium")}
        for f in ground(rules, pages, allowed)[0]:
            if f["severity"] in ("high", "medium") and f["topic"] not in have:
                findings.append({**f, "by_rules": True})
        if rules.get("opinion") not in (None, "not_found", "unmodified"):
            raw["opinion"] = rules["opinion"]
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["page"]))
    findings = _dedupe(findings)
    for f in findings:
        f["label"] = TOPIC_LABEL.get(f["topic"], f["topic"])
    out = {"available": True, "v": VERSION, "mode": how, "model": getattr(llm, "model_id", None) if how == "ai" else None,
           "document": path.name, "pages_total": len(pages),
           "sections": {k: [i + 1 for i in v] for k, v in sections.items()},
           "opinion": raw.get("opinion") or "not_found", "findings": findings, "dropped": dropped,
           "red_flags": sum(1 for f in findings if f["severity"] == "high"),
           "to_note": sum(1 for f in findings if f["severity"] == "medium")}
    out["summary"] = summary(out)
    if how == mode:                                   # a model failure is not cached: the next run tries again
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def summary(n: dict) -> str:
    op = {"unmodified": "an unmodified audit opinion", "qualified": "a QUALIFIED audit opinion",
          "adverse": "an ADVERSE audit opinion", "disclaimer": "a DISCLAIMER of opinion",
          "not_found": "no audit opinion found"}.get(n.get("opinion"), n.get("opinion"))
    head = f"{n['document']}: {op}"
    if n.get("red_flags"):
        head += f"; {n['red_flags']} red flag(s): " + "; ".join(
            f"{f['label']} (p.{f['page']})" for f in n["findings"] if f["severity"] == "high")[:400]
    elif n.get("to_note"):
        head += f"; {n['to_note']} point(s) to note"
    else:
        head += "; no red flags in the auditor's report or the CARO annexure"
    return head + ("" if n.get("mode") == "ai" else " (read by rules: the AI model was not used)") + "."


def for_entity(entity_id: str, llm=None, net_worth_cr: Optional[float] = None, use_model: bool = True,
               max_year: Optional[int] = None) -> dict:
    from src.core.runtime_paths import DOCUMENTS_ROOT
    paths = find_reports(DOCUMENTS_ROOT / entity_id, max_year)
    if not paths:
        return {"available": False, "reason": "No annual report or audited accounts on record"}
    skipped, out = [], None
    for path in paths[:4]:                    # the latest report that has an auditor's report (a summary has none)
        try:
            out = read(path, llm=llm, net_worth_cr=net_worth_cr, use_model=use_model)
        except Exception as e:
            log.exception("Notes reader failed for %s", entity_id)
            out = {"available": False, "document": path.name, "reason": f"Could not read {path.name}: {e}"}
        if out.get("available"):
            if skipped:
                out = {**out, "skipped": skipped,
                       "summary": out["summary"] + f" (later report{'s' if len(skipped) > 1 else ''} "
                                  f"{', '.join(skipped)} had no auditor's report)"}
            return out
        skipped.append(path.name)
    return out
