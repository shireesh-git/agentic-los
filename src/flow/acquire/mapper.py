"""
The acquired records → the borrower record the CAM engine reads.

Whatever obtained a record (an API or a document), it is applied the same way:

  borrower        CIN, PAN, incorporation, registered office, listing, rating
  directors       from the MCA record
  financials      one FinancialStatement per audited year (₹ crore, standalone)
  external_data   mca_data / bureau_data / gst_data / rating_data / market_data envelopes
  existing_exposure, conduct, collateral, market_signals, web_crawl_news
Only values a source states are written; nothing is estimated.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from src.data import demo_registry
from src.models.canonical_model import (
    BorrowerType, Collateral, ConductRecord, DirectorPromoter, ExistingExposure, FinancialStatement,
    MarketSignal, RiskSeverity,
)


def _date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%B %d, %Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _crore(v) -> Optional[float]:
    return round(float(v) / 1e7, 2) if v not in (None, "") else None


def apply(company: dict, records: dict, statements: list[dict], facility: dict) -> dict:
    """Write the records into ``company`` (in place). Returns what was applied, for the audit trail."""
    applied: dict[str, list] = {}
    b = company["borrower"]
    eid = b.entity_id
    ext = dict(company.get("external_data") or {})

    mca = (records.get("mca") or {}).get("payload") or {}
    lei = (records.get("lei") or {}).get("payload") or {}
    if mca:
        ext["mca_data"] = _strip(records["mca"])
        for attr, val in (("cin", mca.get("cin")), ("registered_address", mca.get("registered_office")),
                          ("date_of_incorporation", _date(mca.get("date_of_incorporation"))),
                          ("paid_up_capital", _crore(mca.get("paid_up_capital_inr"))),
                          ("authorized_capital", _crore(mca.get("authorized_capital_inr")))):
            if val:
                setattr(b, attr, val)
                applied.setdefault("borrower", []).append(attr)
        state = mca.get("registered_state") or _state_from_address(mca.get("registered_office"))
        if state:
            b.registered_state = state
        if str(mca.get("listing_status") or "").lower().startswith("listed"):
            b.borrower_type = BorrowerType.LISTED
            b.listed_exchange = b.listed_exchange or "BSE, NSE"
        if mca.get("directors"):
            company["directors"] = [DirectorPromoter(din=d.get("din") or "", name=d["name"],
                                                     designation=d.get("designation") or "", entity_id=eid,
                                                     is_promoter="promoter" in str(d.get("designation", "")).lower()
                                                     or bool(d.get("is_promoter")))
                                    for d in mca["directors"]]
            applied["directors"] = [d["name"] for d in mca["directors"]]
    elif lei.get("registered_as") and not b.cin:
        b.cin = lei["registered_as"]
        applied.setdefault("borrower", []).append("cin")
    if lei.get("legal_address") and not b.registered_address:
        b.registered_address = lei["legal_address"]

    kyc = (records.get("kyc") or {}).get("payload") or {}
    if kyc.get("pan"):
        b.pan = kyc["pan"]
        applied.setdefault("borrower", []).append("pan")
    gst = (records.get("gst") or {}).get("payload") or {}
    if gst:
        ext["gst_data"] = _strip(records["gst"])
        if gst.get("gstin"):
            company["gstin"] = gst["gstin"]
        if gst.get("gstin") and not b.pan:
            b.pan = gst["gstin"][2:12]

    if statements:
        fins = {}
        for s in statements:
            fins[s["period"]] = FinancialStatement(entity_id=eid, period=s["period"],
                                                   statement_type=s.get("basis") or "standalone", source="audited",
                                                   as_of_date=date.fromisoformat(s["as_of"]),
                                                   line_items=dict(s["items"]))
        company["financials"] = fins
        applied["financials"] = sorted(fins)

    bureau = (records.get("bureau") or {}).get("payload") or {}
    # the list checks (wilful defaulter, RBI defaulter, fraud, suits) are read from the bureau payload
    merged = demo_registry.merge_registries(records.get("bureau"), records.get("registries"))
    if merged:
        ext["bureau_data"] = _strip(merged)
        applied["registries"] = sorted(k for k in demo_registry.REGISTRY_FIELDS if k in (merged.get("payload") or {}))
    if bureau:
        company["existing_exposure"] = [
            ExistingExposure(facility_id=f"BUR-{eid}-{i}", entity_id=eid, facility_type=f"{x['lender']} {x['type']}",
                             sanctioned_limit_cr=x["limit_cr"], outstanding_cr=x["outstanding_cr"],
                             utilization_pct=round(x["outstanding_cr"] / x["limit_cr"] * 100, 1) if x["limit_cr"] else 0,
                             overdue_days=x.get("dpd", 0), classification=x.get("classification") or "Standard")
            for i, x in enumerate(bureau.get("facilities") or [], start=1)]
        applied["existing_exposure"] = len(company["existing_exposure"])

    bank = (records.get("bank_statements") or {}).get("payload") or {}
    if bank.get("months"):
        m = bank["months"]
        company["conduct"] = [ConductRecord(
            entity_id=eid, period=bank.get("period") or f"{m[0]['month']} – {m[-1]['month']}",
            avg_bank_balance_cr=bank.get("avg_balance_cr") or 0.0, credit_turnover_cr=bank["total_credits_cr"],
            debit_turnover_cr=bank["total_debits_cr"], cheque_returns=bank.get("returns") or 0,
            limit_utilization_pct=float(bank.get("avg_utilisation_pct") or 0.0), overdue_instances=0,
            max_overdue_days=0)]
        applied["conduct"] = [bank.get("period")]

    rating = (records.get("rating") or {}).get("payload") or {}
    signals = [s for s in (company.get("market_signals") or []) if getattr(s, "source_name", "") not in
               ("rating_agency", "GDELT")]
    if rating.get("long_term_rating"):
        ext["rating_data"] = _strip(records["rating"])
        b.credit_rating = rating["long_term_rating"] + (f" / {rating['short_term_rating']}"
                                                        if rating.get("short_term_rating") else "")
        b.rating_agency = rating.get("rating_agency")
        signals.append(MarketSignal(entity_id=eid, signal_type="rating",
                                    headline=f"{rating.get('rating_agency')}: {rating['long_term_rating']} "
                                             f"{(rating.get('last_action') or '').lower()}".strip(),
                                    sentiment="positive" if rating.get("outlook") in ("Stable", "Positive") else "negative",
                                    severity=RiskSeverity.LOW, source_name="rating_agency",
                                    signal_date=_date(rating.get("action_date")) or date.today()))
        applied["rating"] = [b.credit_rating]

    media = (records.get("adverse_media") or {}).get("payload") or {}
    if "articles" in media:
        arts = media["articles"]
        adverse = [a for a in arts if a.get("adverse")]
        for a in adverse[:10]:
            signals.append(MarketSignal(entity_id=eid, signal_type="news", headline=a["title"][:200],
                                        sentiment="negative", severity=RiskSeverity.MEDIUM, source_name="GDELT",
                                        signal_date=_date(a.get("date")) or date.today(),
                                        details=f"{a.get('source')} · {a.get('url')} · {a.get('adverse_reason') or ''}"))
        company["web_crawl_news"] = {
            "articles": [{"title": a["title"], "url": a.get("url"), "source": a.get("source"), "date": a.get("date"),
                          "sentiment": "negative" if a.get("adverse") else "neutral"} for a in arts[:40]],
            "sentiment_summary": {"articles": len(arts), "adverse": len(adverse)},
            "crawl_date": (records["adverse_media"].get("provenance") or {}).get("fetched_at"),
            "source": "GDELT DOC 2.0 (verified feed)"}
        score = round(1.0 - min(1.0, len(adverse) / max(5, len(arts) or 1) * 2), 2)
        ext["market_data"] = {**_strip(records["adverse_media"]), "payload": {
            "overall_sentiment": "negative" if adverse and score < 0.5 else "neutral",
            "sentiment_score": score, "reputation_risk_score": "high" if len(adverse) >= 3 else
            ("medium" if adverse else "low"), "articles_reviewed": len(arts), "adverse_articles": len(adverse)}}
        applied["adverse_media"] = [f"{len(adverse)} adverse of {len(arts)}"]
    company["market_signals"] = signals

    coll = _security_from_statements(eid, statements, facility)
    if coll:
        company["collateral"] = coll
        applied["collateral"] = [c.description for c in coll]
    if ext:
        company["external_data"] = ext
    company["acquired_records"] = {k: {"via": (v.get("provenance") or {}).get("via"),
                                       "provider": (v.get("provenance") or {}).get("provider"),
                                       "document": (v.get("provenance") or {}).get("document")}
                                   for k, v in records.items() if v}
    return applied


def _security_from_statements(eid: str, statements: list[dict], facility: dict) -> list:
    """A working-capital limit is secured by hypothecation of current assets: its value is the stock and
    receivables in the latest audited balance sheet (drawing power is set later from stock statements)."""
    product = str(facility.get("product") or facility.get("facility_type") or "")
    if not statements or product not in ("working_capital", "cash_credit"):
        return []
    latest = max(statements, key=lambda s: s["as_of"])
    it = latest["items"]
    value = round((it.get("inventory") or 0) + (it.get("trade_receivables") or 0), 2)
    if value <= 0:
        return []
    return [Collateral(collateral_id=f"COL-{eid}-CA", entity_id=eid, collateral_type="Current Assets",
                       description=f"Hypothecation of stock and book debts (first pari passu with working capital "
                                   f"lenders) — per audited balance sheet {latest['as_of']}",
                       market_value_cr=value, forced_sale_value_cr=round(value * 0.75, 2),
                       valuation_date=date.fromisoformat(latest["as_of"]), encumbrance_status="pari passu")]


def _strip(env: dict) -> dict:
    return {k: v for k, v in env.items() if k not in ("identity", "name_found")}


_STATES = ("Uttar Pradesh", "Maharashtra", "Karnataka", "Tamil Nadu", "Gujarat", "Delhi", "Haryana", "Telangana",
           "Andhra Pradesh", "West Bengal", "Rajasthan", "Punjab", "Uttarakhand", "Madhya Pradesh", "Kerala", "Odisha")


def _state_from_address(addr: Optional[str]) -> Optional[str]:
    if not addr:
        return None
    return next((s for s in _STATES if re.search(s, addr, re.I)), None)
