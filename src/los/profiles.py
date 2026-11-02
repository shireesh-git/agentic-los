"""
Institution Profile Framework.

One neutral application, many institutions. Every institution-specific piece
— branding, vocabulary / labels, roles, the journey (stages, steps, routing),
optional modules (ESMS, DMD, ES chain, CMA, consortium, committees), the
due-diligence check catalogue, document checklists (by profile and product),
the delegation / approval matrix and the output templates (CAM, IP note,
committee pack, sanction letter) — lives in an *institution profile*:

    config/institution_profiles/base.yaml          the neutral skeleton
    config/institution_profiles/<id>.yaml          one institution each

A profile file lists only what differs from ``base.yaml``; the two are deep
merged. The application code reads *nothing* institution-specific on its own —
every label, limit and template section resolved here comes from the selected
profile, so a journey can be shortened, reordered or extended and a module
switched off without a separate code path.

Selection, in order:
  1. the application's own ``profile`` field (fixed at creation);
  2. the runtime-active profile (``set_active_profile`` / POST /api/los/profiles/active);
  3. the ``LOS_PROFILE`` environment variable;
  4. ``los.profile`` in config/settings.yaml;
  5. the built-in default (``client_one``).
"""

from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

# config/institution_profiles (CAM_CONFIG_DIR can relocate the whole config tree)
def _profile_dir() -> Path:
    base = (os.getenv("CAM_CONFIG_DIR", "").strip() or str(Path(__file__).resolve().parents[2] / "config"))
    return Path(base) / "institution_profiles"


DEFAULT_PROFILE = "client_one"

# The optional modules and the default workflow steps each one drives. A
# profile switches a module off (``modules: {dmd: {enabled: false}}``) and the
# journey simply loses those steps — no code path is created or removed.
MODULE_DEFAULT_STEPS = {
    "esms": ["ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend"],
    "dmd": ["ap_dmd"],
    "cma": [],
    "consortium": [],
    "committee_ip": ["ip_sanction"],
    "committee_recommendations": ["ap_recommend"],
    "committee_final": ["ap_sanction"],
}

# The decision-field catalogue: id → neutral label (the institution's wording comes from
# the profile's ``labels.decision_fields``). Mirrors workflow.DECISION_FIELD_TYPES.
DECISION_FIELDS = {
    "significant_changes": "Significant changes since the last review and material disclosures",
    "material_information_date": "Date of receipt of last material information",
    "committee_matters": "Matters to be highlighted to the committee",
    "confirmation_ratification": "Proposal for confirmation / ratification",
    "approval_purpose": "Purpose to seek approval",
    "minutes": "Minutes",
    "ceac_recommendation": "Committee recommendation",
    "recommended_committee": "Recommended committee",
    "esms_recommendation": "Environmental & social recommendation",
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}      # profile id → (dir mtime, merged profile)
_runtime_active: Optional[str] = None


class ProfileError(ValueError):
    """An institution profile that does not validate."""


# ── loading & merging ─────────────────────────────────────────────────────────

