"""
External Systems — Identifier resolution & API stubs.

All company data is sourced from Probe42 MCP.  These functions provide
identifier-resolution lookups and return ``not_found`` responses when
the Probe42 bundle has not been fetched.
"""

from datetime import date
import logging

_log = logging.getLogger(__name__)


def _today():
    return date.today().isoformat()


def _not_found(source: str, record_type: str, entity_key: str, version: str = "v2") -> dict:
    return {
        "source": source,
        "record_type": record_type,
        "entity_key": entity_key,
        "as_of_date": _today(),
        "payload_version": version,
        "source_status": "not_found",
        "payload": {},
    }


# ══════════════════════════════════════════════════════════════════════════════
# Identifier Reference Lookups  (CIN ↔ PAN ↔ GSTIN ↔ Entity-ID ↔ Name)
# ══════════════════════════════════════════════════════════════════════════════

def _reference() -> list[dict]:
    """{entity_id, cin, pan, gstin, name, aliases} for every borrower on record, from its data file
    (data/borrowers/<id>.json: the borrower, ``identifiers`` and ``name_aliases``). No identifiers are held in code."""
    from src.data import borrowers
    out = []
    for eid, rec in borrowers.load_all().items():
        b, ids = rec.get("borrower"), rec.get("identifiers") or {}
        if b is None:
            continue
        out.append({"entity_id": eid, "cin": b.cin or None, "pan": ids.get("pan") or b.pan or None,
                    "gstin": ids.get("gstin") or rec.get("gstin"), "name": b.company_name,
                    "aliases": [a.lower() for a in rec.get("name_aliases") or []] + [b.company_name.lower()]})
    return out


def entity_id_map() -> dict[str, dict]:
    """{entity_id: {cin, pan, gstin}} for the borrowers on record (from their data files)."""
    return {r["entity_id"]: {"cin": r["cin"], "pan": r["pan"], "gstin": r["gstin"]} for r in _reference()}


def reference_identifiers(entity_id: str) -> dict:
    """CIN / PAN / GSTIN of a borrower on record ({} if unknown)."""
    r = next((x for x in _reference() if x["entity_id"] == (entity_id or "").upper()), None)
    return {k: r[k] for k in ("cin", "pan", "gstin") if r and r.get(k)} if r else {}


# ══════════════════════════════════════════════════════════════════════════════
# Company Resolution
# ══════════════════════════════════════════════════════════════════════════════

def resolve_company(identifier: str) -> dict | None:
    """
    Smart company resolution — accepts PAN, CIN, GSTIN, Entity ID, or company name.
    Returns { cin, pan, gstin, entity_id, company_name } or None, from the borrowers on record.
    """
    ident = identifier.strip()
    up, low = ident.upper(), ident.lower()
    refs = _reference()

    def out(r, **over):
        return {"cin": r["cin"], "pan": r["pan"], "gstin": r["gstin"], "entity_id": r["entity_id"],
                "company_name": r["name"], **over}

    for match in (lambda r: r["cin"] == up, lambda r: r["pan"] == up, lambda r: r["entity_id"] == up):
        r = next((x for x in refs if match(x)), None)
        if r:
            return out(r)
    if len(up) == 15:                                   # GSTIN: the PAN is characters 3–12
        r = next((x for x in refs if x["pan"] == up[2:12]), None)
        if r:
            return out(r, pan=up[2:12], gstin=up)
    r = next((x for x in refs if low in x["aliases"]), None) or         next((x for x in refs if any(low in a or a in low for a in x["aliases"])), None)
    return out(r) if r else None


# ══════════════════════════════════════════════════════════════════════════════
# API Stubs — All return not_found.  Actual data comes via Probe42 MCP bundle.
# ══════════════════════════════════════════════════════════════════════════════

def mca_company_master(cin: str) -> dict:
    """MCA V3 API — Company Master Data.  Data sourced from Probe42."""
    return _not_found("mca", "company_master", cin)


def mca_directors(cin: str) -> dict:
    """MCA — Board of Directors.  Data sourced from Probe42."""
    return _not_found("mca", "directors", cin)


def mca_charges(cin: str) -> dict:
    """MCA — Charges Register.  Data sourced from Probe42."""
    return _not_found("mca", "charges", cin)


def gstin_details(gstin: str) -> dict:
    """GSTIN API — Registration + compliance.  Data sourced from Probe42."""
    return _not_found("gstin", "registration", gstin)


def gstin_turnover(pan: str) -> dict:
    """GST Turnover summary by PAN.  Data sourced from Probe42."""
    return _not_found("gstin", "turnover", pan)


def bureau_commercial_report(pan: str) -> dict:
    """Credit Bureau commercial report.  Data sourced from Probe42."""
    return _not_found("bureau", "commercial_report", pan)


def rating_action(entity_id: str) -> dict:
    """Credit Rating Agency actions.  Data sourced from Probe42."""
    return _not_found("rating", "rating_action", entity_id)


def market_intelligence(entity_id: str) -> dict:
    """Market intelligence & sentiment.  Data sourced from Probe42."""
    return _not_found("market", "intelligence", entity_id)


def crilc_report(pan: str) -> dict:
    """RBI CRILC large credit report.  Data sourced from Probe42."""
    return _not_found("crilc", "borrower_report", pan)


def epfo_compliance(pan: str) -> dict:
    """EPFO compliance status.  Data sourced from Probe42."""
    return _not_found("epfo", "compliance", pan)


def itr_filing_status(pan: str) -> dict:
    """Income Tax filing status.  Data sourced from Probe42."""
    return _not_found("itr", "filing_status", pan)


def exchange_financial_results(entity_id: str) -> dict:
    """BSE/NSE financial results.  Data sourced from Probe42."""
    return _not_found("exchange", "financial_results", entity_id, "v1")


def exchange_governance_filings(entity_id: str) -> dict:
    """Exchange governance filings.  Data sourced from Probe42."""
    return _not_found("exchange", "governance_filings", entity_id, "v1")


def social_reputation_signals(entity_id: str) -> dict:
    """Social reputation signals.  Data sourced from Probe42."""
    return _not_found("social", "reputation_signals", entity_id, "v1")
