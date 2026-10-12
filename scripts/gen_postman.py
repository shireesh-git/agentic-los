"""Generate comprehensive Postman collection + environment for all 16 companies."""

import json, uuid, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data.synthetic_companies import ALL_COMPANIES

BASE = "{{base_url}}"

# ─── Company metadata ───────────────────────────────────────────────────────

companies = {}
for eid, cd in ALL_COMPANIES.items():
    b = cd["borrower"]
    companies[eid] = {
        "name": b.company_name,
        "pan": b.pan,
        "cin": b.cin,
        "sector": b.sector,
    }

# Case types per company
CASE_TYPES = {
    "BMFG001": "NTB", "PINF001": "NTB", "SPHR001": "NTB", "OLOG001": "ETB",
    "TSTL001": "NTB", "REIL001": "NTB", "INFY001": "NTB", "ADPT001": "NTB",
    "BJFN001": "NTB", "CIPL001": "NTB", "DLFR001": "ETB", "JSWL001": "NTB",
    "MRUT001": "NTB", "TITN001": "NTB", "NTPC001": "ETB", "YESB001": "ETB",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def req(name, method, url, body=None, tests="", pre_req=""):
    r = {
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}] if body else [],
            "url": {"raw": url, "host": [BASE], "path": url.replace(BASE + "/", "").split("/")},
        },
        "response": [],
    }
    if body:
        r["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2)}
    events = []
    if tests:
        events.append({"listen": "test", "script": {"type": "text/javascript", "exec": tests.split("\n")}})
    if pre_req:
        events.append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre_req.split("\n")}})
    if events:
        r["event"] = events
    return r

def status_test(code=200):
    return f"pm.test('Status {code}', function(){{ pm.response.to.have.status({code}); }});"

def json_test(path, desc=""):
    return f"pm.test('{desc or path}', function(){{ var j=pm.response.json(); pm.expect(j.{path}).to.exist; }});"

# ─── Build Folders ───────────────────────────────────────────────────────────

folders = []

# 1. Health & Dashboard
health_items = [
    req("Health Check", "GET", f"{BASE}/api/health",
        tests=status_test() + "\n" + json_test("status", "has status")),
    req("Dashboard", "GET", f"{BASE}/api/dashboard",
        tests=status_test() + "\n" + json_test("metrics", "has metrics")),
    req("Enums", "GET", f"{BASE}/api/enums",
        tests=status_test()),
]
folders.append({"name": "Health & Dashboard", "item": health_items})

# 2. Company Management
co_items = [
    req("List Companies", "GET", f"{BASE}/api/companies",
        tests=status_test() + "\npm.test('has companies', function(){ pm.expect(pm.response.json().length).to.be.above(0); });"),
    req("Get Company (BMFG001)", "GET", f"{BASE}/api/companies/BMFG001",
        tests=status_test()),
]
folders.append({"name": "Company Management", "item": co_items})

# 3. Smart Onboarding — per company with multiple resolution methods
onboard_items = []
for eid, info in companies.items():
    ct = CASE_TYPES.get(eid, "NTB")
    onboard_items.append(
        req(f"Onboard {info['name']} ({eid}) by Entity ID", "POST", f"{BASE}/api/onboard",
            body={"identifier": eid, "case_type": ct, "facility_type": "working_capital",
                  "amount_requested_cr": 500, "purpose": "General corporate"},
            tests=status_test() + "\npm.test('onboarded', function(){ pm.expect(pm.response.json().entity_id).to.eql('" + eid + "'); });")
    )
# Also show PAN-based resolution for a few
for eid in ["BMFG001", "INFY001", "YESB001"]:
    info = companies[eid]
    onboard_items.append(
        req(f"Onboard {info['name']} by PAN", "POST", f"{BASE}/api/onboard",
            body={"identifier": info["pan"], "case_type": CASE_TYPES[eid]},
            tests=status_test())
    )
# CIN-based
for eid in ["TSTL001", "NTPC001"]:
    info = companies[eid]
    onboard_items.append(
        req(f"Onboard {info['name']} by CIN", "POST", f"{BASE}/api/onboard",
            body={"identifier": info["cin"], "case_type": CASE_TYPES[eid]},
            tests=status_test())
    )
# Name-based
onboard_items.append(
    req("Resolve by Name (Bharat Mfg)", "POST", f"{BASE}/api/resolve",
        body={"identifier": "Bharat Manufacturing Ltd"},
        tests=status_test())
)
folders.append({"name": "Smart Onboarding (16 Firms)", "item": onboard_items})

