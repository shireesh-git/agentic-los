#!/usr/bin/env bash
# Deploy the agentic LOS demo to Google Cloud Run (lowest-cost settings). Run it in Cloud Shell:
#
#   git clone https://github.com/shireesh-git/agentic-los.git && cd agentic-los
#   # optional demo data: upload cam_platform.sqlite3 into runtime-db-seed/ (see below)
#   bash scripts/deploy_gcp.sh
#
# Demo data: make a snapshot on the laptop and upload it to runtime-db-seed/ in Cloud Shell:
#   python -c "import sqlite3; s=sqlite3.connect('runtime-db/cam_platform.sqlite3'); o=sqlite3.connect('runtime-db-seed/cam_platform.sqlite3'); s.backup(o)"
# Without it the app starts with an empty database.
#
# Testers' work is kept: the app copies its database and uploaded files to the bucket gs://<project>-los-state
# every minute and on shutdown, and restores them at startup, so restarts and redeploys keep the cases.
# The snapshot above is used only while the bucket is empty. Start again from the demo data:
#   RESET_DATA=1 bash scripts/deploy_gcp.sh
#
# AI model: Gemini on Vertex AI, using the runtime service account (no API key).
# The NVIDIA NIM key, if stored in Secret Manager as 'nvidia-nim-api-key', is passed to the app too,
# so switching back is one setting: LLM_ACTIVE_PROVIDER=nvidia_nim.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-kpmg-lending-trans-sol}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-kpmg-agentic-los}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
RUNTIME_SA="${RUNTIME_SA:-agentic-los-runner@${PROJECT_ID}.iam.gserviceaccount.com}"
STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-los-state}"

cd "$(dirname "$0")/.."
mkdir -p runtime-db-seed
if [[ -f runtime-db-seed/cam_platform.sqlite3 ]]; then
  echo "Demo data: runtime-db-seed/cam_platform.sqlite3 ($(du -k runtime-db-seed/cam_platform.sqlite3 | cut -f1) KB)"
else
  echo "No demo data in runtime-db-seed/: the app will start with an empty database."
fi

gcloud config set project "$PROJECT_ID"
APIS="run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com"
# Enabling is a "mutate" call with a per-minute quota that is sometimes exhausted (RATE_LIMIT_EXCEEDED):
# after the first deploy the APIs are already on, so a failure only matters if one of them is off.
if ! gcloud services enable $APIS 2>/tmp/enable-err.txt; then
  echo "Could not enable the APIs ($(grep -o 'RATE_LIMIT_EXCEEDED' /tmp/enable-err.txt | head -1 || echo 'see /tmp/enable-err.txt')): checking they are already on"
  ENABLED="$(gcloud services list --enabled --format='value(config.name)')"
  for api in $APIS; do
    grep -qx "$api" <<<"$ENABLED" || { echo "$api is not enabled — run the deploy again in a minute"; exit 1; }
  done
  echo "All required APIs are already enabled"
fi

# New Gemini models reach regional Vertex endpoints later than the global one: use the region if
# the model answers there, otherwise 'global'.
GEMINI_LOCATION="${GEMINI_LOCATION:-}"
if [[ -z "$GEMINI_LOCATION" ]]; then
  TOKEN="$(gcloud auth print-access-token)"
  BODY='{"contents":[{"role":"user","parts":[{"text":"Say hi"}]}]}'
  for loc in "$REGION" global; do
    host="${loc}-aiplatform.googleapis.com"; [[ "$loc" == global ]] && host="aiplatform.googleapis.com"
    code="$(curl -s -o /tmp/gemini-check.json -w '%{http_code}' -X POST -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/json' -d "$BODY" \
      "https://${host}/v1/projects/${PROJECT_ID}/locations/${loc}/publishers/google/models/${GEMINI_MODEL}:generateContent")"
    echo "Vertex AI ${GEMINI_MODEL} in ${loc}: HTTP ${code}"
    if [[ "$code" == 200 ]]; then GEMINI_LOCATION="$loc"; break; fi
    grep -m1 '"message"' /tmp/gemini-check.json || true
  done
  [[ -n "$GEMINI_LOCATION" ]] || { echo "Gemini model ${GEMINI_MODEL} is not reachable on Vertex AI"; exit 1; }
fi
echo "Gemini location: ${GEMINI_LOCATION}"

for role in roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$RUNTIME_SA" \
    --role "$role" --condition None --quiet --format none
done

# Where the app keeps its database and uploads between restarts (a few MB: pennies a month)
if ! gcloud storage buckets describe "gs://${STATE_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${STATE_BUCKET}" --location "$REGION" --uniform-bucket-level-access
fi
gcloud storage buckets add-iam-policy-binding "gs://${STATE_BUCKET}" --member "serviceAccount:$RUNTIME_SA"   --role roles/storage.objectAdmin --quiet --format none
if [[ "${RESET_DATA:-}" == "1" ]]; then
  echo "RESET_DATA=1: deleting the saved cases — the app starts again from the demo data."
  gcloud storage rm -r "gs://${STATE_BUCKET}/state/" --quiet 2>/dev/null || true
fi

SECRETS=()
if gcloud secrets describe nvidia-nim-api-key >/dev/null 2>&1; then
  SECRETS=(--set-secrets "NVIDIA_NIM_API_KEY=nvidia-nim-api-key:latest")
else
  echo "Secret 'nvidia-nim-api-key' not found: deploying without the NVIDIA key."
fi

# max-instances 1: SQLite and the in-memory CAM jobs need a single instance.
# no-cpu-throttling: CAM generation runs in background threads after the request returns.
gcloud run deploy "$SERVICE" \
  --quiet \
  --region "$REGION" \
  --source . \
  --service-account "$RUNTIME_SA" \
  --memory 2Gi --cpu 1 \
  --min-instances 0 --max-instances 1 \
  --no-cpu-throttling \
  --concurrency 40 --timeout 900 \
  --session-affinity \
  --allow-unauthenticated \
  --set-env-vars "LLM_ACTIVE_PROVIDER=vertex_ai_gemini,VERTEX_GEMINI_MODEL=${GEMINI_MODEL},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GEMINI_LOCATION},CAM_STATE_BUCKET=${STATE_BUCKET}" \
  "${SECRETS[@]}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
echo
echo "Deployed: ${URL}/los"
