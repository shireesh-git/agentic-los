"""The progress bar while documents are read (a cold first read can take minutes)."""

from src.flow.camjob import CamJob, _doc_label


def test_reading_documents_shows_which_one_and_moves_the_bar():
    job = CamJob("LOS-1", "MRF001")
    job.on_event({"type": "agent_start", "agent": "data_ingestion"})
    assert job.percent() == 0
    job.on_event({"type": "doc_progress", "agent": "data_ingestion", "done": 2, "total": 4,
                  "name": "annual_report_fy2024.pdf", "cached": False})
    assert job.step_label() == "Reading documents · 2 of 4 · annual report FY2024" and job.percent() == 9
    job.on_event({"type": "doc_progress", "done": 4, "total": 4, "name": "results_fy2026.pdf", "cached": True})
    assert job.step_label().endswith("(already read)") and job.percent() == 18
    job.on_event({"type": "agent_complete", "agent": "data_ingestion", "status": "completed"})
    assert not job.step_label().startswith("Reading documents")
    job.on_event({"type": "section_start", "section": "a", "total": 8})
    assert job.percent() >= 18                                     # the bar never goes back


def test_doc_label():
    assert _doc_label("unaudited_results_fy2026.pdf") == "unaudited results FY2026"
