"""R15 idempotency & dedupe, R16 configuration version snapshots, R20 error contract."""

import pathlib

import pytest

from datetime import datetime, timedelta

import tests.conftest  # noqa: F401  (isolates runtime paths)

from src.data.company_catalog import seed_company_store
from src.los import config_version as cv
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.application.errors import (ApplicationError, ConflictError, ForbiddenError,
                                    InvalidRequestError, NotFoundError, ValidationError)

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "demo sourcing decision"}


def make_service(tmp_path, with_docs=True):
    from src.services.document_store import DocumentStore
    docs_root = tmp_path / "docs"
    docs_root.mkdir(exist_ok=True)
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: NOW, documents_root=docs_root,
                      doc_store=DocumentStore(docs_root) if with_docs else None)


def new_app(svc, entity_id="MRF001", **kw):
    kw.setdefault("sourcing_decision", SOURCING)
    return svc.create(svc._system_session("ps_maker"), entity_id=entity_id, **kw)


# ── R20 error contract ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("cls,code,status", [
    (NotFoundError, "NOT_FOUND", 404),
    (UnauthorizedError if False else ApplicationError, "INTERNAL", 500),
    (ForbiddenError, "FORBIDDEN", 403),
    (ConflictError, "CONFLICT", 409),
    (InvalidRequestError, "INVALID_REQUEST", 400),
    (ValidationError, "VALIDATION_FAILED", 422),
])
def test_error_contract_fields(cls, code, status):
    e = cls("something went wrong")
    assert e.status_code == status
    assert e.code == code
    d = e.to_dict("los-abc123")
    assert d == {"code": code, "message": "something went wrong", "correlation_id": "los-abc123"}
    e2 = cls("bad date", field="deferred_until", stage="ip_note", corrective_action="send YYYY-MM-DD")
    d2 = e2.to_dict()
    assert d2["field"] == "deferred_until" and d2["stage"] == "ip_note"
    assert d2["corrective_action"] == "send YYYY-MM-DD"
    assert "correlation_id" not in d2


def test_api_error_handler_shapes():
    from fastapi.testclient import TestClient
    from src.api.app import create_app
    from src.los.service import LosService

    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
    r = APIRouter(prefix="/api/los/_t")

    @r.get("/nf")
    async def nf():
        raise NotFoundError("Application XYZ not found")

    @r.get("/boom")
    async def boom():
        raise RuntimeError("secret /path/to/internal thing")

    app = create_app()
    app.include_router(r)
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/api/los/_t/nf")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Application XYZ not found"
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["correlation_id"].startswith("los-")
    resp2 = c.get("/api/los/_t/boom")
    assert resp2.status_code == 500
    b2 = resp2.json()
    assert "secret" not in b2["detail"] and "/path" not in b2["detail"]
    assert b2["error"]["code"] == "INTERNAL"
    assert b2["error"]["correlation_id"].startswith("los-")
    assert "Traceback" not in resp2.text


# ── R16 configuration version snapshots ────────────────────────────────────────

def test_snapshot_domains_and_stability():
    s1 = cv.config_snapshot("client_one", "term_loan")
    s2 = cv.config_snapshot("client_one", "term_loan")
    assert s1 == s2                                   # deterministic
    for d in cv.DOMAINS:
        assert d in s1, d
    assert s1["profile"]["id"] == "client_one"
    assert s1["product"]["id"] == "term_loan"
    assert s1["workflow"] and s1["approval_matrix"]


def test_snapshot_differs_by_profile():
    a = cv.config_snapshot("client_one")
    b = cv.config_snapshot("dfi")
    assert a["profile"]["version"] != b["profile"]["version"]
    assert a["approval_matrix"] != b["approval_matrix"]          # different matrices
    assert a["output_templates"] != b["output_templates"]


def test_snapshot_drift_and_migration(tmp_path):
    svc = make_service(tmp_path)
    session = svc._system_session("ps_maker")
    app = new_app(svc)
    snap = app["config_snapshot"]
    assert snap["created_at"] and snap["content_hash"]
    # untouched configuration → still current
    assert cv.is_current(app) is True
    assert app.get("config_drift") == []
    # authorise a migration with no changes: it records the move
    entry = cv.migrate(app, reason="policy review", by="u_admin", at="2026-10-27T10:00:00")
    assert app["config_migrations"] and app["config_migrations"][0]["by"] == "u_admin"
    assert entry["from"]["profile"] == entry["to"]["profile"]    # same content, same versions
    # tamper one recorded version → drift is detected
    app["config_snapshot"]["approval_matrix"] = "deadbeef"
    assert cv.is_current(app) is False
    assert "approval_matrix" in app["config_drift"]
    # the application re-resolves under its own profile regardless of the active one
    assert app["profile"] == "client_one"


