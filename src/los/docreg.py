"""Document management and mandatory output gates (Client One GAP-P0-12, P1-06).

A logical document registry per application, scoped to relationship / entity /
application / facility / project, with a category, checklist requirement and
status; multiple uploads under one logical name with an explicit version
history; report/check evidence linkage; and reviewed / accepted / rejected /
rework status with the reviewer. The stage checklist tracks mandatory and
pending documents; the Sanction Letter (reviewed) and the generated+reviewed
Disbursement Memo are hard gates, as the client documents them.

Retention, e-signature, antivirus, formats/sizes and authoritative templates
remain confirmation-required (spec §22/P0-12) — the PDF/25MB limit is the
existing application behaviour, not a client rule.
"""

from __future__ import annotations

import re
from typing import Optional

from src.application.errors import InvalidRequestError


def doc_type_id(name: str, explicit: Optional[str] = None) -> str:
    """The stable identifier of a logical document type.

    An explicit ``type_id`` on the checklist entry always wins; otherwise the id is
    derived deterministically from the canonical display name (lowercased, runs of
    non-alphanumerics collapsed to underscores). Different periods remain distinct
    types ("Bank statements (last 6 months)" != "… (last 12 months)"); the same
    document required by the profile and by the product resolves to one type.
    """
    if explicit:
        return re.sub(r"[^a-z0-9]+", "_", str(explicit).strip().lower()).strip("_") or "doc"
    s = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    return s or "doc"


def merge_stage(entries: list[dict]) -> list[dict]:
    """Deduplicate one stage's document requirements by stable document-type id.

    Deterministic precedence — the highest-priority source wins the display fields:
    product template (``priority`` 2) > institution profile (1) > base checklist (0).
    ``name`` / ``scope`` / ``file_types`` come from the highest-priority entry;
    ``mandatory`` is the OR of all duplicates (a gate is never weakened); ``condition``
    is the union (a requirement any source applies, applies). The merged entry keeps
    the position of the first duplicate, so the checklist order is stable.
    """
    out: list[dict] = []
    index: dict[str, int] = {}
    for e in entries:
        eid = doc_type_id(e.get("name"), e.get("type_id"))
        entry = dict(e)
        entry["type_id"] = eid
        entry.setdefault("mandatory", True)
        entry.setdefault("source", "checklist")
        entry.setdefault("priority", 0)
        conds = entry.pop("condition", None)
        if conds:
            entry["conditions"] = [conds]
        if eid in index:
            cur = out[index[eid]]
            if int(entry["priority"]) > int(cur.get("priority", 0)):     # display fields: highest priority wins
                cur["name"], cur["scope"], cur["priority"] = entry["name"], entry["scope"], entry["priority"]
                if entry.get("file_types"):
                    cur["file_types"] = entry["file_types"]
            cur["mandatory"] = bool(cur.get("mandatory", True)) or bool(entry.get("mandatory", True))
            cur_conds = cur.pop("condition", None)
            cur_conds = [cur_conds] if cur_conds else list(cur.pop("conditions", None) or [])
            merged = list(dict.fromkeys(cur_conds + list(entry.get("conditions") or [])))
            if len(merged) == 1:
                cur["condition"] = merged[0]
            elif merged:
                cur["conditions"] = merged
            cur["merged_from"] = sorted(set(cur.get("merged_from") or [cur.get("source", "checklist")])
                                        | {entry.get("source", "checklist")})
            continue
        if "conditions" in entry and len(entry["conditions"]) == 1:
            entry["condition"] = entry.pop("conditions")[0]
        index[eid] = len(out)
        out.append(entry)
    return out

SCOPES = ("application", "entity", "facility", "project")
DOC_STATUSES = ("pending", "uploaded", "reviewed", "accepted", "rejected", "rework")
MANDATORY_STATUSES = ("reviewed", "accepted")

# The stage checklist: mandatory documents per stage group (the documented set).
CHECKLIST = {
    "PS": [("KYC evidence (POI/POA of the borrower and key persons)", "application"),
           ("Audited financial statements", "entity"),
           ("Board resolution authorising the proposal", "application")],
    "IP": [("MCA certificate of incorporation", "entity"),
           ("CIN / LLPIN certificate", "entity")],
    "AP": [("CMA (prepared in the CMA workspace)", "entity"),
           ("Valuation report for the proposed security", "application"),
           ("TEV report (where project finance is proposed)", "application")],
    "POS": [("Sanction letter (generated, issued and uploaded back)", "application"),
            ("Sanction consent / acceptance", "application"),
            ("Facility agreement (executed)", "facility"),
            ("Security documents (executed)", "application"),
            ("Insurance policy (with bank clause)", "application")],
    "DIS": [("Drawdown request", "application"),
            ("Drawdown schedule report", "application"),
            ("Disbursement memo (generated and reviewed)", "application")],
}

