# Production-readiness gap analysis

This document separates what the repository demonstrates from work required before handling real data.

| Area | Repository evidence | Required next step |
|---|---|---|
| Identity | local demo identity plus tested OAuth2/OIDC token introspection, issuer/audience/expiry checks, configurable IdP group-to-RBAC mapping, bounded short-lived successful-token caching and per-process keyed single-flight coordination | approved IdP tenant and claim contract, credential rotation, revocation/latency policy, representative integration testing and multi-instance IdP load testing |
| Database | PostgreSQL Compose service, Alembic migrations, optimistic concurrency, bounded signed keyset pagination, composite cursor indexes, 20,000-row PostgreSQL default-planner query-plan contract, RDS-style configuration, bounded per-task pool settings, exhaustion/recovery testing and CI-validated RDS reference infrastructure | applied managed RDS environment, representative-cardinality and distribution load testing, query-plan validation against deployed statistics/configuration, backup/restore tests, least-privilege roles, capacity calibration and failover testing |
| Review concurrency | strong id/version ETags, `If-Match` plus legacy expected-version compatibility, database compare-and-swap for claim and final review writes, transactional decision/audit persistence and expiring review-claim lease | representative multi-instance load/concurrency testing, client retry/precondition UX validation and operational tuning of the lease duration |
| Upload idempotency | actor-scoped hashed keys, payload fingerprints, PostgreSQL unique-race recovery, legacy-key migration and staged-file cleanup on replay/conflict/failure | distributed/multi-region retry semantics, durable object-store reconciliation and representative concurrent client testing beyond the CI fixture |
| Storage | quarantine directory, explicit retirement and encrypted EFS/S3 reference controls | approved encrypted storage, bucket/file-system policy, malware scanning, retention enforcement and legal-hold design where required |
| Processing | synchronous local mode plus queued API mode, durable scan jobs, transactional outbox publisher, boto3 SQS transport, independent idempotent workers, per-attempt claim-token fencing, token-guarded DB heartbeats, SQS visibility renewal, retry-safe failures, SQS/DLQ Terraform and PostgreSQL+SQS-compatible CI | malware scanning, parser hard timeouts/resource isolation, applied AWS deployment, workload-calibrated autoscaling/back-pressure tests and controlled DLQ replay exercises |
| Policy | versioned catalogue and retrospective simulation | formal owner, approval record, test corpus and controlled release process |
| Audit | request IDs, hash-linked events, signed reports, atomic review-claim/audit persistence and schema-v2 async request correlation into worker success/failure audit | central append-only log, managed signing key, independent verification and recovery testing |
| Operations | DB-independent core Prometheus telemetry, DB-backed durable async backlog/stale-lease/retry/completion/oldest-age metrics, correlated worker JSON logs carrying request/submission/job/event/disposition context, OIDC/cache/IdP and PostgreSQL pool telemetry, plus native CloudWatch SQS backlog/oldest-age/DLQ alarms | production dashboards, service-level objectives, approved paging destinations, workload-calibrated thresholds, aggregate RDS/ECS capacity alerts and incident exercises |
| Privacy | evidence redaction and synthetic benchmark | privacy review, data-flow assessment and disclosure-control validation |
| Delivery | CI, cross-stack release-version contract, dependency audits, PostgreSQL migration/pool contract, Terraform validation, container configuration and an SQS-compatible committed-outbox-to-worker integration gate | image signing, software bill of materials, environment promotion, deployment migration orchestration and rollback testing |

## Suggested service-level indicators

- API availability and p95 latency;
- identity-provider request latency and failure rate;
- OIDC cache hit rate, single-flight join rate and coordination timeouts;
- database connection failures, pool checkout timeouts and pool saturation;
- upload failures by reason;
- scan completion time;
- queue age, unclaimed count and expired review claims;
- manual block rate by policy version;
- rule frequency drift;
- report or audit verification failures;
- dead-letter queue depth;
- retention jobs completed and failed.

## Database connection-budget boundary

