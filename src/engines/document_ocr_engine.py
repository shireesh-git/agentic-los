"""
Document OCR Engine — High-quality text extraction & document verification
==========================================================================
Uses PyMuPDF (fitz) as primary extractor and pytesseract as fallback OCR
for scanned/image-heavy pages. Provides document fingerprinting (SHA-256)
and metadata extraction for authenticity validation.

This is a USP module — documents processed here feed into RAG and CAM,
so extraction quality directly impacts credit appraisal accuracy.
"""

import hashlib
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)

# ─── Lazy imports (heavy libraries) ──────────────────────────────────────────

_fitz = None
_pytesseract = None
_Image = None


def _get_fitz():
    global _fitz
    if _fitz is None:
        import fitz  # PyMuPDF
        _fitz = fitz
    return _fitz


def _get_tesseract():
    """Return pytesseract module, or None if unavailable."""
    global _pytesseract, _Image
    if _pytesseract is None:
        try:
            import pytesseract
            from PIL import Image
            tesseract_cmd = (
                os.environ.get("TESSERACT_CMD")
                or os.environ.get("TESSERACT_PATH")
                or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )
            if Path(tesseract_cmd).exists():
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            _pytesseract = pytesseract
            _Image = Image
        except ImportError:
            _log.warning("pytesseract/Pillow not installed — OCR fallback unavailable")
            return None, None
    return _pytesseract, _Image


# ─── Document Fingerprint & Authenticity ─────────────────────────────────────

def compute_document_fingerprint(filepath: Path) -> dict[str, Any]:
    """
    Compute SHA-256 hash and extract PDF metadata for authenticity verification.
    Returns a verification record that can be stored and compared later.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}"}

    result = {
        "filename": filepath.name,
        "filepath": str(filepath),
        "file_size_bytes": filepath.stat().st_size,
        "file_size_kb": round(filepath.stat().st_size / 1024, 1),
        "verified_at": datetime.now().isoformat(),
    }

    # SHA-256 hash
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    result["sha256"] = sha256.hexdigest()

    # PDF metadata extraction via PyMuPDF
    if filepath.suffix.lower() == ".pdf":
        try:
            fitz = _get_fitz()
            doc = fitz.open(str(filepath))
            meta = doc.metadata or {}
            result["pdf_metadata"] = {
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
                "creator": meta.get("creator", ""),
                "producer": meta.get("producer", ""),
                "creation_date": meta.get("creationDate", ""),
                "modification_date": meta.get("modDate", ""),
                "page_count": doc.page_count,
                "format": meta.get("format", ""),
                "encryption": meta.get("encryption", ""),
            }
            doc.close()

            # Authenticity signals
            signals = []
            pdf_meta = result["pdf_metadata"]
            if pdf_meta["producer"]:
                signals.append(f"PDF producer: {pdf_meta['producer']}")
            if pdf_meta["creator"]:
                signals.append(f"Creator tool: {pdf_meta['creator']}")
            if pdf_meta["creation_date"]:
                signals.append(f"Created: {pdf_meta['creation_date']}")
            if pdf_meta["page_count"] > 0:
                signals.append(f"Pages: {pdf_meta['page_count']}")
            result["authenticity_signals"] = signals
            result["is_verified"] = True
        except Exception as e:
            _log.warning("PDF metadata extraction failed for %s: %s", filepath.name, e)
            result["pdf_metadata"] = {}
            result["is_verified"] = False
    else:
        result["is_verified"] = True  # Non-PDF files verified by hash only

    return result


def verify_batch(filepaths: list[Path]) -> dict[str, Any]:
    """Verify a batch of documents, return consolidated report."""
    results = []
    for fp in filepaths:
        results.append(compute_document_fingerprint(fp))

    verified = sum(1 for r in results if r.get("is_verified"))
    return {
        "total_documents": len(results),
        "verified_count": verified,
        "unverified_count": len(results) - verified,
        "total_size_mb": round(sum(r.get("file_size_bytes", 0) for r in results) / (1024 * 1024), 2),
        "documents": results,
        "verification_timestamp": datetime.now().isoformat(),
    }


# ─── High-Quality PDF Text Extraction (PyMuPDF) ─────────────────────────────

def extract_text_pymupdf(filepath: Path, *, ocr_fallback: bool = True) -> dict[str, Any]:
    """
    Extract text from PDF using PyMuPDF (fitz).
    Falls back to Tesseract OCR for pages with very little extractable text
    (indicating scanned/image-based pages).

    Returns structured result with per-page text, tables, and quality metrics.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}", "text": "", "pages": []}

    fitz = _get_fitz()
    t0 = time.time()

    result = {
        "filename": filepath.name,
        "text": "",
        "pages": [],
        "tables": [],
        "page_count": 0,
        "extraction_method": "pymupdf",
        "ocr_pages": 0,
        "quality_score": 0.0,
    }

    try:
        doc = fitz.open(str(filepath))
        result["page_count"] = doc.page_count
        all_text_parts = []

        for page_num in range(doc.page_count):
            page = doc[page_num]
            page_text = page.get_text("text")
            char_count = len(page_text.strip())

            # If very little text extracted, page might be scanned/image
            if char_count < 50 and ocr_fallback:
                ocr_text = _ocr_page(page, filepath.name, page_num)
                if ocr_text and len(ocr_text.strip()) > char_count:
                    page_text = ocr_text
                    result["ocr_pages"] += 1

            all_text_parts.append(page_text)

            # Extract tables using PyMuPDF's built-in table finder
            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    for tab in tabs.tables:
                        table_data = tab.extract()
                        if table_data and len(table_data) > 1:
                            result["tables"].append({
                                "page": page_num + 1,
                                "rows": len(table_data),
                                "cols": len(table_data[0]) if table_data else 0,
                                "data": table_data,
                            })
            except Exception:
                pass  # table extraction is best-effort

            result["pages"].append({
                "page_num": page_num + 1,
                "char_count": len(page_text.strip()),
                "is_ocr": char_count < 50 and result["ocr_pages"] > 0,
            })

        doc.close()
        result["text"] = "\n\n".join(all_text_parts)

        # Quality score: ratio of pages with meaningful text
        pages_with_text = sum(1 for p in result["pages"] if p["char_count"] > 50)
        result["quality_score"] = round(pages_with_text / max(result["page_count"], 1), 2)
        result["extraction_time_ms"] = round((time.time() - t0) * 1000, 1)

    except Exception as e:
        _log.error("PyMuPDF extraction failed for %s: %s", filepath.name, e)
        result["error"] = str(e)

    return result