# Generated outputs the application can produce (GAP-P1-06 inventory subset).
GENERATED = ("ip_note", "cam", "executive_summary", "due_diligence_report", "esms_approval_note",
             "cma_download", "disbursement_memo", "committee_minutes", "sanction_letter", "term_sheet")


# The borrower's documents on file that satisfy a checklist item (folder / file-name patterns). The
# document agent links them when it prepares a step, so nobody uploads the same file twice; a person
# still reviews each one before the stage gate accepts it. The sanction letter is never linked: it
# must be the one issued for this application, signed and uploaded back.
ON_FILE = {
    "KYC evidence (POI/POA of the borrower and key persons)": (r"^kyc/(pan|kyc|poi|poa|aadhaar|passport)",),
    "Audited financial statements": (r"^financials/audited", r"^financials/annual_report"),
    "Board resolution authorising the proposal": (r"^kyc/board_resolution", r"^legal/board_resolution"),
    "MCA certificate of incorporation": (r"^kyc/certificate_of_incorporation", r"incorporation"),
    "CIN / LLPIN certificate": (r"^kyc/certificate_of_incorporation", r"(^|/)(cin|llpin)"),
    "Valuation report for the proposed security": (r"^collateral/valuation",),
    "TEV report (where project finance is proposed)": (r"(^|/)tev",),
    "Facility agreement (executed)": (r"facility_agreement",),
    "Security documents (executed)": (r"security_documents?|hypothecation|mortgage",),
    "Insurance policy (with bank clause)": (r"insurance",),
    "Drawdown request": (r"drawdown_request",),
}


def link_on_file(registry: list[dict], files: list[str], at: str) -> list[str]:
    """Link documents on file to the checklist items they satisfy (items with no version yet).
    Returns the names linked."""
    import re
    linked = []
    for d in registry:
        pats = ON_FILE.get(d["name"])
        if not pats or d.get("versions"):
            continue
        match = next((f for p in pats for f in sorted(files) if re.search(p, f, re.I)), None)
        if not match:
            continue
        d["versions"].append({"v": 1, "file_name": match, "uploaded_by": "Document agent", "at": at,
                              "source": "on_file", "detail": "linked from the borrower's documents on file"})
        if d["status"] == "pending":
            d["status"] = "uploaded"
        linked.append(d["name"])
    return linked


CMA_DOC = "CMA (prepared in the CMA workspace)"

# Checklist items prepared in a workspace rather than uploaded: (workspace label, "it has data")
WORKSPACE_ITEMS = {
    "CMA (prepared in the CMA workspace)":
        ("CMA workspace", lambda app: any(s.get("rows") for s in (app.get("cma") or {}).get("subjects") or [])),
    "Drawdown schedule report":
        ("Disbursement ops — drawdown", lambda app: bool(((app.get("disops") or {}).get("drawdown") or {}).get("schedule"))),
}


def link_workspace(app: dict, at: str) -> list[str]:
    """Link the checklist items prepared in a workspace (the CMA, the drawdown schedule) once it has data."""
    linked = []
    for name, (label, ready) in WORKSPACE_ITEMS.items():
        doc = next((d for d in app.get("documents") or [] if d["name"] == name), None)
        if not doc or doc.get("versions") or not ready(app):
            continue
        doc["versions"].append({"v": 1, "file_name": label, "uploaded_by": "Document agent", "at": at,
                                "source": "workspace", "detail": "prepared in the " + label})
        if doc["status"] in ("pending", "uploaded"):   # the step's own work, reviewed where it is prepared
            doc.update(status="reviewed", reviewer="Prepared in the " + label, reviewed_at=at)
        linked.append(name)
    return linked


def initial_registry(checklist: Optional[dict] = None) -> list[dict]:
    """The application's logical document registry, from the profile's checklist
    ({stage: [{name, scope, condition?}]}); the documented base set is the default."""
    if checklist is None:
        checklist = {st: [{"name": n, "scope": s} for n, s in items] for st, items in CHECKLIST.items()}
    out = []
    n = 0
    for stage, entries in checklist.items():
        for e in entries:
            name, scope = (e["name"], e["scope"]) if isinstance(e, dict) else (e[0], e[1])
            extra = e if isinstance(e, dict) else {}
            n += 1
            out.append({"doc_id": f"DOC-{n:03d}", "name": name, "category": "mandatory",
                        "type_id": doc_type_id(name, extra.get("type_id")),
                        "scope": scope, "mandatory_stage": stage, "versions": [], "status": "pending",
                        "reviewer": None, "reviewed_at": None, "remarks": None,
                        **({"merged_from": extra["merged_from"]} if extra.get("merged_from") else {})})
    return out


