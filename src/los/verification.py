"""
Governed due-diligence workspace (Client One GAP-P0-05 / GAP-P0-06).

The fifteen client verification checks, as application records with a governed
lifecycle:

  * check type, subject, execution mode (``api`` | ``manual``) and a mandatory
    flag (demo default — the client's exact mandatory set is confirmation
    required);
  * an *initiated/triggered* state that is deliberately distinct from the
    business result — a green successful trigger is never a clear result;
  * business statuses: pending / clear / matched / failed / unavailable, where
    ``unavailable`` means "the provider did not return a result" (an
    operational state, never a negative or a clear business result);
  * last trigger date/time, triggering user, request source, error detail;
  * a retrigger history that preserves every prior run (results are never
    silently replaced);
  * user comments and, for blocked checks, a Compliance VP exception
    (the only thing that releases a mandatory match/failure block);
  * audit history — every trigger, recording and exception is an LOS event.

API-mode checks run deterministically against the in-app borrower record and
the demo services; every result carries a ``source`` label. Demo data is
explicitly labelled and a not-connected provider yields ``unavailable`` —
mock results are never presented as real integrations.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

CHECK_VERSION = "los_dd/v1"

# id, name, mode, mandatory, subject
CHECKS: list[dict] = [
    {"id": "mca", "name": "MCA — company & corporate information", "mode": "api", "mandatory": True},
    {"id": "cibil", "name": "CIBIL — commercial credit report", "mode": "api", "mandatory": False},
    {"id": "crif", "name": "CRIF — bureau score & status", "mode": "api", "mandatory": False},
    {"id": "crilc", "name": "CRILC — large credit check", "mode": "manual", "mandatory": True},
    {"id": "litigation", "name": "Legal litigation check", "mode": "api", "mandatory": False},
    {"id": "ews", "name": "Early Warning Signals (account conduct)", "mode": "api", "mandatory": False},
    {"id": "cfr", "name": "Central Fraud Registry", "mode": "manual", "mandatory": False},
    {"id": "ceib", "name": "CEIB — entity & relationship search", "mode": "manual", "mandatory": False},
    {"id": "gstin", "name": "GSTIN verification", "mode": "api", "mandatory": False},
    {"id": "lei", "name": "LEI verification", "mode": "api", "mandatory": False},
    {"id": "edd", "name": "Enhanced Due Diligence", "mode": "manual", "mandatory": False},
    {"id": "udin", "name": "UDIN — professional document verification", "mode": "manual", "mandatory": False},
    {"id": "kyc", "name": "KYC — identity & address evidence", "mode": "manual", "mandatory": True},
    {"id": "name_screening", "name": "Name screening (PEP / sanctions)", "mode": "api", "mandatory": True},
    {"id": "mlra", "name": "MLRA — money-laundering risk assessment", "mode": "manual", "mandatory": True},
]
CHECK_IDS = {c["id"]: c for c in CHECKS}
MANUAL_RESULTS = ("clear", "matched", "failed")

# UDIN grid (UAT-P1-8): the professional documents verified through UDIN, recorded manually (demo).
UDIN_STATUSES = ("verified", "not_verified", "pending")

_PENDING = "pending"
_AVAILABLE = ("clear", "matched", "failed", "unavailable")


def initial_checks() -> list[dict]:
    """Every check starts pending: nothing is triggered, nothing is known."""
    return [{"id": c["id"], "name": c["name"], "mode": c["mode"], "mandatory": c["mandatory"],
             "status": _PENDING, "result": None, "source": None, "detail": None,
             "error": None, "last_triggered": None, "triggered_by": None,
             "grid": None, "evidence": [], "history": [], "comments": [], "exception": None}
            for c in CHECKS]


# ─── Deterministic demo execution of the API-mode checks ────────────────────

def _conduct_flags(company: dict) -> list[str]:
    flags = []
    for c in company.get("conduct") or []:
        if getattr(c, "cheque_returns", 0) or getattr(c, "overdue_instances", 0) or \
                getattr(c, "max_overdue_days", 0) > 15 or getattr(c, "dpd_90_count", 0):
            flags.append(f"{getattr(c, 'period', '')}: {getattr(c, 'overdue_instances', 0)} overdue instance(s), "
                         f"{getattr(c, 'cheque_returns', 0)} cheque return(s), "
                         f"max {getattr(c, 'max_overdue_days', 0)} days overdue".strip())
    return flags


def run_api_check(check_id: str, company: dict) -> dict:
    """Run one API-mode check against the in-app record / demo services.
    Returns ``{status, detail, source, error}`` — never raises for a provider gap."""
    borrower = company.get("borrower") or {}
    from src.services.external_systems import reference_identifiers
    reference = reference_identifiers(getattr(borrower, "entity_id", "") or "")
    cin = getattr(borrower, "cin", None) or reference.get("cin") or ""
    pan = getattr(borrower, "pan", None) or reference.get("pan") or ""
    gstin = company.get("gstin") or reference.get("gstin") or ""
    doi = getattr(borrower, "date_of_incorporation", None)

    if check_id == "mca":
        if cin:
            return {"status": "clear", "detail": f"Entity registered in the company registry — CIN {cin}, "
                                                 f"incorporated {doi.isoformat() if doi else 'n/a'} (demo registry)",
                    "source": "MCA (demo data)", "error": None}
        return {"status": "failed", "detail": "No CIN on file for this entity — the registry search cannot be made",
                "source": "MCA (demo data)", "error": None}
    if check_id == "cibil":
        rating = getattr(borrower, "credit_rating", None)
        if rating:
            return {"status": "clear", "detail": f"Commercial report on file — external rating {rating} "
                                                 f"(demo bureau)", "source": "CIBIL (demo data)", "error": None}
        return {"status": "unavailable", "detail": "No bureau response — provider not connected in the demo",
                "source": "CIBIL (demo service)", "error": "provider_not_connected"}
    if check_id == "crif":
        return {"status": "unavailable", "detail": "CRIF provider not connected in the demo",
                "source": "CRIF (demo service)", "error": "provider_not_connected"}
    if check_id == "litigation":
        return {"status": "clear", "detail": "No pending litigation on the demo legal record for this entity",
                "source": "Legal record (demo data)", "error": None}
    if check_id == "ews":
        conduct = company.get("conduct") or []
        flags = _conduct_flags(company)
        grid = [{"period": getattr(c, "period", ""), "overdue_instances": getattr(c, "overdue_instances", 0),
                 "cheque_returns": getattr(c, "cheque_returns", 0),
                 "max_overdue_days": getattr(c, "max_overdue_days", 0),
                 "dpd_90_count": getattr(c, "dpd_90_count", 0)} for c in conduct]
        if flags:
            return {"status": "matched", "detail": "EWS triggers on the account-conduct record: " +
                    "; ".join(flags) + " (demo conduct data)", "source": "Account conduct (demo data)",
                    "error": None, "grid": grid}
        if conduct:
            return {"status": "clear", "detail": f"Account-conduct record reviewed ({len(conduct)} period(s)) — "
                                                 "no EWS triggers (demo conduct data)",
                    "source": "Account conduct (demo data)", "error": None, "grid": grid}
        return {"status": "unavailable", "detail": "No account-conduct record on file for this entity",
                "source": "Account conduct (demo data)", "error": None, "grid": []}
    if check_id == "gstin":
        if gstin:
            return {"status": "clear", "detail": f"GSTIN {gstin} verified against PAN {pan} (demo)",
                    "source": "GST (demo data)", "error": None}
        return {"status": "failed", "detail": "No GSTIN on record for this entity",
                "source": "GST (demo data)", "error": None}
    if check_id == "lei":
        return {"status": "unavailable", "detail": "LEI not on record for this entity — provider not connected in the demo",
                "source": "LEI (demo service)", "error": "provider_not_connected",
                "grid": [{"lei_code": None, "entity_name": getattr(borrower, "name", None) or company.get("name"),
                          "legal_address": None, "iso_country": None, "status": "not_on_record",
                          "provider": "LEI (demo service — not connected)"}]}
    if check_id == "name_screening":
        from src.services.pep_service import screen_directors
        directors = company.get("directors") or []
        try:
            res = screen_directors(getattr(borrower, "entity_id", "") or "", directors)
            pep = len(getattr(res, "pep_hits", None) or [])
            sanc = len(getattr(res, "sanctions_hits", None) or [])
        except Exception as e:                                   # a screening failure is an operational error
            return {"status": "unavailable", "detail": f"Screening run failed: {e}",
                    "source": "Name screening (demo reference list)", "error": str(e)}
        if pep or sanc:
            return {"status": "matched", "detail": f"{pep} PEP / adverse-media hit(s), {sanc} sanctions-list hit(s) "
                                                   "on the demo reference list — resolution or a Compliance VP "
                                                   "exception is required",
                    "source": "Name screening (demo reference list)", "error": None}
        return {"status": "clear", "detail": f"No PEP / sanctions matches for {len(directors)} director(s)/promoter(s) "
                                             "on the demo reference list",
                "source": "Name screening (demo reference list)", "error": None}
    raise ValueError(f"{check_id} is a manual check — record the result instead of triggering it")


# Control for mandatory checks whose provider returned nothing (UAT-P0-3). The client must confirm the
# final policy; until then the stricter, auditable control is in place: an ``unavailable`` mandatory
# check blocks progression until the Compliance VP records an explicit approval (reason required).
# Setting this to "block" makes an unavailable mandatory check block until the provider returns a result.
UNAVAILABLE_MANDATORY_POLICY = "vp_approval"          # alternatives: "vp_approval" | "block"

# 90-day screening control (UAT-P0-2 / spec §28 confirmation item, now implemented with the
# client-stated 90-day semantics): a name-screening (and MLRA) result must be re-run every 90 days,
# a Compliance VP exception lapses 90 days after it was granted, and expiries raise reminders
# (within 14 days) and, once past the due date, block progression until the check is re-run.
RESCREEN_DAYS = 90
RESCREEN_CHECKS = ("name_screening", "mlra")
EXCEPTION_TTL_DAYS = 90
EXPIRY_WARNING_DAYS = 14


def _parse(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def exception_expiry(at: str) -> str:
    """A Compliance VP exception lapses 90 days after it was granted."""
    return (_parse(at) + timedelta(days=EXCEPTION_TTL_DAYS)).isoformat(timespec="seconds")


def exception_expired(exc: Optional[dict], now: datetime) -> bool:
    """Time-based exception expiry (UAT-P0-2): an expired exception no longer releases the block."""
    if not exc:
        return False
    exp = _parse(exc.get("expires_at"))
    if exp is None and exc.get("at"):
        exp = _parse(exc["at"]) + timedelta(days=EXCEPTION_TTL_DAYS)
    return exp is not None and now >= exp


def effective_exception(c: dict, now: Optional[datetime]) -> Optional[dict]:
    """The check's exception, unless it has lapsed (only when a clock is supplied)."""
    exc = c.get("exception")
    if exc and now is not None and exception_expired(exc, now):
        return None
    return exc


