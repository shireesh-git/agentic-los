from __future__ import annotations

import re
from pathlib import Path


_ROLE_RULES: dict[str, dict] = {
    "audited_financial_statements": {
        "category": "financials",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "audited_financial_statements",
            "audited_financials",
            "annual_report_fy2024",
            "annual_report",
        },
        "keywords": (
            "audited",
            "annual report",
            "annual_report",
            "financial statements",
            "financial statement",
        ),
    },
    "provisional_financials": {
        "category": "financials",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "provisional_financials",
            "provisional_financials_fy2025",
            "management_financials",
            "unaudited_results",
        },
        "keywords": (
            "provisional",
            "management financial",
            "unaudited",
            "quarterly result",
            "quarterly results",
            "q1",
            "q2",
            "q3",
            "q4",
            "9m",
            "9 month",
        ),
    },
    "debt_schedule": {
        "category": "financials",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "debt_schedule",
            "existing_facility_details",
            "lender_wise_exposure",
        },
        "keywords": (
            "debt schedule",
            "debt_schedule",
            "lender wise",
            "lender-wise",
            "banking exposure",
            "facility details",
            "sanctioned",
            "outstanding",
        ),
    },
    "board_resolution": {
        "category": "kyc",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "board_resolution",
            "board_resolution_borrowing",
        },
        "keywords": (
            "board resolution",
            "borrowing resolution",
            "borrowing approval",
        ),
    },
    "cma_or_projection": {
        "category": "request",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "cma_data",
            "cma_or_projection",
            "cma_projection",
            "financial_projection",
            "projected_financials",
        },
        "keywords": (
            "cma",
            "projection",
            "projected financial",
            "projected cash flow",
            "repayment assumption",
        ),
    },
    "gst_registration": {
        "category": "gst",
        "extensions": {".pdf", ".xlsx", ".xls"},
        "exact_stems": {
            "gst_registration_certificate",
            "gstr3b_summary",
            "gstr1_summary",
        },
        "keywords": (
            "gst registration",
            "gst certificate",
            "gstr3b",
            "gstr1",
        ),
    },
    "exchange_filing": {
        "category": "exchange",
        "extensions": {".pdf", ".xlsx", ".xls"},
        "exact_stems": {
            "quarterly_results_q3fy2025",
            "quarterly_results",
            "exchange_filing",
        },
        "keywords": (
            "quarterly result",
            "quarterly results",
            "exchange filing",
            "investor release",
            "q1",
            "q2",
            "q3",
            "q4",
            "9m",
            "9 month",
        ),
    },
    "site_visit_report": {
        "category": "request",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "site_visit_report",
            "synthetic_site_visit_report",
            "field_visit_report",
            "branch_visit_report",
            "plant_visit_report",
        },
        "keywords": (
            "site visit",
            "site_visit",
            "field visit",
            "plant visit",
            "branch visit",
            "factory visit",
            "promoter meeting",
        ),
    },
    "valuation_report": {
        "category": "collateral",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "valuation_report",
            "synthetic_valuation_report",
            "property_valuation",
            "collateral_valuation",
        },
        "keywords": (
            "valuation",
            "property valuation",
            "collateral valuation",
            "forced sale value",
            "fsv",
            "market value",
            "fair value",
            "distress value",
        ),
    },
    "bank_statements": {
        "category": "banking",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "bank_statements",
            "synthetic_bank_statements",
            "bank_statement_fy2025",
            "bank_statement",
            "account_statement",
        },
        "keywords": (
            "bank statement",
            "bank_statement",
            "account statement",
            "account conduct",
            "bank conduct",
            "cbs extract",
        ),
    },
    "financial_projections": {
        "category": "request",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "financial_projections",
            "synthetic_cma_projection",
            "cma_data",
            "cma_projection",
            "projected_financials",
        },
        "keywords": (
            "financial projection",
            "cma",
            "projected cash flow",
            "repayment assumption",
            "projected financials",
            "projected p&l",
            "projected balance sheet",
        ),
    },
    "credit_facility_details": {
        "category": "banking",
        "extensions": {".pdf", ".xlsx", ".xls", ".csv"},
        "exact_stems": {
            "credit_facility_details",
            "synthetic_credit_facility_details",
            "facility_details",
            "sanction_details",
        },
        "keywords": (
            "credit facility",
            "facility detail",
            "sanction detail",
            "lender wise",
            "lender-wise",
            "existing exposure",
            "existing facility",
        ),
    },
    "internal_credit_notes": {
        "category": "misc",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "internal_credit_notes",
            "synthetic_internal_credit_notes",
            "credit_note",
            "analyst_note",
        },
        "keywords": (
            "credit note",
            "internal note",
            "analyst note",
            "rm note",
            "sanction memo",
            "approval note",
        ),
    },
    "property_documents": {
        "category": "collateral",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "property_documents",
            "synthetic_property_documents",
            "title_deed",
            "search_report",
            "encumbrance_certificate",
        },
        "keywords": (
            "title deed",
            "property document",
            "search report",
            "encumbrance",
            "title search",
            "conveyance deed",
        ),
    },
    "cersai_search": {
        "category": "legal",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "cersai_search",
            "synthetic_cersai_search",
            "cersai_report",
            "central_registry_search",
        },
        "keywords": (
            "cersai",
            "central registry",
            "securitisation",
            "security interest",
            "sarfaesi",
        ),
    },
    "insurance_policies": {
        "category": "collateral",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "insurance_policies",
            "synthetic_insurance_policies",
            "insurance_policy",
            "insurance_coverage",
        },
        "keywords": (
            "insurance polic",
            "insurance coverage",
            "key man insurance",
            "property insurance",
            "stock insurance",
            "fire insurance",
        ),
    },
    "undertakings": {
        "category": "legal",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "undertakings",
            "synthetic_undertakings",
            "non_default_declaration",
            "information_consent",
            "end_use_declaration",
        },
        "keywords": (
            "undertaking",
            "non-default",
            "non default",
            "information consent",
            "end use",
            "declaration",
        ),
    },
    "board_resolution_borrowing": {
        "category": "kyc",
        "extensions": {".pdf", ".doc", ".docx"},
        "exact_stems": {
            "board_resolution_borrowing",
            "synthetic_board_resolution_borrowing",
            "borrowing_resolution",
        },
        "keywords": (
            "board resolution",
            "borrowing resolution",
            "borrowing power",
            "borrowing approval",
        ),
    },
}


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def classify_document_role(category: str, filename: str) -> str | None:
    best_role = None
    best_score = 0
    for role in _ROLE_RULES:
        score = score_document_role(category, filename, role)
        if score > best_score:
            best_score = score
            best_role = role
    return best_role if best_score > 0 else None


