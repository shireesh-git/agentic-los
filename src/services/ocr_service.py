"""
OCR & Document Intelligence Service
=====================================
Multi-strategy document text extraction:
1. Native PDF text (pdfplumber) — fast, accurate for digital PDFs
2. OCR via pytesseract — for scanned/image PDFs
3. Hybrid — try native first, fall back to OCR if text density is low

Also provides document metadata analysis for fraud detection.
"""

import io
import os
import re
from pathlib import Path
from typing import Any

import pdfplumber
from src.core.runtime_paths import DOCUMENTS_ROOT

# Optional OCR imports — gracefully degrade if not available
try:
    from PIL import Image
    import pytesseract
    _tesseract_cmd = (
        os.environ.get("TESSERACT_CMD")
        or os.environ.get("TESSERACT_PATH")
        or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    if Path(_tesseract_cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

# ─── Configuration ────────────────────────────────────────────────────────────

MIN_TEXT_DENSITY = 50  # chars per page to consider "digital" (vs scanned)
OCR_DPI = 300
OCR_LANG = "eng"


# ─── Core Extraction ─────────────────────────────────────────────────────────

def extract_text_native(filepath: str | Path) -> dict[str, Any]:
    """Extract text using pdfplumber (native PDF text layer)."""
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}", "text": "", "pages": []}

    result = {
        "filename": filepath.name,
        "method": "native",
        "text": "",
        "pages": [],
        "metadata": {},
        "tables": [],
    }

    with pdfplumber.open(filepath) as pdf:
        result["metadata"]["page_count"] = len(pdf.pages)
        result["metadata"]["pdf_info"] = {
            k: str(v) for k, v in (pdf.metadata or {}).items()
        }
        all_text = []
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            result["pages"].append({
                "page_num": i + 1,
                "text": text,
                "char_count": len(text),
                "table_count": len(tables),
            })
            all_text.append(text)
            for tbl in tables:
                if tbl and len(tbl) > 1:
                    result["tables"].append({
                        "page": i + 1,
                        "rows": len(tbl),
                        "data": tbl[:20],  # cap for memory
                    })
        result["text"] = "\n".join(all_text)
        result["total_chars"] = len(result["text"])

    return result


def extract_text_ocr(filepath: str | Path) -> dict[str, Any]:
    """Extract text using OCR (pytesseract) — for scanned PDFs."""
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}", "text": "", "pages": []}

    if not HAS_TESSERACT:
        return {
            "error": "OCR not available. Install pytesseract and Tesseract-OCR.",
            "text": "",
            "pages": [],
            "method": "ocr_unavailable",
        }

    result = {
        "filename": filepath.name,
        "method": "ocr",
        "text": "",
        "pages": [],
        "metadata": {},
        "ocr_confidence": 0,
    }

    try:
        # Convert PDF pages to images via pdfplumber rendering
        with pdfplumber.open(filepath) as pdf:
            result["metadata"]["page_count"] = len(pdf.pages)
            all_text = []
            confidence_scores = []

            for i, page in enumerate(pdf.pages):
                # Render page to image
                img = page.to_image(resolution=OCR_DPI)
                pil_img = img.original

                # Run OCR
                ocr_data = pytesseract.image_to_data(
                    pil_img, lang=OCR_LANG, output_type=pytesseract.Output.DICT
                )
                text = pytesseract.image_to_string(pil_img, lang=OCR_LANG)

                # Calculate confidence
                confs = [int(c) for c in ocr_data["conf"] if int(c) > 0]
                page_conf = sum(confs) / len(confs) if confs else 0

                result["pages"].append({
                    "page_num": i + 1,
                    "text": text,
                    "char_count": len(text),
                    "ocr_confidence": round(page_conf, 1),
                })
                all_text.append(text)
                confidence_scores.append(page_conf)

            result["text"] = "\n".join(all_text)
            result["total_chars"] = len(result["text"])
            result["ocr_confidence"] = round(
                sum(confidence_scores) / len(confidence_scores), 1
            ) if confidence_scores else 0

    except Exception as e:
        result["error"] = f"OCR failed: {str(e)}"

    return result


