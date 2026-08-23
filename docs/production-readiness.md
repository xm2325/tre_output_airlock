# Production-readiness gap analysis

This document separates what the repository demonstrates from work required before handling real data.

| Area | Repository evidence | Required next step |
|---|---|---|
| Identity | local demo identity plus tested OAuth2/OIDC token introspection, issuer/audience/expiry checks, configurable IdP group-to-RBAC mapping, bounded short-lived successful-token caching and per-process keyed single-flight coordination | approved IdP tenant and claim contract, credential rotation, revocation/latency policy, representative integration testing and multi-instance IdP load testing |
| Database | PostgreSQL Compose service, Alembic migration, optimistic concurrency, RDS-style configuration and CI-validated RDS reference infrastructure | applied managed RDS environment, backup/restore tests, least-privilege database roles, connection-pool sizing and failover testing |
| Review concurrency | compare-and-swap `row_version`, transactional claim/audit write and expiring review-claim lease | representative multi-instance load/concurrency testing and operational tuning of the lease duration |
| Storage | quarantine directory, explicit retirement and encrypted EFS/S3 reference controls | approved encrypted storage, bucket/file-system policy, malware scanning, retention enforcement and legal-hold design where required |
| Processing | deterministic synchronous checks | isolated asynchronous workers, malware scan, parser timeouts, retries and workload resource limits |
| Policy | versioned catalogue and retrospective simulation | formal owner, approval record, test corpus and controlled release process |
| Audit | request IDs, hash-linked events, signed reports and atomic review-claim/audit persistence | central append-only log, managed signing key, independent verification and recovery testing |
| Operations | database/storage readiness checks, Prometheus-style HTTP telemetry, OIDC cache/single-flight outcomes, IdP latency and queue-age measures | dashboards, service-level objectives, paging, dependency-specific alerts and incident response |
| Privacy | evidence redaction and synthetic benchmark | privacy review, data-flow assessment and disclosure-control validation |
| Delivery | CI, cross-stack release-version contract, dependency audits, PostgreSQL migration contract, Terraform validation and container configuration | image signing, software bill of materials, environment promotion, deployment migration orchestration and rollback testing |

## Suggested service-level indicators

- API availability and p95 latency;
- identity-provider request latency and failure rate;
- OIDC cache hit rate, single-flight join rate and coordination timeouts;
- database connection failures and pool saturation;
- upload failures by reason;
- scan completion time;
- queue age, unclaimed count and expired review claims;
- manual block rate by policy version;
- rule frequency drift;
- report or audit verification failures;
- dead-letter queue depth;
- retention jobs completed and failed.

## Release gates

A production release should require tests, cross-stack release-version consistency, PostgreSQL migration checks, dependency audit, synthetic benchmark, Terraform validation for infrastructure changes, security review for high-risk changes and a recorded policy approval when decision behaviour changes.

The current OIDC single-flight implementation is deliberately per process. It reduces duplicate introspection requests inside one API process but does not coordinate separate ECS tasks. Any production capacity assessment should therefore assume that the same cold token can still produce one upstream introspection per active task.