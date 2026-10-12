# Postman Mock Server — Setup Guide

## Overview

The CAM Platform uses external data sources (MCA, Bureau, GST, Rating, Market, Exchange).
These are served via a **Postman Mock Server** — you can edit any company's data in Postman
without touching code.

## Architecture

```
┌─────────────────┐          ┌──────────────────────────┐
│   RM enters CIN │          │   Postman Mock Server    │
│   in the app    │          │   (editable responses)   │
│                 │          │                          │
│  POST /api/     │──HTTP───▶│  GET /v3/mca/company/{c} │
│  onboard/       │          │  GET /v2/bureau/{pan}    │
│  cin-lookup     │          │  GET /v1/gstn/{pan}      │
│                 │◀─JSON────│  GET /v1/rating/{eid}    │
│  Show data      │          │  GET /v1/market/{eid}    │
│  + missing docs │          │  GET /v1/dms/{eid}       │
│  RM uploads     │          │  GET /v1/exchange/{isin} │
│  → OCR          │          └──────────────────────────┘
│  → Pipeline     │
│  → CAM          │
└─────────────────┘
```

## Quick Start

### 1. Import Collection into Postman

1. Open Postman
2. Click **Import** (top left)
3. Drag or browse: `postman/CAM_ExternalData_MockServer.postman_collection.json`
4. Import the environment: `postman/CAM_ExternalData.postman_environment.json`

### 2. Create Mock Server

1. In the imported collection, click the **three dots (⋯)** → **Mock Collection**
2. Give it a name: `CAM External Data`
3. Click **Create Mock Server**
4. Copy the generated URL (e.g. `https://abc123.mock.pstmn.io`)

### 3. Configure the App

**Option A: Environment variables**
```powershell
$env:CAM_MOCK_MODE = "http"
$env:CAM_MOCK_URL = "https://abc123.mock.pstmn.io"
python -m uvicorn src.api.main:app --port 8001
```

**Option B: Edit config file** (`config/external_apis.yaml`)
```yaml
mock_server:
  mode: "http"
  url: "https://abc123.mock.pstmn.io"
```

### 4. Test the Flow

```bash
# CIN Lookup — fetch all public data
curl -X POST http://localhost:8001/api/onboard/cin-lookup \
  -H "Content-Type: application/json" \
  -d '{"cin": "L27100MH1907PLC000260"}'

# Full onboarding from CIN
curl -X POST http://localhost:8001/api/onboard \
  -H "Content-Type: application/json" \
  -d '{"identifier": "L27100MH1907PLC000260", "amount_requested_cr": 2500}'
```

## Editing Mock Data

1. Open Postman → navigate to the collection
2. Open any request (e.g. `MCA → Company Master`)
3. Go to the **Examples** tab (bottom panel)
4. Select the company example you want to edit
5. Modify the response JSON body
6. Click **Save**
7. The mock server reflects changes immediately — no restart needed

## Data Sources in the Collection

| Folder | API | Lookup Key | Examples |
|--------|-----|------------|----------|
| 🏛️ MCA | Company Master | CIN | 16 companies |
| 🏛️ MCA | Directors & KMPs | CIN | 16 companies |
| 🏛️ MCA | Charges Register | CIN | 16 companies |
| 📊 Bureau | Commercial Credit Report | PAN | 16 companies |
| 🧾 GSTN | GST Turnover | PAN | 16 companies |
| ⭐ Rating | Latest Rating Action | entity_id | 16 companies |
| 📰 Market | News & Sentiment | entity_id | 16 companies |
| 📈 Exchange | Corporate Filings | ISIN | 14 listed companies |
| 📁 DMS | Document Store | entity_id | 16 companies |
| 🚀 Onboarding | CIN Lookup Flow | CIN | 3 sample flows |

**Total: 147 mock responses**

## RM Workflow

```
1. RM enters CIN  ──────────────────────────────────────────┐
                                                             │
2. System auto-fetches public data:                          │
   ✅ MCA Company Master   (company details, status)         │
   ✅ MCA Directors         (directors, DINs)                 │
   ✅ MCA Charges           (registered charges)              │
   ✅ Bureau Report         (credit score, DPD, exposures)    │
   ✅ GST Turnover          (aggregate turnover, filings)     │
   ✅ Credit Rating         (CRISIL/ICRA rating, outlook)  ◀──┘
   ✅ Market Sentiment      (news, ESG flags)
   ✅ Exchange Filings      (listed companies only)
                                                             │
3. System shows RM: "Found 7/8 data sources"                 │
   "Missing: Audited financials, Provisionals, etc."         │
                                                             │
4. RM uploads missing documents:                             │
   📄 Audited Financial FY2024 (PDF) → OCR → extract data    │
   📄 Audited Financial FY2023 (PDF) → OCR → extract data    │
   📊 Provisional FY2025 (Excel) → parse → extract data      │
   📋 Board Resolution (PDF) → OCR → store                   │
   📋 CMA Projection (Excel) → parse → store                 │
                                                             │
5. Pipeline runs:                                            │
   DataIngestion → FinancialAnalysis → Validation →          │
   Benchmarking → PolicyCompliance → Narrative               │
                                                             │
6. CAM generated with full data + source citations           │
```

## Adding a New Company

1. **In the generator**: Add company data to the `COMPANIES` list in
   `postman/generate_mock_collection.py`, then re-run:
   ```
   python postman/generate_mock_collection.py
   ```

2. **In Postman directly**: Open any request → Examples tab → Add Example →
   paste the response JSON with the new company's data

## Files

| File | Purpose |
|------|---------|
| `postman/generate_mock_collection.py` | Generator script (re-run to update collection) |
| `postman/CAM_ExternalData_MockServer.postman_collection.json` | The Postman collection (368 KB, 147 responses) |
| `postman/CAM_ExternalData.postman_environment.json` | Environment with all company identifiers |
| `config/external_apis.yaml` | App configuration for mock server mode |
| `src/data/mock_external_apis.py` | Mock adapter — supports `local` and `http` modes |

## Modes Comparison

| Feature | `local` mode | `http` mode |
|---------|-------------|-------------|
| Data source | Python dicts | Postman Mock Server |
| Edit data | Modify Python code | Edit in Postman UI |
| Latency | 0 ms | ~200-500 ms |
| Requires | Nothing | Postman + mock server |
| Best for | Development, testing | Demo, user acceptance |
