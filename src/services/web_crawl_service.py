"""
Web Crawling Service — News & market intelligence for NTB companies.

In production, this would:
  - Call Google News API / NewsAPI / Bing News Search
  - Scrape financial news portals (ET, BS, Mint, Moneycontrol)
  - Run NLP sentiment analysis on articles
  - Cache results with TTL

For mock mode, returns sector-specific synthetic news articles
that feed into CAM Section 3.5 (Recent News & Market Intelligence)
and SWOT analysis.
"""

import logging
from datetime import date

_log = logging.getLogger(__name__)


# ─── Sector-specific news corpus ──────────────────────────────────────────────

_SECTOR_NEWS = {
    "manufacturing": [
        {"date": "2026-02-28", "headline": "{name} announces capacity expansion plan worth ₹500 Cr",
         "sentiment": "Positive", "source": "Economic Times", "category": "Expansion",
         "summary": "Company plans to double manufacturing capacity with a ₹500 Cr greenfield plant in Gujarat, expected to be operational by Q2 FY2028."},
        {"date": "2026-02-15", "headline": "{name} bags ₹200 Cr order from defence sector",
         "sentiment": "Positive", "source": "Business Standard", "category": "Orders",
         "summary": "New defence order strengthens order book visibility for next 18 months."},
        {"date": "2026-01-20", "headline": "PLI scheme to benefit companies like {name} — Industry body",
         "sentiment": "Positive", "source": "Mint", "category": "Policy",
         "summary": "Production-linked incentive scheme in manufacturing expected to boost revenue 8-12% for eligible companies."},
        {"date": "2026-01-05", "headline": "Raw material costs rise 8% QoQ impacting manufacturing margins",
         "sentiment": "Negative", "source": "CNBC-TV18", "category": "Costs",
         "summary": "Steel and aluminum price surge drives input cost inflation across the manufacturing sector."},
        {"date": "2025-12-18", "headline": "{name} posts 12% revenue growth in H1 FY2026",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Financial",
         "summary": "First half revenue growth driven by strong domestic demand and export orders."},
        {"date": "2025-12-01", "headline": "{name} receives BIS certification for new product line",
         "sentiment": "Positive", "source": "Financial Express", "category": "Regulatory",
         "summary": "BIS certification opens access to government procurement and institutional markets."},
        {"date": "2025-11-15", "headline": "India manufacturing PMI hits 57.2 — strong expansion",
         "sentiment": "Positive", "source": "Reuters", "category": "Macro",
         "summary": "Manufacturing sector continues to expand with strong new order inflows."},
    ],
    "infrastructure": [
        {"date": "2026-02-25", "headline": "{name} wins NHAI highway project worth ₹800 Cr",
         "sentiment": "Positive", "source": "Economic Times", "category": "Orders",
         "summary": "Highway EPC contract with NHAI for 4-lane expressway in Rajasthan, 36-month execution timeline."},
        {"date": "2026-02-10", "headline": "Order book of {name} crosses ₹5,000 Cr milestone",
         "sentiment": "Positive", "source": "Business Standard", "category": "Orders",
         "summary": "Strong order book provides revenue visibility for next 3 years at current execution capacity."},
        {"date": "2026-01-22", "headline": "Infrastructure spending in Union Budget 2026 — positive for sector",
         "sentiment": "Positive", "source": "Mint", "category": "Policy",
         "summary": "Government allocates ₹12.5 lakh Cr for capital expenditure, benefiting construction and EPC companies."},
        {"date": "2026-01-08", "headline": "Steel prices surge 15% — cost pressure on EPC companies",
         "sentiment": "Negative", "source": "Reuters", "category": "Costs",
         "summary": "Rising steel costs squeeze margins for fixed-price EPC contracts."},
        {"date": "2025-12-20", "headline": "{name} receives rating upgrade from CARE",
         "sentiment": "Positive", "source": "CARE Ratings", "category": "Rating",
         "summary": "Rating upgrade to A+ reflects improved financial profile and strong order pipeline."},
        {"date": "2025-12-05", "headline": "{name} completes ₹300 Cr project 2 months ahead of schedule",
         "sentiment": "Positive", "source": "Construction World", "category": "Execution",
         "summary": "Early project completion demonstrates strong execution capability and earns incentive bonus."},
        {"date": "2025-11-18", "headline": "Cement prices stabilize — relief for infrastructure companies",
         "sentiment": "Positive", "source": "Financial Express", "category": "Costs",
         "summary": "Cement price correction after 6 months of sustained increases."},
    ],
    "pharma": [
        {"date": "2026-02-27", "headline": "{name} receives USFDA approval for key generic drug",
         "sentiment": "Positive", "source": "Economic Times", "category": "Regulatory",
         "summary": "ANDA approval for cardiovascular generic opens $500M addressable market in US."},
        {"date": "2026-02-12", "headline": "{name} expands CDMO capacity with new facility",
         "sentiment": "Positive", "source": "Business Standard", "category": "Expansion",
         "summary": "New CDMO facility in Hyderabad will serve global pharma clients, revenue expected from FY2028."},
        {"date": "2026-01-18", "headline": "DPCO ceiling prices revised — mixed impact on pharma sector",
         "sentiment": "Neutral", "source": "Mint", "category": "Policy",
         "summary": "Drug Price Control Order revision affects 350+ formulations, some margin compression expected."},
        {"date": "2026-01-03", "headline": "API prices from China stabilize after 6-month volatility",
         "sentiment": "Positive", "source": "Pharma Times", "category": "Costs",
         "summary": "Raw material cost normalization expected to improve gross margins by 100-150 bps."},
        {"date": "2025-12-15", "headline": "{name} partners with global MNC for biosimilar development",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Strategic",
         "summary": "Biosimilar partnership brings upfront payment and royalty income stream."},
        {"date": "2025-12-02", "headline": "{name} clears WHO prequalification for 3 products",
         "sentiment": "Positive", "source": "Pharma World", "category": "Regulatory",
         "summary": "WHO PQ opens institutional tender market in Africa and South-East Asia."},
        {"date": "2025-11-20", "headline": "Indian pharma exports grow 11% in H1 FY2026",
         "sentiment": "Positive", "source": "Reuters", "category": "Macro",
         "summary": "Generic exports to US, Europe and Africa drive industry growth."},
    ],
    "logistics": [
        {"date": "2026-02-26", "headline": "{name} adds 2 million sq ft warehousing capacity",
         "sentiment": "Positive", "source": "Economic Times", "category": "Expansion",
         "summary": "Warehouse expansion in Delhi-NCR and Mumbai strengthens last-mile delivery network."},
        {"date": "2026-02-11", "headline": "{name} adopts AI-driven route optimization — cuts costs 12%",
         "sentiment": "Positive", "source": "Business Standard", "category": "Technology",
         "summary": "AI-based fleet management reduces fuel costs and improves delivery timelines."},
        {"date": "2026-01-19", "headline": "National Logistics Policy implementation shows early results",
         "sentiment": "Positive", "source": "Mint", "category": "Policy",
         "summary": "Unified logistics interface reduces transit time by 10-15% for organized players."},
        {"date": "2026-01-04", "headline": "Diesel prices rise 5% — logistics margins under pressure",
         "sentiment": "Negative", "source": "Reuters", "category": "Costs",
         "summary": "Fuel cost increase impacts margins for companies without fuel surcharge pass-through."},
        {"date": "2025-12-17", "headline": "{name} enters cold chain logistics segment",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Expansion",
         "summary": "Cold chain entry targets pharma and food segments with higher margins."},
        {"date": "2025-12-03", "headline": "{name} achieves 98.5% on-time delivery rate",
         "sentiment": "Positive", "source": "Logistics Insider", "category": "Operations",
         "summary": "Industry-leading delivery rate attracts premium e-commerce clients."},
        {"date": "2025-11-19", "headline": "E-commerce growth fuels 20% surge in express logistics demand",
         "sentiment": "Positive", "source": "Financial Express", "category": "Macro",
         "summary": "Rising online retail volumes create strong tailwinds for organized logistics."},
    ],
    "hospitality": [
        {"date": "2026-02-27", "headline": "{name} reports record RevPAR of ₹8,200 in Q3 FY2026",
         "sentiment": "Positive", "source": "Economic Times", "category": "Financial",
         "summary": "Revenue per available room surpasses pre-COVID levels by 35%, driven by strong leisure and MICE demand."},
        {"date": "2026-02-14", "headline": "{name} expands portfolio with 5 new managed hotels",
         "sentiment": "Positive", "source": "Business Standard", "category": "Expansion",
         "summary": "Asset-light strategy continues with managed/franchised properties in tier-2 cities."},
        {"date": "2026-01-25", "headline": "Inbound tourism to India hits new high — 12 million visitors in CY2025",
         "sentiment": "Positive", "source": "Mint", "category": "Macro",
         "summary": "India tourism growth benefits premium hotel chains with international clientele."},
        {"date": "2026-01-10", "headline": "OTA commission costs squeeze hotel margins across the industry",
         "sentiment": "Negative", "source": "Hospitality Biz India", "category": "Costs",
         "summary": "Online travel aggregator commissions averaging 18% erode direct booking margins for mid-segment hotels."},
        {"date": "2025-12-22", "headline": "{name} wins 'Best Luxury Hotel Brand' at World Travel Awards",
         "sentiment": "Positive", "source": "Travel + Leisure India", "category": "Brand",
         "summary": "Global recognition strengthens brand equity and premium pricing power."},
        {"date": "2025-12-08", "headline": "{name} launches sustainability initiative — targets net-zero by 2035",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "ESG",
         "summary": "ESG commitment including solar, water recycling, and local sourcing initiatives across properties."},
        {"date": "2025-11-20", "headline": "India hotel supply-demand gap widens — ADR expected to rise 12% YoY",
         "sentiment": "Positive", "source": "CRISIL", "category": "Macro",
         "summary": "Limited new supply in key markets supports RevPAR growth for existing operators."},
    ],
    "it_services": [
        {"date": "2026-02-25", "headline": "{name} bags $500M digital transformation deal with Fortune 100 client",
         "sentiment": "Positive", "source": "Economic Times", "category": "Orders",
         "summary": "Multi-year cloud migration and AI deal strengthens large deal pipeline and revenue visibility."},
        {"date": "2026-02-10", "headline": "{name} reports 4.2% QoQ revenue growth in Q3 FY2026",
         "sentiment": "Positive", "source": "Business Standard", "category": "Financial",
         "summary": "Sequential growth led by BFSI and healthcare verticals; utilization at 83%."},
        {"date": "2026-01-22", "headline": "GenAI adoption drives 25% growth in digital services revenue for IT majors",
         "sentiment": "Positive", "source": "Mint", "category": "Technology",
         "summary": "Enterprise demand for AI/ML consulting, data engineering, and GenAI solutions accelerating."},
        {"date": "2026-01-08", "headline": "H-1B visa policy uncertainty — potential headwind for Indian IT companies",
         "sentiment": "Negative", "source": "Reuters", "category": "Policy",
         "summary": "Proposed visa restrictions could increase onshore delivery costs by 8-12% for affected companies."},
        {"date": "2025-12-18", "headline": "{name} attrition rate falls to 12.8% — lowest in 3 years",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Operations",
         "summary": "Improving attrition reduces hiring costs and improves project delivery quality."},
        {"date": "2025-12-05", "headline": "IT industry adds 60,000 new jobs in H1 FY2026 — NASSCOM",
         "sentiment": "Positive", "source": "NASSCOM", "category": "Macro",
         "summary": "Industry hiring recovery confirms cyclical upturn in demand environment."},
        {"date": "2025-11-18", "headline": "{name} opens new delivery centre in Poland to serve European clients",
         "sentiment": "Positive", "source": "Financial Express", "category": "Expansion",
         "summary": "Near-shore presence in Europe reduces client concerns around data residency and travel costs."},
    ],
    "nbfc": [
        {"date": "2026-02-26", "headline": "{name} AUM grows 22% YoY to ₹45,000 Cr in Q3 FY2026",
         "sentiment": "Positive", "source": "Economic Times", "category": "Financial",
         "summary": "Strong AUM growth across vehicle finance and MSME lending segments."},
        {"date": "2026-02-12", "headline": "{name} completes ₹2,000 Cr NCD issuance at attractive spreads",
         "sentiment": "Positive", "source": "Business Standard", "category": "Funding",
         "summary": "Strong investor demand reflects confidence in credit quality; coupon at 8.5% for 3-year."},
        {"date": "2026-01-20", "headline": "RBI tightens unsecured lending norms — risk weights hiked to 125%",
         "sentiment": "Negative", "source": "Mint", "category": "Policy",
         "summary": "Regulatory action increases capital requirements for unsecured personal and consumer loans."},
        {"date": "2026-01-05", "headline": "{name} GNPA declines to 1.9% — asset quality improving",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Financial",
         "summary": "Improving asset quality driven by better underwriting and collection efficiency."},
        {"date": "2025-12-15", "headline": "{name} enters co-lending with 3 PSU banks",
         "sentiment": "Positive", "source": "Financial Express", "category": "Strategic",
         "summary": "Co-lending partnerships reduce funding costs by 100-150 bps and expand distribution reach."},
        {"date": "2025-12-01", "headline": "Fintech competition intensifies in digital lending space",
         "sentiment": "Negative", "source": "Business Standard", "category": "Competition",
         "summary": "Digital-first lenders with lower CAC threaten market share in small-ticket segments."},
        {"date": "2025-11-18", "headline": "NBFC sector AUM crosses ₹45 lakh Cr — ICRA report",
         "sentiment": "Positive", "source": "ICRA", "category": "Macro",
         "summary": "Sector growth demonstrates critical role of NBFCs in financial inclusion and credit delivery."},
    ],
    "real_estate": [
        {"date": "2026-02-28", "headline": "{name} launches premium residential project worth ₹1,200 Cr in Mumbai",
         "sentiment": "Positive", "source": "Economic Times", "category": "Expansion",
         "summary": "Premium segment project targets HNI buyers; 40% pre-sold at launch."},
        {"date": "2026-02-15", "headline": "{name} pre-sales surge 35% YoY in H1 FY2026",
         "sentiment": "Positive", "source": "Business Standard", "category": "Financial",
         "summary": "Strong pre-sales provide revenue visibility and improve cash flow predictability."},
        {"date": "2026-01-18", "headline": "Residential sales in top 7 cities cross 3.5 lakh units — new record",
         "sentiment": "Positive", "source": "Knight Frank", "category": "Macro",
         "summary": "India real estate market continues recovery with all-time-high sales volumes in CY2025."},
        {"date": "2026-01-05", "headline": "Rising construction costs impact developer margins — steel +15% YoY",
         "sentiment": "Negative", "source": "Mint", "category": "Costs",
         "summary": "Input cost inflation compresses margins for fixed-price projects where price revisions are limited."},
        {"date": "2025-12-20", "headline": "{name} earns LEED Platinum certification for commercial tower",
         "sentiment": "Positive", "source": "Construction World", "category": "ESG",
         "summary": "Green building certification attracts MNC tenants willing to pay rental premium."},
        {"date": "2025-12-05", "headline": "{name} reduces net debt by ₹500 Cr through QIP and land monetization",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Financial",
         "summary": "Balance sheet deleveraging improves debt-equity and rating trajectory."},
        {"date": "2025-11-20", "headline": "RERA compliance improves buyer confidence — registrations up 18%",
         "sentiment": "Positive", "source": "ANAROCK", "category": "Regulatory",
         "summary": "Regulatory environment favouring organized developers with track record of compliance."},
    ],
    "energy": [
        {"date": "2026-02-27", "headline": "{name} commissions 500 MW solar power plant in Rajasthan",
         "sentiment": "Positive", "source": "Economic Times", "category": "Expansion",
         "summary": "Renewable energy capacity addition supports ESG credentials and long-term PPA revenue."},
        {"date": "2026-02-10", "headline": "{name} reports record PLF of 87% across thermal fleet",
         "sentiment": "Positive", "source": "Business Standard", "category": "Operations",
         "summary": "High plant load factor demonstrates operational efficiency and supports revenue stability."},
        {"date": "2026-01-22", "headline": "India power demand grows 8% YoY — industrial recovery drives consumption",
         "sentiment": "Positive", "source": "Mint", "category": "Macro",
         "summary": "Rising electricity demand from manufacturing, data centres, and EVs benefits power generators."},
        {"date": "2026-01-05", "headline": "Coal import prices rise 12% — cost pressure on thermal power producers",
         "sentiment": "Negative", "source": "Reuters", "category": "Costs",
         "summary": "Imported coal dependency increases fuel costs for non-linkage based thermal plants."},
        {"date": "2025-12-18", "headline": "{name} wins government bid for 1,000 MW green hydrogen project",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Strategic",
         "summary": "Green hydrogen pilot positions company for next-generation clean energy markets."},
        {"date": "2025-12-03", "headline": "{name} maintains AAA credit rating with stable outlook",
         "sentiment": "Positive", "source": "CRISIL", "category": "Rating",
         "summary": "Highest credit rating reflects strong balance sheet, government ownership, and stable cash flows."},
        {"date": "2025-11-18", "headline": "India targets 500 GW renewable energy capacity by 2030",
         "sentiment": "Positive", "source": "MNRE", "category": "Policy",
         "summary": "Ambitious renewable target creates long-term capex opportunity for energy companies."},
    ],
    "trading": [
        {"date": "2026-02-25", "headline": "{name} reports 18% revenue growth driven by festive season demand",
         "sentiment": "Positive", "source": "Economic Times", "category": "Financial",
         "summary": "Festive quarter drives strong same-store-sales growth across retail outlets."},
        {"date": "2026-02-10", "headline": "{name} expands to 50 new stores in tier-2 and tier-3 cities",
         "sentiment": "Positive", "source": "Business Standard", "category": "Expansion",
         "summary": "Aggressive store expansion in smaller cities captures growing aspirational consumer base."},
        {"date": "2026-01-18", "headline": "India retail market expected to reach $2 trillion by 2032 — Deloitte",
         "sentiment": "Positive", "source": "Mint", "category": "Macro",
         "summary": "Large addressable market with rising organized retail penetration from 12% to 25%."},
        {"date": "2026-01-04", "headline": "E-commerce competition puts pressure on offline retail margins",
         "sentiment": "Negative", "source": "Financial Express", "category": "Competition",
         "summary": "Quick commerce and e-commerce discounting force brick-and-mortar to invest in omnichannel."},
        {"date": "2025-12-15", "headline": "{name} launches private label brand — margin accretive",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Strategic",
         "summary": "Private labels typically deliver 10-15% higher gross margins than third-party brands."},
    ],
    "healthcare": [
        {"date": "2026-02-28", "headline": "{name} expands hospital network with 3 new facilities in tier-2 cities",
         "sentiment": "Positive", "source": "Economic Times", "category": "Expansion",
         "summary": "New 500-bed hospitals in Lucknow, Bhubaneswar, and Visakhapatnam to serve underserved regions."},
        {"date": "2026-02-14", "headline": "{name} reports 18% revenue growth in Q3 FY2026 driven by higher occupancy",
         "sentiment": "Positive", "source": "Business Standard", "category": "Financial",
         "summary": "Average Revenue Per Occupied Bed (ARPOB) rises 12% YoY; overall occupancy at 72%."},
        {"date": "2026-01-25", "headline": "Ayushman Bharat expansion to cover more procedures — positive for hospital chains",
         "sentiment": "Positive", "source": "Mint", "category": "Policy",
         "summary": "Government health insurance expansion increases addressable patient pool for empanelled hospitals."},
        {"date": "2026-01-10", "headline": "Doctor and nursing staff costs rise 14% YoY — margin pressure for hospitals",
         "sentiment": "Negative", "source": "CNBC-TV18", "category": "Costs",
         "summary": "Talent shortage in healthcare drives wage inflation, impacting EBITDA margins by 100-150 bps."},
        {"date": "2025-12-20", "headline": "{name} launches digital health platform for remote consultations",
         "sentiment": "Positive", "source": "Moneycontrol", "category": "Technology",
         "summary": "Telemedicine platform enables 50,000+ monthly consultations, expanding reach beyond physical locations."},
        {"date": "2025-12-05", "headline": "{name} receives JCI accreditation for 5 more hospitals",
         "sentiment": "Positive", "source": "Healthcare Executive", "category": "Regulatory",
         "summary": "Joint Commission International accreditation strengthens medical tourism revenue and brand credibility."},
        {"date": "2025-11-18", "headline": "India healthcare sector to reach $372 billion by 2027 — NITI Aayog report",
         "sentiment": "Positive", "source": "Reuters", "category": "Macro",
         "summary": "Growing middle class, health insurance penetration, and medical tourism drive sector growth."},
    ],
}