def register_upload(registry: list[dict], *, name: str, category: str, scope: str,
                    file_name: str, by_name: str, at: str, doc_id: Optional[str] = None) -> dict:
    """Add a version of a logical document (creating it if new)."""
    target = None
    if doc_id:
        target = next((d for d in registry if d["doc_id"] == doc_id), None)
    if target is None:
        target = next((d for d in registry if d["name"].lower() == str(name).strip().lower()), None)
    if target is None:
        registry.append({"doc_id": f"DOC-{len(registry) + 1:03d}", "name": str(name).strip(),
                         "category": category, "scope": scope, "mandatory_stage": None,
                         "versions": [], "status": "pending", "reviewer": None, "reviewed_at": None,
                         "remarks": None})
        target = registry[-1]
    v = len(target["versions"]) + 1
    target["versions"].append({"v": v, "file_name": file_name, "uploaded_by": by_name, "at": at,
                               "source": "upload"})
    if target["status"] not in MANDATORY_STATUSES:
        target["status"] = "uploaded"
    return target


def register_generated(registry: list[dict], *, name: str, kind: str, by_name: str, at: str,
                       detail: str = "") -> dict:
    target = next((d for d in registry if d["name"].lower() == str(name).strip().lower()), None)
    if target is None:
        registry.append({"doc_id": f"DOC-{len(registry) + 1:03d}", "name": str(name).strip(),
                         "category": "generated", "scope": "application", "mandatory_stage": None,
                         "versions": [], "status": "pending", "reviewer": None, "reviewed_at": None,
                         "remarks": None})
        target = registry[-1]
    v = len(target["versions"]) + 1
    target["versions"].append({"v": v, "file_name": f"{kind}-{v}", "uploaded_by": by_name, "at": at,
                               "source": "generated", "kind": kind, "detail": detail})
    if target["name"] in WORKSPACE_ITEMS:       # prepared in its workspace: the step's own reviewed work
        target.update(status="reviewed", reviewer=f"Prepared in the {WORKSPACE_ITEMS[target['name']][0]} by {by_name}",
                      reviewed_at=at)
    elif target["status"] == "pending":
        target["status"] = "uploaded"
    return target


def review_document(registry: list[dict], doc_id: str, status: str, reviewer: str, at: str,
                    remarks: str = "") -> dict:
    if status not in ("reviewed", "accepted", "rejected", "rework"):
        raise InvalidRequestError(f"Document status must be one of {', '.join(DOC_STATUSES)}")
    doc = next((d for d in registry if d["doc_id"] == doc_id), None)
    if not doc:
        raise InvalidRequestError(f"Unknown document: {doc_id}")
    if not doc["versions"]:
        raise InvalidRequestError("A document needs at least one version before it can be reviewed")
    doc["status"] = status
    doc["reviewer"] = reviewer
    doc["reviewed_at"] = at
    doc["remarks"] = (remarks or None)
    return doc


def _required_for_stage(app: dict, only: Optional[set] = None, skip: Optional[set] = None) -> list[str]:
    """Mandatory documents for the application's stage + product, with the profile's
    conditional items evaluated (securities / projects)."""
    from src.los import profiles
    return [n for n in profiles.required_documents(app) if (only is None or n in only) and n not in (skip or set())]


def stage_gate(app: dict, only: Optional[set] = None, skip: Optional[set] = None) -> Optional[str]:
    """Mandatory documents for the application's stage must be present and reviewed
    (``only`` / ``skip``: the subset a step answers for, e.g. the CMA at the AP Risk Maker)."""
    registry = app.get("documents") or []
    required = _required_for_stage(app, only, skip)
    missing = []
    for name in required:
        doc = next((d for d in registry if d["name"] == name), None)
        if not doc:
            missing.append(name)
            continue
        if not doc["versions"]:
            missing.append(f"{name} (no version on file)")
        elif doc["status"] not in MANDATORY_STATUSES:
            missing.append(f"{name} (status: {doc['status']} — needs review)")
    return ("Mandatory documents are not complete for this stage: " + "; ".join(missing[:4])
            + ("…" if len(missing) > 4 else "")) if missing else None


def registry_view(app: dict) -> dict:
    registry = app.get("documents") or []
    stage = (app.get("stage_id") or "PS").upper()
    required = set(_required_for_stage(app))
    pending = [d for d in registry if d["status"] == "pending" and d["name"] in required]
    return {"documents": registry, "stage": stage,
            "mandatory_now": [d for d in registry if d["name"] in required],
            "pending_count": len(pending), "gate": stage_gate(app)}