def _deep_merge(base: Any, override: Any) -> Any:
    """Deep merge: dicts merge recursively; lists and scalars are replaced."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(override) if override is not None else copy.deepcopy(base)


def _read(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def list_profiles() -> list[dict]:
    """Every available profile with its declared metadata."""
    out = []
    for p in sorted(_profile_dir().glob("*.yaml")):
        prof = load_profile(p.stem)
        meta = (prof.get("profile") or {})
        out.append({"id": p.stem, "name": meta.get("name") or p.stem,
                    "short_name": (prof.get("branding") or {}).get("short_name") or "",
                    "kind": meta.get("kind") or "",
                    "description": meta.get("description") or "",
                    "default": p.stem == default_profile_id(),
                    "active": p.stem == active_profile_id()})
    return out


def default_profile_id() -> str:
    return (os.getenv("LOS_DEFAULT_PROFILE", "").strip()
            or (config_profile_id() or DEFAULT_PROFILE))


def config_profile_id() -> Optional[str]:
    from src.core.config_manager import config
    return str(config.get("settings", "los", "profile", default=None) or "").strip() or None


def active_profile_id() -> str:
    """The profile used for new work: runtime override, env var, settings, default."""
    return _runtime_active or (os.getenv("LOS_PROFILE", "").strip()) \
        or config_profile_id() or DEFAULT_PROFILE


def set_active_profile(profile_id: str) -> str:
    """Switch the runtime-active profile (validates first). New applications and the
    workflow use it immediately; existing applications keep the profile they were created in."""
    global _runtime_active
    load_profile(profile_id)          # validates; raises ProfileError if unknown / invalid
    with _lock:                        # do not hold the lock across the validation (load re-enters it)
        _runtime_active = profile_id
    return profile_id


def load_profile(profile_id: str) -> dict:
    """The merged + validated profile (base overlaid with the institution file)."""
    if not profile_id or profile_id == "base":
        merged = _read(_profile_dir() / "base.yaml")
        _validate(profile_id or "base", merged)
        return merged
    d = _profile_dir()
    path = d / f"{profile_id}.yaml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in d.glob("*.yaml"))) or "none"
        raise ProfileError(f"Unknown institution profile '{profile_id}'. Available: {known}")
    mtimes = [f.stat().st_mtime for f in d.glob("*.yaml")]
    with _lock:
        hit = _cache.get(profile_id)
        if hit and mtimes and hit[0] >= max(mtimes):
            return hit[1]
    merged = _deep_merge(_read(d / "base.yaml"), _read(path))
    _validate(profile_id, merged)
    with _lock:
        _cache[profile_id] = (max(mtimes), merged)
    return merged


def get_profile(profile_id: Optional[str] = None, app: Optional[dict] = None) -> dict:
    """Resolve a profile: an explicit id, else the application's, else the active one."""
    return load_profile(profile_id or (app or {}).get("profile") or active_profile_id())


def profile_for_new(profile_id: Optional[str] = None) -> dict:
    """Resolve the profile a NEW application will run under, with controlled errors.

    An unknown id returns 404 (NotFoundError) and the internal ``base`` skeleton returns
    400 (InvalidRequestError); both name the invalid id and the selectable profiles, and
    never expose a traceback or filesystem path. Call this before anything is written.
    """
    from src.application.errors import InvalidRequestError, NotFoundError
    pid = (profile_id or "").strip() or None
    selectable = [p["id"] for p in list_profiles() if p["id"] != "base"]
    if not pid:
        return load_profile(active_profile_id())
    if pid == "base":
        raise InvalidRequestError("The 'base' profile is a configuration skeleton and cannot be used "
                                  f"for applications. Available selectable profiles: {', '.join(selectable)}")
    try:
        return load_profile(pid)
    except ProfileError:
        raise NotFoundError(f"Unknown institution profile '{pid}'. "
                            f"Available selectable profiles: {', '.join(selectable)}")


def profile_for_app(app: Optional[dict]) -> dict:
    return get_profile(app=app or {})


# ── validation ────────────────────────────────────────────────────────────────

def _validate(profile_id: str, p: dict) -> None:
    meta = p.get("profile") or {}
    if not meta.get("id") or not meta.get("name"):
        raise ProfileError(f"profile {profile_id}: profile.id and profile.name are required")
    _validate_branding(p)
    _validate_modules(p)
    _validate_workflow_overrides(p)
    _validate_checks(p)
    _validate_documents(p)
    _validate_approval(p)


def _validate_branding(p: dict) -> None:
    b = p.get("branding") or {}
    if not b.get("institution_name"):
        raise ProfileError(f"profile {p['profile']['id']}: branding.institution_name is required")


def _validate_modules(p: dict) -> None:
    for m, cfg in (p.get("modules") or {}).items():
        if m not in MODULE_DEFAULT_STEPS:
            raise ProfileError(f"profile {p['profile']['id']}: unknown module '{m}' "
                               f"(known: {', '.join(sorted(MODULE_DEFAULT_STEPS))})")
        steps = cfg.get("steps")
        if steps is not None and not isinstance(steps, list):
            raise ProfileError(f"profile {p['profile']['id']}: module {m}.steps must be a list of step ids")


