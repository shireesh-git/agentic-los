"""Configuration version snapshots (R16).

At application creation the LOS captures the exact versions of every
configuration input the application will run against: institution profile,
product template, workflow, role labels, the due-diligence check catalogue,
the document checklists, the approval matrix, the output templates and the
policy rules. Each domain's version is the SHA-256 of its resolved (merged,
profile + product) content, so a change to any configuration file produces a
new version for that domain — without changing the content an application
already runs under.

Existing applications always resolve their behaviour against their recorded
snapshot; new configuration applies to new applications only. A deliberate
move of a running application to a newer configuration is an *authorised
migration*: it is recorded (who, when, from→to versions, reason) in the
application record and in the audit trail, and is the only way a running
application picks up new configuration.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Optional

import yaml

from src.los import profiles, products as prodmod

DOMAINS = ("profile", "product", "workflow", "role_labels", "check_catalogue",
           "document_checklist", "approval_matrix", "output_templates", "policy_rules")


def _hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:24]


def _workflow_payload(profile_id: str) -> list:
    """The effective journey: ordered steps with their routing-relevant attributes."""
    from src.los import workflow as wfmod
    wf = wfmod.Workflow.from_config(profiles.workflow_config(profile_id))
    return [[s.id, s.stage_id, s.role, s.kind, s.sla_days, sorted(s.actions or ()),
             json.dumps([f["id"] if isinstance(f, dict) else f for f in s.decision_fields])] for s in wf.steps]


def workflow_version(profile_id: str) -> str:
    return _hash(_workflow_payload(profile_id))


def role_labels_version(profile_id: str) -> str:
    p = profiles.get_profile(profile_id)
    return _hash({"roles": profiles.role_labels(p), "stages": (profiles.labels(p) or {}).get("stages") or {}})


def check_catalogue_version(profile_id: str) -> str:
    return _hash(profiles.check_catalog(p=profiles.get_profile(profile_id)))


def document_checklist_version(profile_id: str) -> str:
    return _hash(profiles.document_checklist(p=profiles.get_profile(profile_id)))


def approval_matrix_version(profile_id: str) -> str:
    p = profiles.get_profile(profile_id)
    return _hash(profiles.approval(p))


def output_templates_version(profile_id: str) -> str:
    p = profiles.get_profile(profile_id)
    return _hash({k: profiles.output_template(k, p)
                  for k in ("cam", "ip_note", "committee_pack", "sanction_letter", "term_sheet")})


def policy_rules_version() -> str:
    f = pathlib.Path(__file__).resolve().parents[2] / "config" / "policy_rules.yaml"
    rules = yaml.safe_load(f.read_text(encoding="utf-8")) or {} if f.exists() else {}
    return _hash(rules or {})


def profile_version(profile_id: str) -> str:
    """The merged profile document (the institution's complete configuration)."""
    return _hash(profiles.get_profile(profile_id))


def product_version(product_id: Optional[str]) -> Optional[str]:
    if not product_id:
        return None
    return _hash(prodmod.get_product(product_id))


def config_snapshot(profile_id: str, product_id: Optional[str] = None) -> dict:
    """The full configuration version record for an application being created."""
    return {"profile": {"id": profile_id, "version": profile_version(profile_id)},
            "product": {"id": product_id, "version": product_version(product_id)} if product_id else None,
            "workflow": workflow_version(profile_id),
            "role_labels": role_labels_version(profile_id),
            "check_catalogue": check_catalogue_version(profile_id),
            "document_checklist": document_checklist_version(profile_id),
            "approval_matrix": approval_matrix_version(profile_id),
            "output_templates": output_templates_version(profile_id),
            "policy_rules": policy_rules_version(),
            "created_at": None}          # stamped by the caller


def snapshot_with_time(profile_id: str, at: str, product_id: Optional[str] = None) -> dict:
    snap = config_snapshot(profile_id, product_id)
    snap["created_at"] = at
    snap["content_hash"] = _hash({k: v for k, v in snap.items() if k != "content_hash"})
    return snap


def snapshot_for_app(app: dict, at: str) -> dict:
    """The snapshot for a freshly built application record (its profile and product are already set)."""
    pid = app.get("profile") or profiles.default_profile_id()
    return snapshot_with_time(pid, at, product_id=app.get("product"))


def current_snapshot(app: dict) -> dict:
    """The snapshot the application is currently running under (its record, or the
    configuration live at creation for pre-R16 applications)."""
    return app.get("config_snapshot") or {}


def is_current(app: dict) -> bool:
    """Whether the application's recorded snapshot still matches the live configuration
    (any domain that drifted means newer configuration the app does not use)."""
    snap = app.get("config_snapshot")
    if not snap:
        return True
    pid = app.get("profile") or profiles.default_profile_id()
    live = config_snapshot(pid, app.get("product"))
    drifted = []
    for k in DOMAINS:
        rec, cur = snap.get(k), live.get(k)
        rec_v = rec.get("version") if isinstance(rec, dict) else rec
        cur_v = cur.get("version") if isinstance(cur, dict) else cur
        if rec_v and cur_v and rec_v != cur_v:
            drifted.append(k)
    app.setdefault("config_drift", drifted)
    return not drifted


def migrate(app: dict, reason: str, by: str, at: str) -> dict:
    """An authorised migration: re-point the running application at the current configuration,
    recording from→to versions. The previous snapshot is preserved for audit."""
    pid = app.get("profile") or profiles.default_profile_id()
    old = dict(app.get("config_snapshot") or {})
    new = snapshot_with_time(pid, at, product_id=app.get("product"))
    entry = {"at": at, "by": by, "reason": reason,
             "from": {k: (v or {}).get("version") if isinstance(v, dict) else v for k, v in old.items()},
             "to": {k: (v or {}).get("version") if isinstance(v, dict) else v for k, v in new.items()}}
    app.setdefault("config_migrations", []).append(entry)
    app["config_snapshot"] = new
    app.pop("config_drift", None)
    return entry
