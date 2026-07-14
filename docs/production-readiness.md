# Production-readiness gap analysis

This document separates what the repository demonstrates from work required before handling real data.

| Area | Repository evidence | Required next step |
|---|---|---|
| Identity | role and owner checks through demo headers | OIDC/OAuth token validation, project groups and session policy |
| Database | PostgreSQL Compose service, Alembic migration, optimistic concurrency | managed RDS, backups, restore tests, least-privilege roles |
| Storage | quarantine directory and explicit retirement | encrypted object storage, bucket policy, object lock or legal hold where required |
| Processing | deterministic synchronous checks | isolated asynchronous workers, malware scan, parser timeouts and retries |
| Policy | versioned catalogue and retrospective simulation | formal owner, approval record, test corpus and controlled release process |
| Audit | request IDs, hash-linked events and signed reports | central append-only log, managed signing key and independent verification |
| Operations | readiness, Prometheus-style metrics and queue-age measures | dashboards, service-level objectives, paging and incident response |
| Privacy | evidence redaction and synthetic benchmark | privacy review, data-flow assessment and disclosure-control validation |
| Delivery | CI, dependency audits and container configuration | image signing, software bill of materials, environment promotion and rollback |

## Suggested service-level indicators

- API availability and p95 latency;
- upload failures by reason;
- scan completion time;
- queue age and unclaimed count;
- manual block rate by policy version;
- rule frequency drift;
- report or audit verification failures;
- dead-letter queue depth;
- retention jobs completed and failed.

## Release gates

A production release should require tests, migration check, dependency audit, synthetic benchmark, security review for high-risk changes and a recorded policy approval when decision behaviour changes.
