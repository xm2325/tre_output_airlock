# Identity and AWS backend-service extension

This document records the backend changes added to the existing TRE Output Airlock for a stronger Python software-engineering demonstration. It does not describe a Genomics England system and does not claim a live AWS deployment.

## Identity modes

The backend supports two explicit identity modes.

### `demo`

The local/browser demonstration uses `X-Demo-User` and `X-Demo-Role`. It remains the default so the public synthetic demo does not depend on an external identity service.

### `oidc_introspection`

A service deployment can require an OAuth2 bearer token and validate it through a configured token-introspection endpoint. This design can be connected to an identity provider (IdP) that supports RFC 7662-style introspection, including an Okta authorization server configured for that flow.

The backend checks token activity, expiry when `exp` is returned, configured audience and issuer, a configurable subject claim, a configurable group/role claim, and group-to-application role mapping. External groups are mapped to the existing `researcher`, `reviewer` and `admin` roles. If several mapped roles are returned, the deterministic precedence is `admin > reviewer > researcher`.

HTTP behavior is explicit:

| Condition | Response |
|---|---:|
| Missing bearer token in IdP mode | 401 |
| Inactive, expired, wrong-audience or wrong-issuer token | 401 |
| Valid identity without an Airlock role | 403 |
| IdP/configuration unavailable | 503 |
| Valid identity and role | request continues to route-level RBAC |

The tests mock the IdP network boundary. They do not contact or claim a real Okta tenant.

## Short-lived introspection cache

Calling a remote introspection endpoint for every protected API request adds latency and makes every request depend on immediate IdP availability. The backend therefore has an optional, short-lived, per-process cache for **successful active-token introspection only**.

The default cache TTL is 15 seconds. The application rejects configured TTLs above 60 seconds and allows a TTL of zero to disable caching. Each entry also expires no later than the token's returned `exp`, so cached authorization never extends the token lifetime.

Inactive tokens, invalid claims, identities without an Airlock role and IdP failures are not cached. This prevents a temporary upstream error from becoming a cached authentication result.

The cache is bounded with least-recently-used (LRU) eviction. The default capacity is 2,048 entries and the application rejects values above 10,000. This prevents arbitrary bearer-token traffic from causing unbounded cache growth.

Raw bearer tokens are not used as cache dictionary keys. The cache derives a keyed HMAC-SHA256 digest from the token plus the active identity contract, using the introspection client secret as the HMAC key. A client-secret or claim-contract change therefore also changes cache keys.

The security tradeoff is explicit: a token revoked immediately after a successful introspection can remain accepted until the short cache entry expires. Deployments that require immediate revocation can set `AIRLOCK_OIDC_CACHE_TTL_SECONDS=0`. This is why the cache is short and capped rather than a general session cache.

Prometheus output records cache hits, misses, expirations, disabled-cache requests, upstream successes/errors and recent IdP introspection p50/p95/p99 latency. These measures allow the cache benefit and IdP dependency behavior to be checked rather than assumed.

## Why introspection is kept behind an adapter

The route layer depends only on the existing `Actor` and `require_roles` interface. Local demo identity and external IdP identity therefore produce the same application principal. Authentication remains separate from submission, review and audit logic.

A production team could replace the introspection adapter with local JWT/JWKS validation without rewriting route-level RBAC. The choice depends on the organization's IdP, token format, revocation requirements and latency budget.

## PostgreSQL / RDS configuration

Local development can still use a complete `AIRLOCK_DATABASE_URL` or the existing SQLite default. For container platforms that inject Secrets Manager values individually, the service can instead build the PostgreSQL URL from:

```text
AIRLOCK_DATABASE_HOST
AIRLOCK_DATABASE_PORT
AIRLOCK_DATABASE_NAME
AIRLOCK_DATABASE_USER
AIRLOCK_DATABASE_PASSWORD
```

The builder validates required fields and port range and URL-escapes credentials before constructing the `postgresql+psycopg` DSN.

The AWS backend workflow also starts PostgreSQL 16, applies the Alembic migration to that database and runs the backend test suite against PostgreSQL. This tests SQL, transaction, timestamp and optimistic-concurrency behavior against the same database family used by the RDS reference design rather than relying only on SQLite tests.

## Review transaction boundary

A review claim and its hash-linked audit record are committed in one database transaction. If audit persistence fails, the claim is rolled back instead of leaving an unaudited state change. Claims have a configurable lease (30 minutes by default); an expired claim becomes claimable again and reassignment still uses the existing `row_version` compare-and-swap condition.

The compare-and-swap bulk update disables SQLAlchemy's in-memory session evaluation and explicitly refreshes the row after the database update. This keeps SQLite and PostgreSQL behavior aligned and makes the database condition the source of truth for the atomic claim.

## Schema migrations under multiple service tasks

The original container ran `alembic upgrade head` on every start. That behavior is useful in local Docker Compose but is risky when several ECS tasks start during a rolling release.

`AIRLOCK_RUN_MIGRATIONS=false` disables startup migration for the service task. The AWS reference deployment uses that setting together with `AIRLOCK_AUTO_CREATE_SCHEMA=false`. A deployment process should run one one-off ECS task with:

```text
alembic upgrade head
```

and update the service only after the migration succeeds.

## AWS service boundary

`infra/aws/backend_service/` maps the tested containerized backend to this reference path:

```text
API Gateway HTTP API
    -> VPC Link
    -> internal Application Load Balancer
    -> private ECS Fargate tasks
         -> private RDS PostgreSQL
         -> encrypted EFS working storage
         -> external IdP introspection over HTTPS
```

Runtime credentials and signing material come from Secrets Manager. The ECS execution role can read only the declared secret resources in the module. The application task role has no AWS control-plane permissions because the current FastAPI process does not call AWS APIs directly.

CloudWatch receives container logs. `/ready` checks database access and writable working storage and is used for ECS and target-group health checks. API Gateway applies a basic request-rate limit in the reference module.

## Validation boundary

The dedicated workflow runs Ruff, strict MyPy, backend tests with the 90% coverage threshold, a PostgreSQL 16 migration-and-test contract, shell syntax validation for the container entrypoint, `terraform fmt -check`, `terraform init -backend=false` and `terraform validate`.

Passing these checks supports claims about tested Python/PostgreSQL behavior and statically validated Terraform. It does **not** support a claim that the AWS stack has been applied or operated in production.