def _workflow_steps_flat(wf_cfg: dict) -> list[str]:
    return [s["id"] for st in wf_cfg.get("stages") or [] for s in st.get("steps") or []]


def _validate_workflow_overrides(p: dict) -> None:
    ov = (p.get("workflow") or {})
    if ov.get("source"):
        path = Path(ov["source"])
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / "config" / ov["source"]
        if not path.exists():
            raise ProfileError(f"profile {p['profile']['id']}: workflow.source {ov['source']} does not exist")
    wf_cfg = base_workflow_config()
    known = set(_workflow_steps_flat(wf_cfg))
    for sid, s in (ov.get("steps") or {}).items():
        if sid not in known and s.get("enabled") is not False:
            raise ProfileError(f"profile {p['profile']['id']}: workflow.steps names unknown step '{sid}'")
    order = ov.get("reorder")
    if order is not None:
        if sorted(order) != sorted(s for s in known if s not in _disabled_steps(p, wf_cfg)):
            raise ProfileError(f"profile {p['profile']['id']}: workflow.reorder must list exactly the enabled steps")


def _disabled_steps(p: dict, wf_cfg: dict) -> set[str]:
    """Step ids a profile switches off: module steps of disabled modules + explicit step disables."""
    out: set[str] = set()
    steps_by_id = {s["id"]: s for st in wf_cfg.get("stages") or [] for s in st.get("steps") or []}
    for m, cfg in (p.get("modules") or {}).items():
        if cfg.get("enabled") is False:
            for sid in cfg.get("steps") or MODULE_DEFAULT_STEPS.get(m, []):
                out.add(sid)
    for sid, s in ((p.get("workflow") or {}).get("steps") or {}).items():
        if s.get("enabled") is False:
            out.add(sid)
    # steps already off in the source workflow count as disabled for reorder checks
    for sid, s in steps_by_id.items():
        if s.get("enabled") is False:
            out.add(sid)
    return out


def _validate_checks(p: dict) -> None:
    from src.los import verification
    known = {c["id"] for c in verification.CHECKS}
    chk = p.get("checks") or {}
    for key in ("applicable", "mandatory", "optional"):
        vals = chk.get(key)
        if vals in (None, "all"):
            continue
        unknown = [i for i in vals if i not in known]
        if unknown:
            raise ProfileError(f"profile {p['profile']['id']}: checks.{key} names unknown check(s) {', '.join(unknown)}")
    exc = chk.get("exception_authority") or {}
    if exc.get("role") and exc["role"] not in base_workflow_config().get("roles", {}):
        raise ProfileError(f"profile {p['profile']['id']}: checks.exception_authority.role "
                           f"'{exc['role']}' is not a role in the workflow configuration")


def _validate_documents(p: dict) -> None:
    docs = p.get("documents") or {}
    stages = {st["id"] for st in base_workflow_config().get("stages") or []}
    for stage, block in (docs.get("by_stage") or {}).items():
        if stage not in stages:
            raise ProfileError(f"profile {p['profile']['id']}: documents.by_stage names unknown stage '{stage}'")
    for _product, stages_ in (docs.get("by_product") or {}).items():
        for stage in stages_:
            if stage not in stages:
                raise ProfileError(f"profile {p['profile']['id']}: documents.by_product names unknown stage '{stage}'")
    for items, allow_string in _doc_item_lists(docs):
        for it in items:
            if allow_string and isinstance(it, str):
                continue
            if not (isinstance(it, dict) and it.get("name") and it.get("scope") in ("application", "entity", "facility", "project")):
                raise ProfileError(f"profile {p['profile']['id']}: every document needs a name and a scope "
                                   f"(application | entity | facility | project); got {it!r}")


def _doc_item_lists(docs: dict) -> list[list]:
    """(items, allow_string) pairs: set/add entries are {name, scope}; remove entries are names."""
    out = []
    for block in (docs.get("by_stage") or {}).values():
        out += [(block.get("set") or [], False), (block.get("add") or [], False), (block.get("remove") or [], True)]
    for stages_ in (docs.get("by_product") or {}).values():
        for block in stages_.values():
            out += [(block.get("set") or [], False), (block.get("add") or [], False), (block.get("remove") or [], True)]
    return out