# 4. Pipeline Execution — per company
pipeline_items = [
    req("Run Pipeline — All Companies", "POST", f"{BASE}/api/pipeline/run-all",
        tests=status_test() + "\npm.test('has results', function(){ pm.expect(pm.response.json().results.length).to.be.above(0); });"),
]
for eid, info in companies.items():
    pipeline_items.append(
        req(f"Run Case — {info['name']} ({eid})", "POST", f"{BASE}/api/cases/{eid}/run",
            tests=status_test())
    )
folders.append({"name": "Pipeline & Cases", "item": pipeline_items})

# 5. CAM Generation
cam_items = []
for eid, info in companies.items():
    cam_items.append(
        req(f"CAM — {info['name']}", "GET", f"{BASE}/api/cases/{eid}/cam",
            tests=status_test())
    )
folders.append({"name": "CAM Generation", "item": cam_items})

# 6. Document Management
doc_items = []
for eid, info in companies.items():
    doc_items.append(
        req(f"List Docs — {info['name']}", "GET", f"{BASE}/api/companies/{eid}/documents",
            tests=status_test())
    )
folders.append({"name": "Document Repository", "item": doc_items})

# 7. Document Extraction
ext_items = []
for eid in ["BMFG001", "OLOG001", "DLFR001", "NTPC001", "YESB001", "INFY001"]:
    info = companies[eid]
    ext_items.append(
        req(f"Extract Docs — {info['name']}", "POST", f"{BASE}/api/companies/{eid}/extract",
            tests=status_test())
    )
    ext_items.append(
        req(f"Get Extraction — {info['name']}", "GET", f"{BASE}/api/companies/{eid}/extraction",
            tests=status_test())
    )
folders.append({"name": "Document Extraction", "item": ext_items})

# 8. ETB Analytics
etb_items = []
for eid in ["OLOG001", "DLFR001", "NTPC001", "YESB001"]:
    info = companies[eid]
    etb_items.append(
        req(f"Run ETB Analytics — {info['name']}", "POST", f"{BASE}/api/companies/{eid}/etb-analytics",
            tests=status_test())
    )
    etb_items.append(
        req(f"Get ETB Results — {info['name']}", "GET", f"{BASE}/api/companies/{eid}/etb-analytics",
            tests=status_test())
    )
folders.append({"name": "ETB Analytics", "item": etb_items})

# 9. Fraud Detection — all 16
fraud_items = []
for eid, info in companies.items():
    fraud_items.append(
        req(f"Fraud Scan — {info['name']}", "POST", f"{BASE}/api/companies/{eid}/fraud-analysis",
            tests=status_test() + "\npm.test('has risk_grade', function(){ pm.expect(pm.response.json().risk_grade).to.exist; });")
    )
    fraud_items.append(
        req(f"Fraud Results — {info['name']}", "GET", f"{BASE}/api/companies/{eid}/fraud-analysis",
            tests=status_test())
    )
folders.append({"name": "Fraud Detection (16 Firms)", "item": fraud_items})

# 10. OCR & Document Intelligence
ocr_items = [
    req("OCR Extract — BMFG001 annual_report", "POST",
        f"{BASE}/api/companies/BMFG001/ocr/financial_reports/annual_report_FY2024.pdf",
        tests=status_test()),
    req("OCR Metadata — BMFG001 annual_report", "POST",
        f"{BASE}/api/companies/BMFG001/ocr-metadata/financial_reports/annual_report_FY2024.pdf",
        tests=status_test()),
]
folders.append({"name": "OCR & Document Intelligence", "item": ocr_items})

# 11. Analyst Chat
chat_items = [
    req("Chat — Ask about BMFG001", "POST", f"{BASE}/api/chat/BMFG001",
        body={"message": "What is the financial health of this company?"},
        tests=status_test()),
    req("Chat History — BMFG001", "GET", f"{BASE}/api/chat/BMFG001/history",
        tests=status_test()),
    req("Chat Sessions", "GET", f"{BASE}/api/chat/sessions",
        tests=status_test()),
]
folders.append({"name": "Analyst Chat", "item": chat_items})

# 12. 360° View
v360_items = []
for eid in ["BMFG001", "OLOG001", "INFY001", "YESB001", "DLFR001", "NTPC001"]:
    info = companies[eid]
    v360_items.append(
        req(f"360° — {info['name']}", "GET", f"{BASE}/api/companies/{eid}/360",
            tests=status_test())
    )
folders.append({"name": "360° View", "item": v360_items})