def score_document_role(category: str, filename: str, role: str) -> int:
    rule = _ROLE_RULES.get(role)
    if not rule or category != rule["category"]:
        return 0

    path = Path(filename)
    stem = _normalize_name(path.stem)
    suffix = path.suffix.lower()
    if suffix not in rule["extensions"]:
        return 0

    score = 0
    if path.stem.lower() in rule["exact_stems"]:
        score += 80

    for keyword in rule["keywords"]:
        if keyword in stem:
            score += 15

    if score > 0:
        score += 5

    return score


def requirement_is_satisfied(category: str, filenames: list[str], role: str) -> bool:
    return any(score_document_role(category, filename, role) > 0 for filename in filenames)


def find_best_document(category_dir: Path, category: str, role: str) -> Path | None:
    if not category_dir.exists():
        return None

    best_path: Path | None = None
    best_key: tuple[int, float, str] | None = None
    for path in category_dir.iterdir():
        if not path.is_file():
            continue
        score = score_document_role(category, path.name, role)
        if score <= 0:
            continue
        rank = (score, path.stat().st_mtime, path.name.lower())
        if best_key is None or rank > best_key:
            best_key = rank
            best_path = path
    return best_path


def role_label(role: str | None) -> str:
    if not role:
        return "General Document"
    return role.replace("_", " ").title()