def _validate_approval(p: dict) -> None:
    appr = p.get("approval") or {}
    for key in ("preliminary", "final"):
        rows = appr.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list) or not rows:
            raise ProfileError(f"profile {p['profile']['id']}: approval.{key} must be a non-empty list")
        prev_cap = 0.0
        for r in rows:
            cap = r.get("max_amount")
            if cap is not None:
                if cap <= 0:
                    raise ProfileError(f"profile {p['profile']['id']}: approval.{key} max_amount must be > 0 or null")
                if cap <= prev_cap:
                    raise ProfileError(f"profile {p['profile']['id']}: approval.{key} must be ordered from "
                                       "lowest to highest authority")
                prev_cap = cap
            if not r.get("authority"):
                raise ProfileError(f"profile {p['profile']['id']}: approval.{key} rows need an authority name")
    for _product, rows in (appr.get("by_product") or {}).items():
        for r in rows or []:
            if not r.get("authority"):
                raise ProfileError(f"profile {p['profile']['id']}: approval.by_product rows need an authority name")


# ── branding & labels ─────────────────────────────────────────────────────────

def branding(p: Optional[dict] = None) -> dict:
    p = p or get_profile()
    return dict(p.get("branding") or {})


def labels(p: Optional[dict] = None) -> dict:
    p = p or get_profile()
    return copy.deepcopy(p.get("labels") or {})


def decision_field_labels(p: Optional[dict] = None) -> dict:
    """The profile's wording for every decision field (neutral defaults from the catalogue)."""
    out = dict(DECISION_FIELDS)
    out.update(((p or get_profile()).get("labels") or {}).get("decision_fields") or {})
    return out


def role_labels(p: Optional[dict] = None) -> dict:
    return ((p or get_profile()).get("labels") or {}).get("roles") or {}


# ── the journey (workflow) ────────────────────────────────────────────────────

def base_workflow_config() -> dict:
    """The base journey configuration (config/los_workflow.yaml)."""
    from src.core.config_manager import config
    config.reload()
    return config.get("los_workflow", default={}) or {}


def workflow_config(profile_id: Optional[str] = None) -> dict:
    """The institution's journey: the base workflow with the profile's stage / step
    overrides, disabled module steps and optional reorder applied."""
    p = get_profile(profile_id)
    ov = p.get("workflow") or {}
    if ov.get("source"):
        path = Path(ov["source"])
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / "config" / ov["source"]
        cfg = _read(path)
    else:
        from src.core.config_manager import config
        config.reload()
        cfg = copy.deepcopy(config.get("los_workflow", default={}) or {})
    pid = p["profile"]["id"]

    # stage name / description overrides and deletions (workflow.stages, then the profile's display labels)
    stage_ov = ov.get("stages") or {}
    label_stages = ((p.get("labels") or {}).get("stages") or {})
    delete = set(stage_ov.get("delete") or [])
    stages = []
    for st in cfg.get("stages") or []:
        if st["id"] in delete:
            continue
        st = copy.deepcopy(st)
        ov_st = stage_ov.get(st["id"]) or {}
        for k in ("name", "description"):
            if ov_st.get(k):
                st[k] = ov_st[k]
        if label_stages.get(st["id"]):                    # the profile's vocabulary for the stage
            st["name"] = label_stages[st["id"]]
        stages.append(st)
    cfg["stages"] = stages

    # per-step overrides (name, role, sla_days, actions, labels, decision_fields, enabled, …)
    step_ov = ov.get("steps") or {}
    label_steps = ((p.get("labels") or {}).get("steps") or {})
    for st in cfg["stages"]:
        for i, s in enumerate(st.get("steps") or []):
            merged = dict(s)
            o = step_ov.get(s.get("id"))
            if o:
                for k, v in o.items():
                    merged[k] = v
            if label_steps.get(merged.get("id")):          # the profile's vocabulary for the step
                merged["name"] = label_steps[merged["id"]]
            st["steps"][i] = merged

    # optional modules: a disabled module removes its steps from the journey
    disabled = _profile_disabled_steps(p)
    for st in cfg["stages"]:
        st["steps"] = [s for s in st.get("steps") or [] if s.get("id") not in disabled]
    cfg["stages"] = [st for st in cfg["stages"] if st.get("steps")]

    # optional explicit reorder (stages keep their order; steps follow the given order)
    order = ov.get("reorder")
    if order is not None:
        by_id = {s["id"]: (st, s) for st in cfg["stages"] for s in st.get("steps") or []}
        flat = []
        for sid in order:
            if sid not in by_id:
                raise ProfileError(f"profile {pid}: workflow.reorder lists step '{sid}' which is not enabled")
            flat.append(by_id[sid][1])
        # regroup the ordered flat list under the original stages (first appearance keeps stage order)
        stage_of = {sid: by_id[sid][0] for sid in order}
        for st in cfg["stages"]:
            st["steps"] = [s for s in flat if stage_of.get(s["id"]) is st]

    # role display names from the profile's labels
    roles = dict(cfg.get("roles") or {})
    roles.update(((p.get("labels") or {}).get("roles") or {}))
    cfg["roles"] = roles
    return cfg


