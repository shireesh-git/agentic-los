"""Push the CAM collection to Postman via API."""
import json
import os
import sys
import urllib.request
import urllib.error

API_KEY = os.environ.get("POSTMAN_API_KEY")
if not API_KEY:
    print("ERROR: POSTMAN_API_KEY environment variable not set")
    sys.exit(1)

WORKSPACE_ID = "bb454203-6796-4262-8352-7d05e9c4eff0"
BASE = "https://api.getpostman.com"

def api_call(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Api-Key", API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"HTTP {e.code}: {error_body}")
        raise

# Load collection JSON
with open("CAM_ExternalData_MockServer.postman_collection.json", "r", encoding="utf-8") as f:
    collection = json.load(f)

print(f"Collection: {collection['info']['name']}")
print(f"Folders: {len(collection['item'])}")
total_responses = sum(
    len(req.get("response", []))
    for folder in collection["item"]
    for req in folder.get("item", [])
)
print(f"Total example responses: {total_responses}")

# Push collection to workspace
print("\nPushing collection to Postman...")
result = api_call("POST", f"/collections?workspace={WORKSPACE_ID}", {
    "collection": collection
})

coll_id = result["collection"]["id"]
coll_uid = result["collection"]["uid"]
print(f"SUCCESS! Collection created.")
print(f"  ID:  {coll_id}")
print(f"  UID: {coll_uid}")

# Save IDs for mock server creation
with open("_postman_ids.json", "w") as f:
    json.dump({"collection_id": coll_id, "collection_uid": coll_uid}, f)

print("\nCollection imported. Ready for mock server creation.")
