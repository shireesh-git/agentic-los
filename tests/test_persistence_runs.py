"""Run tracking, section checkpoints and run-scoped RM edits in SQLite."""

import sqlite3

from src.services.persistence import PersistenceService


def test_pipeline_run_lifecycle(tmp_path):
    db = PersistenceService(tmp_path / "runs.sqlite3")
    db.start_pipeline_run("r1", "ACME001", "ollama")
    db.finish_pipeline_run("r1", "failed", error="LLM timeout")
    db.start_pipeline_run("r2", "ACME001", "ollama")
    db.finish_pipeline_run("r2", "completed", case_run_id="case-2")

    runs = {r["run_id"]: r for r in db.list_pipeline_runs("ACME001")}
    assert runs["r1"]["status"] == "failed" and runs["r1"]["error"] == "LLM timeout"
    assert runs["r2"]["status"] == "completed" and runs["r2"]["case_run_id"] == "case-2"


def test_run_history_lookups(tmp_path):
    db = PersistenceService(tmp_path / "history.sqlite3")
    db.start_pipeline_run("r1", "ACME001", "nvidia_nim", llm_model="openai/gpt-oss-20b")
    db.finish_pipeline_run("r1", "completed", case_run_id="case-1")
    db.save_case_run({"run_id": "case-1", "entity_id": "ACME001", "company_name": "Acme",
                      "risk_grade": "B", "composite_score": 71.5, "recommendation": "approve",
                      "run_at": "2026-10-07T10:00:00", "cam_text": "# CAM"})
    db.record_workflow_transition(entity_id="ACME001", case_run_id="case-1", action="submit",
                                  from_status="draft", to_status="submitted", actor_id="u1",
                                  actor_role="credit_analyst", required_authority="zonal_credit_committee",
                                  system_recommendation="approve", submitted_by="u1")

    assert db.list_pipeline_runs("ACME001")[0]["llm_model"] == "openai/gpt-oss-20b"
    assert db.latest_pipeline_runs()["ACME001"]["llm_model"] == "openai/gpt-oss-20b"
    assert db.get_case_run("case-1")["cam_text"] == "# CAM"
    assert db.get_case_run("missing") is None
    assert db.list_case_run_summaries("ACME001")["case-1"]["risk_grade"] == "B"
    assert db.run_decision_statuses("ACME001") == {"case-1": "submitted"}


def test_section_checkpoint_keeps_latest_only(tmp_path):
    db = PersistenceService(tmp_path / "cp.sqlite3")
    db.save_section_checkpoint("ACME001", "executive_summary", "h1", "old", "m", "v")
    db.save_section_checkpoint("ACME001", "executive_summary", "h2", "new", "m", "v")
    assert db.load_section_checkpoint("ACME001", "executive_summary", "h1") is None
    assert db.load_section_checkpoint("ACME001", "executive_summary", "h2") == "new"


def test_run_scoped_edits_do_not_leak_between_runs(tmp_path):
    db = PersistenceService(tmp_path / "edits.sqlite3")
    db.save_run_section_edit("run-1", "ACME001", "s1", "<p>edit on run 1</p>")
    assert db.load_run_section_edits("run-2") == {}
    assert db.load_run_section_edits("run-1")["s1"]["html"] == "<p>edit on run 1</p>"
    db.save_run_section_edit("run-1", "ACME001", "s1", "")
    assert db.load_run_section_edits("run-1") == {}


def test_legacy_edits_migrate_to_latest_run_once(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    PersistenceService(path)  # create schema
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM schema_migrations")
        for run_id, run_at in (("old-run", "2026-01-01T00:00:00"), ("new-run", "2026-02-01T00:00:00")):
            conn.execute("INSERT INTO case_runs(run_id, entity_id, company_name, run_at, payload_json, created_at) "
                         "VALUES (?, 'ACME001', 'Acme', ?, '{}', ?)", (run_id, run_at, run_at))
        conn.execute("INSERT INTO cam_section_edits(entity_id, section_key, edited_html, edited_by, updated_at) "
                     "VALUES ('ACME001', 's1', '<p>legacy</p>', 'RM', '2026-02-02T00:00:00Z')")

    db = PersistenceService(path)  # migration runs on init
    assert db.load_run_section_edits("new-run")["s1"]["html"] == "<p>legacy</p>"
    assert db.load_run_section_edits("old-run") == {}

    db.save_run_section_edit("new-run", "ACME001", "s1", "")
    assert PersistenceService(path).load_run_section_edits("new-run") == {}  # not re-migrated
