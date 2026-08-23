# Production-readiness gap analysis

This document separates what the repository directly demonstrates, what exists only as reference infrastructure, and what still requires a live environment before production claims are allowed.

| Area | Repository evidence | Evidence level | Required next step |
|---|---|---|---|
| Identity | demo-header mode plus OIDC token-introspection adapter, issuer/audience/expiry checks, group-to-role mapping and mocked IdP tests | direct implementation with mocked external boundary | integrate with a real test IdP or production-approved IdP; add token lifecycle/revocation and operational policy |
| Database | PostgreSQL Compose service, SQLAlchemy, Alembic, optimistic concurrency, plus private encrypted RDS Terraform reference | direct local DB + reference AWS | apply to a managed test RDS environment; test backup/restore and least-privilege database roles |
| Storage | local quarantine and explicit retirement; encrypted EFS/S3-related reference paths in AWS infrastructure | local direct + reference AWS | run managed storage in a controlled environment; add malware scanning, retention enforcement and recovery tests |
| Processing | deterministic checks and clinical-genomic pipeline with Prefect task structure | direct synthetic implementation | add isolated managed workers, parser timeouts/retries and representative source-system testing |
| Policy | versioned catalogue and retrospective simulation | direct synthetic implementation | add formal owner, approval record, governed test corpus and controlled policy release process |
| Audit | request IDs, hash-linked events and signed reports | direct implementation | central append-only logging, managed signing key and independent verification in a deployed environment |
| Operations | readiness endpoint, structured logs, Prometheus-style metrics and queue-age measures | direct implementation | central dashboards, service-level objectives, paging, incident response and load/failure exercises |
| Privacy | evidence redaction, synthetic benchmark and restricted-zone controls in the clinical-genomic path | direct synthetic implementation | formal privacy review, data-flow assessment and validation on approved representative data |
| AWS service delivery | API Gateway -> VPC Link -> internal ALB -> ECS Fargate -> RDS/EFS reference; IAM/Secrets Manager configuration; Terraform validation in CI | reference infrastructure | safe AWS apply/teardown, environment promotion, deployment/rollback exercise and cost/security review |
| Delivery | CI, dependency audits, container configuration, backend-service Terraform validation | direct CI + reference AWS | image signing, software bill of materials, environment promotion and rollback evidence |

## Evidence boundary

Passing Terraform `fmt`, `init -backend=false` and `validate` supports a claim that the AWS configuration is statically checked. It does not support a claim that the stack has been deployed or operated.

Passing the OIDC authentication tests supports a claim that the application implements and tests an IdP token-introspection adapter. The tests mock the external network boundary, so they do not support a claim of a real Okta tenant integration.

All clinical and genomic records in the repository are synthetic. No production-readiness statement may imply handling of real Genomics England, NHS or participant data.

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

A production release should require tests, migration checks, dependency audits, synthetic benchmark checks, security review for high-risk changes, controlled infrastructure promotion and a recorded policy approval when decision behaviour changes.
