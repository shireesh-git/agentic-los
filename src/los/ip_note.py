"""
In-Principle (IP) Note (LOS Phase 4): the one-page note the RM raises at the IP
stage, assembled from the Prospect Sourcing values the analyst accepted, the
borrower master and the latest audited financials.

  facts        each with its provenance (accepted document value with page, or
               borrower master);
  pre-screen   ratio-engine ratios for the latest audited year checked against the
               credit-policy thresholds (rules.yaml → policy_thresholds) — indicative
               only; the full assessment happens at the Risk Maker step;
  AI summary   optional; the guarded narrator may only quote figures in the note.
"""

from __future__ import annotations

import html as _html
import json
from datetime import datetime
from typing import Optional

from src.engines import ratio_engine as R
from src.engines.cam_composer import fmt
from src.engines.data_provenance import NOT_AVAILABLE

NOTE_VERSION = "los_ip_note/v1"

# metric, label, ratio function, required line items, policy key, limit type, unit
PRESCREEN = [
    ("ebitda_margin", "EBITDA margin", R.ebitda_margin, ("ebitda", "revenue_operating"), "min_ebitda_margin_pct", "min", "pct"),
    ("debt_to_equity", "Debt / equity", R.debt_to_equity, ("total_debt", "total_equity"), "max_debt_to_equity", "max", "x"),
    ("debt_to_ebitda", "Debt / EBITDA", R.debt_to_ebitda, ("total_debt", "ebitda"), "max_debt_to_ebitda", "max", "x"),
    ("interest_coverage_ratio", "Interest coverage", R.interest_coverage_ratio, ("ebit", "finance_cost"),
     "min_interest_coverage", "min", "x"),
    ("dscr", "DSCR (simplified)", R.dscr, ("pat", "depreciation", "finance_cost", "long_term_debt"), "min_dscr", "min", "x"),
    ("current_ratio", "Current ratio", R.current_ratio, ("current_assets", "current_liabilities"),
     "min_current_ratio", "min", "x"),
    ("return_on_equity", "Return on equity", R.return_on_equity, ("pat", "total_equity"), "min_roe_pct", "min", "pct"),
]
_FIN_ROWS = [("revenue_operating", "Revenue from operations"), ("ebitda", "EBITDA"), ("pat", "PAT"),
             ("total_equity", "Net worth"), ("total_debt", "Total debt")]
AI_SYSTEM_PROMPT = """You are a relationship manager at an Indian bank writing the summary paragraph of an In-Principle
Note for a corporate credit proposal. You are given the note's content exactly as the bank's systems produced it.
Rules: do NOT add facts not in the content; do NOT calculate, round or estimate any number — quote only figures that
appear in the content exactly; describe the pre-screen as indicative. 70-120 words, one paragraph, formal Indian
banking usage. Return ONLY a JSON object: {"summary": "<paragraph>"}"""


def _thresholds() -> dict:
    from src.core.config_manager import config
    return config.get("rules", "policy_thresholds", default={}) or {}


def _fmt_ratio(v: Optional[float], unit: str) -> str:
    if v is None:
        return NOT_AVAILABLE
    return f"{R.as_pct(v):.1f}%" if unit == "pct" else f"{v:.2f}x"


def prescreen(fs, thresholds: dict) -> list[dict]:
    rows = []
    for metric, label, fn, needs, key, kind, unit in PRESCREEN:
        limit = thresholds.get(key)
        value = None
        if fs is not None and all(n in fs.line_items for n in needs):
            r = fn(fs)
            value = r.value if r.status == "computed" else None
        if value is None or limit is None:
            result = "not_available"
        else:
            cmp = R.as_pct(value) if unit == "pct" else value
            result = "pass" if (cmp >= limit if kind == "min" else cmp <= limit) else "breach"
        rows.append({"metric": metric, "label": label, "value": _fmt_ratio(value, unit),
                     "limit": f"{kind} {limit}{'%' if unit == 'pct' else 'x'}" if limit is not None else "—",
                     "result": result, "provenance": "calculated" if value is not None else "unavailable"})
    return rows


def _latest_audited(company: dict):
    audited = [fs for fs in ((company or {}).get("financials") or {}).values() if getattr(fs, "source", "") == "audited"]
    return sorted(audited, key=lambda fs: fs.period, reverse=True)


# the figures the RM accepted from the borrower's statements (a prospect has no master financials)
_ACCEPTED_FIN = {"revenue_cr": "revenue_operating", "ebitda_cr": "ebitda", "pat_cr": "pat",
                 "net_worth_cr": "total_equity", "total_debt_cr": "total_debt"}


