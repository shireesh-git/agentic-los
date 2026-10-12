"""Every endpoint keeps its status code and response shape."""

import json

from tests.characterization.api_contract import GOLDEN_PATH, capture


def test_api_contract_matches_golden():
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    actual = capture()
    diffs = {key: {"expected": golden.get(key), "actual": actual.get(key)}
             for key in sorted(set(golden) | set(actual))
             if golden.get(key) != actual.get(key)}
    assert not diffs, json.dumps(diffs, indent=2)