def _profile_disabled_steps(p: dict) -> set[str]:
    out: set[str] = set()
    for m, cfg in (p.get("modules") or {}).items():
        if cfg.get("enabled") is False:
            out.update(cfg.get("steps") or MODULE_DEFAULT_STEPS.get(m, []))
    for sid, s in ((p.get("workflow") or {}).get("steps") or {}).items():
        if s.get("enabled") is False:
            out.add(sid)
    return out


def module_enabled(p: Optional[dict], module: str) -> bool:
    p = p or get_profile()
    cfg = (p.get("modules") or {}).get(module) or {}
    return cfg.get("enabled", True) is not False


def modules(p: Optional[dict] = None) -> dict:
    """The resolved module map with the effective step lists."""
    p = p or get_profile()
    out = {}
    for m, steps in MODULE_DEFAULT_STEPS.items():
        cfg = (p.get("modules") or {}).get(m) or {}
        out[m] = {"enabled": cfg.get("enabled", True) is not False,
                  "steps": cfg.get("steps", steps),
                  "description": cfg.get("description", "")}
    return out


# ── due-diligence check catalogue ─────────────────────────────────────────────

def check_catalog(p: Optional[dict] = None) -> list[dict]:
    """The profile's check list: the base catalogue filtered to the applicable checks,
    with the profile's mandatory flags and exception authority."""
    from src.los import verification
    p = p or get_profile()
    chk = p.get("checks") or {}
    applicable = chk.get("applicable", "all")
    if applicable != "all":
        keep = list(applicable)                      # the profile's order is the display order
        unknown = [i for i in keep if i not in {c["id"] for c in verification.CHECKS}]
        if unknown:
            raise ProfileError(f"profile {p['profile']['id']}: unknown check(s) {', '.join(unknown)}")
        cat = [c for c in verification.CHECKS if c["id"] in set(keep)]
        cat.sort(key=lambda c: keep.index(c["id"]))
    else:
        cat = list(verification.CHECKS)
    mandatory = chk.get("mandatory")
    optional = set(chk.get("optional") or [])
    names = chk.get("names") or {}
    out = []
    for c in cat:
        c2 = dict(c)
        if mandatory is not None:
            c2["mandatory"] = c2["id"] in set(mandatory)
        if c2["id"] in optional and mandatory is not None:
            c2["mandatory"] = False
        if names.get(c2["id"]):
            c2["name"] = names[c2["id"]]
        out.append(c2)
    return out


def exception_authority(p: Optional[dict] = None) -> dict:
    """Who may release a blocked check (profile: role + display name)."""
    p = p or get_profile()
    exc = (p.get("checks") or {}).get("exception_authority") or {}
    roles = base_workflow_config().get("roles") or {}
    role = exc.get("role") or "compliance_vp"
    return {"role": role, "name": exc.get("name") or roles.get(role, "Compliance VP")}


