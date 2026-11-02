"""
Reusable product templates.

A product template (config/product_templates/<id>.yaml) is configuration, not code: it
describes one credit product — facility types, amount / tenor / moratorium rules, pricing
benchmarks, repayment methods, security expectations, financial-analysis requirements, the
due-diligence checks it adds, mandatory documents by stage, the workflow stages / modules it
needs, its delegation-matrix overrides and its output-template overrides. Adding a product
is a new file (or a profile entry) — no new application code path.

Compatibility is two-sided and checked at load time: the product lists the institution
profiles it applies to (``profiles: all`` or ids) and the institution profile lists the
products it runs (``products: [ids]``; unset = every product is available).

Resolution is per application: the product and institution profile stored against the
application (``app["product"]`` / ``app["profile"]``) decide its checks, documents,
authority and output templates. Switching the runtime-active profile never changes them.
"""

from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Optional

import yaml

from src.application.errors import InvalidRequestError


def _product_dir() -> Path:
    base = (os.getenv("CAM_CONFIG_DIR", "").strip()
            or str(Path(__file__).resolve().parents[2] / "config"))
    return Path(base) / "product_templates"


_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


class ProductError(ValueError):
    """A product template that does not validate."""


# ── loading ───────────────────────────────────────────────────────────────────

def _read(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def list_product_ids() -> list[str]:
    return sorted(p.stem for p in _product_dir().glob("*.yaml"))


def get_product(product_id: str) -> dict:
    """Load + validate one product template (cached with hot reload)."""
    if not product_id:
        raise ProductError("A product id is required")
    path = _product_dir() / f"{product_id}.yaml"
    if not path.exists():
        known = ", ".join(list_product_ids()) or "none"
        raise ProductError(f"Unknown product template '{product_id}'. Available: {known}")
    mtime = max((f.stat().st_mtime for f in _product_dir().glob("*.yaml")), default=0.0)
    with _lock:
        hit = _cache.get(product_id)
        if hit and hit[0] >= mtime:
            return hit[1]
    p = _read(path)
    _validate(product_id, p)
    with _lock:
        _cache[product_id] = (mtime, p)
    return p


def _validate(product_id: str, p: dict) -> None:
    meta = p.get("product") or {}
    pid = str(meta.get("id") or "")
    if pid != product_id:
        raise ProductError(f"product template file {product_id}.yaml declares id '{pid}'")
    if not meta.get("name") or not meta.get("category"):
        raise ProductError(f"product {pid}: product.name and product.category are required")
    from src.los.facilities import FACILITY_TYPES, REPAYMENT_TYPES
    ftypes = meta.get("facility_types") or []
    if not ftypes:
        raise ProductError(f"product {pid}: facility_types must list at least one facility type")
    unknown = [t for t in ftypes if t not in FACILITY_TYPES]
    if unknown:
        raise ProductError(f"product {pid}: unknown facility type(s) {', '.join(unknown)} "
                           f"(known: {', '.join(FACILITY_TYPES)})")
    repay = meta.get("repayment") or []
    unknown_r = [r for r in repay if r not in REPAYMENT_TYPES]
    if unknown_r:
        raise ProductError(f"product {pid}: unknown repayment method(s) {', '.join(unknown_r)}")
    amt = meta.get("amount") or {}
    lo, hi = amt.get("min_cr"), amt.get("max_cr")
    if lo is not None and (lo <= 0):
        raise ProductError(f"product {pid}: amount.min_cr must be > 0 or null")
    if hi is not None and (lo is not None and hi < lo):
        raise ProductError(f"product {pid}: amount.max_cr must be >= amount.min_cr")
    tenor = meta.get("tenor") or {}
    if tenor.get("min_months") is not None and tenor.get("max_months") is not None \
            and tenor["max_months"] < tenor["min_months"]:
        raise ProductError(f"product {pid}: tenor.max_months must be >= tenor.min_months")
    chk = meta.get("checks") or {}
    from src.los import verification
    known = {c["id"] for c in verification.CHECKS}
    for key in ("applicable", "mandatory"):
        bad = [i for i in (chk.get(key) or []) if i not in known]
        if bad:
            raise ProductError(f"product {pid}: checks.{key} names unknown check(s) {', '.join(bad)}")
    docs = meta.get("documents") or {}
    stages = {st["id"] for st in base_stages()}
    for stage, block in (docs.get("by_stage") or {}).items():
        if stage not in stages:
            raise ProductError(f"product {pid}: documents.by_stage names unknown stage '{stage}'")
        for it in (block.get("set") or []) + (block.get("add") or []):
            if not (isinstance(it, dict) and it.get("name")
                    and it.get("scope") in ("application", "entity", "facility", "project")):
                raise ProductError(f"product {pid}: every document needs a name and a scope; got {it!r}")
        for it in block.get("remove") or []:
            if not (isinstance(it, str) or (isinstance(it, dict) and it.get("name"))):
                raise ProductError(f"product {pid}: documents remove entries must be names; got {it!r}")
    appr = meta.get("approval") or {}
    for key in ("preliminary", "final"):
        for r in appr.get(key) or []:
            if not r.get("authority") or (r.get("max_amount") is not None and r["max_amount"] <= 0):
                raise ProductError(f"product {pid}: approval.{key} rows need max_amount (>0 or null) and an authority")
    profs = meta.get("profiles")
    if profs not in (None, "all") and not isinstance(profs, list):
        raise ProductError(f"product {pid}: product.profiles must be 'all' or a list of profile ids")


def base_stages() -> list[dict]:
    from src.core.config_manager import config
    config.reload()
    return (config.get("los_workflow", default={}) or {}).get("stages") or []


# ── availability & resolution ─────────────────────────────────────────────────

def profile_products(profile: Optional[dict]) -> list[str]:
    """The product ids the institution profile runs (unset = all products)."""
    prof = profile or {}
    ids = prof.get("products")
    return list(ids) if ids else list_product_ids()


def is_compatible(product: dict, profile: dict) -> bool:
    """Two-sided compatibility: the product applies to the profile and the profile runs it."""
    pid = product["product"]["id"]
    if pid not in profile_products(profile):
        return False
    profs = product["product"].get("profiles")
    if profs in (None, "all"):
        return True
    return profile["profile"]["id"] in profs


def list_products(profile_id: Optional[str] = None) -> list[dict]:
    from src.los import profiles
    prof = profiles.get_profile(profile_id)
    out = []
    for pid in list_product_ids():
        p = get_product(pid)
        out.append({"id": pid, "name": p["product"]["name"], "category": p["product"]["category"],
                    "description": p["product"].get("description") or "",
                    "facility_types": p["product"].get("facility_types") or [],
                    "available": is_compatible(p, prof)})
    return out


def resolve_product(product_id: str, profile: Optional[dict] = None,
                    facility_type: Optional[str] = None) -> dict:
    """The product's resolved configuration against an institution profile (what the API returns)."""
    from src.los import profiles
    p = get_product(product_id)
    prof = profile or profiles.get_profile()
    pid = p["product"]["id"]
    if not is_compatible(p, prof):
        raise InvalidRequestError(f"Product '{p['product']['name']}' is not available under the institution "
                                  f"profile '{prof['profile']['name']}'")
    fac_type = facility_type or (p["product"].get("facility_types") or [None])[0]
    appr_prelim = _json_safe_table(approval_matrix(prof, p, fac_type, final=False)["table"])
    appr_final = _json_safe_table(approval_matrix(prof, p, fac_type, final=True)["table"])
    return {
        "id": pid,
        "name": p["product"]["name"],
        "category": p["product"]["category"],
        "description": p["product"].get("description") or "",
        "profile": {"id": prof["profile"]["id"], "name": prof["profile"]["name"]},
        "facility_types": p["product"].get("facility_types") or [],
        "facility_defaults": p["product"].get("facility_defaults") or {},
        "borrower_fields": p["product"].get("borrower_fields") or [],
        "facility_fields": p["product"].get("facility_fields") or [],
        "amount": p["product"].get("amount") or {},
        "tenor": p["product"].get("tenor") or {},
        "moratorium": p["product"].get("moratorium") or {},
        "pricing": p["product"].get("pricing") or {},
        "repayment": p["product"].get("repayment") or [],
        "security": p["product"].get("security") or {},
        "financial_analysis": p["product"].get("financial_analysis") or {},
        "checks": effective_checks(prof, p),
        "documents": {st: [e["name"] for e in items]
                      for st, items in effective_documents(prof, p, [fac_type]).items()},
        "workflow": {
            "stages": (p["product"].get("workflow") or {}).get("stages") or
                      [st["id"] for st in base_stages()],
            "modules": _effective_modules(prof, p),
        },
        "approval": {
            "currency": ((prof.get("approval") or {}).get("currency", "₹ Cr")),
            "preliminary": appr_prelim,
            "final": appr_final,
        },
        "outputs": {k: v for k, v in (p["product"].get("outputs") or {}).items()},
        "validations": p["product"].get("validations") or [],
    }


def _json_safe_table(table: list) -> list:
    """The delegation bands with the open-ended cap rendered as 'unlimited' for API consumers."""
    return [["unlimited" if m == float("inf") else m, a] for m, a in table]


def _effective_modules(profile: dict, product: dict) -> dict:
    """The modules this product runs under this profile: the profile's switches, with the
    product's requirements winning (a product can demand a module the profile left at default)."""
    from src.los import profiles
    base = profiles.modules(profile)
    override = (product["product"].get("workflow") or {}).get("modules") or {}
    for m, want in override.items():
        if want is True and not base.get(m, {}).get("enabled"):
            # the product needs the module: keep it flagged so the UI / gates can explain the conflict
            base[m] = {**base.get(m), "enabled": True, "forced_by_product": True}
    return base


# ── per-application resolution (profile × product) ────────────────────────────

def checks(profile: dict, product_id: Optional[str]) -> list[dict]:
    """The application's check list: the profile's catalogue with the product's checks applied."""
    from src.los import profiles
    cat = profiles.check_catalog(profile)
    if not product_id:
        return cat
    try:
        p = get_product(product_id)
    except ProductError:
        return cat
    chk = p["product"].get("checks") or {}
    applicable = chk.get("applicable") or []
    mandatory = set(chk.get("mandatory") or [])
    by_id = {c["id"]: c for c in cat}
    out = list(cat)
    for cid in applicable:
        if cid in by_id:
            continue
        base = next((c for c in verification_catalog() if c["id"] == cid), None)
        if base:
            c2 = dict(base)
            c2["mandatory"] = cid in mandatory
            out.append(c2)
    if mandatory:
        for c in out:
            if c["id"] in mandatory:
                c["mandatory"] = True
    return out


def verification_catalog() -> list[dict]:
    from src.los import verification
    return verification.CHECKS


def documents(profile: dict, product_id: Optional[str], facility_types: Optional[list[str]] = None) -> dict:
    """The application's document checklist: the profile's (per product type) with the
    product template's per-stage documents applied (set / add / remove), deduplicated
    by stable document-type id (product template > profile > base for display fields;
    a requirement is never dropped — see ``docreg.merge_stage``)."""
    from src.los import docreg, profiles
    ft = (facility_types or [None])[0]
    base = {st: [dict(e) for e in items] for st, items in profiles.product_checklist(profile, ft).items()}
    if not product_id:
        return base
    try:
        p = get_product(product_id)
    except ProductError:
        return base
    for stage, block in ((p["product"].get("documents") or {}).get("by_stage") or {}).items():
        if not block:
            continue
        cur = [dict(e) for e in base.get(stage, [])]
        if block.get("set") is not None:
            cur = copy.deepcopy(block["set"])
            for e in cur:
                e.setdefault("source", "product")
                e.setdefault("priority", 2)
        removed = {i if isinstance(i, str) else i.get("name") for i in block.get("remove") or []}
        cur = [e for e in cur if e["name"] not in removed]
        added = copy.deepcopy(block.get("add") or [])
        for e in added:
            e.setdefault("source", "product")
            e.setdefault("priority", 2)
        cur += added
        base[stage] = cur
    return {st: docreg.merge_stage(items) for st, items in base.items()}


def effective_documents(profile: dict, product: dict, facility_types: Optional[list[str]] = None) -> dict:
    return documents(profile, product["product"]["id"], facility_types)


def effective_checks(profile: dict, product: dict) -> list[dict]:
    return checks(profile, product["product"]["id"])


def approval_matrix(profile: dict, product: Optional[dict], facility_type: Optional[str],
                    final: bool) -> dict:
    """The delegation rows for a case: the product's own matrix wins, then the profile's
    product route, then the profile's base matrix."""
    from src.los import profiles
    if product:
        rows = (product["product"].get("approval") or {}).get("final" if final else "preliminary") or []
        if rows:
            table = [(float("inf") if r.get("max_amount") is None else float(r["max_amount"]), r["authority"])
                     for r in rows]
            appr = profile.get("approval") or {}
            return {"table": table,
                    "sub_investment_grade_concurrence": bool(appr.get("sub_investment_grade_concurrence", True)),
                    "deviation_escalation_levels": int(appr.get("deviation_escalation_levels", 1)),
                    "currency": appr.get("currency", "₹ Cr"),
                    "profile": profile["profile"]["id"],
                    "source": f"product template '{product['product']['id']}'"}
    return profiles.approval_matrix(p=profile, product=facility_type, final=final)


def module_enabled(profile: dict, product_id: Optional[str], module: str) -> bool:
    """Whether a module runs for one application: the profile's switch, with the product's
    requirement winning (a product can demand a module, or make one unnecessary)."""
    from src.los import profiles
    enabled = profiles.module_enabled(profile, module)
    if product_id:
        try:
            p = get_product(product_id)
        except ProductError:
            return enabled
        want = (p["product"].get("workflow") or {}).get("modules", {}).get(module)
        if want is True:
            return True
        if want is False:
            return False
    return enabled


def output_template(kind: str, profile: dict, product: Optional[dict] = None) -> dict:
    """Output-template settings: the product's overrides on top of the profile's."""
    from src.los import profiles
    tpl = profiles.output_template(kind, profile)
    if product:
        ovr = (product["product"].get("outputs") or {}).get(kind) or {}
        for k, v in ovr.items():
            if isinstance(v, dict) and isinstance(tpl.get(k), dict):
                tpl[k] = {**tpl[k], **v}
            else:
                tpl[k] = v
    return tpl


# ── creation-time validation (the product's gates) ────────────────────────────

def validate_creation(product: dict, facilities: list[dict]) -> None:
    """Product-specific validations at application creation (clear gate messages)."""
    meta = product["product"]
    pid = meta["id"]
    total = 0.0
    for i, f in enumerate(facilities, 1):
        ftype = f.get("facility_type")
        if ftype not in (meta.get("facility_types") or []):
            raise InvalidRequestError(f"Facility {i}: '{str(ftype).replace('_', ' ')}' is not a "
                                      f"{meta['name']} facility (allowed: {', '.join(meta['facility_types'])})")
        if f.get("facility_nature", "fund_based") == "fund_based":
            total += float(f.get("amount_cr") or 0)
        tenor = meta.get("tenor") or {}
        tm = f.get("tenor_months")
        if tm:
            if tenor.get("min_months") is not None and tm < tenor["min_months"]:
                raise InvalidRequestError(f"Facility {i}: a {meta['name']} tenor is at least "
                                          f"{tenor['min_months']} months")
            if tenor.get("max_months") is not None and tm > tenor["max_months"]:
                raise InvalidRequestError(f"Facility {i}: a {meta['name']} tenor is at most "
                                          f"{tenor['max_months']} months")
        rep = (f.get("repayment") or {}).get("repayment_type") or f.get("repayment_type")
        if rep and (meta.get("repayment") or []) and rep not in meta["repayment"]:
            raise InvalidRequestError(f"Facility {i}: repayment method '{rep}' is not available for "
                                      f"{meta['name']} (allowed: {', '.join(meta['repayment'])})")
        mor = (f.get("repayment") or {}).get("moratorium_months") or f.get("moratorium_months")
        mmax = (meta.get("moratorium") or {}).get("max_months")
        if mor and mmax is not None and mor > mmax:
            raise InvalidRequestError(f"Facility {i}: the moratorium for {meta['name']} is at most {mmax} months")
        bench = (f.get("pricing") or {}).get("benchmark") or f.get("benchmark")
        allowed_bench = (meta.get("pricing") or {}).get("benchmarks")
        if bench and allowed_bench and bench not in allowed_bench:
            raise InvalidRequestError(f"Facility {i}: benchmark '{bench}' is not available for "
                                      f"{meta['name']} (allowed: {', '.join(allowed_bench)})")
    amt = meta.get("amount") or {}
    fund_total = total
    if fund_total:
        if amt.get("min_cr") is not None and fund_total < amt["min_cr"]:
            raise InvalidRequestError(f"{meta['name']}: the committed amount (₹{fund_total:g} Cr) is below "
                                      f"the product minimum of ₹{amt['min_cr']:g} Cr")
        if amt.get("max_cr") is not None and fund_total > amt["max_cr"]:
            raise InvalidRequestError(f"{meta['name']}: the committed amount (₹{fund_total:g} Cr) is above "
                                      f"the product maximum of ₹{amt['max_cr']:g} Cr — split the proposal or "
                                      "seek an exception under the approval matrix")
    for v in meta.get("validations") or []:
        fn = _VALIDATION_RULES.get(str(v.get("rule") or ""))
        if fn:
            msg = fn(meta, facilities)
            if msg:
                raise InvalidRequestError(f"{meta['name']}: {msg}")


_VALIDATION_RULES: dict[str, callable] = {}


def register_validation(rule: str):
    def deco(fn):
        _VALIDATION_RULES[rule] = fn
        return fn
    return deco


@register_validation("purpose_not_blank")
def _purpose_not_blank(meta: dict, facilities: list[dict]) -> Optional[str]:
    for i, f in enumerate(facilities, 1):
        if not str(f.get("purpose") or "").strip():
            return f"facility {i}: {meta.get('validations', [{}])[0].get('message', 'the purpose is required')}"
    return None