# 13. External Systems (Mock APIs)
ext_sys = []
# Use first company for each
pan1, cin1 = companies["BMFG001"]["pan"], companies["BMFG001"]["cin"]
ext_sys.append(req("MCA Company Master", "GET", f"{BASE}/api/external/mca/company/{cin1}", tests=status_test()))
ext_sys.append(req("MCA Directors", "GET", f"{BASE}/api/external/mca/directors/{cin1}", tests=status_test()))
ext_sys.append(req("MCA Charges", "GET", f"{BASE}/api/external/mca/charges/{cin1}", tests=status_test()))
ext_sys.append(req("GSTIN Details", "GET", f"{BASE}/api/external/gstin/27AABCB1234F1Z5", tests=status_test()))
ext_sys.append(req("GST Turnover", "GET", f"{BASE}/api/external/gst-turnover/{pan1}", tests=status_test()))
ext_sys.append(req("Bureau Report", "GET", f"{BASE}/api/external/bureau/{pan1}", tests=status_test()))
ext_sys.append(req("Rating Action", "GET", f"{BASE}/api/external/rating/BMFG001", tests=status_test()))
ext_sys.append(req("Market Intelligence", "GET", f"{BASE}/api/external/market/BMFG001", tests=status_test()))
ext_sys.append(req("CRILC Report", "GET", f"{BASE}/api/external/crilc/{pan1}", tests=status_test()))
ext_sys.append(req("EPFO Compliance", "GET", f"{BASE}/api/external/epfo/{pan1}", tests=status_test()))
ext_sys.append(req("ITR Filing Status", "GET", f"{BASE}/api/external/itr/{pan1}", tests=status_test()))
# Add a few more companies' external calls
for eid in ["INFY001", "YESB001", "NTPC001"]:
    info = companies[eid]
    ext_sys.append(req(f"Bureau — {info['name']}", "GET", f"{BASE}/api/external/bureau/{info['pan']}", tests=status_test()))
    ext_sys.append(req(f"Rating — {info['name']}", "GET", f"{BASE}/api/external/rating/{eid}", tests=status_test()))
folders.append({"name": "External Systems (Mock APIs)", "item": ext_sys})

# 14. Configuration
cfg_items = [
    req("Get Benchmarks", "GET", f"{BASE}/api/config/benchmarks", tests=status_test()),
    req("Get Rules", "GET", f"{BASE}/api/config/rules", tests=status_test()),
    req("List Engines", "GET", f"{BASE}/api/engines", tests=status_test()),
    req("LLM Providers", "GET", f"{BASE}/api/llm/providers", tests=status_test()),
    req("LLM Active", "GET", f"{BASE}/api/llm/active", tests=status_test()),
    req("Agents", "GET", f"{BASE}/api/agents", tests=status_test()),
]
folders.append({"name": "Configuration & Engines", "item": cfg_items})

# ─── Assemble Collection ────────────────────────────────────────────────────

collection = {
    "info": {
        "_postman_id": str(uuid.uuid4()),
        "name": "CAM Intelligence Platform — Full Suite (16 Firms)",
        "description": "Comprehensive API collection for the CAM Intelligence Platform covering all 55+ endpoints across 16 Indian corporates. Includes smart onboarding, pipeline execution, CAM generation, document extraction, ETB analytics, fraud detection, OCR, analyst chat, 360° views, and external system integrations.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": folders,
    "variable": [{"key": "base_url", "value": "http://localhost:8001"}],
}

# ─── Generate Environment ───────────────────────────────────────────────────

env_vars = [
    {"key": "base_url", "value": "http://localhost:8001", "type": "default", "enabled": True},
]
for eid, info in companies.items():
    env_vars.append({"key": f"eid_{eid}", "value": eid, "type": "default", "enabled": True})
    env_vars.append({"key": f"pan_{eid}", "value": info["pan"], "type": "default", "enabled": True})
    env_vars.append({"key": f"cin_{eid}", "value": info["cin"], "type": "default", "enabled": True})

environment = {
    "id": str(uuid.uuid4()),
    "name": "CAM Platform — 16 Firms",
    "values": env_vars,
    "_postman_variable_scope": "environment",
}

# ─── Write out ───────────────────────────────────────────────────────────────

out_dir = os.path.join(os.path.dirname(__file__), "..", "postman")
os.makedirs(out_dir, exist_ok=True)

col_path = os.path.join(out_dir, "CAM_Full_Suite.postman_collection.json")
env_path = os.path.join(out_dir, "CAM_16Firms.postman_environment.json")

with open(col_path, "w") as f:
    json.dump(collection, f, indent=2)
print(f"Collection: {col_path}")

with open(env_path, "w") as f:
    json.dump(environment, f, indent=2)
print(f"Environment: {env_path}")

# Count total requests
total = sum(
    sum(1 for _ in folder.get("item", []))
    for folder in folders
)
print(f"Total requests: {total}")
print(f"Folders: {len(folders)}")