def test_existing_app_retains_its_snapshot_on_profile_switch(tmp_path):
    svc = make_service(tmp_path)
    session = svc._system_session("ps_maker")
    app = new_app(svc)
    before = app["config_snapshot"]["profile"]["version"]
    admin = svc._system_session("los_admin")
    svc.set_active_profile(admin, "dfi")
    try:
        again = svc.get(app["application_id"], session)
        assert again["profile"] == "client_one"                  # pinned at creation
        assert again["config_snapshot"]["profile"]["version"] == before
    finally:
        svc.set_active_profile(admin, "client_one")


# ── R15 idempotency ────────────────────────────────────────────────────────────

def test_create_idempotency_returns_original(tmp_path):
    svc = make_service(tmp_path)
    a1 = new_app(svc, idempotency_key="key-1")
    a2 = new_app(svc, idempotency_key="key-1")
    assert a1["application_id"] == a2["application_id"]
    assert svc.store.count() == 1                                # no duplicate application
    # a different key creates a different application
    a3 = new_app(svc, idempotency_key="key-2")
    assert a3["application_id"] != a1["application_id"]
    # no key at all: each call creates (legacy behaviour)
    a4 = new_app(svc)
    assert a4["application_id"] not in (a1["application_id"], a3["application_id"])


def test_idempotency_not_cached_on_failure(tmp_path):
    svc = make_service(tmp_path)
    with pytest.raises(NotFoundError):
        new_app(svc, entity_id="NOPE001", idempotency_key="key-f")
    # the failed request may be retried with the same key (no phantom block)
    with pytest.raises(NotFoundError):
        new_app(svc, entity_id="NOPE001", idempotency_key="key-f")
    assert svc.store.count() == 0


def test_act_idempotency_replays_without_double_transition(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    rm = svc._system_session("ps_maker", app["assignee_id"])
    # resolve the (deterministic) blocking checks so the step's submit gate is clear
    for c in app["due_diligence"]["checks"]:
        if c["status"] == "pending":
            if c["mode"] == "manual":
                svc.record_check(sid, rm, c["id"], result="clear", remarks="idempotency test — cleared")
            else:
                svc.trigger_check(sid, rm, c["id"])
    for d in app["documents"]:
        if d["status"] != "on_file":
            svc.upload_document(sid, rm, "request", d["doc_id"] + ".pdf", b"%PDF-1.4\n" + b"x" * 400,
                                link_to=d["doc_id"])
    app = svc.get(sid, rm)
    for d in app["documents"]:
        if d["status"] == "uploaded":
            svc.review_document(sid, rm, d["doc_id"], "accepted", "idempotency test — accepted")
    r1 = svc.act(sid, rm, "submit", comment="first", idempotency_key="act-1")
    r2 = svc.act(sid, rm, "submit", comment="REPEAT (must not run)", idempotency_key="act-1")
    assert r1["step_id"] == r2["step_id"]
    submits = [e for e in svc.store.events(sid) if e["action"] == "submit"]
    assert len(submits) == 1                                     # one transition, one audit event
    assert submits[0]["comment"] == "first"


def test_in_flight_reclaimed_after_ttl(tmp_path):
    svc = make_service(tmp_path)
    at = svc.now().isoformat(timespec="seconds")
    assert svc.store.idempotency_begin("k", "create", None, at) == "new"
    assert svc.store.idempotency_begin("k", "create", None, at) == "in_flight"
    # an in-flight claim older than the ttl (e.g. after a crash) is reclaimed on retry
    later = (svc.now() + timedelta(seconds=700)).isoformat(timespec="seconds")
    assert svc.store.idempotency_begin("k", "create", None, later) == "new"
    svc.store.idempotency_complete("k", {"application_id": "X"}, later)
    r = svc.store.idempotency_result("k")
    assert r["status"] == "completed" and r["result"]["application_id"] == "X"
    # a completed key always replays
    assert svc.store.idempotency_begin("k", "create", None, later) == "hit"
