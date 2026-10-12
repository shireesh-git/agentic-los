FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim-bookworm AS runtime

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
COPY synthetic-assets/ ./synthetic-assets/
COPY ["downloaded document/CAM/", "./reference-docs/"]

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

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
