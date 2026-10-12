"""Comprehensive E2E cloud validation script"""
import requests, json, time, sys

CLOUD = "https://camdemo-228620181301.asia-south1.run.app"
passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name} {detail}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")

print("=" * 60)
print("E2E Cloud Validation")
print("=" * 60)

# 1. Health Check
print("\n--- 1. Health Check ---")
r = requests.get(f"{CLOUD}/api/health", timeout=15)
d = r.json()
check("Health status", d["status"] == "healthy", d["status"])
check("LLM active", d.get("active_llm") is not None, d.get("active_llm"))

# 2. Companies
print("\n--- 2. Companies ---")
r = requests.get(f"{CLOUD}/api/companies", timeout=15)
d = r.json()
companies = d.get("companies", d) if isinstance(d, dict) else d
check("Companies loaded", len(companies) >= 6, f"{len(companies)} companies")
company_ids = [c.get("entity_id", c.get("id")) for c in companies]
check("PNCR001 present", "PNCR001" in company_ids)
check("INFY001 present", "INFY001" in company_ids)

# 3. Extraction for all companies
print("\n--- 3. Document Extraction ---")
for cid in company_ids:
    try:
        r = requests.post(f"{CLOUD}/api/companies/{cid}/extract", timeout=180)
        d = r.json()
        status = d.get("status", "unknown")
        check(f"Extract {cid}", status == "extracted", status)
    except Exception as e:
        check(f"Extract {cid}", False, str(e))

# 4. Pipeline run for PNCR001 (infra KPI test)
print("\n--- 4. Pipeline Run: PNCR001 (Infra KPIs) ---")
try:
    r = requests.post(f"{CLOUD}/api/cases/PNCR001/run", timeout=600)
    d = r.json()
    status = d.get("status", "unknown")
    check("PNCR001 pipeline", status in ("completed", "success", "complete"), status)
    
    # Check the case result
    r2 = requests.get(f"{CLOUD}/api/cases/PNCR001", timeout=30)
    case_data = r2.json()
    
    # Check infra_metrics in fact_pack
    fact_pack = case_data.get("fact_pack", {})
    infra_metrics = fact_pack.get("infra_metrics", {})
    check("Infra metrics populated", isinstance(infra_metrics, dict) and len(infra_metrics) > 0, f"{len(infra_metrics)} keys")
    if infra_metrics:
        print(f"  Infra metric keys: {list(infra_metrics.keys())}")
    
    # Check financial score (flat top-level key)
    fin_score = case_data.get("financial_score")
    check("Financial score present", fin_score is not None, f"score={fin_score}")
    
    # Check covenants (flat top-level key: covenants_proposed)
    covenants = case_data.get("covenants_proposed", [])
    check("Covenants present", len(covenants) > 0, f"{len(covenants)} covenants")
    if covenants:
        print(f"  Sample covenant: {covenants[0] if isinstance(covenants[0], str) else json.dumps(covenants[0])[:100]}")
    
    # Print key scoring fields
    print(f"  Sector: {case_data.get('sector')}")
    print(f"  Financial Score: {fin_score}")
    print(f"  Composite Score: {case_data.get('composite_score')}")
    print(f"  Risk Grade: {case_data.get('risk_grade')}")
    print(f"  Recommendation: {case_data.get('recommendation')}")
except Exception as e:
    check("PNCR001 pipeline", False, str(e))

# 5. Pipeline run for INFY001 (non-infra baseline)
print("\n--- 5. Pipeline Run: INFY001 (Baseline) ---")
try:
    r = requests.post(f"{CLOUD}/api/cases/INFY001/run", timeout=600)
    d = r.json()
    status = d.get("status", "unknown")
    check("INFY001 pipeline", status in ("completed", "success", "complete"), status)
except Exception as e:
    check("INFY001 pipeline", False, str(e))

# 6. Pipeline run for MRF001
print("\n--- 6. Pipeline Run: MRF001 ---")
try:
    r = requests.post(f"{CLOUD}/api/cases/MRF001/run", timeout=600)
    d = r.json()
    status = d.get("status", "unknown")
    check("MRF001 pipeline", status in ("completed", "success", "complete"), status)
except Exception as e:
    check("MRF001 pipeline", False, str(e))

# 7. PDF Generation for PNCR001
print("\n--- 7. PDF Generation ---")
try:
    r = requests.get(f"{CLOUD}/api/cases/PNCR001/cam-pdf", timeout=120)
    check("PNCR001 PDF", r.status_code == 200, f"status={r.status_code}, size={len(r.content)} bytes")
    check("PDF content type", "pdf" in r.headers.get("content-type", ""), r.headers.get("content-type", ""))
    check("PDF size reasonable", len(r.content) > 10000, f"{len(r.content)} bytes")
except Exception as e:
    check("PNCR001 PDF", False, str(e))

# 8. Dashboard
print("\n--- 8. Dashboard ---")
try:
    r = requests.get(f"{CLOUD}/api/dashboard", timeout=30)
    check("Dashboard", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    check("Dashboard", False, str(e))

# 9. Analyst Chat
print("\n--- 9. Analyst Chat ---")
try:
    r = requests.post(f"{CLOUD}/api/chat/PNCR001", 
                      json={"message": "What is the credit risk for PNCR001?"},
                      timeout=60)
    check("Analyst chat", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        d = r.json()
        response_text = d.get("response", d.get("message", ""))
        check("Chat response non-empty", len(str(response_text)) > 20, f"{len(str(response_text))} chars")
except Exception as e:
    check("Analyst chat", False, str(e))

# Summary
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
