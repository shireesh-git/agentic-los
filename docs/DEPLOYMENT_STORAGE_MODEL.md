# Deployment And Storage Model

## Runtime Design

The application now uses a Docker-friendly split between immutable application code and mutable runtime state.

### In-image

- `src/`
- `config/`
- `scripts/`
- `run.py`

### Mounted at runtime

- `/app/storage`
- `/app/output`
- `/app/runtime-db`
- `/app/reference-docs`
- `/app/synthetic-assets`

## Database

Engine:

- SQLite

Default path:

- `runtime-db/cam_platform.sqlite3`

Tables:

- `app_users`
- `companies`
- `case_runs`
- `case_comments`

### app_users

Reserved for future login / RBAC work. The current runtime seeds a placeholder `system` user only.

### companies

Stores the current serialized company payload used by the pipeline.

Key fields:

- `entity_id`
- `company_name`
- `catalog_source`
- `is_seeded`
- `payload_json`
- `created_at`
- `updated_at`

### case_runs

Stores the latest and historical CAM runs per entity.

Key fields:

- `run_id`
- `entity_id`
- `company_name`
- `recommendation`
- `risk_grade`
- `composite_score`
- `run_at`
- `payload_json`

### case_comments

Stores reviewer comments per run and section.

Key fields:

- `run_id`
- `section_id`
- `comment_text`
- `updated_at`

## Why Notes Previously Reappeared

The old implementation stored CAM comments in one JSON file per borrower:

- `output/{entity_id}_cam_comments.json`

That made comments survive across regenerated CAMs for the same entity.

The new model stores comments against `run_id`, which fixes that leakage.

## Storage Folders

### storage/documents

Canonical working document store used by the UI and extraction pipeline.

### storage/cache/probe42

Cached verified public-record bundles. TTL is 576 hours = 24 days.

### output

Rendered outputs and legacy compatibility artifacts:

- `*_fact_pack.json`
- `*_pipeline_result.json`
- `*_CAM.md`

### reference-docs

Mounted reference annual reports used to bootstrap the 5 active companies.

### synthetic-assets

Optional non-production mock assets outside the image. Current use:

- `synthetic-assets/etb_overlays/IHCL001.json`

## Five-Company Scope

The runtime seed catalog is limited to:

- `APOL001`
- `INFY001`
- `IHCL001`
- `MFL001`
- `MRF001`

The app intentionally does not seed the old demo NTB borrowers.

## Docker Notes

The image is minimized by:

- excluding `storage/`, `output/`, `runtime-db/`, `downloaded document/`, and `synthetic-assets/` from build context
- using `python:3.11-slim-bookworm`
- keeping runtime OCR dependencies to Tesseract plus the Python packages in `requirements.txt`

## Future Login Scope

The current DB model deliberately leaves room for future user/login work:

- attach `created_by_user_id` and `updated_by_user_id` to `companies`
- attach `run_by_user_id` to `case_runs`
- attach `author_user_id` to `case_comments`
- add sessions / auth provider tables later without replacing the storage model
