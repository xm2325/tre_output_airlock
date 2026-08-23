# Production-readiness gap analysis

This document separates what the repository demonstrates from work required before handling real data.

| Area | Repository evidence | Required next step |
|---|---|---|
| Identity | local demo identity plus tested OAuth2/OIDC token introspection, issuer/audience/expiry checks, configurable IdP group-to-RBAC mapping, bounded short-lived successful-token caching and per-process keyed single-flight coordination | approved IdP tenant and claim contract, credential rotation, revocation/latency policy, representative integration testing and multi-instance IdP load testing |
| Database | PostgreSQL Compose service, Alembic migrations, optimistic concurrency, bounded signed keyset submission pagination, composite cursor indexes, RDS-style configuration, bounded per-task SQLAlchemy pool settings, `pool_pre_ping`, checkout timeout/recycle controls, PostgreSQL 16 exhaustion/recovery testing and CI-validated RDS reference infrastructure | applied managed RDS environment, representative-cardinality pagination/load testing, backup/restore tests, least-privilege database roles, capacity calibration against the actual RDS connection limit and ECS task count, and failover testing |
| Review concurrency | compare-and-swap `row_version`, transactional claim/audit write and expiring review-claim lease | representative multi-instance load/concurrency testing and operational tuning of the lease duration |
| Storage | quarantine directory, explicit retirement and encrypted EFS/S3 reference controls | approved encrypted storage, bucket/file-system policy, malware scanning, retention enforcement and legal-hold design where required |
| Processing | deterministic synchronous checks | isolated asynchronous workers, malware scan, parser timeouts, retries and workload resource limits |
| Policy | versioned catalogue and retrospective simulation | formal owner, approval record, test corpus and controlled release process |
| Audit | request IDs, hash-linked events, signed reports and atomic review-claim/audit persistence | central append-only log, managed signing key, independent verification and recovery testing |
| Operations | database/storage readiness checks, Prometheus HTTP telemetry, OIDC cache/single-flight outcomes, IdP latency, live per-process PostgreSQL pool capacity/utilisation gauges and checkout-timeout counts | dashboards, service-level objectives, paging, aggregate RDS/ECS capacity alerts, dependency-specific alerts and incident response |
| Privacy | evidence redaction and synthetic benchmark | privacy review, data-flow assessment and disclosure-control validation |
| Delivery | CI, cross-stack release-version contract, dependency audits, PostgreSQL migration/pool contract, Terraform validation and container configuration | image signing, software bill of materials, environment promotion, deployment migration orchestration and rollback testing |

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

## Submission pagination boundary

The API keeps the existing bounded page/offset submission endpoint for browser compatibility and adds a separate signed keyset endpoint for deeper traversal. The keyset cursor is HMAC-protected and bound to the authenticated actor, active filters and sort order, so a tampered cursor or one reused under a different query contract is rejected. Stable unique-ID tie-breakers are used for `newest`, `oldest` and `risk_desc`, and the endpoint fetches only `limit + 1` rows rather than running a total-count query.

Alembic revision `0002` adds `(created_at, id)` and `(risk_score DESC, created_at ASC, id ASC)` indexes. PostgreSQL 16 CI applies the real migration and verifies both indexes through `pg_indexes` before running the backend suite. This demonstrates the query/index contract, not production-scale latency. Representative-cardinality load tests and query-plan evidence are still required before making performance claims.

Keyset pagination is not snapshot isolation. Concurrent inserts, deletes or rechecks can change the result set while a client traverses it; in particular, a recheck that changes `risk_score` can move a submission across a `risk_desc` cursor boundary. A production consumer that requires a frozen export must use an explicit snapshot/versioning design rather than treating this cursor as a snapshot token.

## Release gates

A production release should require tests, cross-stack release-version consistency, PostgreSQL migration and connection-pool checks, dependency audit, synthetic benchmark, Terraform validation for infrastructure changes, security review for high-risk changes and a recorded policy approval when decision behaviour changes.

The current OIDC single-flight implementation is deliberately per process. It reduces duplicate introspection requests inside one API process but does not coordinate separate ECS tasks. Any production capacity assessment should therefore assume that the same cold token can still produce one upstream introspection per active task.