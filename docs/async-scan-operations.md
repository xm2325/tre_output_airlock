# Asynchronous scan operations and recovery

This runbook describes the operational signals and recovery boundaries demonstrated by the asynchronous scan path. It is evidence for the repository's synthetic/reference environment, not a claim that these thresholds have been calibrated for a live production workload.

## Signal sources

The design intentionally keeps two monitoring planes separate.

### Durable application state

`GET /metrics/async` reads PostgreSQL state and exposes:

- `airlock_async_outbox_pending`: committed events waiting for a publisher;
- `airlock_async_outbox_publishing`: events currently holding a publisher lease;
- `airlock_async_outbox_published`: durable events marked published;
- `airlock_async_outbox_stale_publishing`: publisher leases old enough to be reclaimed;
- `airlock_async_outbox_retry_events`: events claimed more than once;
- `airlock_async_outbox_oldest_unpublished_age_seconds`: age of the oldest unpublished event;
- `airlock_async_scan_queued`: durable jobs waiting for a worker;
- `airlock_async_scan_processing`: durable jobs with an active worker lease;
- `airlock_async_scan_completed`: durable jobs completed successfully;
- `airlock_async_scan_stale_processing`: worker leases old enough to be reclaimed;
- `airlock_async_scan_retry_jobs`: jobs claimed more than once;
- `airlock_async_scan_retryable_failures`: queued jobs carrying a recorded retryable failure;
- `airlock_async_scan_oldest_queued_age_seconds`: age of the oldest queued job.

This endpoint requires a database checkout. The original `/metrics` endpoint deliberately does not: it remains available for HTTP/OIDC/database-pool telemetry when the PostgreSQL pool itself is saturated.

### AWS queue state

The API task has no SQS permissions. Queue health is therefore monitored through native CloudWatch `AWS/SQS` metrics rather than by granting the HTTP service queue access.

The Terraform reference defines alarms for:

- visible scan-queue backlog;
- age of the oldest visible scan message;
- any visible message in the scan DLQ.

Alarm actions are optional inputs so a deployment can connect approved SNS or incident-routing destinations without hard-coding an account-specific target in this repository.

## Recovery matrix

| Signal | Likely failure window | Demonstrated recovery | Operator action |
|---|---|---|---|
| Outbox pending grows | publisher unavailable or repeated SQS send failure | committed outbox remains durable and a later publisher pass retries it | check publisher logs, database connectivity and SQS availability; do not recreate submissions |
| Stale `PUBLISHING` events | publisher stopped after claiming, including after SQS accepted a send | lease expiry makes the event claimable again; duplicate SQS delivery is allowed | investigate repeated stale leases if the count does not return to zero |
| Scan queue backlog/age grows | workers unavailable, under-provisioned or slow | SQS retains visible messages and workers continue consuming when capacity returns | check worker service health and workload duration before changing task count |
| Stale `PROCESSING` jobs | worker stopped after durable claim | an expired worker lease can be reclaimed when the message is delivered again | investigate repeated expiry; validate visibility timeout against worst-case scan duration |
| Retryable scan failures | checker/parser attempt raised before terminal completion | job returns to `QUEUED`, error text is retained, SQS message is not deleted | inspect repeated error type; fix deterministic failures before allowing retries to exhaust |
| DLQ depth > 0 | message exceeded SQS `maxReceiveCount` | no automatic replay is claimed | quarantine the incident, inspect payload/job/audit state, correct the cause, then use an approved controlled redrive procedure |

## At-least-once boundary

Two duplicate-delivery windows are expected and tested:

1. SQS accepts an outbox send but the publisher stops before committing `PUBLISHED` in PostgreSQL. The event can be sent again after its lease expires.
2. A worker commits a completed scan but stops before deleting the SQS receipt. The same message can be delivered again.

The durable job state makes these re-deliveries safe inside the demonstrated single-PostgreSQL contract. This is **at-least-once delivery with idempotent processing**, not distributed exactly-once execution.

## Thresholds in the reference module

The default Terraform values are deliberately illustrative:

- queue backlog: 50 visible messages for two consecutive one-minute periods;
- oldest visible message: 300 seconds for two consecutive one-minute periods;
- DLQ: one visible message triggers immediately.

These values are not production SLOs. A real deployment must calibrate them from arrival rate, scan-duration distribution, worker concurrency, SQS visibility timeout, error budget and the expected time to detect/respond.

## Validation evidence

The v0.16 functional gate exercises the observability and recovery additions on both database paths rather than relying on SQLite alone:

- standard backend: **111 collected, 109 passed + 2 environment-specific skipped, 90.76% coverage** against the 90% gate;
- PostgreSQL 16: **110 passed + 1 environment-specific skipped** after applying Alembic through `0004(head)`;
- durable-state tests cover pending/publishing/published outbox rows, queued/processing/completed jobs, stale publisher and worker leases, retries, oldest backlog age and stale `PROCESSING` reclamation;
- Terraform `fmt`, `init -backend=false` and `validate` cover the three native SQS CloudWatch alarms;
- the existing PostgreSQL + SQS-compatible committed-outbox-to-worker integration remains green, so the monitoring changes do not alter transport or acknowledgement semantics.

The first dual-database run also exposed a test-fixture issue that SQLite tolerated: child `ScanJob`/`OutboxEvent` rows had been staged without explicit parent flushes. The fixture now explicitly persists `Submission -> ScanJob -> OutboxEvent` ordering before the PostgreSQL foreign-key checks. This was a test-evidence repair, not a relaxation of database constraints.

## What is not automated

The repository does not automatically redrive the DLQ, change ECS desired count from queue depth, or publish custom PostgreSQL metrics to CloudWatch. Those are deliberate boundaries: automatic replay can amplify deterministic failures, and autoscaling thresholds should not be invented without representative workload evidence.

A production rollout would additionally require an approved incident destination, dashboards, alert ownership, controlled DLQ replay, workload-based autoscaling/back-pressure tests, parser CPU/memory/time limits, malware scanning and recovery exercises against the deployed RDS/ECS/SQS environment.
