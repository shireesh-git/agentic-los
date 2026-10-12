"""
PEP (Politically Exposed Person) Screening Service
Screens directors/promoters against PEP databases, sanctions lists,
and adverse media sources.  Mock implementation for the platform.
"""

from datetime import date
from typing import Optional

from src.models.canonical_model import (
    DirectorPromoter, PEPMatch, PEPScreeningResult,
)

# ════════════════════════════════════════════════════════════════════════
# MOCK PEP DATABASE
# ════════════════════════════════════════════════════════════════════════

_PEP_DATABASE: dict[str, dict] = {
    # Known PEP entries (by DIN or name fragments)
    "00012345": {
        "person_name": "Sample PEP Director",
        "pep_category": "Domestic PEP",
        "pep_designation": "Former Member of Parliament",
        "pep_jurisdiction": "India",
        "risk_level": "high",
        "sanctions_list_hit": False,
        "adverse_media_count": 3,
        "related_pep": True,
        "source": "Consolidated PEP List — MHA/FATF",
    },
    # N. Chandrasekaran — Chairman of Tata Sons / IHCL (not PEP but high-profile)
    "00121863": {
        "person_name": "Natarajan Chandrasekaran",
        "pep_category": "Close Associate",
        "pep_designation": "Chairman — Tata Sons (Government Board advisory roles)",
        "pep_jurisdiction": "India",
        "risk_level": "low",
        "sanctions_list_hit": False,
        "adverse_media_count": 0,
        "related_pep": False,
        "source": "Corporate PEP Watch — Advisory",
    },
    # Nandan Nilekani — Infosys Chairman & former UIDAI Chairman (Govt role = PEP)
    "00041059": {
        "person_name": "Nandan Nilekani",
        "pep_category": "Domestic PEP",
        "pep_designation": "Former Chairman — UIDAI / Aadhaar (Cabinet rank)",
        "pep_jurisdiction": "India",
        "risk_level": "low",
        "sanctions_list_hit": False,
        "adverse_media_count": 0,
        "related_pep": False,
        "source": "Consolidated PEP List — MHA/FATF",
    },
    # D. Subbarao — Former RBI Governor, independent director on several boards
    "00387734": {
        "person_name": "Duvvuri Subbarao",
        "pep_category": "Domestic PEP",
        "pep_designation": "Former Governor — Reserve Bank of India",
        "pep_jurisdiction": "India",
        "risk_level": "low",
        "sanctions_list_hit": False,
        "adverse_media_count": 0,
        "related_pep": False,
        "source": "Consolidated PEP List — MHA/FATF",
    },
    # Rana Kapoor — Yes Bank fraud case
    "00019957": {
        "person_name": "Rana Kapoor",
        "pep_category": "Adverse Media",
        "pep_designation": "Former MD & CEO — Yes Bank (ED custody)",
        "pep_jurisdiction": "India",
        "risk_level": "critical",
        "sanctions_list_hit": False,
        "adverse_media_count": 45,
        "related_pep": False,
        "source": "Adverse Media Screening — Dow Jones / World-Check",
    },
    # G. Satheesh Reddy — Former DRDO Chairman, potential board member on defence companies
    "00112233": {
        "person_name": "G. Satheesh Reddy",
        "pep_category": "Domestic PEP",
        "pep_designation": "Former Chairman — DRDO / Scientific Adviser to Defence Minister",
        "pep_jurisdiction": "India",
        "risk_level": "medium",
        "sanctions_list_hit": False,
        "adverse_media_count": 0,
        "related_pep": True,
        "source": "Consolidated PEP List — MHA/FATF",
    },
    # Dr. Prathap C. Reddy — Apollo Hospitals founder, Padma Vibhushan, Rajya Sabha consideration
    "00003964": {
        "person_name": "Dr. Prathap C. Reddy",
        "pep_category": "Close Associate",
        "pep_designation": "Padma Vibhushan awardee — Government advisory roles in healthcare policy",
        "pep_jurisdiction": "India",
        "risk_level": "low",
        "sanctions_list_hit": False,
        "adverse_media_count": 0,
        "related_pep": False,
        "source": "Corporate PEP Watch — Advisory",
    },
}

_SANCTIONS_NAMES: set[str] = {
    "sanctioned person a",
    "sanctioned entity b",
    "nirav modi",
}

_ADVERSE_MEDIA_TRIGGERS: dict[str, int] = {
    "rana kapoor": 45,
    "vijay mallya": 32,
    "chanda kochhar": 18,
    "anil ambani": 14,
    "subhash chandra": 9,
}


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
