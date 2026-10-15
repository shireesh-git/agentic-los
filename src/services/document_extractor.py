"""
Document Extraction Service
============================
Extracts structured financial data from PDFs (PyMuPDF primary, pdfplumber fallback),
Excel (openpyxl), and CSVs.  Returns normalized dictionaries that feed into
validation, RAG, and CAM generation.

OCR engine: PyMuPDF (fitz) for high-quality text extraction with Tesseract
fallback for scanned pages.  Produces RAG-ready data.
"""

import csv
import hashlib
import json
import logging
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

import openpyxl
from src.core.runtime_paths import CACHE_ROOT, DOCUMENTS_ROOT
from src.services.document_classifier import find_best_document

_log = logging.getLogger(__name__)

# Try PyMuPDF first; fall back to pdfplumber
_USE_PYMUPDF = False
try:
    from src.engines.document_ocr_engine import (
        extract_text_pymupdf,
        extract_text_best,
        extract_financials_enhanced,
        compute_document_fingerprint,
    )
    _USE_PYMUPDF = True
    _log.info("Document extractor: using PyMuPDF (high-quality OCR engine)")
except Exception:
    _log.warning("PyMuPDF unavailable — falling back to pdfplumber")
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None


# ─── Per-file extraction cache ───────────────────────────────────────────────
#
# Reading a PDF (especially OCR of scanned pages) is the slow part of
# extraction, and the same files are re-read after every upload and after a
# restart. Each extractor's result depends only on its file, so it is cached
# on disk under the file's content hash: unchanged files are not read again.
# Bump _EXTRACTION_CACHE_VERSION whenever an extractor's output changes.

_EXTRACTION_CACHE_VERSION = "3"   # 3: first matching label wins (revenue never pooled with total income)
_EXTRACTION_CACHE_DIR = CACHE_ROOT / "extractions"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ocr_signature() -> str:
    """Whether a Tesseract binary is available: results differ with and without OCR."""
    configured = os.environ.get("TESSERACT_CMD") or os.environ.get("TESSERACT_PATH")
    candidates = [configured, r"C:\Program Files\Tesseract-OCR\tesseract.exe"]
    found = any(c and Path(c).exists() for c in candidates) or shutil.which("tesseract")
    return "ocr" if found else "no-ocr"


def _safe_extract(extractor: Callable[[Path], dict], filepath: Path) -> dict[str, Any]:
    """One document's extraction; a failure is reported for that document instead of
    abandoning the whole case's extraction."""
    try:
        return extractor(filepath)
    except Exception as e:
        _log.warning("Extraction of %s with %s failed: %s", filepath.name, extractor.__name__, e)
        return {"error": f"{extractor.__name__}: {e}", "source_file": str(filepath)}


def _cached_extract(extractor: Callable[[Path], dict], filepath: Path) -> dict[str, Any]:
    """Run ``extractor(filepath)``, reusing a cached result for identical file contents."""
    filepath = Path(filepath)
    try:
        content_hash = _file_sha256(filepath)
    except OSError:
        return _safe_extract(extractor, filepath)

    engine = "pymupdf" if _USE_PYMUPDF else "pdfplumber"
    # The path is part of the key because some results embed the file name.
    key_material = "|".join([_EXTRACTION_CACHE_VERSION, extractor.__name__, engine, _ocr_signature(),
                             str(filepath.resolve()), content_hash])
    cache_file = _EXTRACTION_CACHE_DIR / (hashlib.sha256(key_material.encode("utf-8")).hexdigest() + ".json")
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # unreadable cache entry: extract again and overwrite it

    result = _safe_extract(extractor, filepath)
    if isinstance(result, dict) and "error" not in result:  # failures may be transient; retry next time
        try:
            text = json.dumps(result)
            # Only cache results that survive a JSON round trip unchanged (no tuples,
            # non-string keys, NaN or other types JSON would silently alter).
            if json.loads(text) == result:
                _EXTRACTION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                tmp = cache_file.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(cache_file)
        except (TypeError, ValueError, OSError) as e:
            _log.debug("Extraction cache skipped for %s: %s", filepath.name, e)
    return result


# ─── PDF Extraction ──────────────────────────────────────────────────────────

