"""Integration adapter layer (Client One GAP-P0-17).

A governed registry of every external source the LOS uses, with the *honest*
current state of each: which are production-connected (none in the demo),
which serve labelled demo data, and which are not connected (yielding
``unavailable``). Every invoke preserves request/response status, source
timestamp, provider reference and the raw/normalised evidence, and the
distinction between unavailable data and a clear result.

The registry is the single source of truth for the Integrations view and the
``/api/los/integrations`` endpoint — no mock is ever presented as a real
production integration.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

# (key, source, client_use, state) — state is one of:
#   "not_connected"  provider call yields ``unavailable``; no demo data
#   "demo_data"      labelled in-app demo data; explicitly not production
#   "mock"           local mock service
ADAPTERS = [
    ("cbs", "CBS", "Customer fetch, CIF, address/account data, limits, accounts, security references", "demo_data"),
    ("lms", "LMS", "Existing loans, committed exposure and facility details", "demo_data"),
    ("mca", "MCA", "Company/LLP, directors, charges and shareholding", "demo_data"),
    ("pan", "PAN", "Identity and tax verification / dedupe", "demo_data"),
    ("gstin", "GSTIN", "GST verification and PAN-based GSTIN selection", "demo_data"),
    ("tan", "TAN", "TAN verification", "demo_data"),
    ("cibil", "CIBIL", "Commercial bureau score and report", "demo_data"),
    ("crif", "CRIF", "Commercial bureau score and report", "not_connected"),
    ("crilc", "CRILC", "Manual large-credit check and evidence", "demo_data"),
    ("litigation", "Litigation", "Legal pending-case check", "demo_data"),
    ("ews", "Early Warning Signals", "Account-conduct warning triggers", "demo_data"),
    ("cfr", "Central Fraud Registry", "Fraud-related registry check", "demo_data"),
    ("ceib", "CEIB", "Entity search, relationship, Proforma A", "not_connected"),
    ("lei", "LEI", "Legal-entity identifier validity", "not_connected"),
    ("udin", "UDIN", "Professional-document verification", "not_connected"),
    ("screening", "Name screening", "PEP / sanctions / adverse-media matching", "demo_data"),
    ("mlra", "MLRA", "Money-laundering risk assessment", "demo_data"),
    ("save_risk", "Save Risk", "Prior external credit ratings", "not_connected"),
    ("ft", "FT", "Bond exposure", "not_connected"),
    ("capital_markets", "Capital-markets source", "IP entity enrichment", "demo_data"),
    ("cerbsai", "CERSAI", "Charge search/filing reference", "demo_data"),
    ("roc", "ROC", "Charge registration reference", "demo_data"),
]

_state_by_key = {k: state for k, _, _, state in ADAPTERS}
_usage: dict[str, dict] = {}


def state_of(key: str) -> str:
    return _state_by_key.get(key, "not_connected")


def invoke(key: str, *, request: dict, response: dict, status: str,
           provider_ref: str = None, raw: str = None) -> dict:
    """Record one adapter call with its full evidence trail."""
    at = datetime.now(timezone.utc).isoformat()
    entry = {"at": at, "status": status, "request": request, "response": response,
             "provider_ref": provider_ref, "raw": raw, "source": state_of(key)}
    _usage[key] = {"last_used_at": at, "last_status": status, "calls": _usage.get(key, {}).get("calls", 0) + 1}
    return entry


def view() -> list[dict]:
    out = []
    for key, name, use, state in ADAPTERS:
        u = _usage.get(key)
        out.append({"key": key, "source": name, "client_use": use, "state": state,
                    "production_connected": False,
                    "label": "Core banking (demo data)" if key == "cbs" else
                             ("demo data — not a production integration" if state == "demo_data"
                              else "not connected — yields unavailable"),
                    "last_used_at": (u or {}).get("last_used_at"),
                    "last_status": (u or {}).get("last_status"),
                    "calls": (u or {}).get("calls", 0)})
    return out