def esms_policy(p: Optional[dict] = None) -> dict:
    """R5: the institution's E&S exception path (profile ``esms`` block). ``exceptions_enabled``
    is off by default — the base behaviour is the hard block on an excluded activity."""
    p = p or get_profile()
    es = p.get("esms") or {}
    exc = es.get("exception_authority") or {}
    roles = base_workflow_config().get("roles") or {}
    role = exc.get("role") or "crp_vp"
    return {"exceptions_enabled": bool(es.get("exceptions_enabled") is True),
            "exception_authority": {"role": role, "name": exc.get("name") or roles.get(role, "CRP VP")},
            "exception_ttl_days": int(es.get("exception_ttl_days") or 180)}


def check_policy(p: Optional[dict] = None) -> dict:
    p = p or get_profile()
    chk = p.get("checks") or {}
    return {"rescreen_days": int(chk.get("rescreen_days", 90)),
            "exception_ttl_days": int(chk.get("exception_ttl_days", 90)),
            "unavailable_policy": chk.get("unavailable_policy", "vp_approval")}


# ── document checklists ───────────────────────────────────────────────────────

def document_checklist(p: Optional[dict] = None) -> dict:
    """Mandatory documents per stage as {stage: [ {name, scope, condition?, type_id}, … ]}.
    ``condition`` is ``securities`` / ``projects`` (evaluated on the application)
    or absent (always mandatory). Requirements are deduplicated by stable
    document-type id; the profile wins the display fields over the base checklist
    (``docreg.merge_stage``)."""
    p = p or get_profile()
    from src.los import docreg
    out: dict[str, list[dict]] = {}
    for stage, items in docreg.CHECKLIST.items():
        out[stage] = [{"name": n, "scope": s, "source": "base", "priority": 0} for n, s in items]
    docs = p.get("documents") or {}
    for stage, block in (docs.get("by_stage") or {}).items():
        cur = [dict(e) for e in out.get(stage, [])]
        if block.get("set") is not None:                    # set replaces the stage's list…
            cur = copy.deepcopy(block["set"])
        removed = {i if isinstance(i, str) else i.get("name") for i in block.get("remove") or []}
        cur = [e for e in cur if e["name"] not in removed]  # …remove / add still apply over it
        cur += copy.deepcopy(block.get("add") or [])
        for e in cur:                                       # entries coming from the profile block
            e.setdefault("source", "profile")
            e.setdefault("priority", 1)
        out[stage] = docreg.merge_stage(cur)
    return {st: docreg.merge_stage(items) for st, items in out.items()}


def product_checklist(p: Optional[dict] = None, product: Optional[str] = None) -> dict:
    """The checklist with the product's extra / removed documents applied (additive over by_stage)."""
    p = p or get_profile()
    from src.los import docreg
    base = document_checklist(p)
    block = ((p.get("documents") or {}).get("by_product") or {}).get(product or "")
    if not block:
        return {st: [dict(e) for e in items] for st, items in base.items()}
    out = {st: [dict(e) for e in items] for st, items in base.items()}
    for stage, stage_block in block.items():
        cur = out.get(stage, [])
        if stage_block.get("set") is not None:
            cur = copy.deepcopy(stage_block["set"])
        removed = {i if isinstance(i, str) else i.get("name") for i in stage_block.get("remove") or []}
        cur = [e for e in cur if e["name"] not in removed]
        cur += copy.deepcopy(stage_block.get("add") or [])
        for e in cur:
            e.setdefault("source", "profile")
            e.setdefault("priority", 1)
        out[stage] = docreg.merge_stage(cur)
    return out


def primary_product(app: Optional[dict]) -> Optional[str]:
    """The application's product for checklist / authority routing: its first facility type."""
    facs = (app or {}).get("facilities") or []
    if facs:
        return facs[0].get("facility_type")
    return ((app or {}).get("facility") or {}).get("facility_type")


def products(app: Optional[dict]) -> list[str]:
    seen = []
    for f in (app or {}).get("facilities") or [ (app or {}).get("facility") or {} ]:
        t = (f or {}).get("facility_type")
        if t and t not in seen:
            seen.append(t)
    return seen