def extract_pdf(filepath: str | Path) -> dict[str, Any]:
    """Extract text and tables from a PDF file (PyMuPDF or pdfplumber)."""
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}", "tables": [], "text": ""}

    # ── PyMuPDF path (preferred) — use extract_text_best for Gemini Vision fallback ──
    if _USE_PYMUPDF:
        raw = extract_text_best(filepath)
        tables_flat = []
        for t in raw.get("tables", []):
            if isinstance(t, dict) and "data" in t:
                tables_flat.append(t["data"])
            elif isinstance(t, list):
                tables_flat.append(t)
        return {
            "filename": filepath.name,
            "type": "pdf",
            "text": raw.get("text", ""),
            "tables": tables_flat,
            "metadata": {
                "pages": raw.get("page_count", 0),
                "quality_score": raw.get("quality_score", 0),
                "ocr_pages": raw.get("ocr_pages", 0),
                "extraction_method": "pymupdf",
            },
        }

    # ── pdfplumber fallback ──
    import pdfplumber as _pdfplumber
    result = {"filename": filepath.name, "type": "pdf", "text": "", "tables": [], "metadata": {}}

    with _pdfplumber.open(filepath) as pdf:
        result["metadata"]["pages"] = len(pdf.pages)
        result["metadata"]["extraction_method"] = "pdfplumber"
        all_text = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text.append(text)
            tables = page.extract_tables()
            for tbl in tables:
                if tbl and len(tbl) > 1:
                    result["tables"].append(tbl)
        result["text"] = "\n".join(all_text)

    return result