def _accepted_statement(app: dict, accepted: dict):
    items = {}
    for fid, key in _ACCEPTED_FIN.items():
        try:
            items[key] = float(accepted[fid]["value"])
        except (KeyError, TypeError, ValueError):
            continue
    if not items:
        return None
    from datetime import date
    from src.models.canonical_model import FinancialStatement
    docs = sorted({(accepted[f].get("source") or {}).get("document") for f in _ACCEPTED_FIN if f in accepted} - {None})
    fs = FinancialStatement(entity_id=app.get("entity_id") or "", period="Latest year (documents)",
                            statement_type="standalone", source="documents", as_of_date=date.today(), line_items=items)
    return fs, docs


def _fact(label, value, provenance, source=None):
    return {"label": label, "value": value if value not in (None, "") else NOT_AVAILABLE,
            "provenance": provenance if value not in (None, "") else "unavailable", "source": source}


def build_ip_note(app: dict, company: dict, now: Optional[datetime] = None) -> dict:
    accepted = ((app.get("sourcing") or {}).get("accepted")) or {}
    b = (company or {}).get("borrower")

    def pick(fid, master_value, label):
        a = accepted.get(fid)
        if a:
            src = a.get("source") or {}
            where = f"{src['document']} p.{src['page']}" if src.get("document") else "Edited by analyst"
            return _fact(label, a["display"], "source" if src.get("document") else "derived",
                         f"{where} · accepted by {a.get('by_name')}")
        return _fact(label, master_value, "source", "Borrower master")

    sector = getattr(getattr(b, "sector", None), "value", None)
    borrower = [
        pick("legal_name", getattr(b, "company_name", None), "Borrower"),
        pick("cin", getattr(b, "cin", None), "CIN"),
        pick("pan", getattr(b, "pan", None), "PAN"),
        pick("gstin", None, "GSTIN"),
        _fact("Constitution", (app.get("constitution") or "").replace("_", " ").title() or None, "source", "Borrower master"),
        _fact("Sector", (sector or "").replace("_", " ").title() or None, "source", "Borrower master"),
        pick("date_of_incorporation", getattr(getattr(b, "date_of_incorporation", None), "isoformat", lambda: None)(),
             "Date of incorporation"),
        pick("registered_address", getattr(b, "registered_address", None), "Registered office"),
        pick("external_rating", getattr(b, "credit_rating", None), "External rating"),
        pick("authorised_signatory", None, "Authorised signatory"),
    ]
    fac = app.get("facility") or {}
    proposal = [
        _fact("Facility type", (fac.get("facility_type") or "").replace("_", " ").title() or None, "source", "Application"),
        _fact("Proposal type", fac.get("proposal_type"), "source", "Application"),
        _fact("Case type", fac.get("case_type"), "source", "Application"),
        _fact("Proposed amount", fmt(app.get("amount_cr"), "cr") if app.get("amount_cr") else None, "source", "Application"),
        _fact("Tenor", f"{fac['tenor_months']} months" if fac.get("tenor_months") else None, "source", "Application"),
        _fact("Purpose", fac.get("purpose"), "source", "Application"),
    ]
    exposure = [[e.facility_type, fmt(e.sanctioned_limit_cr, "cr"), fmt(e.outstanding_cr, "cr"), e.classification]
                for e in (company or {}).get("existing_exposure") or []]

    years = _latest_audited(company)[:3]
    fin_note = "Audited financial statements (borrower master)"
    if not years:                               # a prospect: the figures accepted from its statements
        from_docs = _accepted_statement(app, accepted)
        if from_docs:
            years = [from_docs[0]]
            fin_note = ("Accepted from the borrower's documents" + (f" ({', '.join(from_docs[1])})" if from_docs[1] else "")
                        + " — partial line items; ratios needing other items show as not available")
    fin_table = {"columns": ["₹ Cr"] + [fs.period for fs in years],
                 "rows": [[label] + [fmt(fs.line_items.get(k), "num") if k in fs.line_items else "—" for fs in years]
                          for k, label in _FIN_ROWS],
                 "provenance": "source", "note": fin_note}
    checks = prescreen(years[0] if years else None, _thresholds())
    breaches = [c for c in checks if c["result"] == "breach"]
    unavailable = [c for c in checks if c["result"] == "not_available"]

    mv = accepted.get("collateral_mv_cr", {}).get("value")
    fsv = accepted.get("collateral_fsv_cr", {}).get("value")
    if mv is None:
        coll = (company or {}).get("collateral") or []
        mv = sum(c.market_value_cr for c in coll) or None
        fsv = sum(c.forced_sale_value_cr for c in coll) or None
        sec_source = "Borrower master (collateral register)"
    else:
        sec_source = "Valuation report (accepted prefill)"
    amount = app.get("amount_cr")
    security = [_fact("Collateral market value", fmt(mv, "cr") if mv else None, "source", sec_source),
                _fact("Collateral forced-sale value", fmt(fsv, "cr") if fsv else None, "source", sec_source),
                _fact("FSV cover on proposed amount", f"{fsv / amount:.2f}x" if fsv and amount else None, "calculated",
                      "FSV ÷ proposed amount")]

    if not years:
        outcome = "Pre-screen not possible — no audited financials on record or accepted from the documents"
    elif not breaches:
        outcome = "Within policy thresholds — proceed to in-principle review"
    elif len(breaches) <= 2:
        outcome = f"{len(breaches)} policy exception(s) — proceed with the exceptions noted"
    else:
        outcome = f"{len(breaches)} policy exceptions — refer for in-principle discussion before proceeding"

    sourcing = app.get("sourcing") or {}
    note = {
        "available": True, "version": NOTE_VERSION,
        "generated_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "title": f"In-Principle Note — {app.get('borrower_name')}",
        "application_id": app.get("application_id"),
        "borrower": borrower, "proposal": proposal,
        "existing_exposure": {"columns": ["Facility", "Sanctioned", "Outstanding", "Classification"], "rows": exposure},
        "financials": fin_table, "security": security,
        "prescreen": {"period": years[0].period if years else None, "checks": checks, "outcome": outcome,
                      "breaches": [c["label"] for c in breaches], "not_available": [c["label"] for c in unavailable],
                      "note": "Indicative ratio-engine pre-screen against credit-policy thresholds; the full credit "
                              "assessment is performed at the Risk Maker step."},
        "sourcing": {"prefill_run": bool(sourcing.get("prefill")), "accepted": len(accepted),
                     "edited": sum(1 for a in accepted.values() if a.get("edited")),
                     "documents": len((sourcing.get("prefill") or {}).get("documents") or [])},
        "ai_summary": None,
    }
    return note


