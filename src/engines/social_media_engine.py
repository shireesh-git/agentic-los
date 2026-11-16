"""
Social Media & News Intelligence Engine
========================================
Deep analysis of social media sentiment, news signals, and reputation risk.
For NTB companies: web-sourced intelligence forms a critical decision factor.
For ETB companies: supplements existing relationship data.

In production, would integrate:
  - Twitter/X API for corporate mentions & sentiment
  - LinkedIn for hiring trends, employee reviews
  - Google News / NewsAPI for financial news
  - Glassdoor/AmbitionBox for employee sentiment
  - Reddit/financial forums for retail investor sentiment
  - BSE/NSE announcements for regulatory filings

No social-media source is connected yet: a borrower's profile is read from its data file when one is supplied,
and otherwise the analysis reports that it is not available (it never invents one).
"""

import logging
from datetime import date

_log = logging.getLogger(__name__)


def _on_record(entity_id: str) -> dict:
    """The borrower's social-media profile from its data file (``social_media``), when a source has supplied one.
    No profile is held in code: the made-up profiles for real companies were removed in round 8."""
    from src.data import borrowers
    try:
        return dict(borrowers.load(entity_id).get("social_media") or {})
    except FileNotFoundError:
        return {}


def analyze_social_media(entity_id: str, company_name: str, sector: str) -> dict:
    """
    Perform social media analysis for a company.
    Returns structured intelligence for CAM integration.
    """
    raw = _on_record(entity_id)
    if not raw:
        return {}                                        # no source connected: "not available", never a default

    # Compute risk flags from social data
    flags = []
    if raw["controversy_index"] > 0.50:
        flags.append({"flag": "High controversy index", "severity": "high",
                      "detail": f"Controversy score: {raw['controversy_index']:.2f} — significant negative media presence"})
    if raw["sentiment_score"] < -0.10:
        flags.append({"flag": "Negative social sentiment", "severity": "medium",
                      "detail": f"Overall sentiment score: {raw['sentiment_score']:.2f} — below neutral threshold"})
    if raw.get("glassdoor_rating", 4.0) < 3.3:
        flags.append({"flag": "Low employee satisfaction", "severity": "medium",
                      "detail": f"Glassdoor rating: {raw['glassdoor_rating']}/5 — below industry average"})

    # Extract negative themes
    negative_themes = [t for t in raw.get("top_themes", []) if t.get("sentiment", 0) < 0]
    if len(negative_themes) >= 2:
        flags.append({"flag": "Multiple negative themes in social media", "severity": "medium",
                      "detail": f"{len(negative_themes)} themes with negative sentiment detected"})

    # Compute reputation risk score (0-100, higher = riskier)
    rep_risk = min(100, max(0, int(raw["controversy_index"] * 100)))
    if raw["sentiment_score"] < 0:
        rep_risk += 15
    if raw.get("glassdoor_rating", 4.0) < 3.5:
        rep_risk += 10

    # Determine impact on credit decision
    if rep_risk >= 50:
        decision_impact = "ADVERSE — Social media signals indicate significant reputational risk. Enhanced due diligence required."
    elif rep_risk >= 25:
        decision_impact = "MODERATE — Some negative signals noted; monitoring recommended."
    else:
        decision_impact = "FAVORABLE — Positive social presence supports creditworthiness."

    return {
        "entity_id": entity_id,
        "company_name": company_name,
        "analysis_date": str(date.today()),
        "twitter_mentions_30d": raw["twitter_mentions_30d"],
        "overall_sentiment": {
            "score": raw["sentiment_score"],
            "label": raw["sentiment_label"],
        },
        "themes": raw.get("top_themes", []),
        "employee_intelligence": {
            "glassdoor_rating": raw["glassdoor_rating"],
            "reviews_count": raw["glassdoor_reviews_count"],
            "employee_sentiment": raw["employee_sentiment"],
            "hiring_trend": raw["hiring_trend"],
        },
        "digital_presence": {
            "linkedin_followers": raw["linkedin_followers"],
            "linkedin_engagement_rate": raw["linkedin_engagement_rate"],
        },
        "notable_mentions": raw.get("notable_posts", []),
        "regulatory_filings_sentiment": raw["regulatory_filings_sentiment"],
        "controversy_index": raw["controversy_index"],
        "reputation_risk_score": rep_risk,
        "risk_flags": flags,
        "decision_impact": decision_impact,
        "source_note": "From the borrower's data file (social_media); production would integrate the social APIs",
    }


def social_media_risk_score(social_data: dict) -> float:
    """
    Convert social media analysis into a 0-100 risk score for policy engine.
    0 = no risk, 100 = maximum reputational risk.
    """
    if not social_data:
        return 15.0  # Default — neutral (no data)

    score = social_data.get("reputation_risk_score", 15)
    return float(min(100, max(0, score)))


def social_media_summary_for_cam(social_data: dict) -> str:
    """Generate a one-paragraph summary for CAM narrative."""
    if not social_data:
        return "Social media analysis not available for this entity."

    name = social_data.get("company_name", "The company")
    sent = social_data.get("overall_sentiment", {})
    emp = social_data.get("employee_intelligence", {})
    flags = social_data.get("risk_flags", [])

    summary = (
        f"{name} has {social_data.get('twitter_mentions_30d', 0):,} social media mentions "
        f"in the last 30 days with an overall {sent.get('label', 'Neutral')} sentiment "
        f"(score: {sent.get('score', 0):.2f}). "
    )

    if emp.get("glassdoor_rating"):
        summary += (
            f"Employee sentiment is {emp.get('employee_sentiment', 'N/A')} "
            f"(Glassdoor: {emp['glassdoor_rating']}/5, {emp.get('reviews_count', 0):,} reviews). "
        )

    if flags:
        summary += f"Risk flags: {len(flags)} issue(s) noted — "
        summary += "; ".join(f["flag"] for f in flags[:3]) + ". "
    else:
        summary += "No significant reputation risk flags detected. "

    summary += social_data.get("decision_impact", "")
    return summary