def required_documents(app: dict, p: Optional[dict] = None) -> list[str]:
    """The names mandatory now for this application's stage + product (conditions evaluated)."""
    p = p or get_profile(app=app)
    stage = (app.get("stage_id") or "PS").upper()
    out = []
    for product in (products(app) or [None]):
        for e in product_checklist(p, product).get(stage, []):
            name = e["name"]
            conds = e.get("condition") or e.get("conditions") or []
            if isinstance(conds, str):
                conds = [conds]
            # a unioned condition applies when ANY of its sources applies (never weaker)
            if conds and not any((c == "securities" and bool(app.get("securities")))
                                 or (c == "projects" and bool(app.get("projects")))
                                 or c not in ("securities", "projects") for c in conds):
                continue
            if name not in out:
                out.append(name)
    return out


# ── delegation & approval matrix ──────────────────────────────────────────────

def approval_matrix(p: Optional[dict] = None, product: Optional[str] = None, final: bool = False) -> dict:
    """(cap, authority) rows + flags from the profile; the product's own routing wins when it has one."""
    p = p or get_profile()
    appr = p.get("approval") or {}
    table_key = "final" if final else "preliminary"
    rows = None
    if product:
        rows = (appr.get("by_product") or {}).get(product)
    if not rows:
        rows = appr.get(table_key)
    if not rows:
        raise ProfileError(f"profile {p['profile']['id']}: approval.{table_key} (or by_product."
                           f"{product}) is not configured")
    table = [(float("inf") if r.get("max_amount") is None else float(r["max_amount"]), r["authority"])
             for r in rows]
    return {"table": table,
            "sub_investment_grade_concurrence": bool(appr.get("sub_investment_grade_concurrence", True)),
            "deviation_escalation_levels": int(appr.get("deviation_escalation_levels", 1)),
            "currency": appr.get("currency", "₹ Cr"),
            "profile": p["profile"]["id"]}


def approval(p: Optional[dict] = None) -> dict:
    p = p or get_profile()
    return copy.deepcopy(p.get("approval") or {})


# ── output templates ──────────────────────────────────────────────────────────

def output_template(kind: str, p: Optional[dict] = None) -> dict:
    """The template configuration for one output kind: cam | ip_note | committee_pack |
    sanction_letter | term_sheet. Unknown kinds get the empty (default) template.

    Precedence (documented): the neutral base template < the institution-profile template
    < the product template. A product overrides only the fields it explicitly provides
    (``products.output_template`` overlays field-by-field), so institution branding is
    never lost by a product overlay."""
    p = p or get_profile()
    return copy.deepcopy(((p.get("outputs") or {}).get(kind)) or {})


CANONICAL_SECTIONS = {
    "ip_note": ["borrower", "proposal", "exposure", "financials", "security", "prescreen"],
    "sanction_letter": ["terms", "security", "conditions_precedent", "conditions_subsequent", "covenants", "deviations"],
    "term_sheet": ["terms", "security", "conditions_precedent", "conditions_subsequent", "covenants"],
    "committee_pack": ["headline", "decision_trail", "risks", "due_diligence", "deviations", "overrides", "comments", "brief"],
}

DEFAULT_SECTION_HEADINGS = {
    "ip_note": {"borrower": "Borrower", "proposal": "Proposal",
                "exposure": "Existing exposure with the bank", "financials": "Financial snapshot",
                "security": "Security", "prescreen": "Policy pre-screen"},
    "sanction_letter": {"terms": "Key terms", "security": "Security",
                        "conditions_precedent": "Conditions precedent (before first disbursement)",
                        "conditions_subsequent": "Conditions subsequent", "covenants": "Covenants",
                        "deviations": "Deviations approved with this sanction"},
    "term_sheet": {"terms": "Key terms", "security": "Security",
                   "conditions_precedent": "Conditions precedent (before first disbursement)",
                   "conditions_subsequent": "Conditions subsequent", "covenants": "Covenants"},
    "committee_pack": {"headline": "Headline", "decision_trail": "Decision trail", "risks": "Key risks",
                       "due_diligence": "Due diligence", "deviations": "Deviations", "overrides": "Overrides",
                       "comments": "Comments", "brief": "Brief"},
}