def _ocr_page(page, filename: str, page_num: int) -> str:
    """OCR a single page using Tesseract. Returns extracted text or empty string."""
    tess, PILImage = _get_tesseract()
    if tess is None:
        return ""

    try:
        # Render page to image at 300 DPI for good OCR quality
        pix = page.get_pixmap(dpi=300)
        img_data = pix.tobytes("png")

        import io
        img = PILImage.open(io.BytesIO(img_data))

        # Run Tesseract with English + best available model
        text = tess.image_to_string(img, lang="eng", config="--psm 6")
        _log.debug("OCR page %d of %s: %d chars", page_num + 1, filename, len(text))
        return text
    except Exception as e:
        _log.warning("OCR failed for page %d of %s: %s", page_num + 1, filename, e)
        return ""


# ─── Financial Data Extraction (Enhanced) ────────────────────────────────────

def extract_financials_enhanced(filepath: Path, precomputed_raw: dict | None = None) -> dict[str, Any]:
    """
    Extract financial metrics from annual reports / financial statements
    using PyMuPDF for high-quality text extraction.
    Designed for RAG-quality data capture from real annual reports.
    """
    raw = precomputed_raw or extract_text_pymupdf(filepath)
    if raw.get("error") and not raw.get("text"):
        return raw

    text = raw["text"]
    financials = {
        "source_file": str(filepath),
        "filename": filepath.name,
        "type": "financial_extraction_enhanced",
        "extraction_method": raw.get("extraction_method", "pymupdf"),
        "page_count": raw.get("page_count", 0),
        "quality_score": raw.get("quality_score", 0),
        "ocr_pages": raw.get("ocr_pages", 0),
        "data": {},
        "tables_found": len(raw.get("tables", [])),
        "raw_text_length": len(text),
    }

    # Enhanced regex patterns for Indian financial statements
    patterns = {
        "revenue": [
            r"Revenue\s+from\s+Operations?\s*[\|:\s]*([\d,]+\.?\d*)\s*(?:Cr|Lakhs|Mn)?",
            r"Total\s+Income\s*[\|:\s]*([\d,]+\.?\d*)",
            r"Turnover\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "ebitda": [
            r"EBITDA\s*[\|:\s]*([\d,]+\.?\d*)",
            r"Operating\s+Profit\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "pat": [
            r"Profit\s+(?:After|after)\s+Tax\s*[\|:\s]*([\d,]+\.?\d*)",
            r"Net\s+Profit\s*[\|:\s]*([\d,]+\.?\d*)",
            r"PAT\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "pbt": [
            r"Profit\s+(?:Before|before)\s+Tax\s*[\|:\s]*([\d,]+\.?\d*)",
            r"PBT\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "total_assets": [
            r"Total\s+Assets?\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "total_equity": [
            r"(?:Total\s+)?Shareholders?\s*['\u2019]?\s*(?:Funds?|Equity)\s*[\|:\s]*([\d,]+\.?\d*)",
            r"Net\s+Worth\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "total_debt": [
            r"Total\s+(?:Borrowings?|Debt)\s*[\|:\s]*([\d,]+\.?\d*)",
            r"Long[\- ]?[Tt]erm\s+Borrowings?\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "depreciation": [
            r"Depreciation\s*(?:&|and)\s*(?:Amortis?ation)\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "finance_cost": [
            r"Finance\s+Costs?\s*[\|:\s]*([\d,]+\.?\d*)",
            r"Interest\s+(?:Expense|Cost)\s*[\|:\s]*([\d,]+\.?\d*)",
        ],
        "eps": [
            r"(?:Basic\s+)?(?:EPS|Earnings\s+[Pp]er\s+[Ss]hare)\s*[\|:\s(₹Rs]*\s*([\d,]+\.?\d*)",
        ],
        "dividend": [
            r"Dividend\s*(?:per\s+share)?\s*[\|:\s(₹Rs]*\s*([\d,]+\.?\d*)",
        ],
        "cash_and_equivalents": [
            r"Cash\s+(?:and|&)\s+Cash\s+Equivalents?\s*[\|:\s]*([\d,]+\.?\d*)",
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

    # Also extract from detected tables
    for tbl_info in raw.get("tables", []):
        _extract_from_table_enhanced(tbl_info.get("data", []), financials["data"])

    # Fiscal year detection
    fy_patterns = [
        r"FY\s*20\d{2}(?:-\d{2})?",
        r"(?:Financial\s+Year|Year\s+[Ee]nded)\s+(?:March\s+31|31\.03),?\s*(20\d{2})",
        r"20\d{2}-\d{2}",
    ]
    fiscal_years = set()
    for pat in fy_patterns:
        for m in re.findall(pat, text):
            fiscal_years.add(m)

    if fiscal_years:
        financials["fiscal_years"] = sorted(fiscal_years)

    return financials


def _extract_from_table_enhanced(table: list[list], data: dict):
    """Extract financial metrics from a parsed table (enhanced version)."""
    if not table or len(table) < 2:
        return

    metric_map = {
        "revenue from operations": "revenue",
        "revenue": "revenue",
        "total income": "total_income",
        "ebitda": "ebitda",
        "operating profit": "ebitda",
        "profit after tax": "pat",
        "net profit": "pat",
        "profit before tax": "pbt",
        "total assets": "total_assets",
        "shareholders' equity": "total_equity",
        "shareholders equity": "total_equity",
        "net worth": "total_equity",
        "total debt": "total_debt",
        "total borrowings": "total_debt",
        "depreciation": "depreciation",
        "finance costs": "finance_cost",
        "finance cost": "finance_cost",
        "interest expense": "finance_cost",
        "earnings per share": "eps",
        "basic eps": "eps",
        "cash and cash equivalents": "cash_and_equivalents",
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
                            val = float(str(cell).replace(",", "").replace("(", "-").replace(")", "").strip())
                            if val != 0:
                                data.setdefault(metric, [])
                                if val not in data[metric]:
                                    data[metric].append(val)
                        except (ValueError, AttributeError):
                            continue
                break


# ─── Full Document Processing (for RAG) ─────────────────────────────────────

def process_document_for_rag(filepath: Path) -> dict[str, Any]:
    """
    Process a single document for RAG ingestion.
    Returns text chunks, metadata, and quality metrics.
    """
    filepath = Path(filepath)
    t0 = time.time()

    # Step 1: Fingerprint
    fingerprint = compute_document_fingerprint(filepath)

    # Step 2: Extract text
    extraction = extract_text_pymupdf(filepath, ocr_fallback=True)

    # Step 3: Chunk text for RAG (by page or section)
    text = extraction.get("text", "")
    chunks = _chunk_text(text, chunk_size=2000, overlap=200)

    return {
        "filepath": str(filepath),
        "filename": filepath.name,
        "fingerprint": fingerprint,
        "extraction": {
            "page_count": extraction.get("page_count", 0),
            "quality_score": extraction.get("quality_score", 0),
            "ocr_pages": extraction.get("ocr_pages", 0),
            "tables_found": len(extraction.get("tables", [])),
            "total_chars": len(text),
        },
        "chunks": chunks,
        "chunk_count": len(chunks),
        "processing_time_ms": round((time.time() - t0) * 1000, 1),
    }


def _chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list[dict]:
    """Split text into overlapping chunks for RAG indexing."""
    if not text:
        return []

    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + chunk_size
        # Try to break at paragraph or sentence boundary
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                boundary = text.rfind(sep, start + chunk_size // 2, end + 100)
                if boundary > start:
                    end = boundary + len(sep)
                    break

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "chunk_id": idx,
                "text": chunk_text,
                "char_start": start,
                "char_end": end,
                "length": len(chunk_text),
            })
            idx += 1

        start = end - overlap if end < len(text) else len(text)

    return chunks


# ─── Gemini Vision OCR (for scanned/image-heavy PDFs) ───────────────────────

_gemini_client = None


def _get_gemini():
    """Lazy-load Google GenAI client for Gemini Vision OCR."""
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        try:
            from google import genai
            if api_key:
                _gemini_client = genai.Client(api_key=api_key)
                _log.info("Gemini OCR: Initialized with API key (gemini-2.0-flash)")
            else:
                project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
                location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
                _gemini_client = genai.Client(vertexai=True, project=project, location=location)
                _log.info("Gemini OCR: Initialized with Vertex AI ADC (gemini-2.0-flash)")
        except ImportError:
            _log.warning("Gemini OCR: google-genai package not installed")
            return None
        except Exception as e:
            _log.warning("Gemini OCR: Failed to initialize: %s", e)
            return None
    return _gemini_client


def extract_text_gemini(filepath: Path, *, max_pages: int = 20) -> dict[str, Any]:
    """
    Extract text from a PDF using Google Gemini Vision API.
    Renders each page as an image and sends to Gemini for OCR.
    Best for scanned documents, handwritten notes, or image-heavy PDFs
    where PyMuPDF extraction yields poor results.

    Args:
        filepath: Path to the PDF file
        max_pages: Maximum pages to process (to control API costs)

    Returns:
        Structured result with per-page text and quality metrics
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}", "text": "", "pages": []}

    model = _get_gemini()
    if model is None:
        _log.info("Gemini OCR unavailable — falling back to PyMuPDF + Tesseract")
        return extract_text_pymupdf(filepath, ocr_fallback=True)

    fitz = _get_fitz()
    t0 = time.time()

    result = {
        "filename": filepath.name,
        "text": "",
        "pages": [],
        "page_count": 0,
        "extraction_method": "gemini_vision",
        "ocr_pages": 0,
        "quality_score": 0.0,
    }

    try:
        import io
        from PIL import Image as PILImage
        from google.genai import types

        doc = fitz.open(str(filepath))
        result["page_count"] = doc.page_count
        pages_to_process = min(doc.page_count, max_pages)
        all_text_parts = []

        for page_num in range(pages_to_process):
            page = doc[page_num]

            # First try PyMuPDF text extraction
            pymupdf_text = page.get_text("text").strip()

            if len(pymupdf_text) >= 200:
                # Good text extraction — no need for Gemini
                all_text_parts.append(pymupdf_text)
                result["pages"].append({
                    "page_num": page_num + 1,
                    "char_count": len(pymupdf_text),
                    "is_ocr": False,
                    "method": "pymupdf",
                })
                continue

            # Low text — use Gemini Vision
            try:
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                img = PILImage.open(io.BytesIO(img_bytes))

                config = types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                )
                response = model.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        "Extract ALL text from this document page. "
                        "Preserve the original structure including tables, headers, and formatting. "
                        "Return only the extracted text, no commentary.",
                        img,
                    ],
                    config=config,
                )

                gemini_text = response.text.strip() if response.text else ""

                if len(gemini_text) > len(pymupdf_text):
                    all_text_parts.append(gemini_text)
                    result["ocr_pages"] += 1
                    result["pages"].append({
                        "page_num": page_num + 1,
                        "char_count": len(gemini_text),
                        "is_ocr": True,
                        "method": "gemini_vision",
                    })
                else:
                    all_text_parts.append(pymupdf_text)
                    result["pages"].append({
                        "page_num": page_num + 1,
                        "char_count": len(pymupdf_text),
                        "is_ocr": False,
                        "method": "pymupdf",
                    })
            except Exception as e:
                _log.warning("Gemini OCR failed for page %d of %s: %s", page_num + 1, filepath.name, e)
                all_text_parts.append(pymupdf_text)
                result["pages"].append({
                    "page_num": page_num + 1,
                    "char_count": len(pymupdf_text),
                    "is_ocr": False,
                    "method": "pymupdf_fallback",
                })

        doc.close()
        result["text"] = "\n\n".join(all_text_parts)

        pages_with_text = sum(1 for p in result["pages"] if p["char_count"] > 50)
        result["quality_score"] = round(pages_with_text / max(result["page_count"], 1), 2)
        result["extraction_time_ms"] = round((time.time() - t0) * 1000, 1)

    except ImportError:
        _log.warning("PIL not available for Gemini OCR — falling back to PyMuPDF")
        return extract_text_pymupdf(filepath, ocr_fallback=True)
    except Exception as e:
        _log.error("Gemini OCR extraction failed for %s: %s", filepath.name, e)
        result["error"] = str(e)
        # Fall back to standard extraction
        return extract_text_pymupdf(filepath, ocr_fallback=True)

    return result


def extract_text_best(filepath: Path) -> dict[str, Any]:
    """
    Extract text using the best available method.
    1. Try PyMuPDF first — if quality_score >= 0.7, use it
    2. If quality is low, try Gemini Vision for better OCR
    3. Fall back to PyMuPDF + Tesseract if Gemini unavailable
    """
    result = extract_text_pymupdf(filepath, ocr_fallback=False)

    if result.get("error"):
        return result

    if result.get("quality_score", 0) >= 0.7:
        return result

    # Low quality — try Gemini
    _log.info("Low PyMuPDF quality (%.2f) for %s — trying Gemini Vision",
              result.get("quality_score", 0), filepath.name)

    gemini_result = extract_text_gemini(filepath)
    if not gemini_result.get("error") and gemini_result.get("quality_score", 0) > result.get("quality_score", 0):
        return gemini_result

    # Gemini didn't help — use PyMuPDF with Tesseract fallback
    return extract_text_pymupdf(filepath, ocr_fallback=True)


# ─── Downloaded Document Mapper ──────────────────────────────────────────────

# Mapping from filename prefixes (in "downloaded document/CAM/") to entity IDs
DOWNLOADED_DOC_MAP: dict[str, dict] = {
    "Apollo Hosp": {
        "entity_id": "APOL001",
        "company_name": "Apollo Hospitals Enterprise Limited",
        "doc_type": "annual_report",
    },
    "Infy": {
        "entity_id": "INFY001",
        "company_name": "Infosys Limited",
        "doc_type": "annual_report",
    },
    "IHCL": {
        "entity_id": "IHCL001",
        "company_name": "The Indian Hotels Company Limited",
        "doc_type": "annual_report",
    },
    "Madras Fert": {
        "entity_id": "MFL001",
        "company_name": "Madras Fertilizers Limited",
        "doc_type": "annual_report",
    },
    "MRF": {
        "entity_id": "MRF001",
        "company_name": "MRF Limited",
        "doc_type": "annual_report",
    },
    "TVS Mot": {
        "entity_id": None,
        "company_name": "TVS Motor Company Limited",
        "doc_type": "annual_report",
    },
}


def classify_downloaded_document(filename: str) -> dict[str, Any]:
    """Classify a downloaded document file by company and type."""
    for prefix, info in DOWNLOADED_DOC_MAP.items():
        if filename.startswith(prefix):
            # Determine if it's unaudited or annual report
            is_unaudited = "Unaudited" in filename
            # Extract fiscal year
            fy_match = re.search(r"(\d{2,4})[-_](\d{2,4})", filename)
            fy = fy_match.group(0) if fy_match else ""
            if "Unaudited" in filename:
                fy_match2 = re.search(r"Unaudited[-_]?(\d{4})-?(\d{2})?", filename)
                if fy_match2:
                    fy = fy_match2.group(1)
                    if fy_match2.group(2):
                        fy += "-" + fy_match2.group(2)

            return {
                "entity_id": info["entity_id"],
                "company_name": info["company_name"],
                "doc_type": "unaudited_financials" if is_unaudited else "annual_report",
                "fiscal_year": fy,
                "filename": filename,
            }

    return {"entity_id": None, "company_name": "Unknown", "doc_type": "unknown", "filename": filename}


def ingest_downloaded_documents(
    downloaded_dir: Path,
    storage_root: Path,
    entity_id: Optional[str] = None,
    on_progress: Optional[callable] = None,
) -> dict[str, Any]:
    """
    Process documents from the 'downloaded document/CAM/' folder.
    Verifies, extracts, and indexes them for RAG and CAM.

    If entity_id is specified, only processes docs matching that entity.
    """
    cam_dir = downloaded_dir / "CAM"
    if not cam_dir.exists():
        return {"status": "no_documents", "message": "No downloaded documents found"}

    results = {
        "processed": [],
        "skipped": [],
        "entity_extractions": {},
        "total_pages": 0,
        "total_chunks": 0,
    }

    pdf_files = sorted(cam_dir.glob("*.pdf"))

    # Filter and limit: keep only matching files, sorted newest first (max 2)
    matching_files = []
    for pdf_path in pdf_files:
        classification = classify_downloaded_document(pdf_path.name)
        if entity_id and classification["entity_id"] != entity_id:
            continue
        if classification["entity_id"] is None:
            results["skipped"].append({
                "filename": pdf_path.name,
                "reason": "No matching entity in system",
                "company": classification["company_name"],
            })
            continue
        matching_files.append((pdf_path, classification))

    # Sort descending by fiscal year so newest come first; keep up to 5 audited reports.
    matching_files.sort(key=lambda x: x[1].get("fiscal_year", ""), reverse=True)
    ar_count = 0
    selected = []
    for item in matching_files:
        if item[1]["doc_type"] == "annual_report":
            if ar_count >= 5:
                results["skipped"].append({
                    "filename": item[0].name,
                    "reason": "Older report — limited to 2 most recent ARs",
                })
                continue
            ar_count += 1
        selected.append(item)

    for pdf_path, classification in selected:
        if on_progress:
            on_progress(f"Processing {pdf_path.name} ({classification['fiscal_year']})...")

        _log.info("Processing downloaded doc: %s → %s", pdf_path.name, classification["entity_id"])

        # Fingerprint for authenticity
        fingerprint = compute_document_fingerprint(pdf_path)

        # Full PyMuPDF extraction
        extraction = extract_text_pymupdf(pdf_path, ocr_fallback=True)

        # Financial data extraction if it's an annual report
        fin_data = {}
        if classification["doc_type"] in ("annual_report", "unaudited_financials"):
            fin_data = extract_financials_enhanced(pdf_path, precomputed_raw=extraction)

        eid = classification["entity_id"]
        results["entity_extractions"].setdefault(eid, [])
        results["entity_extractions"][eid].append({
            "filename": pdf_path.name,
            "doc_type": classification["doc_type"],
            "fiscal_year": classification["fiscal_year"],
            "fingerprint": fingerprint.get("sha256", ""),
            "page_count": extraction.get("page_count", 0),
            "quality_score": extraction.get("quality_score", 0),
            "ocr_pages": extraction.get("ocr_pages", 0),
            "text_length": len(extraction.get("text", "")),
            "tables_found": len(extraction.get("tables", [])),
            "financial_metrics_found": list(fin_data.get("data", {}).keys()),
            "is_verified": fingerprint.get("is_verified", False),
        })

        results["total_pages"] += extraction.get("page_count", 0)
        results["processed"].append(pdf_path.name)

    return results
