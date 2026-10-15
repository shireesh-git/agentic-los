"""CAM narrative: build the approved fact pack and render the CAM (LLM or template)."""

import logging

from src.agents.base_agent import BaseAgent

log = logging.getLogger(__name__)


class NarrativeAgent(BaseAgent):
    name = "narrative"
    description = "Build fact-pack and render CAM narrative"
    critical = True
    uses_llm = True
    requires = ("financial_analysis", "validation", "benchmark", "policy")
    # Reuse PEP screening in the fact pack when it succeeded; screen again if it failed.
    waits_for = ("pep_screening",)

    def __init__(self, llm_provider=None, checkpoint_factory=None):
        """``checkpoint_factory(entity_id, llm_provider)`` returns a section
        checkpoint store, or None to generate every section from scratch."""
        self.llm = llm_provider
        self.checkpoint_factory = checkpoint_factory

    def _template_mode(self) -> bool:
        from src.core.config_manager import config

        is_mock = not self.llm or getattr(self.llm, "name", None) == "mock"
        narrative_cfg = config.get("llm_providers", "narrative", default={}) or {}
        return is_mock or narrative_cfg.get("mode") == "template"

    def _max_parallel_sections(self, settings: dict) -> int:
        """Provider setting first (a local model may only manage one), then the narrative default."""
        value = getattr(self.llm, "max_parallel_sections", None)
        if value is None:
            value = settings.get("max_parallel_sections", 1)
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 1

    def _section_models(self) -> dict[str, str]:
        """{section id: model} from the active provider's model_routing, when enabled.

        Config shape (config/llm_providers.yaml, under a provider):
            model_routing:
              enabled: true
              routes:
                qwen2.5:3b: [compliance, conduct, ...]
        """
        routing = getattr(self.llm, "model_routing", None) or {}
        if not routing.get("enabled"):
            return {}
        return {str(section_id): str(model)
                for model, section_ids in (routing.get("routes") or {}).items()
                for section_id in (section_ids or [])}

    @staticmethod
    def _assessment(context):
        """The credit assessment already made by the analysis agents."""
        from src.engines.credit_assessment import CreditAssessment

        r = context["results"]
        return CreditAssessment(
            exceptions=r["validation"]["exceptions"],
            benchmarks=r["benchmark"]["view"],
            latest_ratios=r["financial_analysis"]["latest_ratios"],
            policy=r["policy"]["outcome"],
        )

    def _counting(self, forward):
        """Progress callback that also counts sections written by the LLM vs resumed from checkpoints."""
        counts = {"llm_calls": 0, "checkpoint_hits": 0, "template_sections": 0}

        def callback(event: dict) -> None:
            if event.get("type") == "section_complete":
                if event.get("mode") == "template":
                    counts["template_sections"] += 1
                elif event.get("resumed"):
                    counts["checkpoint_hits"] += 1
                else:
                    counts["llm_calls"] += 1
            if forward:
                forward(event)

        return callback, counts

    def run(self, context):
        import time

        from src.core.config_manager import config
        from src.engines.cam_fact_builder import build_cam_fact_pack
        from src.engines.cam_llm_renderer import render_cam_template_only, render_cam_with_llm

        pep = context["results"].get("pep_screening") or {}
        started = time.perf_counter()
        fact_pack = build_cam_fact_pack(context["company_data"], assessment=self._assessment(context),
                                        pep_result=pep.get("pep_result"),
                                        financial_analysis=context["results"]["financial_analysis"])
        fact_pack_ms = round((time.perf_counter() - started) * 1000, 1)
        section_cb, counts = self._counting(context.get("_on_progress"))

        if self._template_mode():
            cam_text = render_cam_template_only(fact_pack, on_section_progress=section_cb)
            self.diagnostics = {"execution_mode": "template", "llm_invoked": False, "llm_calls": 0,
                                "fact_pack_ms": fact_pack_ms, "fact_pack_keys": len(fact_pack), **counts}
            return {"fact_pack": fact_pack, "cam_text": cam_text, "narrative_mode": "template"}

        settings = config.get_narrative_settings()  # raises if mode != 'llm'
        entity_id = context["company_data"]["borrower"].entity_id
        checkpoints = self.checkpoint_factory(entity_id, self.llm) if self.checkpoint_factory else None
        try:
            cam_text = render_cam_with_llm(
                fact_pack=fact_pack,
            llm_provider=self.llm,
            temperature=settings.get("temperature", 0.1),
            max_tokens_per_section=settings.get("max_tokens_per_section", 1500),
                on_section_progress=section_cb,
                checkpoints=checkpoints,
                max_parallel_sections=self._max_parallel_sections(settings),
                section_max_tokens=settings.get("section_max_tokens") or {},
                section_models=self._section_models(),
                verify_figures=bool((getattr(self.llm, "model_routing", None) or {}).get("verify_figures", True)),
            )
        except RuntimeError as e:
            # The LLM cannot be reached (no key, no network): with narrative.on_llm_unavailable = template the
            # CAM is rendered by the deterministic templates — same sections, figures from the fact pack — and
            # the fallback is labelled on the case, never silent. Any other failure still stops the run.
            if not str(e).startswith("LLM connection failed") or settings.get("on_llm_unavailable", "fail") != "template":
                raise
            cam_text = render_cam_template_only(fact_pack, on_section_progress=section_cb)
            warning = (f"The LLM was not reachable, so the CAM narrative was written from the templates "
                       f"(figures and sections are complete; prose is not AI-drafted). Reason: {str(e)[:240]}")
            self.diagnostics = {"execution_mode": "template_fallback", "llm_invoked": False, "llm_calls": 0,
                                "fallback_reason": str(e)[:500], "fact_pack_ms": fact_pack_ms,
                                "fact_pack_keys": len(fact_pack), **counts}
            return {"fact_pack": fact_pack, "cam_text": cam_text, "narrative_mode": "template_fallback",
                    "narrative_warning": warning}
        mode = ("llm" if counts["llm_calls"] and not counts["checkpoint_hits"] else
                "llm+cached" if counts["llm_calls"] else "cached" if counts["checkpoint_hits"] else "llm")
        self.diagnostics = {"execution_mode": mode, "llm_invoked": counts["llm_calls"] > 0,
                            "model": getattr(self.llm, getattr(self.llm, "_model_attr", "model"), None),
                            "provider": getattr(self.llm, "name", None), "fact_pack_ms": fact_pack_ms,
                            "fact_pack_keys": len(fact_pack), **counts}
        if not cam_text or len(cam_text.strip()) < 100:
            raise RuntimeError("LLM narrative generation produced empty or insufficient output")
        return {"fact_pack": fact_pack, "cam_text": cam_text, "narrative_mode": "llm"}
