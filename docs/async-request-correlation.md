# Asynchronous request correlation

This note documents the application-level correlation contract used by the TRE Output Airlock asynchronous scan path. It is intended to make failure investigation across the API, PostgreSQL outbox, SQS transport and scan worker reproducible without claiming a full distributed-tracing platform.

## Correlation path

A queued HTTP upload already has an `X-Request-ID` at the FastAPI boundary. `enqueue_scan()` persists that value in two places inside the same database transaction:

1. the `SCAN_QUEUED` hash-linked audit event; and
2. the schema-v2 `ScanMessage` stored in the transactional outbox payload.

If a non-HTTP caller enqueues work without a request ID, the service generates a UUID correlation value before persisting either record. The publisher sends the committed outbox payload unchanged. The worker therefore receives the same identifier that was durably recorded before queue publication.

The worker passes that identifier to the shared scanning application service. Successful `AUTOMATED_CHECK_COMPLETED` audit events and retryable `SCAN_ATTEMPT_FAILED` events retain the same request ID. Worker JSON logs also carry `request_id`, `submission_id`, `job_id`, `event_id` and processing `disposition` so an operator can join one request across durable and transient evidence.

```text
HTTP X-Request-ID
      |
      v
PostgreSQL transaction
  submission + ScanJob + OutboxEvent + SCAN_QUEUED audit
                       |
                       v
                ScanMessage v2
                       |
                       v
                      SQS
                       |
                       v
                  scan worker
             /         |          \
      worker log   success audit   failure audit
             \         |          /
              same request_id
```

## Message-version boundary

New messages use schema version 2 and require a non-empty `request_id`. The consumer deliberately continues to accept schema version 1 messages that contain only `event_id`, `job_id` and `submission_id`.

This compatibility matters during a rolling deployment: an old v1 message can remain visible while newer workers are starting. Rejecting it solely because the producer has moved to v2 would turn a harmless deployment overlap into a queue failure. A v1 message therefore remains processable with `request_id=None`; a correlation identifier that was never persisted cannot be reconstructed safely after the fact.

Unsupported future schema versions fail closed rather than being guessed.

## At-least-once failure windows

Correlation is preserved across both queue redelivery windows already covered by the asynchronous delivery contract.

**Publisher crash after SQS acceptance.** If SQS accepts the payload but the publisher crashes before the outbox row is committed as `PUBLISHED`, the expired outbox claim can be reclaimed and the identical v2 payload can be sent again. Both copies carry the same request ID.

**Worker crash after durable completion.** If the worker commits the completed scan but crashes before deleting the SQS receipt, the same message may be delivered again. The worker checks the durable `ScanJob` first, recognises `COMPLETED`, emits a correlated duplicate disposition and acknowledges the message without another scan or another completion audit.

**Retryable scan failure.** A scan exception returns the job to `QUEUED`, records a bounded error and a `SCAN_ATTEMPT_FAILED` audit event with the original request ID, and leaves the queue message undeleted for retry/redrive handling.

## Troubleshooting workflow

For an incident that starts with an API request ID:

1. find the submission audit event carrying that `request_id` and record its submission ID and queued job/outbox IDs;
2. inspect durable async metrics for pending/publishing outbox rows, queued/processing jobs, stale leases, retry counts and oldest backlog age;
3. filter worker JSON logs by the same `request_id` and then by `job_id` or `event_id` to distinguish publication, active processing, retry and duplicate-delivery paths;
4. compare the durable job state with SQS backlog/oldest-message/DLQ alarms before deciding whether a lease will recover automatically or operator action is required;
5. use the async operations runbook for controlled recovery rather than manually creating a second job or rewriting a completed job state.

The durable database state remains authoritative. Correlation fields help join evidence; they do not replace idempotency, claim leases or state-transition checks.

## Validation evidence

The feature contract currently exercises:

- schema-v2 encode/decode with a required request ID;
- legacy schema-v1 consumption during rolling deployment;
- generated correlation for non-HTTP enqueue paths;
- correlation in queued, successful and failed audit events;
- preservation across publisher redelivery and completed-message replay;
- PostgreSQL-specific schema validation in addition to SQLite tests; and
- a PostgreSQL 16 + Moto SQS-compatible boto3 integration from committed outbox through correlated worker completion and deliberate duplicate replay.

The validated functional head collected 115 standard backend tests: 113 passed with two environment-specific skips at 90.81% coverage. The PostgreSQL 16 contract passed 114 tests with one environment-specific skip.

The first PostgreSQL feature run also caught a test fixture identifier that exceeded the existing `VARCHAR(36)` schema while SQLite accepted it. The fixture was corrected; the database constraint was not weakened. This is a useful example of why the project keeps a real PostgreSQL contract alongside the low-friction SQLite test path.

## Explicit non-claims

This implementation is **application-level request correlation**. It is not OpenTelemetry, AWS X-Ray, W3C `traceparent`, cross-service span propagation or a live central log platform. A production deployment may adopt those technologies, but this repository does not claim evidence it has not demonstrated.