def rescreen_state(check: dict, now: datetime) -> Optional[dict]:
    """The 90-day re-screening state of one check: None when not screenable, else
    ``{due_at, days_left, state}`` with state in current / due_soon / overdue."""
    if check.get("id") not in RESCREEN_CHECKS:
        return None
    last = _parse(check.get("last_triggered"))
    if not last or check["status"] != "clear":
        return None
    due = last + timedelta(days=RESCREEN_DAYS)
    days_left = (due - now).days
    state = "overdue" if days_left < 0 else ("due_soon" if days_left <= EXPIRY_WARNING_DAYS else "current")
    return {"id": check["id"], "name": check["name"], "last_run": last.date().isoformat(),
            "due_at": due.date().isoformat(), "days_left": days_left, "state": state}


def screening_review(checks: list[dict], now: datetime) -> dict:
    """Reminders and escalations: re-screening due/overdue and exceptions expiring or expired."""
    rescreens = [r for r in (rescreen_state(c, now) for c in checks) if r]
    exceptions = []
    for c in checks:
        exc = c.get("exception")
        if not exc:
            continue
        exp = _parse(exc.get("expires_at")) or (_parse(exc["at"]) + timedelta(days=EXCEPTION_TTL_DAYS) if exc.get("at") else None)
        if exp is None:
            continue
        days_left = (exp - now).days
        exceptions.append({"check_id": c["id"], "name": c["name"], "by_name": exc.get("by_name"),
                           "at": exc["at"], "expires_at": exp.isoformat(timespec="seconds"),
                           "days_left": days_left,
                           "state": "expired" if days_left < 0 else ("expiring" if days_left <= EXPIRY_WARNING_DAYS else "current")})
    overdue = [r for r in rescreens if r["state"] == "overdue"]
    return {"rescreen_days": RESCREEN_DAYS, "exception_ttl_days": EXCEPTION_TTL_DAYS,
            "rescreens": rescreens, "exceptions": exceptions, "overdue": overdue,
            "needs_attention": bool(overdue) or any(e["state"] in ("expiring", "expired") for e in exceptions)}


