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

Mock mode returns sector- and entity-specific synthetic data
that feeds into CAM risk assessment and decision analysis.
"""

import logging
from datetime import date, timedelta

_log = logging.getLogger(__name__)


# ─── Social Media Sentiment Corpus ────────────────────────────────────────────

_ENTITY_SOCIAL_MEDIA = {
    "INFY001": {
        "twitter_mentions_30d": 12450,
        "sentiment_score": 0.72,  # -1 to +1
        "sentiment_label": "Positive",
        "top_themes": [
            {"theme": "AI & Generative AI investments", "mentions": 3200, "sentiment": 0.85},
            {"theme": "Large deal wins", "mentions": 2800, "sentiment": 0.90},
            {"theme": "Margin guidance concern", "mentions": 1800, "sentiment": -0.15},
            {"theme": "Employee attrition", "mentions": 1450, "sentiment": -0.35},
            {"theme": "Campus hiring commitments", "mentions": 980, "sentiment": 0.60},
        ],
        "glassdoor_rating": 3.8,
        "glassdoor_reviews_count": 42500,
        "employee_sentiment": "Moderately Positive",
        "hiring_trend": "Stable — selective hiring in AI/cloud",
        "linkedin_followers": 8500000,
        "linkedin_engagement_rate": 2.8,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-10",
             "content": "Infosys wins $1.5B deal from European bank for core modernization",
             "engagement": 4500, "sentiment": "Positive"},
            {"platform": "LinkedIn", "date": "2026-03-05",
             "content": "Infosys AI-first strategy: 50% workforce to be AI-skilled by 2027",
             "engagement": 12000, "sentiment": "Positive"},
            {"platform": "Reddit/r/IndianStockMarket", "date": "2026-02-28",
             "content": "Infosys Q3 results solid but margin pressure from wage hikes noted",
             "engagement": 850, "sentiment": "Neutral"},
        ],
        "regulatory_filings_sentiment": "Clean — no adverse SEBI observations",
        "controversy_index": 0.08,  # 0=clean, 1=heavily controversial
    },
    "DRRD001": {
        "twitter_mentions_30d": 3200,
        "sentiment_score": 0.65,
        "sentiment_label": "Positive",
        "top_themes": [
            {"theme": "USFDA approvals", "mentions": 1100, "sentiment": 0.88},
            {"theme": "Biosimilar pipeline progress", "mentions": 800, "sentiment": 0.75},
            {"theme": "API pricing stability", "mentions": 450, "sentiment": 0.40},
            {"theme": "Patent litigation risk", "mentions": 350, "sentiment": -0.30},
        ],
        "glassdoor_rating": 3.9,
        "glassdoor_reviews_count": 8500,
        "employee_sentiment": "Positive",
        "hiring_trend": "Growing — R&D and regulatory affairs",
        "linkedin_followers": 1200000,
        "linkedin_engagement_rate": 2.2,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-08",
             "content": "Dr. Reddy's receives tentative ANDA approval for blockbuster generic",
             "engagement": 1800, "sentiment": "Positive"},
            {"platform": "LinkedIn", "date": "2026-02-25",
             "content": "Dr. Reddy's expands biosimilar portfolio — partners with Fresenius Kabi",
             "engagement": 5200, "sentiment": "Positive"},
        ],
        "regulatory_filings_sentiment": "Clean — FDA inspections all cleared",
        "controversy_index": 0.05,
    },
    "IHCL001": {
        "twitter_mentions_30d": 8500,
        "sentiment_score": 0.78,
        "sentiment_label": "Positive",
        "top_themes": [
            {"theme": "New hotel openings & expansion", "mentions": 2800, "sentiment": 0.88},
            {"theme": "RevPAR growth and occupancy rates", "mentions": 1900, "sentiment": 0.82},
            {"theme": "Taj brand recognition globally", "mentions": 1500, "sentiment": 0.92},
            {"theme": "Sustainability initiatives", "mentions": 800, "sentiment": 0.70},
            {"theme": "Staff welfare programs", "mentions": 600, "sentiment": 0.85},
        ],
        "glassdoor_rating": 4.1,
        "glassdoor_reviews_count": 12000,
        "employee_sentiment": "Very Positive",
        "hiring_trend": "Expanding — 15,000 new hires planned",
        "linkedin_followers": 950000,
        "linkedin_engagement_rate": 3.1,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-12",
             "content": "IHCL crosses 300 hotels milestone — Taj brand now in 15 countries",
             "engagement": 6200, "sentiment": "Positive"},
            {"platform": "LinkedIn", "date": "2026-03-01",
             "content": "Indian Hotels wins 'World's Strongest Hotel Brand' by Brand Finance",
             "engagement": 18500, "sentiment": "Positive"},
            {"platform": "TripAdvisor", "date": "2026-02-20",
             "content": "Taj Palace Delhi ranked #1 luxury hotel in Asia-Pacific",
             "engagement": 3200, "sentiment": "Positive"},
        ],
        "regulatory_filings_sentiment": "Clean — compliant with all FHRAI/SEBI norms",
        "controversy_index": 0.03,
    },
    "YESB001": {
        "twitter_mentions_30d": 5800,
        "sentiment_score": -0.25,
        "sentiment_label": "Negative",
        "top_themes": [
            {"theme": "Governance concerns", "mentions": 2200, "sentiment": -0.65},
            {"theme": "NPA resolution progress", "mentions": 1500, "sentiment": 0.20},
            {"theme": "Regulatory actions", "mentions": 800, "sentiment": -0.80},
            {"theme": "Capital adequacy", "mentions": 650, "sentiment": -0.40},
            {"theme": "Recovery roadmap", "mentions": 400, "sentiment": 0.30},
        ],
        "glassdoor_rating": 3.2,
        "glassdoor_reviews_count": 15000,
        "employee_sentiment": "Below Average",
        "hiring_trend": "Flat — restructuring in progress",
        "linkedin_followers": 680000,
        "linkedin_engagement_rate": 1.5,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-05",
             "content": "RBI flags Yes Bank for delayed NPA recognition — stock drops 8%",
             "engagement": 12000, "sentiment": "Negative"},
            {"platform": "SEBI Filing", "date": "2026-02-28",
             "content": "Promoter pledge stands at 45% — market concerns on governance",
             "engagement": 0, "sentiment": "Negative"},
        ],
        "regulatory_filings_sentiment": "Adverse — multiple regulatory observations",
        "controversy_index": 0.72,
    },
    "DLFR001": {
        "twitter_mentions_30d": 2800,
        "sentiment_score": -0.10,
        "sentiment_label": "Neutral",
        "top_themes": [
            {"theme": "Real estate recovery", "mentions": 900, "sentiment": 0.45},
            {"theme": "Debt concerns", "mentions": 750, "sentiment": -0.55},
            {"theme": "New project launches", "mentions": 600, "sentiment": 0.60},
            {"theme": "RERA compliance", "mentions": 300, "sentiment": 0.30},
        ],
        "glassdoor_rating": 3.5,
        "glassdoor_reviews_count": 5500,
        "employee_sentiment": "Average",
        "hiring_trend": "Selective — project-based",
        "linkedin_followers": 320000,
        "linkedin_engagement_rate": 1.8,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-02",
             "content": "DLF launches ₹4,000 Cr luxury project in Gurugram — pre-bookings strong",
             "engagement": 2800, "sentiment": "Positive"},
        ],
        "regulatory_filings_sentiment": "Some concerns — delayed filings noted",
        "controversy_index": 0.35,
    },
    "APOL001": {
        "twitter_mentions_30d": 9200,
        "sentiment_score": 0.74,
        "sentiment_label": "Positive",
        "top_themes": [
            {"theme": "Hospital expansion in tier-2 cities", "mentions": 2600, "sentiment": 0.82},
            {"theme": "Medical tourism growth", "mentions": 1800, "sentiment": 0.88},
            {"theme": "Digital health & telemedicine", "mentions": 1500, "sentiment": 0.75},
            {"theme": "Doctor attrition & staffing costs", "mentions": 1200, "sentiment": -0.30},
            {"theme": "Ayushman Bharat & govt schemes", "mentions": 900, "sentiment": 0.60},
        ],
        "glassdoor_rating": 3.9,
        "glassdoor_reviews_count": 14500,
        "employee_sentiment": "Moderately Positive",
        "hiring_trend": "Growing — aggressive hiring for new hospitals",
        "linkedin_followers": 1800000,
        "linkedin_engagement_rate": 2.5,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-10",
             "content": "Apollo Hospitals crosses 12,000 beds milestone — largest private hospital network in India",
             "engagement": 5800, "sentiment": "Positive"},
            {"platform": "LinkedIn", "date": "2026-03-04",
             "content": "Apollo 24|7 digital health app crosses 30 million downloads — telemedicine leadership",
             "engagement": 8500, "sentiment": "Positive"},
            {"platform": "Reddit/r/IndianStockMarket", "date": "2026-02-22",
             "content": "Apollo Q3 results: ARPOB +12%, occupancy 72%, margins stable — solid quarter",
             "engagement": 1200, "sentiment": "Positive"},
        ],
        "regulatory_filings_sentiment": "Clean — NABH accredited, SEBI compliant",
        "controversy_index": 0.06,
    },
    "PNCR001": {
        "twitter_mentions_30d": 3800,
        "sentiment_score": 0.62,
        "sentiment_label": "Positive",
        "top_themes": [
            {"theme": "NHAI highway project wins", "mentions": 1200, "sentiment": 0.88},
            {"theme": "Expressway construction progress", "mentions": 950, "sentiment": 0.82},
            {"theme": "Order book growth & execution", "mentions": 680, "sentiment": 0.75},
            {"theme": "Rising input costs (bitumen, steel)", "mentions": 450, "sentiment": -0.35},
            {"theme": "HAM annuity income visibility", "mentions": 320, "sentiment": 0.70},
        ],
        "glassdoor_rating": 3.7,
        "glassdoor_reviews_count": 2800,
        "employee_sentiment": "Moderately Positive",
        "hiring_trend": "Growing — project engineers & site managers in demand",
        "linkedin_followers": 185000,
        "linkedin_engagement_rate": 2.1,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-15",
             "content": "PNC Infratech bags ₹2,400 Cr NHAI highway project in Uttar Pradesh — order book crosses ₹27,000 Cr",
             "engagement": 2400, "sentiment": "Positive"},
            {"platform": "LinkedIn", "date": "2026-03-08",
             "content": "PNC Infratech completes 220 km NH-44 4-laning ahead of schedule; receives ₹45 Cr NHAI early completion bonus",
             "engagement": 5600, "sentiment": "Positive"},
            {"platform": "Economic Times", "date": "2026-02-20",
             "content": "CARE reaffirms AA+/Stable on PNC Infratech citing strong order book at 3.2x book-to-bill",
             "engagement": 1800, "sentiment": "Positive"},
        ],
        "regulatory_filings_sentiment": "Clean — compliant with SEBI, MCA, and NHAI norms",
        "controversy_index": 0.08,
    },
    "MRF001": {
        "twitter_mentions_30d": 4500,
        "sentiment_score": 0.68,
        "sentiment_label": "Positive",
        "top_themes": [
            {"theme": "Premium tyre segment growth", "mentions": 1500, "sentiment": 0.80},
            {"theme": "Motorsport & brand visibility", "mentions": 1200, "sentiment": 0.90},
            {"theme": "Raw material cost pressure", "mentions": 800, "sentiment": -0.25},
            {"theme": "Capacity expansion plans", "mentions": 600, "sentiment": 0.65},
        ],
        "glassdoor_rating": 3.8,
        "glassdoor_reviews_count": 4200,
        "employee_sentiment": "Moderately Positive",
        "hiring_trend": "Stable — plant expansion hiring",
        "linkedin_followers": 420000,
        "linkedin_engagement_rate": 2.0,
        "notable_posts": [
            {"platform": "Twitter/X", "date": "2026-03-12",
             "content": "MRF retains leadership in premium passenger tyre segment — market share at 24%",
             "engagement": 3200, "sentiment": "Positive"},
        ],
        "regulatory_filings_sentiment": "Clean — compliant with all regulatory norms",
        "controversy_index": 0.05,
    },
    "MFL001": {
        "twitter_mentions_30d": 680,
        "sentiment_score": 0.15,
        "sentiment_label": "Neutral",
        "top_themes": [
            {"theme": "Urea production & government subsidy", "mentions": 280, "sentiment": 0.30},
            {"theme": "PSU governance concerns", "mentions": 180, "sentiment": -0.20},
            {"theme": "Environmental compliance", "mentions": 120, "sentiment": -0.15},
        ],
        "glassdoor_rating": 3.4,
        "glassdoor_reviews_count": 850,
        "employee_sentiment": "Average",
        "hiring_trend": "Flat — government hiring norms",
        "linkedin_followers": 45000,
        "linkedin_engagement_rate": 1.2,
        "notable_posts": [],
        "regulatory_filings_sentiment": "Some delays — PSU filing cadence",
        "controversy_index": 0.18,
    },
}

_DEFAULT_SOCIAL = {
    "twitter_mentions_30d": 500,
    "sentiment_score": 0.30,
    "sentiment_label": "Neutral",
    "top_themes": [],
    "glassdoor_rating": 3.5,
    "glassdoor_reviews_count": 0,
    "employee_sentiment": "Not Available",
    "hiring_trend": "Unknown",
    "linkedin_followers": 0,
    "linkedin_engagement_rate": 0.0,
    "notable_posts": [],
    "regulatory_filings_sentiment": "Not Available",
    "controversy_index": 0.15,
}


def analyze_social_media(entity_id: str, company_name: str, sector: str) -> dict:
    """
    Perform social media analysis for a company.
    Returns structured intelligence for CAM integration.
    """
    raw = _ENTITY_SOCIAL_MEDIA.get(entity_id, _DEFAULT_SOCIAL)

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
        "source_note": "Mock data — production would integrate Twitter API, LinkedIn API, Glassdoor, NewsAPI",
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