def section_plan(kind: str, tpl: Optional[dict] = None, p: Optional[dict] = None) -> list[dict]:
    """The output's section list, order and headings from the template configuration.

    ``sections: all`` (or absent) keeps every canonical section in canonical order; an
    explicit list orders the listed sections first (unknown ids are ignored, omitted
    canonical sections follow in canonical order — nothing is ever removed silently).
    ``headings`` maps a section id to a custom heading; defaults are the institution-
    neutral headings above."""
    p = p or get_profile()
    tpl = tpl if tpl is not None else output_template(kind, p)
    canonical = CANONICAL_SECTIONS.get(kind, [])
    defaults = DEFAULT_SECTION_HEADINGS.get(kind, {})
    headings = tpl.get("headings") or {}
    sel = tpl.get("sections", "all")
    ids = list(sel) if isinstance(sel, list) else list(canonical)
    ordered = [i for i in ids if i in canonical]
    ordered += [i for i in canonical if i not in ordered]
    return [{"id": i, "heading": headings.get(i) or defaults.get(i) or i.replace("_", " ").title()}
            for i in ordered]


def institution_branding(p: Optional[dict] = None) -> dict:
    """The institution's letterhead data for generated outputs (CAM, IP Note, committee
    pack, letters) — with neutral base values wherever the profile omits a field."""
    p = p or get_profile()
    b = branding(p)
    colors = b.get("colors") or {}
    return {"institution_name": b.get("institution_name") or "Institution",
            "short_name": b.get("short_name") or "",
            "app_name": b.get("app_name") or "Credit LOS",
            "logo": b.get("logo"),
            "colors": {k: colors[k] for k in ("primary", "accent") if colors.get(k)},
            "paper_header": (b.get("paper") or {}).get("header") or "",
            "demo_mark": ((p.get("outputs") or {}).get("sanction_letter") or {}).get("demo_mark", ""),
            "cam_title": ((p.get("outputs") or {}).get("cam") or {}).get("title") or "Credit Appraisal Memorandum"}


def letter_branding(p: Optional[dict] = None) -> dict:
    """What the generated letters / papers print under the profile's name."""
    p = p or get_profile()
    b = branding(p)
    tpl = output_template("sanction_letter", p)
    return {"institution_name": b.get("institution_name", "Institution"),
            "short_name": b.get("short_name", ""),
            "paper_header": (b.get("paper") or {}).get("header", ""),
            "bank_term": ((p.get("labels") or {}).get("terms") or {}).get("bank", "the institution"),
            "demo_mark": tpl.get("demo_mark", ""),
            "kind_titles": tpl.get("kind_titles") or {"term_sheet": "Term sheet (indicative)",
                                                      "sanction_letter": "Sanction letter"},
            "acceptance_days": int(tpl.get("acceptance_days", 30))}


# ── views for the API / UI ────────────────────────────────────────────────────

def profile_summary(profile_id: str, full: bool = False) -> dict:
    p = load_profile(profile_id)
    out = {
        "id": p["profile"]["id"],
        "name": p["profile"]["name"],
        "description": p["profile"].get("description") or "",
        "branding": branding(p),
        "modules": modules(p),
        "checks": {"count": len(check_catalog(p)),
                   "mandatory": [c["id"] for c in check_catalog(p) if c["mandatory"]],
                   "exception_authority": exception_authority(p),
                   "policy": check_policy(p)},
        "documents": {st: [e["name"] for e in items] for st, items in document_checklist(p).items()},
        "approval": {
            "currency": (p.get("approval") or {}).get("currency", "₹ Cr"),
            "preliminary": [r for r in (p.get("approval") or {}).get("preliminary", [])],
            "final": [r for r in (p.get("approval") or {}).get("final", [])],
            "deviation_escalation_levels": (p.get("approval") or {}).get("deviation_escalation_levels", 1),
        },
        "outputs": {k: v for k, v in (p.get("outputs") or {}).items()},
    }
    if full:
        out["workflow"] = workflow_config(p["profile"]["id"])
        out["check_catalog"] = check_catalog(p)
        out["decision_field_labels"] = decision_field_labels(p)
    return out


def profiles_view() -> dict:
    return {"active": active_profile_id(), "default": default_profile_id(),
            "profiles": list_profiles()}