def blocking(checks: list[dict], unavailable_policy: str = UNAVAILABLE_MANDATORY_POLICY,
             now: Optional[datetime] = None) -> list[dict]:
    """Mandatory checks that block progression: pending; matched/failed without a still-valid
    approved exception; a mandatory ``unavailable`` without an explicit Compliance VP approval
    (under the ``vp_approval`` policy); and — when a clock is supplied — a 90-day re-screening
    that is overdue, or an exception that has lapsed. ``unavailable`` is never presented as a
    clear/positive result."""
    out = []
    for c in checks:
        if not c.get("mandatory"):
            continue
        exc = effective_exception(c, now)
        if c["status"] == "pending":
            out.append(c)
        elif c["status"] in ("failed", "matched") and not exc:
            out.append(c)
        elif c["status"] == "unavailable" and unavailable_policy in ("vp_approval", "block") and not exc:
            out.append(c)
        elif now is not None and c["status"] == "clear" and rescreen_state(c, now) and \
                rescreen_state(c, now)["state"] == "overdue":
            out.append(c)
    return out


def summary(checks: list[dict], now: Optional[datetime] = None) -> dict:
    s = {k: sum(1 for c in checks if c["status"] == k) for k in ("pending", "clear", "matched", "failed", "unavailable")}
    s["exceptions"] = sum(1 for c in checks if c.get("exception"))
    s["blocking"] = len(blocking(checks, now=now))
    s["rescreen_overdue"] = sum(1 for c in checks if now and rescreen_state(c, now) and rescreen_state(c, now)["state"] == "overdue")
    return s
