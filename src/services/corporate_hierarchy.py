"""
Corporate Hierarchy & Web Scraping Service
=============================================
Builds corporate hierarchy trees from MCA director linkages.
Stubs for web-scraped financials of parent/subsidiary companies.

In production, these would call MCA V3 API, BSE/NSE EDIFAR, and
company websites. For POC, uses deterministic mock data.
"""

from dataclasses import asdict
from typing import Optional

from src.models.canonical_model import CorporateNode, GroupEntity, DirectorPromoter



def scrape_company_financials(company_name: str) -> dict:
    """Stub — returns empty financials. Real data comes from Probe42."""
    return {
        "revenue_cr": None, "pat_cr": None, "net_worth_cr": None,
        "total_debt_cr": None, "credit_rating": None, "sector": "Unknown",
    }


def build_corporate_hierarchy(entity_id: str, borrower, directors: list,
                              group: Optional[GroupEntity] = None) -> list:
    """
    Build corporate hierarchy tree from MCA director linkages.
    Returns list of CorporateNode trees (roots).
    """
    # Self node
    self_node = CorporateNode(
        entity_id=entity_id,
        company_name=borrower.company_name,
        relationship="self",
        holding_pct=100.0,
        cin=borrower.cin,
        pan=borrower.pan,
        sector=borrower.sector.value if hasattr(borrower.sector, "value") else str(borrower.sector),
    )

    # Gather related entities from director linkages
    related_companies = {}
    for d in directors:
        if d.other_directorships:
            for company_name in d.other_directorships:
                if company_name not in related_companies:
                    fin = scrape_company_financials(company_name)
                    related_companies[company_name] = CorporateNode(
                        entity_id="",
                        company_name=company_name,
                        relationship="associate",
                        holding_pct=0.0,
                        sector=fin.get("sector", ""),
                        revenue_cr=fin.get("revenue_cr"),
                        pat_cr=fin.get("pat_cr"),
                        net_worth_cr=fin.get("net_worth_cr"),
                        total_debt_cr=fin.get("total_debt_cr"),
                        credit_rating=fin.get("credit_rating"),
                    )

    # Classify relationships based on promoter holdings
    subsidiaries = []
    associates = []
    for name, node in related_companies.items():
        # Heuristic: if multiple promoter directors, likely subsidiary
        director_count = sum(
            1 for d in directors
            if d.is_promoter and name in (d.other_directorships or [])
        )
        if director_count >= 2:
            node.relationship = "subsidiary"
            node.holding_pct = min(75.0, director_count * 25.0)
            subsidiaries.append(node)
        else:
            node.relationship = "associate"
            associates.append(node)

    self_node.children = subsidiaries + associates

    # Calculate group-level aggregates
    group_revenue = sum(
        n.revenue_cr for n in related_companies.values()
        if n.revenue_cr is not None
    )
    group_net_worth = sum(
        n.net_worth_cr for n in related_companies.values()
        if n.net_worth_cr is not None
    )
    group_debt = sum(
        n.total_debt_cr for n in related_companies.values()
        if n.total_debt_cr is not None
    )

    return [self_node], group_revenue, group_net_worth, group_debt


def hierarchy_to_dict(nodes: list) -> list:
    """Convert CorporateNode trees to serializable dicts."""
    result = []
    for node in nodes:
        d = {
            "entity_id": node.entity_id,
            "company_name": node.company_name,
            "relationship": node.relationship,
            "holding_pct": node.holding_pct,
            "cin": node.cin,
            "pan": node.pan,
            "sector": node.sector,
            "revenue_cr": node.revenue_cr,
            "pat_cr": node.pat_cr,
            "net_worth_cr": node.net_worth_cr,
            "total_debt_cr": node.total_debt_cr,
            "credit_rating": node.credit_rating,
            "children": hierarchy_to_dict(node.children) if node.children else [],
        }
        result.append(d)
    return result


def enrich_group_with_hierarchy(company_data: dict) -> dict:
    """
    Enrich company_data with corporate hierarchy.
    Mutates and returns company_data.
    """
    borrower = company_data.get("borrower")
    directors = company_data.get("directors", [])
    group = company_data.get("group")

    if not borrower:
        return company_data

    hierarchy, group_rev, group_nw, group_debt = build_corporate_hierarchy(
        borrower.entity_id, borrower, directors, group
    )

    if group:
        group.hierarchy = hierarchy
        group.group_revenue_cr = group_rev
        group.group_net_worth_cr = group_nw
        group.group_total_debt_cr = group_debt
        group.ultimate_parent = borrower.company_name

    company_data["corporate_hierarchy"] = hierarchy_to_dict(hierarchy)
    return company_data