The application pool budget is **per API task**, not a service-wide global cap. With the current reference defaults, each task can hold up to `pool_size + max_overflow = 5 + 5 = 10` application connections. A two-task service can therefore attempt roughly 20 application connections before allowing for a one-off migration task, administrative sessions, monitoring, failover behavior and other database users.

The dedicated PostgreSQL 16 CI job deliberately uses a smaller `3 + 2` budget with a 0.2-second checkout timeout. Its PostgreSQL-only regression test opens all five allowed connections, verifies the live Prometheus gauges show full utilisation and zero remaining capacity, confirms readiness and a database-backed API return 503 while saturated, checks the checkout-timeout counter increases, closes every held connection, confirms the gauges recover, readiness returns 200 and `SELECT 1` succeeds on a new connection. This validates bounded exhaustion, observability and recovery; it does not determine the correct production capacity for a particular RDS instance.

Production values must therefore be chosen from the actual RDS `max_connections`, expected ECS task count and scaling range, request concurrency and transaction duration, with explicit headroom for migrations, administration, monitoring and failover.

## Review precondition boundary

Submission detail responses expose a strong ETag derived from the submission identifier and current `row_version`. Manual review accepts that tag through `If-Match`; stale header preconditions return 412, a missing header/body version precondition returns 428, contradictory header/body versions and unsupported weak or wildcard tags return 400, while the legacy stale JSON `expected_version` path retains its existing 409 behavior. The final decision itself is guarded by a database compare-and-swap on id, workflow status and row version, plus the active reviewer claim/lease for non-admin users. The decision transition and hash-linked audit event remain in one transaction, so an audit persistence failure rolls back the decision.

The ETag is an optimistic-concurrency token for the current mutable submission representation. It is not a database lock, distributed mutex, snapshot-isolation guarantee or frozen export token. A client must fetch the current representation again after a failed precondition and decide whether to retry. Multi-instance contention and retry behavior still require representative load testing.

## Upload idempotency boundary

`Idempotency-Key` is scoped to the authenticated actor through a SHA-256 digest rather than stored as a new raw submission key. A request fingerprint binds normalized submission metadata to filename, content type, byte count and file SHA-256. Reusing the same actor/key with an identical payload returns the existing submission; changing the payload or metadata returns 409. Different actors may independently reuse the same original key.

Alembic revision `0003` introduces the durable idempotency-record table and backfills legacy keyed submissions. The PostgreSQL-only concurrency regression forces two first requests past the initial lookup together. The unique scope key selects one database winner; the losing transaction rolls back its flushed submission/audit state, removes its staged quarantine file and replays the committed winner. CI verifies one durable submission, one idempotency record and one resulting quarantine file. This is retry/idempotency evidence for the single PostgreSQL-backed service contract, not a claim of distributed exactly-once execution. Database state and filesystem/object storage are not one distributed transaction, so production storage still requires reconciliation and orphan-cleanup controls.

## Submission pagination boundary

The API keeps the existing bounded page/offset submission endpoint for browser compatibility and adds a separate signed keyset endpoint for deeper traversal. The keyset cursor is HMAC-protected and bound to the authenticated actor, active filters and sort order, so a tampered cursor or one reused under a different query contract is rejected. Stable unique-ID tie-breakers are used for `newest`, `oldest` and `risk_desc`, and the endpoint fetches only `limit + 1` rows rather than running a total-count query.

Alembic revision `0002` adds `(created_at, id)` and `(risk_score DESC, created_at ASC, id ASC)` indexes. PostgreSQL 16 CI applies the real migration and verifies both indexes through `pg_indexes`. A separate query-plan contract then inserts 20,000 synthetic submissions, runs `ANALYZE`, and executes default-planner `EXPLAIN (FORMAT JSON)` for deep `newest` and `risk_desc` keyset predicates. CI requires the former plan to reference `ix_submissions_created_id` and the latter to reference `ix_submissions_risk_cursor`, and retains the complete plan JSON as an artifact. This is repeatable planner/index-selection evidence, not a production latency or throughput benchmark; representative production cardinalities, data distributions, concurrent workload and RDS configuration still require validation.

