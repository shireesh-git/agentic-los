"""
Probe42 v2 MCP integration layer.

This module resolves companies through Probe42, fetches Probe bundles via MCP,
maps them into the app's canonical model, and exposes compact summaries for UI
and analyst chat.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.core.config_manager import config
from src.core.runtime_paths import CACHE_ROOT
from src.models.canonical_model import (
    Borrower,
    BorrowerType,
    CaseType,
    DirectorPromoter,
    ExistingExposure,
    FacilityRequest,
    FacilityType,
    FinancialStatement,
    GroupEntity,
    MarketSignal,
    RiskSeverity,
    Sector,
)
from src.services.document_store import doc_store
from src.services.document_classifier import requirement_is_satisfied
from src.services.external_systems import resolve_company as resolve_local_company, _ENTITY_TO_IDS
from src.services.probe_mcp_client import ProbeMcpClient, ProbeMcpError

log = logging.getLogger(__name__)


_PROBE_PROVIDER = "probe42_mcp_v2"
_IDENTIFIER_TOOLS = {
    "base_details": "get_base_details_by_identifier",
    "kyc_details": "get_kyc_by_identifier",
    "epfo_details": "get_epfo_details_by_identifier",
    "gst_details": "get_gst_details_by_identifier",
    "suit_filed_cases": "get_suit_filed_cases_by_identifier",
    "credit_ratings": "get_credit_ratings_by_identifier",
    "legal_history": "get_legal_history_by_identifier",
    "open_charges": "get_open_charges_by_identifier",
    "data_status": "get_data_status",
}
_BUNDLE_PROFILES = {
    "lean": (
        "base_details",
        "kyc_details",
        "credit_ratings",
        "legal_history",
        "open_charges",
        "data_status",
    ),
    "compliance": (
        "base_details",
        "kyc_details",
        "credit_ratings",
        "legal_history",
        "open_charges",
        "gst_details",
        "epfo_details",
        "data_status",
    ),
    "full": (
        "base_details",
        "kyc_details",
        "gst_details",
        "epfo_details",
        "suit_filed_cases",
        "credit_ratings",
        "legal_history",
        "open_charges",
        "data_status",
        "director_network",
    ),
}
_MISSING_DOCUMENTS = [
    {"type": "audited_financial_statements", "description": "Audited financial statements for latest 3 years", "category": "financials", "source": "rm_upload"},
    {"type": "provisional_financials", "description": "Latest provisional or management financials", "category": "financials", "source": "rm_upload"},
    {"type": "debt_schedule", "description": "Detailed debt schedule and lender-wise exposure", "category": "financials", "source": "rm_upload"},
    {"type": "board_resolution", "description": "Board resolution / borrowing approval", "category": "kyc", "source": "rm_upload"},
    {"type": "cma_or_projection", "description": "CMA data / projections / repayment assumptions", "category": "request", "source": "rm_upload"},
]
_SECTOR_KEYWORDS = {
    Sector.IT_SERVICES: ("information technology", "software", "it consulting", "it services"),
    Sector.PHARMA: ("pharma", "pharmaceutical", "biotech", "healthcare products"),
    Sector.LOGISTICS: ("logistics", "transport", "shipping", "ports", "warehousing", "freight"),
    Sector.INFRASTRUCTURE: ("infrastructure", "construction", "road", "power", "project"),
    Sector.NBFC: ("finance", "financial service", "nbfc", "bank", "lending"),
    Sector.REAL_ESTATE: ("real estate", "realty", "property", "developer"),
    Sector.TRADING: ("trading", "retail", "wholesale", "distribution"),
    Sector.HOSPITALITY: ("hospitality", "hotel", "travel", "restaurant"),
    Sector.HEALTHCARE: ("hospital", "healthcare", "diagnostic", "clinic"),
    Sector.ENERGY: ("energy", "oil", "gas", "renewable", "power"),
    Sector.MANUFACTURING: ("manufacturing", "industrial", "engineering", "factory", "metals"),
}
_DEFAULT_EBITDA_MARGIN = {
    Sector.IT_SERVICES: 0.24,
    Sector.PHARMA: 0.20,
    Sector.LOGISTICS: 0.13,
    Sector.INFRASTRUCTURE: 0.15,
    Sector.NBFC: 0.30,
    Sector.REAL_ESTATE: 0.18,
    Sector.TRADING: 0.08,
    Sector.HOSPITALITY: 0.12,
    Sector.HEALTHCARE: 0.17,
    Sector.ENERGY: 0.16,
    Sector.MANUFACTURING: 0.18,
}
_DEFAULT_PAT_MARGIN = {
    Sector.IT_SERVICES: 0.16,
    Sector.PHARMA: 0.12,
    Sector.LOGISTICS: 0.06,
    Sector.INFRASTRUCTURE: 0.05,
    Sector.NBFC: 0.13,
    Sector.REAL_ESTATE: 0.07,
    Sector.TRADING: 0.03,
    Sector.HOSPITALITY: 0.04,
    Sector.HEALTHCARE: 0.07,
    Sector.ENERGY: 0.06,
    Sector.MANUFACTURING: 0.08,
}
_DEFAULT_DEBT_TO_REVENUE = {
    Sector.IT_SERVICES: 0.15,
    Sector.PHARMA: 0.35,
    Sector.LOGISTICS: 0.38,
    Sector.INFRASTRUCTURE: 0.65,
    Sector.NBFC: 0.72,
    Sector.REAL_ESTATE: 0.70,
    Sector.TRADING: 0.30,
    Sector.HOSPITALITY: 0.45,
    Sector.HEALTHCARE: 0.32,
    Sector.ENERGY: 0.55,
    Sector.MANUFACTURING: 0.40,
}
_CACHE_DIR = CACHE_ROOT / "probe42"
_DEFAULT_CACHE_TTL_HOURS = 24 * 24


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def _probe_cfg() -> dict[str, Any]:
    return config.get("external_apis", "probe42", default={}) or {}


def is_probe_enabled() -> bool:
    return bool(_probe_cfg().get("enabled"))


def is_probe_configured() -> bool:
    return ProbeMcpClient().is_configured()


def get_probe_status(include_tools: bool = False) -> dict[str, Any]:
    cfg = _probe_cfg()
    client = ProbeMcpClient()
    cache_ttl_hours = _cache_ttl_hours()
    status = {
        "enabled": is_probe_enabled(),
        "configured": client.is_configured(),
        "provider": _PROBE_PROVIDER,
        "transport": cfg.get("transport", "mcp"),
        "mcp_url": cfg.get("mcp_url"),
        "api_key_env": cfg.get("api_key_env", "PROBE42_API_KEY"),
        "bundle_profile": cfg.get("bundle_profile", "full"),
        "cache_enabled": bool(cfg.get("cache_enabled", True)),
        "cache_ttl_hours": cache_ttl_hours,
        "cache_retention": "manual_delete" if cache_ttl_hours == 0 else "ttl",
        "tool_names": [],
    }
    if include_tools and status["enabled"] and status["configured"]:
        try:
            tools = client.list_tools().get("tools", [])
            status["tool_names"] = [tool.get("name") for tool in tools if isinstance(tool, dict) and tool.get("name")]
        except Exception as exc:
            status["error"] = str(exc)
    return status


def _default_bundle_profile() -> str:
    profile = str(_probe_cfg().get("bundle_profile", "full") or "full").strip().lower()
    return profile if profile in _BUNDLE_PROFILES else "full"


def _cache_enabled() -> bool:
    return bool(_probe_cfg().get("cache_enabled", True))


def _cache_ttl_hours() -> int:
    try:
        return max(int(_probe_cfg().get("cache_ttl_hours", _DEFAULT_CACHE_TTL_HOURS)), 0)
    except Exception:
        return _DEFAULT_CACHE_TTL_HOURS


def _tools_for_profile(profile: str | None = None) -> tuple[str, ...]:
    normalized = str(profile or _default_bundle_profile()).strip().lower()
    return _BUNDLE_PROFILES.get(normalized, _BUNDLE_PROFILES["full"])


def _normalize_profile(profile: str | None = None) -> str:
    normalized = str(profile or _default_bundle_profile()).strip().lower()
    return normalized if normalized in _BUNDLE_PROFILES else "full"


def _cache_file_key(value: str) -> str:
    text = re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")
    return text or "UNKNOWN"


def _cache_path(identifier: str, profile: str) -> Path:
    return _CACHE_DIR / f"{_cache_file_key(identifier)}__{_normalize_profile(profile)}.json"


def _load_cached_bundle(identifier: str, profile: str) -> dict[str, Any] | None:
    if not _cache_enabled():
        return None

    path = _cache_path(identifier, profile)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    cached_at = float(payload.get("cached_at_epoch") or 0.0)
    if not cached_at:
        return None
    ttl_hours = _cache_ttl_hours()
    if ttl_hours > 0 and time.time() - cached_at > ttl_hours * 3600:
        return None

    bundle = payload.get("bundle")
    if not isinstance(bundle, dict):
        return None
    # Reject cached bundles where every tool returned errors
    if not _bundle_has_valid_data(bundle):
        return None
    bundle["cache"] = {
        "status": "hit",
        "profile": _normalize_profile(profile),
        "cache_key": identifier,
        "cached_at_epoch": cached_at,
        "retention": "manual_delete" if ttl_hours == 0 else "ttl",
        "retained_until_deleted": ttl_hours == 0,
    }
    return bundle


def _bundle_has_valid_data(bundle: dict[str, Any]) -> bool:
    """Return True if at least one tool in the bundle returned real (non-error) data."""
    tool_results = bundle.get("tool_results") or {}
    if not tool_results:
        return False
    for entry in tool_results.values():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "")
        if status == "success":
            return True
    return False


def _store_cached_bundle(identifier: str, profile: str, bundle: dict[str, Any]) -> None:
    if not _cache_enabled() or not identifier:
        return
    # Never cache bundles where every tool returned an error
    if not _bundle_has_valid_data(bundle):
        return

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "cached_at_epoch": time.time(),
        "profile": _normalize_profile(profile),
        "bundle": bundle,
    }
    _cache_path(identifier, profile).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def clear_probe_cache(*identifiers: str, profile: str | None = None) -> dict[str, Any]:
    deleted_files: list[str] = []
    if not _CACHE_DIR.exists():
        return {"deleted_count": 0, "deleted_files": deleted_files}

    seen_paths: set[Path] = set()
    normalized_profile = _normalize_profile(profile) if profile else None

    for identifier in identifiers:
        if not identifier:
            continue
        cache_key = _cache_file_key(identifier)
        if normalized_profile:
            candidates = [_CACHE_DIR / f"{cache_key}__{normalized_profile}.json"]
        else:
            candidates = list(_CACHE_DIR.glob(f"{cache_key}__*.json"))

        for path in candidates:
            if path in seen_paths or not path.exists():
                continue
            try:
                path.unlink()
                deleted_files.append(path.name)
                seen_paths.add(path)
            except Exception:
                continue

    return {"deleted_count": len(deleted_files), "deleted_files": deleted_files}


def _tool_entry(bundle: dict[str, Any], key: str) -> dict[str, Any]:
    return (bundle.get("tool_results") or {}).get(key, {})


def _tool_payload(bundle: dict[str, Any], key: str) -> Any:
    data = _tool_entry(bundle, key).get("data")
    if isinstance(data, str):
        try:
            import json as _json
            data = _json.loads(data)
        except (ValueError, TypeError):
            return None
    if isinstance(data, dict) and "data" in data:
        return data.get("data")
    return data


def _identifier_kind(identifier: str) -> str:
    value = (identifier or "").strip()
    if re.fullmatch(r"[A-Z]{1}\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}", value.upper()):
        return "cin"
    if re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", value.upper()):
        return "pan"
    if re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z[A-Z\d]", value.upper()):
        return "gstin"
    if value.upper() in _ENTITY_TO_IDS:
        return "entity_id"
    return "name"


def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    try:
        return float(text)
    except Exception:
        return default


def _to_crore(value: Any) -> float:
    raw = _safe_float(value)
    if raw <= 0:
        return 0.0
    return round(raw / 1e7, 2) if raw > 100000 else round(raw, 2)


def _parse_crore_range(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().lower()
    if not text:
        return 0.0
    numbers = [_safe_float(match) for match in re.findall(r"[\d,.]+", text)]
    numbers = [num for num in numbers if num > 0]
    if not numbers:
        return 0.0
    if "more than" in text or "above" in text:
        return round(numbers[0], 2)
    if "less than" in text or "below" in text:
        return round(numbers[0] * 0.7, 2)
    if len(numbers) >= 2:
        return round((numbers[0] + numbers[1]) / 2, 2)
    return round(numbers[0], 2)


def _parse_employee_range(value: Any) -> int | None:
    parsed = int(_parse_crore_range(value))
    return parsed or None


def _format_registered_address(address: dict[str, Any] | None) -> str:
    if not isinstance(address, dict):
        return ""
    parts = [address.get("address_line"), address.get("city"), address.get("state"), address.get("pincode")]
    return ", ".join([str(part).strip() for part in parts if part])


def _normalize_company_name(value: str, fallback: str = "") -> str:
    return _clean_name(value) or fallback


def _build_entity_id(company_name: str, cin: str | None = None) -> str:
    local = next((eid for eid, ids in _ENTITY_TO_IDS.items() if cin and ids.get("cin") == cin), None)
    if local:
        return local
    letters = re.sub(r"[^A-Z0-9]", "", (company_name or "").upper())[:4] or "PRBE"
    suffix = re.sub(r"[^A-Z0-9]", "", (cin or "").upper())[-3:] or "001"
    return f"{letters}{suffix}"


SECTOR_DEFAULT_BASIS = "default"   # no industry text matched; the sector is a placeholder, not evidence


def _infer_sector_from_text(industry: str, segments: list[str] | None = None) -> tuple[Sector, str]:
    """(sector, basis): basis is "industry_text" when a keyword matched, else SECTOR_DEFAULT_BASIS."""
    combined = " ".join([industry or "", *(segments or [])]).lower()
    for sector, keywords in _SECTOR_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            return sector, "industry_text"
    return Sector.MANUFACTURING, SECTOR_DEFAULT_BASIS


def _infer_borrower_type(listing_status: str | None) -> BorrowerType:
    return BorrowerType.LISTED if str(listing_status or "").lower() == "listed" else BorrowerType.UNLISTED


def _score_search_match(query: str, candidate_name: str) -> float:
    q = (query or "").strip().lower()
    c = (candidate_name or "").strip().lower()
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if c.startswith(q):
        return 0.97
    if q in c:
        return 0.92
    return SequenceMatcher(None, q, c).ratio()


def _probe_summary_from_components(base_data: dict[str, Any], kyc_data: dict[str, Any]) -> dict[str, Any]:
    vitals = kyc_data.get("vitals") or {}
    return {
        "status": base_data.get("status") or vitals.get("status"),
        "listing_status": vitals.get("listing_status"),
        "industry": (kyc_data.get("industry_segment") or {}).get("industry"),
        "directors_count": len(kyc_data.get("directors") or []),
        "probe_score": (kyc_data.get("key_indicators") or {}).get("probe_score"),
    }


def _build_resolved_identity(
    identifier: str,
    base_data: dict[str, Any] | None = None,
    kyc_data: dict[str, Any] | None = None,
    fallback: dict[str, Any] | None = None,
    source: str = "probe42_bundle",
    resolution_mode: str = "bundle",
) -> dict[str, Any]:
    fallback = fallback or {}
    base_data = base_data or {}
    kyc_data = kyc_data or {}
    vitals = kyc_data.get("vitals") or {}
    active_gstins = (kyc_data.get("active_gstins") or {}).get("details") or []
    active_gstin = None
    if active_gstins and isinstance(active_gstins[0], dict):
        active_gstin = active_gstins[0].get("gstin")

    fallback_cin = fallback.get("cin") or fallback.get("identifier")
    cin = vitals.get("entity_identifier") or base_data.get("entity_identifier") or fallback_cin or identifier
    local = resolve_local_company(cin) or fallback or {}
    kind = _identifier_kind(identifier)
    pan = vitals.get("pan_of_entity") or local.get("pan") or (identifier if kind == "pan" else None)
    gstin = active_gstin or local.get("gstin") or (identifier if kind == "gstin" else None)
    company_name = _normalize_company_name(
        vitals.get("legal_name")
        or base_data.get("legal_name")
        or fallback.get("company_name")
        or identifier,
        fallback=str(identifier or ""),
    )

    return {
        "cin": cin,
        "pan": pan,
        "gstin": gstin,
        "entity_id": local.get("entity_id") or fallback.get("entity_id") or _build_entity_id(company_name, cin),
        "company_name": company_name,
        "source": source,
        "provider": _PROBE_PROVIDER,
        "resolution_mode": resolution_mode,
        "probe_summary": _probe_summary_from_components(base_data, kyc_data),
    }


def _resolved_from_cached_bundle(bundle: dict[str, Any], identifier: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    local = resolve_local_company(summary.get("cin") or identifier) or fallback or {}
    company_name = _normalize_company_name(summary.get("company_name") or local.get("company_name") or identifier, fallback=str(identifier or ""))
    cin = summary.get("cin") or local.get("cin") or identifier
    return {
        "cin": cin,
        "pan": summary.get("pan") or local.get("pan"),
        "gstin": summary.get("gstin") or local.get("gstin"),
        "entity_id": local.get("entity_id") or _build_entity_id(company_name, cin),
        "company_name": company_name,
        "source": "probe42_cache",
        "provider": _PROBE_PROVIDER,
        "resolution_mode": "cached_bundle",
        "probe_summary": summary,
    }


def _first_cached_bundle(*identifiers: str, profile: str | None = None) -> dict[str, Any] | None:
    bundle_profile = _normalize_profile(profile)
    seen: set[str] = set()
    for identifier in identifiers:
        key = str(identifier or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        bundle = _load_cached_bundle(key, bundle_profile)
        if bundle:
            return bundle
    return None


def _search_probe_candidates(client: ProbeMcpClient, session_id: str, api_key: str, name: str) -> list[dict[str, Any]]:
    result = client.call_tool(
        "search_companies_by_name_starts_with",
        {"name_starts_with": name, "api_key": api_key},
        session_id=session_id,
    )
    payload = result.get("data") or {}
    companies = (((payload.get("data") or {}).get("companies")) or [])
    return [company for company in companies if isinstance(company, dict)]


def resolve_company_with_probe(identifier: str) -> dict[str, Any] | None:
    identifier = (identifier or "").strip()
    if not identifier:
        return None

    local = resolve_local_company(identifier)
    cached_bundle = _first_cached_bundle(
        identifier,
        (local or {}).get("cin"),
        (local or {}).get("pan"),
        (local or {}).get("gstin"),
    )
    if cached_bundle:
        return _resolved_from_cached_bundle(cached_bundle, identifier, fallback=local)

    if not is_probe_enabled() or not is_probe_configured():
        if local:
            merged = dict(local)
            merged["source"] = "local_reference"
            merged["provider"] = _PROBE_PROVIDER
            merged["resolution_mode"] = "local_reference"
            return merged
        return None

    client = ProbeMcpClient()
    api_key = client.get_api_key()
    if not api_key:
        return local

    kind = _identifier_kind(identifier)
    probe_identifier = identifier
    if kind == "entity_id" and local:
        probe_identifier = local.get("cin") or local.get("pan") or local.get("gstin") or identifier

    try:
        session_id = client.initialize_session()
        if kind == "name":
            candidates = _search_probe_candidates(client, session_id, api_key, identifier)
            if candidates:
                best = max(candidates, key=lambda company: _score_search_match(identifier, company.get("legal_name") or company.get("company_name") or ""))
                probe_identifier = best.get("identifier") or best.get("cin") or identifier
                cached_bundle = _first_cached_bundle(probe_identifier)
                if cached_bundle:
                    return _resolved_from_cached_bundle(cached_bundle, identifier, fallback=local)
                merged_local = resolve_local_company(probe_identifier) or local or {}
                company_name = _normalize_company_name(best.get("legal_name") or best.get("company_name") or merged_local.get("company_name") or identifier)
                return {
                    "cin": probe_identifier,
                    "pan": merged_local.get("pan"),
                    "gstin": merged_local.get("gstin"),
                    "entity_id": merged_local.get("entity_id") or _build_entity_id(company_name, probe_identifier),
                    "company_name": company_name,
                    "source": "probe42_search",
                    "provider": _PROBE_PROVIDER,
                    "resolution_mode": "search",
                    "probe_summary": {},
                }

            if local:
                merged = dict(local)
                merged["source"] = "local_reference"
                merged["provider"] = _PROBE_PROVIDER
                merged["resolution_mode"] = "local_reference"
                return merged
            return None

        if local and kind in {"cin", "pan", "gstin", "entity_id"}:
            merged = dict(local)
            merged["source"] = "local_registry"
            merged["provider"] = _PROBE_PROVIDER
            merged["resolution_mode"] = "local_mapping"
            merged.setdefault("probe_summary", {})
            return merged

        base_result = client.call_tool("get_base_details_by_identifier", {"identifier": probe_identifier, "api_key": api_key}, session_id=session_id)
        base_payload = base_result.get("data") or {}
        base_data = (base_payload.get("data") or {}) if isinstance(base_payload, dict) else {}
        resolved = _build_resolved_identity(
            identifier,
            base_data=base_data,
            fallback=local,
            source="probe42_base_details",
            resolution_mode="base_details",
        )
        return resolved
    except Exception as exc:
        log.warning("Probe42 resolution failed for %s: %s", identifier, exc)
        if local:
            merged = dict(local)
            merged["source"] = "local_reference"
            merged["provider"] = _PROBE_PROVIDER
            merged["resolution_mode"] = "local_reference"
            return merged
        return None


def _estimate_market_reputation_score(bundle: dict[str, Any]) -> str:
    kyc = _tool_payload(bundle, "kyc_details") or {}
    legal_cases = _tool_payload(bundle, "legal_history") or []
    key_indicators = kyc.get("key_indicators") or {}
    pending_cases = bool(key_indicators.get("has_pending_cases_against_company"))
    defaults = bool(key_indicators.get("has_bureau_defaults"))
    medium_or_high = sum(1 for case in legal_cases if str(case.get("severity") or "").lower() in {"medium", "high", "critical"})
    if defaults or medium_or_high >= 3:
        return "high"
    if pending_cases or legal_cases:
        return "medium"
    return "low"


def _estimate_market_sentiment(bundle: dict[str, Any]) -> str:
    ratings = _tool_payload(bundle, "credit_ratings") or []
    reputation = _estimate_market_reputation_score(bundle)
    first_rating = ""
    if ratings and isinstance(ratings[0], dict):
        details = ratings[0].get("rating_details") or []
        if details and isinstance(details[0], dict):
            first_rating = str(details[0].get("rating") or "")
    if reputation == "high":
        return "negative"
    if "AAA" in first_rating or "AA" in first_rating or "A1+" in first_rating:
        return "positive"
    return "neutral"


def _summarize_rating(ratings: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not ratings:
        return None, None
    top = ratings[0] if isinstance(ratings[0], dict) else {}
    agency = top.get("rating_agency")
    details = top.get("rating_details") or []
    long_term = next((item for item in details if "long" in str(item.get("instrument") or "").lower()), None)
    first = long_term or (details[0] if details else {})
    rating = str(first.get("rating") or "").strip() or None
    outlook = str(first.get("outlook") or "").strip() or None
    if rating and outlook:
        return rating, agency
    return rating or None, agency


def fetch_probe_bundle(identifier: str, profile: str | None = None, force_refresh: bool = False) -> dict[str, Any]:
    if not is_probe_enabled():
        raise ProbeMcpError("Probe42 is disabled in configuration")
    client = ProbeMcpClient()
    api_key = client.get_api_key()
    if not api_key:
        raise ProbeMcpError(f"Set {client.api_key_env} to use Probe42")

    bundle_profile = _normalize_profile(profile)
    local = resolve_local_company(identifier) or {}
    resolved = resolve_company_with_probe(identifier) or {}
    probe_identifier = resolved.get("cin") or local.get("cin") or resolved.get("pan") or local.get("pan") or resolved.get("gstin") or local.get("gstin") or identifier
    if not force_refresh:
        cached_bundle = _first_cached_bundle(
            probe_identifier,
            resolved.get("cin"),
            resolved.get("pan"),
            resolved.get("gstin"),
            identifier,
            profile=bundle_profile,
        )
        if cached_bundle:
            return cached_bundle

    session_id = client.initialize_session()

    bundle = {
        "provider": _PROBE_PROVIDER,
        "identifier": identifier,
        "resolved_identifier": probe_identifier,
        "profile": bundle_profile,
        "fetched_at": _now_iso(),
        "cache": {
            "status": "miss",
            "profile": bundle_profile,
            "cache_key": probe_identifier,
        },
        "tool_results": {},
    }

    for bundle_key in _tools_for_profile(bundle_profile):
        if bundle_key == "director_network":
            continue
        tool_name = _IDENTIFIER_TOOLS[bundle_key]
        try:
            result = client.call_tool(tool_name, {"identifier": probe_identifier, "api_key": api_key}, session_id=session_id)
            raw_data = result.get("data")
            raw_text = result.get("text") or ""
            # Detect Probe42 error payloads returned as data strings
            is_error = (
                isinstance(raw_data, str) and raw_data.strip().startswith("Error:")
            ) or (
                isinstance(raw_text, str) and "'message':" in raw_text and "does not exist" in raw_text
            )
            if is_error:
                bundle["tool_results"][bundle_key] = {
                    "tool_name": tool_name,
                    "status": "error",
                    "error": str(raw_data or raw_text),
                    "data": None,
                    "text": raw_text,
                }
            else:
                bundle["tool_results"][bundle_key] = {
                    "tool_name": tool_name,
                    "status": "success" if raw_data is not None or raw_text else "not_found",
                    "data": raw_data,
                    "text": raw_text,
                }
        except Exception as exc:
            bundle["tool_results"][bundle_key] = {
                "tool_name": tool_name,
                "status": "error",
                "error": str(exc),
                "data": None,
                "text": "",
            }

    kyc = _tool_payload(bundle, "kyc_details") or {}
    if not isinstance(kyc, dict):
        kyc = {}
    if "director_network" in _tools_for_profile(bundle_profile):
        directors = kyc.get("directors") or []
        network_payloads: list[dict[str, Any]] = []
        for director in directors:
            if not isinstance(director, dict):
                continue
            din = str(director.get("din") or "").strip()
            if not din:
                continue
            try:
                result = client.call_tool("get_director_network_by_din", {"din": din, "api_key": api_key}, session_id=session_id)
                data = result.get("data")
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    network_payloads.extend(item for item in data["data"] if isinstance(item, dict))
            except Exception:
                continue
            if len(network_payloads) >= 8:
                break

        bundle["tool_results"]["director_network"] = {
            "tool_name": "get_director_network_by_din",
            "status": "success" if network_payloads else "not_found",
            "data": {"data": network_payloads, "metadata": {"generated_at": _now_iso()}},
            "text": "",
        }

    base_data = _tool_payload(bundle, "base_details") or {}
    bundle["resolved"] = _build_resolved_identity(
        identifier,
        base_data=base_data if isinstance(base_data, dict) else {},
        kyc_data=kyc if isinstance(kyc, dict) else {},
        fallback=resolved or local,
    )
    bundle["summary"] = _build_probe_summary(bundle, bundle["resolved"])
    for alias in {
        probe_identifier,
        bundle["resolved"].get("cin"),
        bundle["resolved"].get("pan"),
        bundle["resolved"].get("gstin"),
    }:
        if alias:
            _store_cached_bundle(str(alias), bundle_profile, bundle)
    return bundle


def _build_probe_summary(bundle: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    kyc = _tool_payload(bundle, "kyc_details") or {}
    base = _tool_payload(bundle, "base_details") or {}
    vitals = kyc.get("vitals") or {}
    industry = (kyc.get("industry_segment") or {}).get("industry")
    segments = (kyc.get("industry_segment") or {}).get("segments") or []
    legal_cases = _tool_payload(bundle, "legal_history") or []
    ratings = _tool_payload(bundle, "credit_ratings") or []
    open_charges = _tool_payload(bundle, "open_charges") or []
    gst_records = _tool_payload(bundle, "gst_details") or []
    epfo_records = _tool_payload(bundle, "epfo_details") or []
    data_status = _tool_payload(bundle, "data_status") or {}
    rating, rating_agency = _summarize_rating(ratings if isinstance(ratings, list) else [])

    return {
        "provider": _PROBE_PROVIDER,
        "fetched_at": bundle.get("fetched_at"),
        "company_name": resolved.get("company_name") or base.get("legal_name") or vitals.get("legal_name"),
        "cin": resolved.get("cin") or base.get("entity_identifier") or vitals.get("entity_identifier"),
        "pan": resolved.get("pan") or vitals.get("pan_of_entity"),
        "gstin": resolved.get("gstin"),
        "status": base.get("status") or vitals.get("status"),
        "listing_status": vitals.get("listing_status"),
        "industry": industry,
        "segments": segments,
        "registered_state": (base.get("registered_address") or {}).get("state") or (vitals.get("registered_address") or {}).get("state"),
        "directors_count": len(kyc.get("directors") or []),
        "ratings_count": len(ratings) if isinstance(ratings, list) else 0,
        "rating": rating,
        "rating_agency": rating_agency,
        "legal_case_count": len(legal_cases) if isinstance(legal_cases, list) else 0,
        "open_charge_count": len(open_charges) if isinstance(open_charges, list) else 0,
        "active_gstin_count": len(gst_records) if isinstance(gst_records, list) and gst_records else len(((kyc.get("active_gstins") or {}).get("details")) or []),
        "epfo_establishment_count": len(epfo_records) if isinstance(epfo_records, list) and epfo_records else int(_safe_float(vitals.get("active_epfo_establishments_count"))),
        "probe_score": (kyc.get("key_indicators") or {}).get("probe_score"),
        "data_status": data_status if isinstance(data_status, dict) else {},
    }


def _build_probe_market_signals(entity_id: str, bundle: dict[str, Any]) -> list[MarketSignal]:
    signals: list[MarketSignal] = []
    kyc = _tool_payload(bundle, "kyc_details") or {}
    legal_cases = _tool_payload(bundle, "legal_history") or []
    open_charges = _tool_payload(bundle, "open_charges") or []
    ratings = _tool_payload(bundle, "credit_ratings") or []
    key_indicators = kyc.get("key_indicators") or {}

    if ratings:
        agency = ratings[0].get("rating_agency", "Public Rating Record")
        details = ratings[0].get("rating_details") or []
        first = next((item for item in details if "long" in str(item.get("instrument") or "").lower()), None) or (details[0] if details else {})
        rating = first.get("rating")
        outlook = first.get("outlook")
        sentiment = "positive" if rating and any(token in str(rating) for token in ("AAA", "AA", "A1+")) else "neutral"
        signals.append(MarketSignal(
            entity_id=entity_id,
            signal_type="rating",
            headline=f"Public rating view: {rating or 'Not rated'}",
            sentiment=sentiment,
            severity=RiskSeverity.LOW if sentiment == "positive" else RiskSeverity.MEDIUM,
            source_name=str(agency).upper(),
            signal_date=date.today(),
            details=f"Outlook: {outlook or 'Not stated'}",
        ))

    if key_indicators.get("has_pending_cases_against_company"):
        signals.append(MarketSignal(
            entity_id=entity_id,
            signal_type="legal",
            headline=f"Public records show {len(legal_cases) or 'multiple'} legal matters against the company",
            sentiment="negative",
            severity=RiskSeverity.MEDIUM if legal_cases else RiskSeverity.LOW,
            source_name="Verified Legal History",
            signal_date=date.today(),
            details="Legal matters should be reviewed in the case worksheet and CAM narrative.",
        ))

    if key_indicators.get("has_bureau_defaults"):
        signals.append(MarketSignal(
            entity_id=entity_id,
            signal_type="bureau",
            headline="Public records indicate bureau default flags",
            sentiment="negative",
            severity=RiskSeverity.HIGH,
            source_name="Verified KYC",
            signal_date=date.today(),
        ))

    if open_charges:
        signals.append(MarketSignal(
            entity_id=entity_id,
            signal_type="charges",
            headline=f"{len(open_charges)} open charge(s) detected in public filings",
            sentiment="neutral",
            severity=RiskSeverity.LOW,
            source_name="Verified Charges",
            signal_date=date.today(),
        ))

    return signals


def _extract_charge_amount_cr(charge: dict[str, Any]) -> float:
    for key in ("amount", "amount_secured", "charge_amount", "amount_of_charge", "sum_of_charges"):
        value = charge.get(key)
        amount = _to_crore(value)
        if amount > 0:
            return amount
    return 0.0


def _build_probe_exposure(entity_id: str, bundle: dict[str, Any]) -> list[ExistingExposure]:
    open_charges = _tool_payload(bundle, "open_charges") or []
    exposures: list[ExistingExposure] = []
    if isinstance(open_charges, list):
        for idx, charge in enumerate(open_charges, start=1):
            if not isinstance(charge, dict):
                continue
            amount_cr = _extract_charge_amount_cr(charge)
            exposures.append(ExistingExposure(
                facility_id=f"PRB-CHG-{entity_id}-{idx}",
                entity_id=entity_id,
                facility_type="secured_charge",
                sanctioned_limit_cr=amount_cr,
                outstanding_cr=amount_cr,
                utilization_pct=100.0 if amount_cr else 0.0,
                overdue_days=0,
                classification="Charge Registered",
            ))
            if idx >= 6:
                break
    return exposures


def _estimate_financials_from_probe(entity_id: str, bundle: dict[str, Any], sector: Sector) -> dict[str, FinancialStatement]:
    kyc = _tool_payload(bundle, "kyc_details") or {}
    vitals = kyc.get("vitals") or {}
    indicators = kyc.get("key_indicators") or {}
    revenue_cr = _parse_crore_range(indicators.get("revenue_range"))
    pat_cr = _parse_crore_range(indicators.get("profit_range"))
    paid_up_capital_cr = _to_crore(vitals.get("paid_up_capital"))
    sum_of_charges_cr = _to_crore(vitals.get("sum_of_charges"))

    if revenue_cr <= 0:
        revenue_cr = max(paid_up_capital_cr * 4.0, 50.0)
    if pat_cr <= 0:
        pat_cr = round(revenue_cr * _DEFAULT_PAT_MARGIN.get(sector, 0.08), 2)

    ebitda_margin = _DEFAULT_EBITDA_MARGIN.get(sector, 0.18)
    ebitda_cr = max(round(revenue_cr * ebitda_margin, 2), round(pat_cr * 2.2, 2))
    finance_cost_cr = max(round(revenue_cr * 0.02, 2), round(sum_of_charges_cr * 0.08, 2) if sum_of_charges_cr else 0.0)
    pbt_cr = round(max(pat_cr / 0.75, pat_cr + finance_cost_cr), 2)
    tax_expense_cr = round(max(pbt_cr - pat_cr, 0.0), 2)
    total_debt_cr = max(sum_of_charges_cr, round(revenue_cr * _DEFAULT_DEBT_TO_REVENUE.get(sector, 0.40), 2))
    total_equity_cr = max(round(total_debt_cr / 1.2, 2), round(max(paid_up_capital_cr * 1.6, revenue_cr * 0.22), 2))
    current_assets_cr = round(revenue_cr * 0.32, 2)
    current_liabilities_cr = round(revenue_cr * 0.19, 2)
    total_assets_cr = max(round(total_equity_cr + total_debt_cr + revenue_cr * 0.10, 2), round(current_assets_cr + total_equity_cr, 2))
    ocf_cr = round(ebitda_cr * 0.68, 2)

    last_fin_year_end = str(vitals.get("last_fin_year_end") or "").strip()
    try:
        latest_date = date.fromisoformat(last_fin_year_end) if last_fin_year_end else date(2025, 3, 31)
    except Exception:
        latest_date = date(2025, 3, 31)
    latest_year = latest_date.year
    periods = [
        (f"FY{latest_year}", latest_date, 1.00),
        (f"FY{latest_year - 1}", date(latest_year - 1, latest_date.month, latest_date.day), 0.92),
        (f"FY{latest_year - 2}", date(latest_year - 2, latest_date.month, latest_date.day), 0.84),
        (f"FY{latest_year - 3}", date(latest_year - 3, latest_date.month, latest_date.day), 0.77),
        (f"FY{latest_year - 4}", date(latest_year - 4, latest_date.month, latest_date.day), 0.71),
    ]

    financials: dict[str, FinancialStatement] = {}
    for period, as_of_date, factor in periods:
        revenue = round(revenue_cr * factor, 2)
        ebitda = round(ebitda_cr * factor, 2)
        pat = round(pat_cr * factor, 2)
        total_debt = round(total_debt_cr * max(0.88, factor), 2)
        total_equity = round(total_equity_cr * factor, 2)
        financials[period] = FinancialStatement(
            entity_id=entity_id,
            period=period,
            statement_type="standalone",
            source="probe42_estimated_from_ranges",
            as_of_date=as_of_date,
            line_items={
                "revenue_operating": revenue,
                "other_income": round(revenue * 0.01, 2),
                "total_income": round(revenue * 1.01, 2),
                "ebitda": ebitda,
                "depreciation": round(revenue * 0.03, 2),
                "ebit": round(ebitda - revenue * 0.03, 2),
                "finance_cost": round(finance_cost_cr * max(0.90, factor), 2),
                "pbt": round(pbt_cr * factor, 2),
                "tax_expense": round(tax_expense_cr * factor, 2),
                "pat": pat,
                "total_debt": total_debt,
                "long_term_debt": round(total_debt * 0.65, 2),
                "total_equity": total_equity,
                "current_assets": round(current_assets_cr * factor, 2),
                "current_liabilities": round(current_liabilities_cr * factor, 2),
                "total_assets": round(max(total_assets_cr * factor, total_equity + total_debt), 2),
                "trade_receivables": round(revenue * 0.15, 2),
                "inventory": round(revenue * (0.03 if sector == Sector.IT_SERVICES else 0.09), 2),
                "trade_payables": round(revenue * 0.08, 2),
                "cash_equivalents": round(revenue * 0.06, 2),
                "operating_cash_flow": round(ocf_cr * factor, 2),
                "capex": round(revenue * 0.04, 2),
            },
        )
    return financials


def _build_probe_directors(entity_id: str, bundle: dict[str, Any]) -> list[DirectorPromoter]:
    kyc = _tool_payload(bundle, "kyc_details") or {}
    directors_data = kyc.get("directors") or []
    networks = _tool_payload(bundle, "director_network") or []
    network_map: dict[str, list[str]] = {}

    if isinstance(networks, list):
        for item in networks:
            if not isinstance(item, dict):
                continue
            din = str(item.get("din") or "")
            companies = (((item.get("network") or {}).get("companies")) or [])
            names = []
            for company in companies:
                if not isinstance(company, dict):
                    continue
                legal_name = _normalize_company_name(company.get("legal_name"))
                if legal_name:
                    names.append(legal_name)
            network_map[din] = sorted(set(names))

    directors: list[DirectorPromoter] = []
    seen: set[tuple[str, str]] = set()
    for item in directors_data:
        if not isinstance(item, dict):
            continue
        name = _normalize_company_name(item.get("name"))
        din = str(item.get("din") or "").strip() or "00000000"
        if (din, name) in seen:
            continue
        seen.add((din, name))
        designation = str(item.get("designation") or "Director")
        directors.append(DirectorPromoter(
            din=din,
            name=name or "Unknown Director",
            designation=designation,
            entity_id=entity_id,
            other_directorships=network_map.get(din, []),
            is_promoter="managing" in designation.lower() or "promoter" in designation.lower(),
        ))
    return directors


def _build_probe_group(entity_id: str, company_name: str, directors: list[DirectorPromoter]) -> GroupEntity | None:
    related: set[str] = set()
    for director in directors:
        for company in director.other_directorships:
            if company and company.lower() != company_name.lower():
                related.add(company)
    if not related:
        return None
    return GroupEntity(
        group_id=f"GRP_{entity_id}",
        group_name=f"{company_name.split()[0]} Group",
        parent_entity_id=entity_id,
        entities=[entity_id, *sorted(related)],
    )


def _build_probe_external_data(bundle: dict[str, Any], borrower: Borrower) -> dict[str, Any]:
    base = _tool_payload(bundle, "base_details") or {}
    kyc = _tool_payload(bundle, "kyc_details") or {}
    vitals = kyc.get("vitals") or {}
    industry_segment = kyc.get("industry_segment") or {}
    ratings = _tool_payload(bundle, "credit_ratings") or []
    gst_records = _tool_payload(bundle, "gst_details") or []
    legal_cases = _tool_payload(bundle, "legal_history") or []
    open_charges = _tool_payload(bundle, "open_charges") or []
    epfo_records = _tool_payload(bundle, "epfo_details") or []
    suit_filed = _tool_payload(bundle, "suit_filed_cases")
    indicators = kyc.get("key_indicators") or {}

    gst_payload = {}
    if isinstance(gst_records, list) and gst_records:
        first = gst_records[0] if isinstance(gst_records[0], dict) else {}
        filings = first.get("filings") or []
        filing_status = first.get("filing_timeliness") or (filings[0].get("filing_timeliness") if filings and isinstance(filings[0], dict) else None)
        gst_payload = {
            "gstin": first.get("gstin"),
            "legal_name": first.get("company_name") or borrower.company_name,
            "aggregate_turnover_fy2024_cr": None,
            "aggregate_turnover_fy2023_cr": None,
            "filing_status": filing_status,
            "last_return_filed": filings[0].get("date_of_filing") if filings and isinstance(filings[0], dict) else None,
            "pending_returns": sum(1 for filing in filings if isinstance(filing, dict) and str(filing.get("status") or "").lower() != "filed"),
        }

    rating_payload = {}
    if ratings:
        agency = str(ratings[0].get("rating_agency") or "").upper() or "PUBLIC RECORD"
        details = ratings[0].get("rating_details") or []
        long_term = next((item for item in details if "long" in str(item.get("instrument") or "").lower()), None) or (details[0] if details else {})
        rating_payload = {
            "rating_agency": agency,
            "long_term_rating": long_term.get("rating"),
            "short_term_rating": next((item.get("rating") for item in details if "commercial paper" in str(item.get("instrument") or "").lower()), None),
            "outlook": long_term.get("outlook"),
            "last_action": long_term.get("action"),
            "action_date": ratings[0].get("rating_date"),
            "history": ratings,
        }

    total_charge_amount_cr = 0.0
    unique_holders: set[str] = set()
    if isinstance(open_charges, list):
        for charge in open_charges:
            if not isinstance(charge, dict):
                continue
            total_charge_amount_cr += _extract_charge_amount_cr(charge)
            holder = charge.get("charge_holder") or charge.get("holder")
            if holder:
                unique_holders.add(str(holder))

    bureau_payload = {
        "credit_score": 620 + int(_safe_float(indicators.get("probe_score")) * 35) if indicators.get("probe_score") is not None else None,
        "score_description": "Verified public-record snapshot",
        "total_exposure_cr": round(total_charge_amount_cr, 2) if total_charge_amount_cr else 0.0,
        "total_lenders": len(unique_holders),
        "dpd_status": "Adverse signal" if indicators.get("has_bureau_defaults") else "Standard",
        "max_dpd_last_12m": 90 if indicators.get("has_bureau_defaults") else 0,
        "worst_status_12m": "Default signal" if indicators.get("has_bureau_defaults") else "Standard",
        "suit_filed_amount_cr": 0.0,
        "wilful_defaulter": False,
        "fraud_flag": False,
        "rbi_defaulter_list": False,
        "enquiries_last_6m": None,
    }

    market_payload = {
        "overall_sentiment": _estimate_market_sentiment(bundle),
        "reputation_risk_score": _estimate_market_reputation_score(bundle),
        "news_count_90d": len(legal_cases),
        "market_position": industry_segment.get("industry"),
        "industry_outlook": industry_segment.get("industry"),
        "gst_compliance": "Delayed" if indicators.get("gst_filing_after_due_date") else "Regular",
    }

    epfo_payload = {}
    if isinstance(epfo_records, list) and epfo_records:
        first = epfo_records[0] if isinstance(epfo_records[0], dict) else {}
        filings = first.get("filing_details") or []
        epfo_payload = {
            "active_members": sum(int(_safe_float(item.get("no_of_employees"))) for item in filings[:3] if isinstance(item, dict)) or vitals.get("active_epfo_establishments_count"),
            "compliance_status": first.get("payment_timeliness"),
            "establishment_count": len(epfo_records),
        }

    mca_payload = {
        "company_name": base.get("legal_name") or vitals.get("legal_name") or borrower.company_name,
        "cin": base.get("entity_identifier") or vitals.get("entity_identifier") or borrower.cin,
        "status": base.get("status") or vitals.get("status"),
        "date_of_incorporation": base.get("date_of_incorporation") or vitals.get("date_of_incorporation"),
        "registered_state": (base.get("registered_address") or {}).get("state") or (vitals.get("registered_address") or {}).get("state"),
        "registered_office": _format_registered_address(base.get("registered_address") or vitals.get("registered_address")),
        "paid_up_capital_inr": vitals.get("paid_up_capital"),
        "listing_status": vitals.get("listing_status"),
        "listed_exchange": "Listed" if vitals.get("listing_status") == "Listed" else None,
        "email": vitals.get("email"),
        "last_agm_date": vitals.get("last_agm_date"),
        "last_bs_date": vitals.get("last_fin_year_end"),
        "industrial_class": industry_segment.get("industry"),
    }

    return {
        "mca_data": {"source": "probe42", "record_type": "company_master", "entity_key": borrower.cin, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": _tool_entry(bundle, "base_details").get("status", "not_found"), "payload": mca_payload},
        "bureau_data": {"source": "probe42", "record_type": "public_record_snapshot", "entity_key": borrower.pan, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": "success", "payload": bureau_payload},
        "gst_data": {"source": "probe42", "record_type": "gst_profile", "entity_key": borrower.pan, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": _tool_entry(bundle, "gst_details").get("status", "not_found"), "payload": gst_payload},
        "rating_data": {"source": "probe42", "record_type": "ratings", "entity_key": borrower.entity_id, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": _tool_entry(bundle, "credit_ratings").get("status", "not_found"), "payload": rating_payload},
        "market_data": {"source": "probe42", "record_type": "market_proxy", "entity_key": borrower.entity_id, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": "success", "payload": market_payload},
        "crilc_data": {"source": "probe42", "record_type": "crilc_unavailable", "entity_key": borrower.pan, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": "not_available", "payload": {"note": "Probe42 does not provide internal CRILC exposure. Use internal banking systems for ETB and CRILC checks."}},
        "epfo_data": {"source": "probe42", "record_type": "epfo_profile", "entity_key": borrower.pan, "as_of_date": _now_iso(), "payload_version": "probe42_v2", "source_status": _tool_entry(bundle, "epfo_details").get("status", "not_found"), "payload": epfo_payload},
        "legal_cases": legal_cases,
        "open_charges": open_charges,
        "suit_filed_cases": suit_filed,
    }


def store_probe_bundle_documents(entity_id: str, bundle: dict[str, Any]) -> None:
    doc_store.init_company_folder(entity_id)
    company_root = doc_store.root / entity_id
    if company_root.exists():
        for stale_file in company_root.glob("**/probe42_*.json"):
            try:
                stale_file.unlink()
            except Exception:
                pass

    category_map = {
        "base_details": "mca",
        "kyc_details": "kyc",
        "epfo_details": "legal",
        "gst_details": "gst",
        "suit_filed_cases": "legal",
        "credit_ratings": "ratings",
        "legal_history": "legal",
        "open_charges": "mca",
        "director_network": "mca",
        "data_status": "misc",
    }
    for key, entry in (bundle.get("tool_results") or {}).items():
        category = category_map.get(key, "misc")
        payload = entry.get("data")
        if payload is None and entry.get("text"):
            payload = {"text": entry.get("text")}
        content = json.dumps(payload or {}, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        doc_store.store_document(entity_id, category, f"probe42_{key}.json", content, source=_PROBE_PROVIDER)

    bundle_content = json.dumps(bundle, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    doc_store.store_document(entity_id, "misc", "probe42_bundle.json", bundle_content, source=_PROBE_PROVIDER)


def _missing_rm_documents_for_entity(entity_id: str) -> list[dict[str, Any]]:
    workspace = doc_store.list_company_documents(entity_id)
    categories = workspace.get("categories") or {}
    missing: list[dict[str, Any]] = []
    for requirement in _MISSING_DOCUMENTS:
        category = requirement.get("category")
        if not category:
            missing.append(dict(requirement))
            continue
        visible_files = (categories.get(category) or {}).get("files") or []
        if requirement_is_satisfied(category, visible_files, str(requirement.get("type") or "")):
            continue
        missing.append(dict(requirement))
    return missing


def company_probe_snapshot(company_data: dict[str, Any]) -> dict[str, Any]:
    bundle = company_data.get("probe_bundle")
    summary = company_data.get("probe_summary") or {}
    return {
        "available": bool(bundle),
        "provider": company_data.get("data_provider"),
        "profile": (bundle or {}).get("profile"),
        "cache": (bundle or {}).get("cache", {}),
        "summary": summary,
        "data_status": summary.get("data_status", {}),
        "tool_status": {
            key: entry.get("status", "unknown")
            for key, entry in (bundle.get("tool_results", {}) if isinstance(bundle, dict) else {}).items()
        },
    }


def probe_context_text(bundle: dict[str, Any] | None) -> str:
    if not bundle:
        return ""

    summary = bundle.get("summary") or {}
    kyc = _tool_payload(bundle, "kyc_details") or {}
    industry_segment = kyc.get("industry_segment") or {}
    ratings = _tool_payload(bundle, "credit_ratings") or []
    legal_cases = _tool_payload(bundle, "legal_history") or []
    open_charges = _tool_payload(bundle, "open_charges") or []
    data_status = _tool_payload(bundle, "data_status") or {}

    parts = ["## Probe42 Snapshot"]
    parts.append(f"- Provider: {_PROBE_PROVIDER}")
    parts.append(f"- Fetched At: {bundle.get('fetched_at', 'N/A')}")
    parts.append(f"- Legal Name: {summary.get('company_name', 'N/A')}")
    parts.append(f"- CIN: {summary.get('cin', 'N/A')}")
    parts.append(f"- PAN: {summary.get('pan', 'N/A')}")
    parts.append(f"- Status: {summary.get('status', 'N/A')}")
    parts.append(f"- Listing: {summary.get('listing_status', 'N/A')}")
    parts.append(f"- Industry: {summary.get('industry', 'N/A')}")
    if industry_segment.get("segments"):
        parts.append(f"- Segments: {', '.join(industry_segment.get('segments')[:4])}")
    parts.append(f"- Probe Score: {(kyc.get('key_indicators') or {}).get('probe_score', 'N/A')}")
    parts.append(f"- Active GSTIN Count: {summary.get('active_gstin_count', 0)}")
    parts.append(f"- EPFO Establishments: {summary.get('epfo_establishment_count', 0)}")
    parts.append(f"- Legal Case Count: {summary.get('legal_case_count', 0)}")
    parts.append(f"- Open Charges: {summary.get('open_charge_count', 0)}")

    if ratings:
        parts.append("- Ratings:")
        for rating in ratings[:3]:
            if not isinstance(rating, dict):
                continue
            agency = str(rating.get("rating_agency") or "").upper() or "PROBE42"
            details = rating.get("rating_details") or []
            for item in details[:3]:
                if not isinstance(item, dict):
                    continue
                parts.append(f"  - {agency}: {item.get('instrument')} | {item.get('rating')} | {item.get('action')} | Outlook {item.get('outlook') or 'N/A'}")

    if legal_cases:
        parts.append("- Legal History:")
        for case in legal_cases[:5]:
            if not isinstance(case, dict):
                continue
            parts.append(f"  - {case.get('date')}: {case.get('court')} | {case.get('case_status')} | {case.get('case_category')} | Severity {case.get('severity')}")

    if open_charges:
        parts.append("- Open Charges:")
        for charge in open_charges[:5]:
            if not isinstance(charge, dict):
                continue
            holder = charge.get("charge_holder") or charge.get("holder") or "Unknown holder"
            amount = _extract_charge_amount_cr(charge)
            parts.append(f"  - Holder: {holder} | Amount: {amount or 'N/A'} Cr")

    if isinstance(data_status, dict) and data_status:
        freshness = ", ".join(f"{key}={value}" for key, value in sorted(data_status.items()))
        parts.append(f"- Module Freshness: {freshness}")

    return "\n".join(parts)


def onboard_company_via_probe(
    identifier: str,
    case_type: str = "NTB",
    facility_type: str = "working_capital",
    amount_requested_cr: float = 100.0,
    purpose: str = "General corporate purpose",
    tenor_months: int | None = None,
) -> dict[str, Any] | None:
    if not is_probe_enabled() or not is_probe_configured():
        return None

    resolved = resolve_company_with_probe(identifier)
    if not resolved or resolved.get("provider") != _PROBE_PROVIDER:
        return None

    bundle = fetch_probe_bundle(resolved.get("cin") or identifier, profile=_default_bundle_profile())

    # If Probe42 returned errors for ALL tools, report the error — don't fabricate data
    if not _bundle_has_valid_data(bundle):
        tool_errors = {
            key: entry.get("error") or entry.get("status")
            for key, entry in (bundle.get("tool_results") or {}).items()
        }
        return {
            "status": "error",
            "provider": _PROBE_PROVIDER,
            "error": f"Probe42 returned errors for all endpoints — CIN '{resolved.get('cin') or identifier}' may not exist in Probe42 database",
            "probe_errors": tool_errors,
            "entity_id": resolved.get("entity_id"),
            "company_name": resolved.get("company_name") or identifier,
            "resolved": resolved,
        }

    summary = bundle.get("summary") or {}
    kyc = _tool_payload(bundle, "kyc_details") or {}
    if not isinstance(kyc, dict):
        kyc = {}
    base = _tool_payload(bundle, "base_details") or {}
    if not isinstance(base, dict):
        base = {}
    vitals = kyc.get("vitals") or {}
    industry_segment = kyc.get("industry_segment") or {}
    company_name = resolved.get("company_name") or summary.get("company_name") or identifier
    cin = resolved.get("cin") or summary.get("cin") or identifier
    entity_id = resolved.get("entity_id") or _build_entity_id(company_name, cin)
    sector, sector_basis = _infer_sector_from_text(industry_segment.get("industry"), industry_segment.get("segments"))
    borrower_type = _infer_borrower_type(vitals.get("listing_status"))
    rating, rating_agency = _summarize_rating(_tool_payload(bundle, "credit_ratings") or [])
    employee_count = _parse_employee_range((kyc.get("key_indicators") or {}).get("employee_count_range"))

    registered_address = vitals.get("registered_address") or base.get("registered_address") or {}
    borrower = Borrower(
        entity_id=entity_id,
        company_name=company_name,
        cin=cin,
        pan=resolved.get("pan") or vitals.get("pan_of_entity") or "",
        borrower_type=borrower_type,
        sector=sector,
        subsector=industry_segment.get("industry") or sector.value,
        date_of_incorporation=date.fromisoformat(vitals.get("date_of_incorporation") or base.get("date_of_incorporation") or "2010-01-01"),
        registered_state=registered_address.get("state") or "Unknown",
        registered_address=_format_registered_address(registered_address),
        authorized_capital=_to_crore(vitals.get("paid_up_capital")) * 1.25 if vitals.get("paid_up_capital") else 0.0,
        paid_up_capital=_to_crore(vitals.get("paid_up_capital")),
        listed_exchange="Listed" if borrower_type == BorrowerType.LISTED else None,
        credit_rating=rating,
        rating_agency=rating_agency,
        employee_count=employee_count,
        website=vitals.get("website"),
    )

    directors = _build_probe_directors(entity_id, bundle)
    group = _build_probe_group(entity_id, company_name, directors)
    # Only estimate financials if Probe42 returned real KYC data with revenue/capital indicators
    kyc_indicators = (kyc.get("key_indicators") or {})
    has_financial_indicators = bool(kyc_indicators.get("revenue_range") or kyc_indicators.get("profit_range") or vitals.get("paid_up_capital"))
    financials = _estimate_financials_from_probe(entity_id, bundle, sector) if has_financial_indicators else {}
    existing_exposure = _build_probe_exposure(entity_id, bundle)
    market_signals = _build_probe_market_signals(entity_id, bundle)
    external_data = _build_probe_external_data(bundle, borrower)

    try:
        ct = CaseType(case_type)
    except ValueError:
        ct = CaseType.NTB
    try:
        ft = FacilityType(facility_type)
    except ValueError:
        ft = FacilityType.WORKING_CAPITAL

    facility = FacilityRequest(
        facility_id=f"FAC-{entity_id}",
        entity_id=entity_id,
        case_type=ct,
        facility_type=ft,
        amount_requested_cr=amount_requested_cr,
        purpose=purpose,
        tenor_months=tenor_months,
    )

    company_data = {
        "borrower": borrower,
        "sector_basis": sector_basis,
        "group": group,
        "directors": directors,
        "financials": financials,
        "provisional": None,
        "facility": facility,
        "collateral": [],
        "market_signals": market_signals,
        "existing_exposure": existing_exposure,
        "conduct": [],
        "covenants": [],
        "exchange_filing": None,
        "web_crawl_news": [],
        "data_provider": _PROBE_PROVIDER,
        "probe_bundle": bundle,
        "probe_summary": summary,
        "external_data": external_data,
    }

    try:
        from src.services.web_crawl_service import crawl_company_news
        news_result = crawl_company_news(company_name, sector.value, is_ntb=(ct == CaseType.NTB))
        company_data["web_crawl_news"] = news_result.get("articles", [])
    except Exception:
        pass

    store_probe_bundle_documents(entity_id, bundle)
    documents_stored = doc_store.list_company_documents(entity_id)
    source_summary = {key: entry.get("status", "unknown") for key, entry in (bundle.get("tool_results") or {}).items()}
    # Surface partial failures clearly
    error_tools = [key for key, status in source_summary.items() if status in ("error", "not_found")]
    overall_status = "success" if not error_tools else "partial"
    return {
        "status": overall_status,
        "provider": _PROBE_PROVIDER,
        "profile": bundle.get("profile"),
        "cache": bundle.get("cache", {}),
        "entity_id": entity_id,
        "company_name": company_name,
        "resolved": resolved,
        "probe_summary": summary,
        "company_data": company_data,
        "source_summary": source_summary,
        "missing_documents": _missing_rm_documents_for_entity(entity_id),
        "documents_stored": documents_stored,
    }