def note_content(note: dict) -> str:
    """The note as given to the summary model (and used to check the figures it quotes)."""
    keep = {k: note[k] for k in ("title", "borrower", "proposal", "existing_exposure", "financials", "security")}
    keep["prescreen"] = {k: note["prescreen"][k] for k in ("period", "checks", "outcome")}
    return json.dumps(keep, ensure_ascii=False, default=str)


def summarise(note: dict, llm) -> dict:
    from src.services.observation_narrator import _parse_json_object, unsupported_figures

    content = note_content(note)
    data = _parse_json_object(llm.generate(prompt=f"IP Note content (JSON):\n{content}\n\nWrite the JSON object.",
                                           system_prompt=AI_SYSTEM_PROMPT, temperature=0.2, max_tokens=600))
    text = str(data.get("summary") or "").strip()
    if len(text) < 40:
        raise ValueError("model response is missing the summary")
    bad = unsupported_figures(text, content)
    if bad:
        raise ValueError(f"summary quoted figures not in the note: {', '.join(bad[:5])}")
    return {"text": text, "model": getattr(llm, "model", None) or getattr(llm, "name", "llm"), "provenance": "ai",
            "generated_at": datetime.now().isoformat(timespec="seconds")}


def render_markdown(note: dict) -> str:
    def facts(rows):
        return "\n".join(["| Item | Value | Source |", "|---|---|---|"]
                         + [f"| {r['label']} | {r['value']} | {r.get('source') or r['provenance']} |" for r in rows])

    def table(t):
        if not t["rows"]:
            return "_None on record._"
        return "\n".join(["| " + " | ".join(t["columns"]) + " |", "|" + "---|" * len(t["columns"])]
                         + ["| " + " | ".join(str(c) for c in r) + " |" for r in t["rows"]])

    ps = note["prescreen"]
    checks = "\n".join(["| Ratio | Value | Policy | Result |", "|---|---|---|---|"]
                       + [f"| {c['label']} | {c['value']} | {c['limit']} | {c['result'].replace('_', ' ')} |"
                          for c in ps["checks"]])
    parts = [f"# {note['title']}", f"Application {note['application_id']} · prepared {note['generated_at']}"]
    if note.get("ai_summary"):
        parts += ["## Summary (AI-generated, figures verified against the note)", note["ai_summary"]["text"]]
    parts += ["## 1. Borrower", facts(note["borrower"]), "## 2. Proposal", facts(note["proposal"]),
              "## 3. Existing exposure with the bank", table(note["existing_exposure"]),
              "## 4. Financial snapshot", table(note["financials"]), "## 5. Security", facts(note["security"]),
              f"## 6. Policy pre-screen ({ps['period'] or 'n/a'})", checks, f"**Outcome:** {ps['outcome']}",
              f"_{ps['note']}_"]
    return "\n\n".join(parts)


def render_html(note: dict) -> str:
    from src.rendering.cam_markdown import markdown_to_html

    page = markdown_to_html(render_markdown(note), title=note["title"])
    return page.replace(f"{_html.escape(note['title'])} — CAM Report", _html.escape(note["title"]))