def extract_financials_from_pdf(filepath: str | Path) -> dict[str, Any]:
    """Extract financial figures from audited financials / annual report PDFs.
    Uses the enhanced OCR engine when available for better pattern coverage,
    negative value handling, and table extraction."""
    filepath = Path(filepath)

    # Prefer the enhanced extractor (more patterns, handles negatives, better tables)
    if _USE_PYMUPDF:
        result = extract_financials_enhanced(filepath)
        if result and result.get("data"):
            # Detect and normalize units (Lakhs → Crores)
            _detect_and_normalize_units(result)
            return result

    # Fallback to basic regex extraction
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    financials = {"source_file": str(filepath), "type": "financial_extraction", "data": {}}

    text = raw["text"]

    # Extract key financial metrics using regex patterns
    patterns = {
        "revenue": [
            r"Revenue\s+from\s+Operations?\s*[\|:]?\s*([\d,]+\.?\d*)",
            r"Revenue\s+([\d,]+\.?\d*)",
            r"Total\s+Income\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "ebitda": [
            r"EBITDA\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "pat": [
            r"Profit\s+After\s+Tax\s*[\|:]?\s*([\d,]+\.?\d*)",
            r"Net\s+Profit\s*[\|:]?\s*([\d,]+\.?\d*)",
            r"PAT\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "pbt": [
            r"Profit\s+Before\s+Tax\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "total_assets": [
            r"TOTAL\s+ASSETS?\s*[\|:]?\s*([\d,]+\.?\d*)",
            r"Total\s+Assets?\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "total_equity": [
            r"Shareholders?\s*['\u2019]?\s*Equity\s*[\|:]?\s*([\d,]+\.?\d*)",
            r"Net\s+Worth\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "total_debt": [
            r"Total\s+Debt\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "depreciation": [
            r"Depreciation\s*(?:&|and)?\s*(?:Amortisation)?\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
        "finance_cost": [
            r"Finance\s+Costs?\s*[\|:]?\s*([\d,]+\.?\d*)",
            r"Interest\s+Expense\s*[\|:]?\s*([\d,]+\.?\d*)",
        ],
    }

    for metric, pats in patterns.items():
        values = []
        for pat in pats:
            matches = re.findall(pat, text, re.IGNORECASE)
            for m in matches:
                try:
                    val = float(m.replace(",", ""))
                    if val > 0:
                        values.append(val)
                except ValueError:
                    continue
        if values:
            financials["data"][metric] = values

    # Extract from tables if regex didn't capture enough
    for table in raw["tables"]:
        _extract_from_table(table, financials["data"])

    # Try to identify fiscal years
    fy_pattern = r"FY\s*20\d{2}"
    fiscal_years = re.findall(fy_pattern, text)
    if fiscal_years:
        financials["fiscal_years"] = list(dict.fromkeys(fiscal_years))  # deduplicate

    return financials


def _detect_and_normalize_units(result: dict):
    """Detect if financial values are in Lakhs (vs Crores) and normalize to Crores.
    Indian annual reports state the unit in table captions ('₹ in Lakhs', '(` In lakhs)').
    The enhanced extractor records the unit it read from the full text (``statement_unit``)
    instead of carrying the text itself."""
    from src.engines.document_ocr_engine import detect_statement_unit

    if not isinstance(result, dict):
        return
    unit = result.get("statement_unit") or detect_statement_unit(result.get("text", "") or "")
    if unit == "lakhs":
        _log.info("Detected Lakhs unit — normalizing to Crores (÷100)")
        result["detected_unit"] = "lakhs"
        data = result.get("data", {})
        for metric, values in data.items():
            if isinstance(values, list):
                data[metric] = [round(v / 100, 2) for v in values]
    else:
        result["detected_unit"] = "crores"


def _extract_from_table(table: list[list], data: dict):
    """Extract financial metrics from a parsed table."""
    if not table or len(table) < 2:
        return

    metric_map = {
        "revenue from operations": "revenue",
        "revenue": "revenue",
        "total income": "total_income",
        "ebitda": "ebitda",
        "profit after tax": "pat",
        "net profit": "pat",
        "profit before tax": "pbt",
        "total assets": "total_assets",
        "shareholders' equity": "total_equity",
        "shareholders equity": "total_equity",
        "net worth": "total_equity",
        "total debt": "total_debt",
        "depreciation": "depreciation",
        "finance costs": "finance_cost",
        "finance cost": "finance_cost",
    }

    for row in table[1:]:  # skip header
        if not row or not row[0]:
            continue
        label = str(row[0]).strip().lower()
        for pattern, metric in metric_map.items():
            if pattern in label:
                for cell in row[1:]:
                    if cell:
                        try:
                            val = float(str(cell).replace(",", "").strip())
                            if val > 0:
                                data.setdefault(metric, [])
                                if val not in data[metric]:
                                    data[metric].append(val)
                        except (ValueError, AttributeError):
                            continue
                break


def extract_rating_from_pdf(filepath: str | Path) -> dict[str, Any]:
    """Extract credit rating information from a rating report PDF."""
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    text = raw["text"]
    result = {"source_file": str(filepath), "type": "rating_extraction", "data": {}}

    # Rating agency
    for agency in ["CRISIL", "CARE", "ICRA", "India Ratings", "Brickwork", "Acuité"]:
        if agency.lower() in text.lower():
            result["data"]["agency"] = agency
            break

    # Rating
    rating_patterns = [
        r"(CRISIL\s+[A-D][A-D]?[\+\-]?/\w+)",
        r"(CARE\s+[A-D][A-D]?[\+\-]?/[\w\s]+)",
        r"(ICRA\s+[A-D][A-D]?[\+\-]?/\w+)",
        r"Rating[:\s]+(A[\+\-]?|AA[\+\-]?|AAA|BBB[\+\-]?|BB[\+\-]?|B[\+\-]?|C|D)",
    ]
    for pat in rating_patterns:
        m = re.search(pat, text)
        if m:
            result["data"]["rating"] = m.group(1) if "(" in pat else m.group(0)
            break

    # Outlook
    for outlook in ["Stable", "Positive", "Negative", "Watch Negative", "Watch Positive"]:
        if outlook.lower() in text.lower():
            result["data"]["outlook"] = outlook
            break

    return result


def extract_gst_from_pdf(filepath: str | Path) -> dict[str, Any]:
    """Extract GST information from a GST certificate/return PDF."""
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    text = raw["text"]
    result = {"source_file": str(filepath), "type": "gst_extraction", "data": {}}

    # GSTIN
    gstin_match = re.search(r"(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2})", text)
    if gstin_match:
        result["data"]["gstin"] = gstin_match.group(1)

    # Total turnover
    turnover_patterns = [
        r"TOTAL\s+FY\d{4}\s+\S+\s+\S+\s+([\d,]+\.?\d*)",
        r"Total.*?Taxable\s+Value.*?([\d,]+\.?\d*)",
    ]
    for pat in turnover_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result["data"]["total_turnover"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    # Also extract from tables
    for table in raw["tables"]:
        if table and len(table) > 1:
            for row in table:
                if row and str(row[0]).strip().upper().startswith("TOTAL"):
                    for cell in row[1:]:
                        if cell:
                            try:
                                val = float(str(cell).replace(",", "").strip())
                                if val > 100:  # reasonable turnover
                                    result["data"].setdefault("total_turnover", val)
                            except (ValueError, AttributeError):
                                continue

    return result


_PERIOD_COLUMN = re.compile(
    r"\b(?:Q[1-4]\s*FY\s?\d{2,4}|9M\s*FY\s?\d{2,4}|[1-9]M\s*FY\s?\d{2,4}|H[12]\s*FY\s?\d{2,4}|FY\s?\d{2,4}"
    r"|Apr(?:il)?[- ]Dec(?:ember)?[^\n|]{0,12}|Nine\s+months[^\n|]{0,30}|Quarter\s+ended[^\n|]{0,30}"
    r"|Year\s+ended[^\n|]{0,30})", re.IGNORECASE)
_NUMBER = re.compile(r"\(?-?[\d,]+\.\d+\)?|\(?-?\d{1,3}(?:,\d{2,3})+\)?")


def _nine_month_revenue(text: str) -> float | None:
    """The 'Revenue from Operations' value under the 9-month column of a results table.

    The column headers are the period labels between the table's 'Particulars' caption
    and the revenue row; the row's numbers follow in the same order."""
    for row in re.finditer(r"Revenue\s+from\s+Operations?", text or "", re.IGNORECASE):
        head_start = text.rfind("Particulars", max(0, row.start() - 600), row.start())
        if head_start < 0:
            continue
        headers = [m.group(0) for m in _PERIOD_COLUMN.finditer(text[head_start:row.start()])]
        nine = [i for i, h in enumerate(headers) if re.match(r"9M|Apr|Nine", h, re.IGNORECASE)]
        if not nine:
            continue
        values = _NUMBER.findall(text[row.end():row.end() + 300])[:len(headers)]
        if len(values) == len(headers):
            raw = values[nine[0]]
            try:
                value = float(raw.strip("()").replace(",", ""))
            except ValueError:
                continue
            return -value if raw.startswith("(") else value
    return None


def extract_exchange_filing_from_pdf(filepath: str | Path) -> dict[str, Any]:
    """Extract quarterly results from exchange filing PDF."""
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    text = raw["text"]
    result = {"source_file": str(filepath), "type": "exchange_extraction", "data": {}}

    # 9-month revenue: the value in the 9M column of the results table (results tables
    # put the quarter first, so "the first number after Revenue" is the quarter, not 9M).
    nine_m = _nine_month_revenue(text)
    if nine_m is not None:
        result["data"]["nine_month_revenue"] = nine_m
    patterns = [] if nine_m is not None else [
        r"9M\s+FY\d{4}.*?Revenue.*?([\d,]+\.?\d*)",
        r"Apr[- ]Dec.*?Revenue.*?([\d,]+\.?\d*)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                result["data"]["nine_month_revenue"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    # Also search tables
    for table in raw["tables"]:
        _extract_from_table(table, result["data"])

    return result


# ─── Excel Extraction ────────────────────────────────────────────────────────

def extract_excel(filepath: str | Path) -> dict[str, Any]:
    """Extract data from an Excel file (all sheets)."""
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}"}

    result = {"filename": filepath.name, "type": "excel", "sheets": {}}
    wb = openpyxl.load_workbook(filepath, data_only=True)

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([_cell_value(c) for c in row])
        result["sheets"][sheet_name] = rows

    wb.close()
    return result


def extract_provisional_financials(filepath: str | Path) -> dict[str, Any]:
    """Extract provisional / projected financials from Excel."""
    raw = extract_excel(filepath)
    if raw.get("error"):
        return raw

    result = {"source_file": str(filepath), "type": "provisional_extraction", "data": {}}

    metric_map = {
        "revenue from operations": "revenue",
        "ebitda": "ebitda",
        "profit after tax": "pat",
        "profit before tax": "pbt",
        "depreciation": "depreciation",
        "finance cost": "finance_cost",
        "tax expense": "tax",
    }

    for sheet_name, rows in raw["sheets"].items():
        if not rows:
            continue
        for row in rows[1:]:  # skip header
            if not row or not row[0]:
                continue
            label = str(row[0]).strip().lower()
            for pattern, metric in metric_map.items():
                if pattern in label:
                    # Column indices: typically [label, audited, provisional, growth]
                    if len(row) >= 3 and row[2] is not None:
                        try:
                            provisional_val = float(row[2])
                            result["data"][f"provisional_{metric}"] = provisional_val
                        except (ValueError, TypeError):
                            pass
                    if len(row) >= 2 and row[1] is not None:
                        try:
                            audited_val = float(row[1])
                            result["data"][f"audited_{metric}"] = audited_val
                        except (ValueError, TypeError):
                            pass
                    break

    return result


def extract_debt_schedule(filepath: str | Path) -> dict[str, Any]:
    """Extract debt schedule from Excel."""
    raw = extract_excel(filepath)
    if raw.get("error"):
        return raw

    result = {"source_file": str(filepath), "type": "debt_schedule_extraction", "data": {"facilities": []}}

    for sheet_name, rows in raw["sheets"].items():
        if "debt" not in sheet_name.lower():
            continue
        if not rows or len(rows) < 2:
            continue
        headers = [str(h).lower() if h else "" for h in rows[0]]
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            if str(row[0]).strip().upper() == "TOTAL":
                continue
            facility = {}
            for i, header in enumerate(headers):
                if i < len(row) and row[i] is not None:
                    if "lender" in header:
                        facility["lender"] = str(row[i])
                    elif "facility" in header:
                        facility["facility_type"] = str(row[i])
                    elif "sanctioned" in header:
                        facility["sanctioned"] = _to_float(row[i])
                    elif "outstanding" in header:
                        facility["outstanding"] = _to_float(row[i])
                    elif "rate" in header:
                        facility["rate"] = _to_float(row[i])
                    elif "security" in header:
                        facility["security"] = str(row[i])
            if facility:
                result["data"]["facilities"].append(facility)

    return result


# ─── CSV Extraction ──────────────────────────────────────────────────────────

def extract_csv(filepath: str | Path) -> dict[str, Any]:
    """Extract data from a CSV file."""
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}"}

    result = {"filename": filepath.name, "type": "csv", "headers": [], "rows": []}

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        result["headers"] = reader.fieldnames or []
        for row in reader:
            # Convert numeric strings to numbers
            clean_row = {}
            for k, v in row.items():
                try:
                    clean_row[k] = float(v)
                except (ValueError, TypeError):
                    clean_row[k] = v
            result["rows"].append(clean_row)

    return result


def extract_etb_conduct(entity_folder: str | Path) -> dict[str, Any]:
    """Extract all ETB internal conduct CSVs from entity folder."""
    folder = Path(entity_folder) / "etb_internal"
    if not folder.exists():
        return {"error": f"No ETB internal data found at {folder}"}

    result = {"type": "etb_conduct_extraction", "data": {}}

    csv_files = {
        "account_conduct": "account_conduct.csv",
        "repayment_history": "repayment_history.csv",
        "covenant_tracker": "covenant_tracker.csv",
        "loan_utilization": "loan_utilization.csv",
    }

    for key, filename in csv_files.items():
        fpath = folder / filename
        if fpath.exists():
            extracted = extract_csv(fpath)
            result["data"][key] = extracted.get("rows", [])

    return result


# ─── Optional Document Extraction ────────────────────────────────────────────

def extract_site_visit_report(filepath: str | Path) -> dict[str, Any]:
    """Extract structured data from a site visit report PDF."""
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    text = raw["text"]
    result = {"source_file": str(filepath), "type": "site_visit_extraction", "data": {}}

    # Visit date
    date_match = re.search(r"(?:Visit|Date|Visited)\s*[:\-]?\s*(\d{1,2}[\s/\-]\w+[\s/\-]\d{2,4})", text, re.IGNORECASE)
    if date_match:
        result["data"]["visit_date"] = date_match.group(1).strip()

    # Visited by
    by_match = re.search(r"(?:Visited\s+by|Officer|Inspector|RM)\s*[:\-]?\s*([A-Z][a-zA-Z\s\.]+)", text)
    if by_match:
        result["data"]["visited_by"] = by_match.group(1).strip()

    # Location / address
    loc_match = re.search(r"(?:Location|Address|Site|Plant|Factory)\s*[:\-]?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if loc_match:
        result["data"]["location"] = loc_match.group(1).strip()[:200]

    # Extract observations and key findings from text
    sections = {
        "operational_status": r"(?:Operational|Operations?|Business)\s*(?:Status|Overview|Activity)?\s*[:\-]?\s*(.+?)(?:\n\n|\Z)",
        "infrastructure": r"(?:Infrastructure|Premises|Building|Facility)\s*(?:Status|Condition|Overview)?\s*[:\-]?\s*(.+?)(?:\n\n|\Z)",
        "inventory": r"(?:Inventory|Stock|Warehouse|Raw Material)\s*(?:Status|Level|Overview)?\s*[:\-]?\s*(.+?)(?:\n\n|\Z)",
        "management_observations": r"(?:Management|Promoter|Director)\s*(?:Observation|Discussion|Meeting|Impression)?\s*[:\-]?\s*(.+?)(?:\n\n|\Z)",
        "overall_assessment": r"(?:Overall|General|Summary|Conclusion|Assessment|Recommendation)\s*[:\-]?\s*(.+?)(?:\n\n|\Z)",
    }
    for key, pat in sections.items():
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            result["data"][key] = m.group(1).strip()[:500]

    # Full text for LLM consumption
    result["data"]["full_text"] = text[:3000]

    return result


def extract_valuation_report(filepath: str | Path) -> dict[str, Any]:
    """Extract structured data from a property/collateral valuation report PDF."""
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    text = raw["text"]
    result = {"source_file": str(filepath), "type": "valuation_extraction", "data": {}}

    # Property type
    prop_match = re.search(r"(?:Property\s+Type|Type\s+of\s+Property|Nature)\s*[:\-]?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if prop_match:
        result["data"]["property_type"] = prop_match.group(1).strip()[:100]

    # Market value
    mv_patterns = [
        r"Market\s+Value\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)\s*(?:Cr|Crore|Lakh|Lac)?",
        r"Fair\s+(?:Market\s+)?Value\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
    ]
    for pat in mv_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result["data"]["market_value"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    # Forced Sale Value
    fsv_patterns = [
        r"(?:Forced\s+Sale|Distress|FSV|Realizable)\s*(?:Value)?\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
    ]
    for pat in fsv_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result["data"]["forced_sale_value"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue

    # Valuation date
    vd_match = re.search(r"(?:Valuation|Assessment)\s*Date\s*[:\-]?\s*(\d{1,2}[\s/\-]\w+[\s/\-]\d{2,4})", text, re.IGNORECASE)
    if vd_match:
        result["data"]["valuation_date"] = vd_match.group(1).strip()

    # Location
    loc_match = re.search(r"(?:Location|Address|Property\s+Address)\s*[:\-]?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if loc_match:
        result["data"]["location"] = loc_match.group(1).strip()[:200]

    # Area / size
    area_match = re.search(r"(?:Total\s+Area|Built[\- ]up\s+Area|Land\s+Area|Plot\s+Area)\s*[:\-]?\s*([\d,\.]+\s*(?:sq\.?\s*(?:ft|m|mtr)|acres?|hectares?))", text, re.IGNORECASE)
    if area_match:
        result["data"]["area"] = area_match.group(1).strip()

    # Encumbrance status
    enc_match = re.search(r"(?:Encumbrance|Lien|Charge|Mortgage)\s*(?:Status)?\s*[:\-]?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if enc_match:
        result["data"]["encumbrance_status"] = enc_match.group(1).strip()[:150]

    # Full text for LLM
    result["data"]["full_text"] = text[:3000]

    return result


def extract_bank_statement_structured(filepath: str | Path) -> dict[str, Any]:
    """Extract structured data from bank statements PDF."""
    raw = extract_pdf(filepath)
    if raw.get("error"):
        return raw

    text = raw["text"]
    result = {"source_file": str(filepath), "type": "bank_statement_extraction", "data": {}}

    # Account number
    acct_match = re.search(r"(?:Account\s*(?:No|Number|#))\s*[:\-]?\s*(\d{8,18})", text, re.IGNORECASE)
    if acct_match:
        result["data"]["account_number"] = acct_match.group(1)

    # Account type
    type_match = re.search(r"(?:Account\s*Type|Type\s*of\s*Account)\s*[:\-]?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if type_match:
        result["data"]["account_type"] = type_match.group(1).strip()[:50]

    # Bank name
    bank_match = re.search(r"(?:Bank|Branch)\s*[:\-]?\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if bank_match:
        result["data"]["bank_name"] = bank_match.group(1).strip()[:100]

    # Balance figures
    balance_patterns = {
        "opening_balance": r"(?:Opening|Begin+ing)\s+Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
        "closing_balance": r"(?:Closing|End(?:ing)?)\s+Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
        "average_balance": r"(?:Average|Avg\.?|Mean)\s+(?:Monthly\s+)?Balance\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)",
    }
    for key, pat in balance_patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result["data"][key] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass

    # Total credits / debits
    credit_match = re.search(r"Total\s+Credits?\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if credit_match:
        try:
            result["data"]["total_credits"] = float(credit_match.group(1).replace(",", ""))
        except ValueError:
            pass

    debit_match = re.search(r"Total\s+Debits?\s*[:\-]?\s*(?:Rs\.?\s*|INR\s*|₹\s*)?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if debit_match:
        try:
            result["data"]["total_debits"] = float(debit_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Cheque return / bounced
    bounce_match = re.search(r"(?:Cheque|Check)\s+(?:Return|Bounce|Dishono)", text, re.IGNORECASE)
    result["data"]["cheque_returns_found"] = bool(bounce_match)

    # Full text for LLM
    result["data"]["full_text"] = text[:3000]
    result["data"]["pages"] = raw.get("metadata", {}).get("pages", 0)

    return result


# ─── Unified Extraction for a Company ────────────────────────────────────────

def extract_all_documents(entity_id: str, storage_root: Path | None = None) -> dict[str, Any]:
    """
    Extract ALL documents for a given entity and return structured data.
    This is the main entry point for the extraction pipeline.
    """
    if storage_root is None:
        storage_root = DOCUMENTS_ROOT

    entity_dir = storage_root / entity_id
    if not entity_dir.exists():
        return {"error": f"No documents found for {entity_id}"}

    extraction = {
        "entity_id": entity_id,
        "type": "full_extraction",
        "extraction_engine": "pymupdf" if _USE_PYMUPDF else "pdfplumber",
        "selected_documents": {},
        "financials": {},
        "rating": {},
        "gst": {},
        "exchange": {},
        "provisional": {},
        "debt_schedule": {},
        "etb_conduct": {},
        "bank_statement": {},
        "kyc": {},
        "collateral": {},
        "request_note": {},
        "site_visit": {},
        "valuation": {},
        "downloaded_annual_reports": {},
        "document_verification": {},
        "raw_texts": {},
        "document_count": 0,
    }

    # 1. Audited Financials / Annual Report
    fpath = find_best_document(entity_dir / "financials", "financials", "audited_financial_statements")
    if fpath and fpath.exists():
        ext = _cached_extract(extract_financials_from_pdf, fpath)
        if "data" in ext:
            extraction["financials"]["audited"] = ext["data"]
            extraction["selected_documents"]["audited_financials"] = fpath.name
            extraction["document_count"] += 1

    # 2. Rating Report
    fpath = entity_dir / "ratings" / "credit_rating_report.pdf"
    if fpath.exists():
        extraction["rating"] = _cached_extract(extract_rating_from_pdf, fpath).get("data", {})
        extraction["document_count"] += 1

    # 3. GST
    fpath = find_best_document(entity_dir / "gst", "gst", "gst_registration")
    if fpath and fpath.exists():
        extraction["gst"] = _cached_extract(extract_gst_from_pdf, fpath).get("data", {})
        extraction["selected_documents"]["gst"] = fpath.name
        extraction["document_count"] += 1

    # 4. Exchange Filing
    fpath = find_best_document(entity_dir / "exchange", "exchange", "exchange_filing")
    if fpath and fpath.exists():
        extraction["exchange"] = _cached_extract(extract_exchange_filing_from_pdf, fpath).get("data", {})
        extraction["selected_documents"]["exchange"] = fpath.name
        extraction["document_count"] += 1

    # 5. Provisional Financials (spreadsheet) or unaudited results (PDF)
    fpath = find_best_document(entity_dir / "financials", "financials", "provisional_financials")
    if fpath and fpath.exists() and fpath.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        extraction["provisional"] = _cached_extract(extract_provisional_financials, fpath).get("data", {})
        extraction["selected_documents"]["provisional"] = fpath.name
        extraction["document_count"] += 1
    elif fpath and fpath.exists() and fpath.suffix.lower() == ".pdf":
        # Unaudited results published as PDF: read with the PDF financials extractor. Kept separate from
        # "provisional" so unverified PDF figures never override the statements used for analysis.
        ext = _cached_extract(extract_financials_from_pdf, fpath)
        extraction["unaudited_results"] = {"source_file": fpath.name, "data": ext.get("data", {}),
                                           "error": ext.get("error"),
                                           "status": "extracted from PDF (unaudited; not used to override statements)"}
        extraction["selected_documents"]["unaudited_results"] = fpath.name
        extraction["document_count"] += 1

    # 6. Debt Schedule
    fpath = find_best_document(entity_dir / "financials", "financials", "debt_schedule")
    if fpath and fpath.exists():
        extraction["debt_schedule"] = _cached_extract(extract_debt_schedule, fpath).get("data", {})
        extraction["selected_documents"]["debt_schedule"] = fpath.name
        extraction["document_count"] += 1

    # 7. ETB Conduct
    etb = extract_etb_conduct(entity_dir)
    if "data" in etb and etb["data"]:
        extraction["etb_conduct"] = etb["data"]
        extraction["document_count"] += len(etb["data"])

    # 8. Bank Statement (structured extraction)
    fpath = find_best_document(entity_dir / "banking", "banking", "bank_statements")
    if not fpath:
        fpath = entity_dir / "banking" / "bank_statement_fy2025.pdf"
    if fpath and fpath.exists():
        bs_ext = _cached_extract(extract_bank_statement_structured, fpath)
        extraction["bank_statement"] = bs_ext.get("data", {"text_preview": "", "pages": 0})
        extraction["selected_documents"]["bank_statement"] = fpath.name
        extraction["document_count"] += 1

    # 9. KYC docs (basic text extraction for reference)
    for fname in ["pan_card.pdf", "certificate_of_incorporation.pdf", "board_resolution_borrowing.pdf"]:
        fpath = entity_dir / "kyc" / fname
        if fpath.exists():
            raw = _cached_extract(extract_pdf, fpath)
            extraction["kyc"][fname.replace(".pdf", "")] = raw["text"][:300]
            extraction["document_count"] += 1

    # 10. Collateral / Valuation Report (structured extraction)
    fpath = find_best_document(entity_dir / "collateral", "collateral", "valuation_report")
    if not fpath:
        fpath = entity_dir / "collateral" / "valuation_report.pdf"
    if fpath and fpath.exists():
        val_ext = _cached_extract(extract_valuation_report, fpath)
        extraction["valuation"] = val_ext.get("data", {})
        extraction["collateral"] = {"text_preview": extraction["valuation"].get("full_text", "")[:500]}
        extraction["selected_documents"]["valuation_report"] = fpath.name
        extraction["document_count"] += 1

    # 11. Request Note
    fpath = entity_dir / "request" / "request_note.pdf"
    if fpath.exists():
        raw = _cached_extract(extract_pdf, fpath)
        extraction["request_note"] = {"text_preview": raw["text"][:500]}
        extraction["document_count"] += 1

    # 11b. Site Visit Report (structured extraction)
    fpath = find_best_document(entity_dir / "request", "request", "site_visit_report")
    if fpath and fpath.exists():
        sv_ext = _cached_extract(extract_site_visit_report, fpath)
        extraction["site_visit"] = sv_ext.get("data", {})
        extraction["selected_documents"]["site_visit_report"] = fpath.name
        extraction["document_count"] += 1

    # 12. Document verification (fingerprint every PDF found; cached per file contents)
    if _USE_PYMUPDF:
        all_pdfs = list(entity_dir.rglob("*.pdf"))
        for pdf_path in all_pdfs:
            extraction["document_verification"][pdf_path.name] = _cached_extract(_fingerprint_summary, pdf_path)

    return extraction


def _fingerprint_summary(pdf_path: Path) -> dict[str, Any]:
    """The stable parts of a document fingerprint (no timestamp), so they can be cached."""
    fp = compute_document_fingerprint(pdf_path)
    if fp.get("error"):
        return {"error": fp["error"]}
    return {
        "sha256": fp.get("sha256", ""),
        "file_size_kb": fp.get("file_size_kb", 0),
        "file_size_bytes": fp.get("file_size_bytes", 0),
        "page_count": fp.get("pdf_metadata", {}).get("page_count", 0),
        "producer": fp.get("pdf_metadata", {}).get("producer", ""),
        "is_verified": fp.get("is_verified", False),
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _cell_value(c):
    if c is None:
        return None
    if isinstance(c, (int, float)):
        return c
    return str(c)


def _to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
