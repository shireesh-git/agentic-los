FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime

LABEL maintainer="CAM Platform Team"
LABEL description="Credit appraisal platform with verified public-record onboarding and document-driven CAM generation"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r camuser && useradd -r -g camuser -d /app -s /usr/sbin/nologin camuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY run.py .
COPY requirements.txt .
COPY storage/documents/ ./storage/documents/
# Demo bureau / MCA / registry records (fix list E5): stand-ins for the APIs that are not connected
COPY storage/demo_registry/ ./storage/demo_registry/
# Demo cases: a consistent snapshot of runtime-db made by scripts/deploy_gcp.sh
COPY runtime-db-seed/ ./runtime-db/

# Read the catalogue borrowers' documents now, so the first CAM in the cloud does not read hundreds of
# pages on one CPU (the cache is keyed by the image's own paths and OCR setup).
RUN python scripts/warm_doc_cache.py

RUN mkdir -p /app/storage/cache /app/output /app/runtime-db /app/reference-docs /app/synthetic-assets \
    && chown -R camuser:camuser /app

USER camuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    CAM_STORAGE_ROOT=/app/storage \
    CAM_OUTPUT_ROOT=/app/output \
    CAM_RUNTIME_DB_ROOT=/app/runtime-db \
    CAM_REFERENCE_ROOT=/app/reference-docs \
    CAM_SYNTHETIC_ROOT=/app/synthetic-assets

# Cloud Run passes the port in $PORT
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + __import__('os').environ.get('PORT','8000') + '/api/health')" || exit 1

CMD ["sh", "-c", "exec python -m uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}"]
