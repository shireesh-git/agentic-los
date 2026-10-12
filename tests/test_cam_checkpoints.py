"""CAM sections are saved as they are written, and a failed run resumes."""

import copy

import pytest

from src.engines.cam_llm_renderer import clean_section_output, render_cam_with_llm


class MemoryCheckpoints:
    def __init__(self):
        self.saved: dict[tuple[str, str], str] = {}

    def load(self, section_id, input_hash):
        return self.saved.get((section_id, input_hash))

    def save(self, section_id, input_hash, content):
        self.saved[(section_id, input_hash)] = content


class FlakyLLM:
    """Writes a valid section per call; raises on call number ``fail_on``."""

    name = "fake"
    model = "flaky-1"

    def __init__(self, fail_on: int | None = None):
        self.fail_on = fail_on
        self.calls = 0

    def test_connection(self):
        return {"status": "ok"}

    def generate(self, prompt, system_prompt="", temperature=None, max_tokens=None):
        self.calls += 1
        if self.calls == self.fail_on:
            raise TimeoutError("simulated LLM timeout")
        title = prompt.split("\n", 1)[0].replace("## Section: ", "")
        return f"<think>internal reasoning</think>\n## {title}\n\n" + "Narrative text. " * 10


@pytest.fixture(scope="module")
def fact_pack():
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack

    return build_cam_fact_pack(copy.deepcopy(seed_company_store()["MFL001"]))


def _render(fact_pack, llm, checkpoints, events=None):
    return render_cam_with_llm(fact_pack, llm, checkpoints=checkpoints,
                               on_section_progress=events.append if events is not None else None)


def test_failed_run_keeps_completed_sections_and_resumes(fact_pack):
    checkpoints = MemoryCheckpoints()
    first = FlakyLLM(fail_on=5)
    with pytest.raises(TimeoutError):
        _render(fact_pack, first, checkpoints)
    assert len(checkpoints.saved) == 4

    retry = FlakyLLM()
    events = []
    cam = _render(fact_pack, retry, checkpoints, events)

    completed = [e for e in events if e["type"] == "section_complete"]
    resumed = [e for e in completed if e["resumed"]]
    assert len(resumed) == 4
    assert retry.calls == len(completed) - 4
    assert "<think>" not in cam


def test_unchanged_inputs_reuse_every_section(fact_pack):
    checkpoints = MemoryCheckpoints()
    _render(fact_pack, FlakyLLM(), checkpoints)
    again = FlakyLLM()
    _render(fact_pack, again, checkpoints)
    assert again.calls == 0


def test_changed_model_regenerates(fact_pack):
    checkpoints = MemoryCheckpoints()
    _render(fact_pack, FlakyLLM(), checkpoints)
    other = FlakyLLM()
    other.model = "flaky-2"
    _render(fact_pack, other, checkpoints)
    assert other.calls > 0


@pytest.mark.parametrize("raw, expected", [
    ("<think>plan</think>\n## A\nbody", "## A\nbody"),
    ("reasoning without open tag</think>## A", "## A"),
    ("```markdown\n## A\nbody\n```", "## A\nbody"),
    ("## A\nbody", "## A\nbody"),
    (None, ""),
])
def test_clean_section_output(raw, expected):
    assert clean_section_output(raw) == expected
