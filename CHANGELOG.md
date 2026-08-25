# Changelog

## 0.18.0 — 2026-08-24

### Long-running scan ownership fencing

- Added a per-attempt UUID `claim_token` to durable scan jobs through Alembic revision `0005`.
- Added token-guarded PostgreSQL lease heartbeats and SQS `ChangeMessageVisibility` renewal for long-running asynchronous scans.
- Guarded terminal success and failure/requeue writes by the current claim token so a stale worker cannot commit findings, audit state or retry state after ownership changes.
- Kept active duplicate deliveries unacknowledged while another worker owns a live lease, preserving a recoverable message if the active worker later fails.
- Added PostgreSQL-only evidence that changes ownership during an in-flight scan and verifies the stale transaction rolls back its pending scan audit/results.
- Expanded the backend contract to 122 collected tests: 119 passed with three environment-specific skips at 90.16% coverage on the standard job; PostgreSQL passes 121 with one environment-specific skip.

### Boundary

- Heartbeats reduce avoidable redelivery but are not the correctness mechanism. Claim-token conditional writes fence stale workers. Delivery remains at-least-once, not distributed exactly-once, and SQS visibility renewal failure can still cause duplicate delivery.

## 0.17.0 — 2026-08-24

### Async request correlation and troubleshooting

- Promoted new asynchronous scan messages to schema v2 carrying the originating request/correlation ID from HTTP or a generated non-HTTP correlation value.
- Preserved rolling-deployment compatibility by continuing to consume legacy schema v1 queue messages that predate persisted request correlation.
- Propagated correlation into successful and failed worker audit events and structured worker logs with request, submission, job, outbox-event and disposition context.
- Extended retry and duplicate-delivery tests to prove the same correlation survives publisher redelivery, scan failure/retry and completed-message replay without duplicate completion audit.
- Extended the PostgreSQL 16 + SQS-compatible boto3 integration gate to verify committed outbox -> SQS -> worker -> correlated durable audit -> duplicate-safe replay.
- Expanded the backend contract to 115 collected tests: 113 passed with two environment-specific skips at 90.81% coverage on the standard job; PostgreSQL passes 114 with one environment-specific skip.

### Boundary

- This is application-level request correlation for troubleshooting, not a distributed-tracing, OpenTelemetry, AWS X-Ray or W3C `traceparent` implementation. Legacy v1 messages remain consumable but cannot reconstruct a request ID that was never persisted.

## 0.16.0 — 2026-08-24

### Async operations and recovery

- Added DB-backed `/metrics/async` gauges for durable outbox/job backlog, completion, retries, stale leases and oldest backlog age while preserving the DB-independent core metrics endpoint.
- Added cross-SQLite/PostgreSQL stale-worker lease recovery coverage and explicit foreign-key-safe test fixtures.
- Added native CloudWatch alarms for SQS visible backlog, oldest visible message age and DLQ depth without granting the API SQS permissions.
- Added an async operations runbook covering alert interpretation, at-least-once failure windows, automatic lease recovery and controlled DLQ handling boundaries.
- Kept alert thresholds explicitly illustrative rather than claiming production SLO calibration or live AWS operation.

## 0.15.0 — 2026-08-24

### Durable asynchronous scanning

- Moved AWS-reference upload scanning out of the HTTP request path with a PostgreSQL transactional outbox, durable scan jobs and HTTP 202 queued submissions while keeping synchronous local/demo compatibility.
- Added an independent outbox publisher and idempotent Python scan worker with expiring claims, retry-safe failure handling and duplicate-delivery suppression after durable completion.
- Added a boto3 SQS transport plus encrypted SQS/DLQ/redrive Terraform, separate publisher/worker ECS services and least-privilege runtime IAM roles.
- Added PostgreSQL 16 + SQS-compatible HTTP integration evidence from committed outbox through worker completion and deliberate duplicate replay.
- Added Alembic revision `0004` for scan jobs/outbox persistence and routed create/recheck/worker execution through one scanning application service.
- Expanded the backend contract to 108 collected tests; the standard job passes 106 with two environment-specific skips at 90.50% coverage, with Ruff, strict MyPy and dependency audit green.

### Boundaries

- Queue delivery is deliberately at-least-once, not exactly-once; durable job state makes the demonstrated crash-window redeliveries idempotent within the single-PostgreSQL contract.
- The AWS stack remains a CI-validated Terraform reference, not a claimed live deployment.

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