def extract_document(filepath: str | Path) -> dict[str, Any]:
    """
    Smart extraction: try native first, fall back to OCR if text is sparse.
    Returns unified result with method indicator.
    """
    filepath = Path(filepath)

    # Step 1: Try native extraction
    native = extract_text_native(filepath)
    if native.get("error"):
        return native

    # Check text density
    page_count = native["metadata"].get("page_count", 1) or 1
    avg_chars = native.get("total_chars", 0) / page_count

    if avg_chars >= MIN_TEXT_DENSITY:
        # Good native text — return as-is
        native["extraction_strategy"] = "native"
        native["text_density"] = round(avg_chars, 1)
        return native

    # Step 2: Text is sparse — try OCR
    if HAS_TESSERACT:
        ocr = extract_text_ocr(filepath)
        if not ocr.get("error") and ocr.get("total_chars", 0) > native.get("total_chars", 0):
            ocr["extraction_strategy"] = "ocr_fallback"
            ocr["native_chars"] = native.get("total_chars", 0)
            return ocr

    # Step 3: Return native even if sparse
    native["extraction_strategy"] = "native_sparse"
    native["text_density"] = round(avg_chars, 1)
    native["ocr_available"] = HAS_TESSERACT
    return native


# ─── Document Metadata Analysis ──────────────────────────────────────────────

def analyze_document_metadata(filepath: str | Path) -> dict[str, Any]:
    """
    Analyze PDF metadata for fraud detection indicators.
    Checks: creation date, modification history, producer software, anomalies.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {"error": f"File not found: {filepath}"}

    result = {
        "filename": filepath.name,
        "file_size_bytes": filepath.stat().st_size,
        "metadata": {},
        "anomalies": [],
        "risk_score": 0,
    }

    with pdfplumber.open(filepath) as pdf:
        meta = pdf.metadata or {}
        result["metadata"] = {k: str(v) for k, v in meta.items()}
        result["page_count"] = len(pdf.pages)

        # Check for modification indicators
        creator = str(meta.get("Creator", "")).lower()
        producer = str(meta.get("Producer", "")).lower()
        mod_date = str(meta.get("ModDate", ""))
        create_date = str(meta.get("CreationDate", ""))

        # Anomaly checks
        risk = 0

        # 1. Edited with different tool than created
        if creator and producer and creator != producer:
            if any(ed in producer for ed in ["edit", "modify", "foxit", "nitro"]):
                result["anomalies"].append("Document modified with editing tool")
                risk += 15

        # 2. Very small file for page count
        pages = len(pdf.pages)
        if pages > 0:
            bytes_per_page = filepath.stat().st_size / pages
            if bytes_per_page < 500:
                result["anomalies"].append(f"Unusually small file ({bytes_per_page:.0f} bytes/page)")
                risk += 10

        # 3. Recently created with old dates
        if create_date and mod_date and create_date != mod_date:
            result["anomalies"].append("Document has been modified after creation")
            risk += 5

        # 4. Inconsistent page sizes (could indicate spliced pages)
        widths = set()
        for page in pdf.pages:
            w = round(page.width, 0)
            widths.add(w)
        if len(widths) > 1:
            result["anomalies"].append(f"Inconsistent page widths: {widths}")
            risk += 10

        result["risk_score"] = min(risk, 100)

    return result


# ─── Batch Processing ────────────────────────────────────────────────────────

def ocr_all_documents(entity_id: str, storage_root: Path | None = None) -> dict[str, Any]:
    """
    Run OCR/extraction on all documents for an entity.
    Returns structured results per document.
    """
    if storage_root is None:
        storage_root = DOCUMENTS_ROOT

    entity_dir = storage_root / entity_id
    if not entity_dir.exists():
        return {"error": f"No documents found for {entity_id}"}

    results = {
        "entity_id": entity_id,
        "documents": [],
        "metadata_analysis": [],
        "total_documents": 0,
        "ocr_used_count": 0,
        "anomaly_count": 0,
    }

    for pdf_path in sorted(entity_dir.rglob("*.pdf")):
        rel = str(pdf_path.relative_to(entity_dir))

        # Extract text
        ext = extract_document(pdf_path)
        ext["relative_path"] = rel
        results["documents"].append({
            "path": rel,
            "method": ext.get("extraction_strategy", "unknown"),
            "chars": ext.get("total_chars", 0),
            "pages": ext.get("metadata", {}).get("page_count", 0),
            "text_preview": ext.get("text", "")[:300],
        })
        results["total_documents"] += 1
        if "ocr" in ext.get("extraction_strategy", ""):
            results["ocr_used_count"] += 1

        # Metadata analysis
        meta = analyze_document_metadata(pdf_path)
        if meta.get("anomalies"):
            results["metadata_analysis"].append({
                "path": rel,
                "anomalies": meta["anomalies"],
                "risk_score": meta["risk_score"],
            })
            results["anomaly_count"] += len(meta["anomalies"])

    return results
