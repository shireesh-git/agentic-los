# GCP Deployment

## Target

- Project: `camdemo`
- Service: `camdemo`
- Region: `asia-south1`
- Runtime: Cloud Run from source using the repo Dockerfile

## Current blocker

As of March 31, 2026, deployment is blocked because billing is not attached to the `camdemo` project. Enabling these APIs fails until billing is configured:

- `run.googleapis.com`
- `cloudbuild.googleapis.com`
- `artifactregistry.googleapis.com`

## One-command deploy after billing is enabled

From the repo root:

```powershell
.\scripts\deploy_gcp_camdemo.ps1
```

The script:

- reads `PROBE42_API_KEY` from the current environment or `.env.local`
- enables required GCP services
- deploys the app to Cloud Run in `asia-south1`
- keeps optional mock data disabled

## Important runtime limitation

The current app still uses local filesystem storage for:

- borrower documents
- output artifacts
- runtime SQLite database

On Cloud Run, that storage is ephemeral. This is acceptable for a demo service, but not for persistent production usage. A production GCP version should move to:

- Cloud SQL for the app database
- Cloud Storage for documents and generated outputs

## Narrative and model behavior today

- CAM narrative generation is currently `template` mode, not LLM-written.
- The active configured provider is `ollama`, model `qwen2.5:7b`, but it is only used if narrative mode is switched to `llm`.
- Analyst chat tries Ollama first and falls back to rule-based responses if Ollama is unavailable.
- Validation, scoring, policy, and recommendation are deterministic rule engines, not ML models.
