"""
PEP (Politically Exposed Person) Screening Service
Screens directors/promoters against PEP databases, sanctions lists,
and adverse media sources, from the demo watchlist data file (data/reference/pep_watchlist.json).
"""

from datetime import date
from typing import Optional

from src.models.canonical_model import (
    DirectorPromoter, PEPMatch, PEPScreeningResult,
)

# The demo watchlist is a data file (data/reference/pep_watchlist.json); no names are held in code.
def _watchlist() -> dict:
    import json
    from src.core.runtime_paths import PROJECT_ROOT
    p = PROJECT_ROOT / "data" / "reference" / "pep_watchlist.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


_WL = _watchlist()
_PEP_DATABASE: dict[str, dict] = _WL.get("persons_by_din") or {}
_SANCTIONS_NAMES: set[str] = set(_WL.get("sanctions_names") or [])
_ADVERSE_MEDIA_TRIGGERS: dict[str, int] = _WL.get("adverse_media_counts") or {}


# ════════════════════════════════════════════════════════════════════════
# SCREENING LOGIC
# ════════════════════════════════════════════════════════════════════════

def _screen_single_person(director: DirectorPromoter) -> Optional[PEPMatch]:
    """Screen one director/promoter against PEP databases."""
    # 1. Check by DIN in PEP database
    if director.din and director.din in _PEP_DATABASE:
        entry = _PEP_DATABASE[director.din]
        return PEPMatch(
            person_name=director.name,
            din=director.din,
            match_type="exact_din",
            pep_category=entry["pep_category"],
            pep_designation=entry["pep_designation"],
            pep_jurisdiction=entry["pep_jurisdiction"],
            risk_level=entry["risk_level"],
            sanctions_list_hit=entry["sanctions_list_hit"],
            adverse_media_count=entry["adverse_media_count"],
            related_pep=entry["related_pep"],
            source=entry["source"],
            remarks=f"DIN {director.din} matched in PEP registry",
        )

    # 2. Check name against sanctions list
    name_lower = director.name.lower().strip()
    if name_lower in _SANCTIONS_NAMES:
        return PEPMatch(
            person_name=director.name,
            din=director.din,
            match_type="sanctions_name",
            pep_category="Sanctioned",
            pep_designation="Sanctioned Individual",
            pep_jurisdiction="International",
            risk_level="critical",
            sanctions_list_hit=True,
            adverse_media_count=0,
            related_pep=False,
            source="UN/OFAC/EU Consolidated Sanctions List",
            remarks=f"Name matched on international sanctions list",
        )

    # 3. Check name against adverse media triggers
    if name_lower in _ADVERSE_MEDIA_TRIGGERS:
        count = _ADVERSE_MEDIA_TRIGGERS[name_lower]
        return PEPMatch(
            person_name=director.name,
            din=director.din,
            match_type="adverse_media",
            pep_category="Adverse Media",
            pep_designation="Subject of adverse media reports",
            pep_jurisdiction="India",
            risk_level="high",
            sanctions_list_hit=False,
            adverse_media_count=count,
            related_pep=False,
            source="Adverse Media Screening — Dow Jones / World-Check",
            remarks=f"{count} adverse media articles found in last 24 months",
        )

    return None


def screen_directors(
    entity_id: str,
    directors: list[DirectorPromoter],
) -> PEPScreeningResult:
    """Run PEP screening for all directors of a borrower entity.

    Returns a PEPScreeningResult with hits, risk level, and status.
    """
    pep_hits: list[PEPMatch] = []
    sanctions_hits = 0
    adverse_media_hits = 0

    for d in directors:
        match = _screen_single_person(d)
        if match:
            pep_hits.append(match)
            if match.sanctions_list_hit:
                sanctions_hits += 1
            if match.match_type == "adverse_media":
                adverse_media_hits += 1

    # Determine overall risk
    if sanctions_hits > 0:
        overall_risk = "critical"
        status = "fail"
    elif any(m.risk_level == "high" for m in pep_hits):
        overall_risk = "high"
        status = "review"
    elif any(m.risk_level in ("medium", "low") for m in pep_hits):
        overall_risk = "low"
        status = "clear_with_observations"
    else:
        overall_risk = "nil"
        status = "clear"

    remarks = (
        f"Screened {len(directors)} persons. "
        f"{len(pep_hits)} PEP/adverse hits, {sanctions_hits} sanctions hits."
    )

    return PEPScreeningResult(
        entity_id=entity_id,
        screening_date=date.today().isoformat(),
        total_persons_screened=len(directors),
        pep_hits=pep_hits,
        sanctions_hits=sanctions_hits,
        adverse_media_hits=adverse_media_hits,
        overall_risk=overall_risk,
        status=status,
        remarks=remarks,
    )
