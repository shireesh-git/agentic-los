"""
API contract snapshot: status code and response shape for each endpoint.

Shape, not content: JSON objects record their sorted top-level keys, lists
record "list", other responses record their media type. That is stable across
dates and run IDs while still catching a missing route, a renamed field or a
changed status code.

Regenerate:  python -m tests.characterization.api_contract --write
"""

import json
import sys
from pathlib import Path

GOLDEN_PATH = Path(__file__).with_name("golden_api.json")
ENTITY = "MFL001"

# (method, path, json body). Order matters: cases exist only after the run.
REQUESTS = [
    ("GET", "/", None),
    ("GET", "/api/health", None),
    ("GET", "/api/enums", None),
    ("GET", "/api/dashboard", None),
    ("GET", "/api/companies", None),
    ("GET", "/api/cases", None),
    ("GET", f"/api/cases/{ENTITY}", None),
    ("GET", "/api/config", None),
    ("GET", "/api/config/rules", None),
    ("GET", "/api/engines", None),
    ("GET", "/api/llm/providers", None),
    ("GET", "/api/agents", None),
    ("GET", f"/api/companies/{ENTITY}/hierarchy", None),
    ("GET", f"/api/companies/{ENTITY}/documents", None),
    ("GET", f"/api/companies/{ENTITY}/document-operations", None),
    ("GET", "/api/document-operations", None),
    ("GET", f"/api/companies/{ENTITY}/data-gaps", None),
    ("GET", f"/api/companies/{ENTITY}/extraction", None),
    ("GET", f"/api/companies/{ENTITY}/etb-analytics", None),
    ("GET", f"/api/companies/{ENTITY}/fraud-analysis", None),
    ("GET", "/api/chat/sessions", None),
    ("GET", "/api/companies/NOPE999/hierarchy", None),
    ("POST", f"/api/cases/{ENTITY}/run", None),
    ("GET", "/api/cases", None),
    ("GET", f"/api/cases/{ENTITY}", None),
    ("GET", f"/api/cases/{ENTITY}/cam", None),
    ("GET", f"/api/cases/{ENTITY}/cam-html", None),
    ("GET", f"/api/cases/{ENTITY}/cam-pdf", None),
    ("GET", f"/api/cases/{ENTITY}/one-pager", None),
    ("PUT", f"/api/cases/{ENTITY}/comments", {"comments": {"executive_summary": "Looks fine"}}),
    ("GET", f"/api/cases/{ENTITY}/comments", None),
    ("PUT", f"/api/cases/{ENTITY}/cam-section-edits", {"section_key": "s1", "edited_html": "<p>x</p>"}),
    ("GET", f"/api/cases/{ENTITY}/cam-section-edits", None),
    ("GET", "/api/dashboard", None),
]


def shape(response) -> dict:
    media = response.headers.get("content-type", "").split(";")[0]
    if media == "application/json":
        body = response.json()
        if isinstance(body, dict):
            return {"status": response.status_code, "keys": sorted(body)}
        return {"status": response.status_code, "json": type(body).__name__}
    return {"status": response.status_code, "media": media, "empty": not response.content}


def capture() -> dict:
    from fastapi.testclient import TestClient
    from src.api.main import app

    client = TestClient(app)
    results = {}
    for index, (method, path, body) in enumerate(REQUESTS):
        response = client.request(method, path, json=body)
        results[f"{index:02d} {method} {path}"] = shape(response)
    return results


if __name__ == "__main__":
    import tests.conftest  # noqa: F401

    data = capture()
    if "--write" in sys.argv:
        GOLDEN_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {GOLDEN_PATH}")
    else:
        print(json.dumps(data, indent=2))
