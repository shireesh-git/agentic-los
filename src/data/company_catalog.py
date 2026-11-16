"""The borrowers on record: one data file each in data/borrowers/ (see src/data/borrowers.py).

No borrower data lives in code. Each file is the borrower's full record: real public figures where they exist (the
audited statements are read from its annual reports by scripts/read_fy2026_statements.py) and labelled demo values
for what is not public (collateral, account conduct, existing exposure, covenants).
"""

from __future__ import annotations

from typing import Any

from src.data import borrowers


def seed_company_store() -> dict[str, dict[str, Any]]:
    """Every borrower on record, as canonical records (a fresh copy on each call)."""
    return borrowers.load_all()


def catalog_company_ids() -> list[str]:
    return borrowers.ids()
