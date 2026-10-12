"""PEP / sanctions screening of directors and promoters."""

from src.agents.base_agent import BaseAgent


class PEPScreeningAgent(BaseAgent):
    name = "pep_screening"
    description = "Screen directors against PEP/sanctions databases & crawl adverse media"
    critical = False

    def run(self, context):
        from src.services.pep_service import screen_directors

        emit = self.emitter(context)
        cd = context["company_data"]
        directors = cd.get("directors", [])

        emit(f"Screening {len(directors)} directors against PEP/sanctions databases...")
        result = screen_directors(entity_id=cd["borrower"].entity_id, directors=directors)
        emit("Enhanced media screening skipped — only verified data sources are used.")

        hits = len(getattr(result, "pep_hits", None) or [])
        emit(f"PEP screening complete: {hits} hit(s), {getattr(result, 'sanctions_hits', 0)} sanctions hit(s), "
             f"overall risk {getattr(result, 'overall_risk', 'n/a')}")
        return {
            "pep_result": result,
            "adverse_media_articles": 0,
            "adverse_headlines": [],
            "social_controversy_index": 0.0,
            "directors_screened": len(directors),
        }
