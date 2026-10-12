"""
Mock External API stubs — All functions return not_found responses.
Actual data is sourced from Probe42 MCP bundle.
"""

import logging
from datetime import date

_log = logging.getLogger(__name__)


def _today():
    return date.today().isoformat()


def _not_found(source: str, record_type: str, entity_key: str) -> dict:
    return {
        "source": source,
        "record_type": record_type,
        "entity_key": entity_key,
        "as_of_date": _today(),
        "payload_version": "v2",
        "source_status": "not_found",
        "payload": {},
    }


def mock_mca_company_master(cin: str) -> dict:
    return _not_found("mca", "company_master", cin)


def mock_mca_directors(cin: str) -> dict:
    return _not_found("mca", "directors", cin)


def mock_mca_charges(cin: str) -> dict:
    return _not_found("mca", "charges", cin)


def mock_bureau_commercial_report(pan: str) -> dict:
    return _not_found("bureau", "commercial_report", pan)


def mock_gst_turnover(pan: str) -> dict:
    return _not_found("gstin", "turnover", pan)


def mock_rating_action(entity_id: str) -> dict:
    return _not_found("rating", "rating_action", entity_id)


def mock_market_news_sentiment(entity_id: str) -> dict:
    return _not_found("market", "news_sentiment", entity_id)


def mock_crilc_report(entity_id: str) -> dict:
    return _not_found("crilc", "borrower_report", entity_id)
