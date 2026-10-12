"""Cloud deployment verification script"""
import requests, json, sys

CLOUD = "https://camdemo-228620181301.asia-south1.run.app"
print("=== Cloud Verification ===\n")

# Health
r = requests.get(f"{CLOUD}/api/health", timeout=15)
d = r.json()
print(f"Health: {d['status']}, LLM: {d['active_llm']}")

# LLM test
r = requests.post(f"{CLOUD}/api/llm/test", timeout=30)
d = r.json()
print(f"LLM test: status={d['status']}, provider={d.get('provider')}, model={d.get('model')}")
if d.get("response"):
    print(f"  response: {d['response'][:80]}")
if d["status"] != "ok":
    print(f"  message: {d.get('message', '')[:200]}")

# Companies
r = requests.get(f"{CLOUD}/api/companies", timeout=10)
d = r.json()
companies = d.get("companies", d) if isinstance(d, dict) else d
print(f"Companies: {len(companies)} loaded")

# Documents
r = requests.get(f"{CLOUD}/api/companies/INFY001/documents", timeout=10)
d = r.json()
total = sum(len(v) if isinstance(v, list) else 0 for v in d.values())
print(f"INFY001 docs: {total} files")

# Extraction
print("\nRunning extraction...")
r = requests.post(f"{CLOUD}/api/companies/INFY001/extract", timeout=120)
print(f"Extraction: status={r.status_code}")
print(f"  body: {r.text[:300]}")

# 360 View
r = requests.get(f"{CLOUD}/api/companies/INFY001/360", timeout=30)
d = r.json()
print(f"\n360 View: {len(d)} sections, keys={list(d.keys())[:8]}")
