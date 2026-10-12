"""Pipeline output for every seeded company must match the golden snapshot."""

import json

import pytest

from tests.characterization.snapshot import GOLDEN_PATH, run_all_seeded


@pytest.fixture(scope="module")
def actual() -> dict:
    return run_all_seeded()


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_same_companies(actual, golden):
    assert sorted(actual) == sorted(golden)


@pytest.mark.parametrize("field", [
    "agents", "recommendation", "risk_grade", "composite_score", "component_scores",
    "conditions", "tier1", "exceptions", "fact_pack_keys", "fact_pack_recommendation",
    "fact_pack_risk_grade", "narrative_mode", "cam_headings",
])
def test_snapshot_field(actual, golden, field):
    mismatches = {
        entity_id: {"expected": golden[entity_id][field], "actual": actual[entity_id][field]}
        for entity_id in golden
        if json.loads(json.dumps(actual[entity_id][field], default=str)) != golden[entity_id][field]
    }
    assert not mismatches, json.dumps(mismatches, indent=2, default=str)
