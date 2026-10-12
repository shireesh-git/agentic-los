"""SQLite-backed CAM section checkpoints for one borrower."""

from src.engines.cam_llm_renderer import PROMPT_VERSION, model_identity


class PersistentSectionCheckpoints:
    """Implements ``cam_llm_renderer.SectionCheckpoints`` on ``PersistenceService``."""

    def __init__(self, persistence, entity_id: str, llm_provider):
        self.persistence = persistence
        self.entity_id = entity_id
        self.model = model_identity(llm_provider)

    def load(self, section_id: str, input_hash: str) -> str | None:
        return self.persistence.load_section_checkpoint(self.entity_id, section_id, input_hash)

    def save(self, section_id: str, input_hash: str, content: str) -> None:
        self.persistence.save_section_checkpoint(
            self.entity_id, section_id, input_hash, content,
            model=self.model, prompt_version=PROMPT_VERSION,
        )
