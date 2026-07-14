# Threat model

## Assets

- quarantined file bytes;
- submission ownership and project context;
- automated findings and human decisions;
- reviewer identity and rationale;
- policy versions;
- audit events and report signatures;
- service availability.

## Trust boundaries

1. Browser to API.
2. API to quarantine storage.
3. API and worker to database.
4. Reviewer workflow to final decision.
5. Application secret to signed report.
6. Monitoring system to operational responders.

## Threats and demonstrated controls

| Threat | Demonstrated control | Remaining production work |
|---|---|---|
| Misleading file extension | binary signature validation | sandboxed parsers and malware scanning |
| Oversized upload | streaming size limit | gateway limits and rate limits |
| Path traversal | server-generated submission directory and basename handling | isolated object-store prefixes |
| Identifier leakage in logs | evidence is redacted; logs do not repeat matched values | automated log scanning and data-loss prevention |
| Researcher views another project | role and owner filtering | managed identity and project membership claims |
| Two reviewers overwrite each other | claim ownership and `row_version` conflict check | distributed lock expiry and recovery policy |
| Review evidence is silently removed | findings remain after the final decision | restricted database roles and append-only storage |
| Audit history is edited | previous-event hash chain and verification endpoint | write-once archive and independent log sink |
| Decision report is modified | HMAC signature and verification endpoint | KMS asymmetric signing and key rotation |
| Quarantine is retained forever | admin file retirement while metadata remains | scheduled retention jobs and legal-hold handling |
| Queue failure is unnoticed | operations metrics and AWS dead-letter queue example | production alarms, on-call rota and runbooks |
| Parser denial of service | file size and row limits | process isolation, CPU/memory/time limits |

## Abuse cases

### Researcher retries the same request

The client sends an idempotency key. Repeating that key returns the existing submission instead of creating a second workflow record.

### Reviewer uses a stale browser tab

The review request includes `expected_version`. A changed record returns HTTP 409 and must be refreshed.

### Reviewer attempts to decide without ownership

A reviewer must claim an item. Admin can intervene when an item is abandoned.

### File bytes are deleted under retention policy

The file is removed, `file_deleted_at` is recorded, and an audit event is added. Metadata, findings and decisions remain available. Recheck then returns a conflict because bytes are no longer present.

## Non-goals

This repository does not provide a certified disclosure-control system, clinical validation, malware detection, secure authentication, hardened document rendering or formal regulatory compliance.
