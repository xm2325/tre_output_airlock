# Changelog

## 0.3.1 — 2026-07-14

### Delivery reliability

- Added a committed `uv.lock` and frozen Python dependency installation in CI and Docker.
- Added a full Docker Compose integration job covering PostgreSQL, Alembic, FastAPI and the frontend container.
- Added a GitHub Pages workflow for a browser-only synthetic demonstration.
- Added frontend API contract tests for actor headers, optimistic concurrency errors and retention requests.
- Avoided duplicate PDF and image parser findings when file signatures are already invalid.
- Added CI and Pages badges plus a direct link to the browser-only demo.

## 0.3.0 — 2026-07-14

### Workflow and permissions

- Added researcher, reviewer and admin scopes through a clearly marked demo identity layer.
- Restricted researchers to their own submissions.
- Added review claim and release operations.
- Added optimistic concurrency through `row_version` and HTTP 409 conflicts.
- Added idempotency keys for submission retries.
- Added project code, output type and output-purpose metadata.

### Evidence and governance

- Added HMAC-SHA256 decision-report signatures and verification.
- Added SHA-256-linked audit events and verification.
- Added retrospective policy workload simulation.
- Added explicit quarantine-file retirement while retaining decision metadata.
- Added postcode-like, labelled date-of-birth-like and free-text-column checks.

### Data and operations

- Added PostgreSQL to Docker Compose.
- Added Alembic database migration and startup migration step.
- Added server-side pagination, search, filters and risk ordering.
- Added queue age, claimed review, manual block and file-retirement metrics.
- Added Prometheus-style request counts and latency summaries.

### Frontend

- Added role switching and role-specific views.
- Added project context to upload.
- Added review claim controls and stale-state protection.
- Added report and audit verification.
- Added policy simulation and retention controls.
- Added frontend unit tests.

### Delivery

- Added a nine-case synthetic benchmark and committed results.
- Added an OpenAPI snapshot and CI drift check.
- Added migration smoke testing, dependency audits and container builds to CI.
- Added an AWS encrypted quarantine and scan-queue baseline.
- Removed all interview-specific material from the public repository.

## 0.2.0

- Added policy versioning, rule catalogue, file-signature checks, duplicate detection, recheck, decision reports, review queue and operational dashboard.

## 0.1.0

- Initial FastAPI and React demonstration with deterministic output checks, human review, audit events, tests, Docker Compose and GitHub Actions.
