"""
CAM documents for a case: the stored narrative, RM comments and section edits,
and the HTML / PDF / one-pager renditions.
"""

from src.application.case_service import CaseService
from src.application.errors import InvalidRequestError
from src.application.state import AppState
from src.rendering import apply_section_edits_to_markdown, generate_cam_pdf, markdown_to_html


class CamService:
    def __init__(self, state: AppState, persistence, cases: CaseService, companies):
        self.state = state
        self.persistence = persistence
        self.cases = cases
        self.companies = companies

    # Reads take an optional ``run_id`` to show an earlier run's CAM exactly as that run
    # left it (its own comments and edits); writes always go to the latest run.

    # ── Comments (per run) ───────────────────────────────────────────────

    def load_comments(self, entity_id: str, run_id: str | None = None) -> dict[str, str]:
        if run_id:
            return self.persistence.load_case_comments(self.cases.get_run(entity_id, run_id).get("run_id"))
        run_id = (self.state.cases.get(entity_id) or {}).get("run_id")
        if not run_id:
            return {}
        return self.persistence.load_case_comments(run_id)

    def save_comments(self, entity_id: str, raw_comments) -> dict[str, str]:
        self.cases.require(entity_id)
        if not isinstance(raw_comments, dict):
            raise InvalidRequestError("comments must be an object")
        clean = {str(k): str(v or "").strip() for k, v in raw_comments.items()}
        clean = {k: v for k, v in clean.items() if v}
        run_id = (self.state.cases.get(entity_id) or {}).get("run_id")
        self.persistence.save_case_comments(run_id, clean)
        return self.load_comments(entity_id)

    # ── RM section edits ─────────────────────────────────────────────────

    # Edits belong to the run whose CAM the RM was editing; a re-run starts clean.

    def load_section_edits(self, entity_id: str, run_id: str | None = None) -> dict:
        case = self.cases.get_run(entity_id, run_id)
        return self.persistence.load_run_section_edits(case.get("run_id"))

    def save_section_edit(self, entity_id: str, section_key: str, edited_html: str) -> dict:
        case = self.cases.require(entity_id)
        section_key = str(section_key or "").strip()
        if not section_key:
            raise InvalidRequestError("section_key is required")
        self.persistence.save_run_section_edit(case.get("run_id"), entity_id, section_key,
                                               str(edited_html or "").strip())
        return self.persistence.load_run_section_edits(case.get("run_id"))

    # ── Renditions ───────────────────────────────────────────────────────

    def cam_text(self, entity_id: str, run_id: str | None = None) -> str:
        return self.cases.get_run(entity_id, run_id).get("cam_text", "")

    def _renderable_markdown(self, entity_id: str, case: dict) -> str:
        """Stored CAM text; re-rendered from the fact pack only when none was stored.

        A short LLM-written CAM is shown as written, never silently swapped for
        the template version.
        """
        md = case.get("cam_text", "")
        if not md.strip():
            md = self.regenerate_from_template(entity_id)
        return md

    def _edited_markdown(self, entity_id: str, case: dict) -> str:
        """The CAM as the RM last saw it: stored text plus section edits, sanitized."""
        from src.engines.cam_llm_renderer import _sanitize_llm_markdown

        md = self._renderable_markdown(entity_id, case)
        section_edits = self.persistence.load_run_section_edits(case.get("run_id"))
        if section_edits:
            md = apply_section_edits_to_markdown(md, section_edits)
        return _sanitize_llm_markdown(md)

    def html(self, entity_id: str, run_id: str | None = None) -> str:
        case = self.cases.get_run(entity_id, run_id)
        return markdown_to_html(self._edited_markdown(entity_id, case), case.get("company_name", entity_id))

    def pdf(self, entity_id: str, run_id: str | None = None) -> bytes:
        case = self.cases.get_run(entity_id, run_id)
        return generate_cam_pdf(self._edited_markdown(entity_id, case), case.get("company_name", entity_id),
                                section_comments=self.persistence.load_case_comments(case.get("run_id")))

    def one_pager(self, entity_id: str, run_id: str | None = None) -> str:
        from src.engines.cam_one_pager import generate_one_pager_html

        case = self.cases.get_run(entity_id, run_id)
        return generate_one_pager_html(case.get("fact_pack", {}), case)

    def regenerate_from_template(self, entity_id: str) -> str:
        """Re-render the CAM with the template renderer from the stored fact pack."""
        from src.engines.cam_fact_builder import build_cam_fact_pack
        from src.engines.cam_renderer_v2 import render_complete_cam

        case = self.state.cases.get(entity_id, {})
        fp = case.get("fact_pack")
        if not fp and self.companies.exists(entity_id):
            fp = build_cam_fact_pack(self.companies.get(entity_id))
        if fp:
            try:
                cam_text = render_complete_cam(fp)
                case["cam_text"] = cam_text
                case["narrative_mode"] = "template"
                return cam_text
            except Exception:
                pass
        return "# CAM Report\n\nNarrative content could not be generated. Please re-run the case."