_DEFAULT_NEWS = [
    {"date": "2026-02-20", "headline": "{name} reports steady growth in latest quarter",
     "sentiment": "Positive", "source": "Economic Times", "category": "Financial",
     "summary": "Quarterly results show consistent revenue and profit growth trajectory."},
    {"date": "2026-01-15", "headline": "Sector outlook stable — rating agency report",
     "sentiment": "Neutral", "source": "CRISIL", "category": "Rating",
     "summary": "Industry credit outlook remains stable with adequate growth prospects."},
    {"date": "2025-12-10", "headline": "{name} plans expansion in new geography",
     "sentiment": "Positive", "source": "Business Standard", "category": "Expansion",
     "summary": "Geographic diversification expected to drive next phase of growth."},
]


def crawl_company_news(company_name: str, sector: str, is_ntb: bool = True,
                       max_articles: int = 7) -> dict:
    """
    Crawl/fetch news for a company. In production, would call real news APIs.
    Returns structured news data for CAM integration.

    Args:
        company_name: Name of the company to search for
        sector: Industry sector for relevant news
        is_ntb: Whether this is a New-to-Bank customer (gets more thorough search)
        max_articles: Maximum number of articles to return
    """
    sector_lower = sector.lower() if sector else ""
    news_corpus = _SECTOR_NEWS.get(sector_lower, _DEFAULT_NEWS)

    articles = []
    for item in news_corpus[:max_articles]:
        article = {k: v for k, v in item.items()}
        article["headline"] = article["headline"].format(name=company_name)
        if "summary" in article:
            article["summary"] = article["summary"].format(name=company_name)
        articles.append(article)

    # Compute sentiment summary
    pos = sum(1 for a in articles if a.get("sentiment") == "Positive")
    neg = sum(1 for a in articles if a.get("sentiment") == "Negative")
    neu = sum(1 for a in articles if a.get("sentiment") == "Neutral")

    sentiment_label = "Positive" if pos > neg + neu else ("Negative" if neg > pos else "Neutral")

    return {
        "company_name": company_name,
        "sector": sector,
        "is_ntb": is_ntb,
        "articles_found": len(articles),
        "articles": articles,
        "sentiment_summary": {
            "positive": pos,
            "negative": neg,
            "neutral": neu,
            "overall": sentiment_label,
        },
        "source_note": "Mock data — production would integrate Google News API / NewsAPI",
        "crawl_date": str(date.today()),
    }


def build_swot_from_news(news_data: dict) -> dict:
    """
    Extract SWOT signals from news articles.
    Uses keyword matching on headlines and categories.
    In production, would use NLP/LLM for extraction.
    """
    strengths, weaknesses, opportunities, threats = [], [], [], []

    for article in news_data.get("articles", []):
        headline = article.get("headline", "")
        sentiment = article.get("sentiment", "")
        category = article.get("category", "")

        if sentiment == "Positive":
            if category in ("Orders", "Execution", "Operations"):
                strengths.append(headline)
            elif category in ("Expansion", "Strategic", "Technology"):
                opportunities.append(headline)
            elif category in ("Policy", "Macro"):
                opportunities.append(headline)
            else:
                strengths.append(headline)
        elif sentiment == "Negative":
            if category == "Costs":
                threats.append(headline)
            else:
                weaknesses.append(headline)
        else:
            opportunities.append(headline)

    return {
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "opportunities": opportunities[:3],
        "threats": threats[:3],
    }