Keyset pagination is not snapshot isolation. Concurrent inserts, deletes or rechecks can change the result set while a client traverses it; in particular, a recheck that changes `risk_score` can move a submission across a `risk_desc` cursor boundary. A production consumer that requires a frozen export must use an explicit snapshot/versioning design rather than treating this cursor as a snapshot token.

## Asynchronous scan delivery boundary

Queued execution uses PostgreSQL as the durable hand-off boundary. The upload request writes the submission, `ScanJob`, `OutboxEvent` and hash-linked `SCAN_QUEUED` audit state in one transaction and returns HTTP 202 without executing the disclosure checker. A separate publisher claims committed outbox rows and sends their versioned payload to SQS; independent workers receive messages, claim the matching durable job, execute the shared scanning application service, commit terminal database/audit state, and only then delete the SQS receipt.

New queue payloads use schema v2 and carry the request/correlation ID that originated at the HTTP boundary, or a generated correlation value for non-HTTP enqueue paths. The worker propagates that value into successful and failed audit events and structured logs alongside submission, job, outbox event and processing disposition. Consumers continue to accept schema-v1 messages during rolling deployment; those legacy messages use `request_id=None` because a correlation value that was never persisted cannot be reconstructed. This is application-level troubleshooting correlation, not an OpenTelemetry, AWS X-Ray or W3C `traceparent` implementation.

Delivery is intentionally **at-least-once**. If SQS accepts a message but the publisher crashes before marking the outbox row `PUBLISHED`, the expired outbox claim can be reclaimed and the payload sent again. If the worker commits a completed scan but crashes before deleting the SQS receipt, the message can also be delivered again. The worker checks the durable job state first, so a `COMPLETED` job is acknowledged without a second scan or duplicate completion audit. Failed scans return the job to `QUEUED`, record a bounded error/audit entry and leave the message undeleted so queue visibility/redrive policy can retry it.

Long-running workers use a fresh per-attempt UUID claim token. A background heartbeat renews `claimed_at` with a token-guarded database update and, only while durable ownership remains current, renews SQS visibility through `ChangeMessageVisibility`. Heartbeat timing is not the correctness mechanism: terminal success and failure/requeue writes are also conditional on the current claim token. If ownership changes during a scan, the stale transaction rolls back pending findings/audit instead of committing them. An active duplicate delivery is not acknowledged while another worker holds a live lease. Visibility renewal failure can therefore cause another delivery, but it cannot authorise a stale database write.

CI covers both deterministic failure windows, stale-worker lease reclamation, token renewal/loss, active-duplicate non-acknowledgement and PostgreSQL-only stale-worker fencing, plus a separate PostgreSQL 16 and Moto SQS-compatible HTTP integration using the production boto3 transport. The integration creates a queue and DLQ, publishes a committed outbox event, consumes and completes it, then deliberately re-sends the same payload and verifies no duplicate scan completion is persisted. Moto is used because recent LocalStack images require an external commercial auth token even for startup; no repository secret or live-AWS claim is introduced. Terraform separately validates real AWS SQS/DLQ/redrive resources and least-privilege publisher/worker IAM.

The reference now also exposes durable PostgreSQL async state through `/metrics/async` and validates native CloudWatch alarms for SQS visible backlog, oldest-message age and DLQ depth; see [`async-scan-operations.md`](async-scan-operations.md) for signal interpretation and recovery steps. This is not a production exactly-once guarantee, a live AWS deployment, or evidence of queue throughput/latency under real load. Production still requires applied infrastructure, approved alert destinations and workload-calibrated thresholds, autoscaling/back-pressure tests, controlled DLQ replay exercises, malware scanning and resource/time limits around untrusted parsers.

## Release gates

A production release should require tests, cross-stack release-version consistency, PostgreSQL migration and connection-pool checks, asynchronous outbox/worker retry contracts when queue code changes, dependency audit, synthetic benchmark, Terraform validation for infrastructure changes, security review for high-risk changes and a recorded policy approval when decision behaviour changes.

The current OIDC single-flight implementation is deliberately per process. It reduces duplicate introspection requests inside one API process but does not coordinate separate ECS tasks. Any production capacity assessment should therefore assume that the same cold token can still produce one upstream introspection per active task.