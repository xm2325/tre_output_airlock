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

## Per-token single-flight coordination

A short cache does not by itself prevent a cache stampede. If several requests for the same cold or just-expired bearer token arrive together, each request could observe the miss before the first introspection completes and all of them could call the IdP.

The backend therefore keeps a small per-process in-flight registry keyed by the same HMAC token/config digest used by the resident cache. The first request for a key becomes the leader and performs the upstream introspection. Concurrent requests for that same key wait on the leader's completion event and reuse its current result. The registry lock protects only lookup, insertion and removal; it is not held while the network request runs, so different token/config keys remain concurrent.

Successful active-token results are published to the current waiting group and then follow the existing TTL/`exp` cache rules. Authentication failures and IdP 503 responses can be shared with requests already waiting on that flight, but they are not added to the resident cache. A later request therefore attempts introspection again rather than inheriting a cached failure. Setting the cache TTL to zero disables resident reuse but still allows simultaneous requests to coalesce while one introspection is in flight.

Follower waiting is bounded by the configured upstream timeout plus one second. If the leader does not complete inside that coordination window, the follower fails with 503 instead of waiting indefinitely. Telemetry distinguishes leaders, joined requests, shared successes/errors and wait timeouts.

Threaded regression tests exercise four concurrency properties: eight simultaneous same-token requests collapse to one simulated upstream introspection; two different tokens reach a barrier inside the simulated IdP concurrently; a shared upstream failure returns 503 to the current group but is retried by a later request; and TTL-zero mode coalesces only the concurrent work.

This coordination is intentionally **per API process**. Separate ECS tasks do not share the in-flight registry, so a cold token can still cause one introspection per task. The repository does not claim a distributed lock or distributed identity cache.

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

PostgreSQL engines also use an explicit, bounded per-process SQLAlchemy connection-pool contract:

```text
AIRLOCK_DATABASE_POOL_SIZE=5
AIRLOCK_DATABASE_MAX_OVERFLOW=5
AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS=5.0
AIRLOCK_DATABASE_POOL_RECYCLE_SECONDS=900
```

`pool_pre_ping` remains enabled. Persistent pool size is constrained to 1–20 connections, overflow to 0–20, checkout timeout to 0.1–30 seconds and recycle age to 30–3,600 seconds. Numeric configuration fails closed, including non-finite timeout values. SQLite does not consume these QueuePool settings, so an invalid PostgreSQL pool environment value does not alter the local SQLite path.

The pool is a **per-task budget**. With the reference defaults, one API task can hold up to 10 application connections. If ECS runs two tasks, the service can therefore attempt roughly 20 application connections before accounting for migrations, administration, monitoring, failover and any other RDS users. These defaults are demonstration/reference values, not a claim that 10 connections per task is appropriate for a particular production database.

The AWS backend workflow starts PostgreSQL 16, applies the Alembic migration and runs all 70 backend tests against PostgreSQL. Its pool contract deliberately uses `pool_size=3`, `max_overflow=2`, a 0.2-second checkout timeout and a 300-second recycle interval. The PostgreSQL-only test checks that the configured QueuePool has the expected size and timeout, opens all five permitted connections, verifies that a sixth checkout raises SQLAlchemy `TimeoutError`, closes the held connections, confirms the checked-out count returns to zero and then executes `SELECT 1` through a fresh connection. This proves bounded exhaustion and recovery behavior against PostgreSQL rather than only testing configuration parsing.

The standard SQLite coverage job now collects 71 tests; the PostgreSQL-only saturation contract is skipped there, producing 70 passed / 1 skipped with 91.07% coverage. The dedicated PostgreSQL path also collects 71 tests, with 70 passed / 1 SQLite-only skipped.

## Database pool observability

The existing `/metrics` endpoint exposes live **per-process** PostgreSQL QueuePool state: configured persistent size, maximum overflow, total capacity, checked-out and checked-in connections, open overflow connections, remaining checkout capacity and a utilisation ratio. It also exposes a cumulative checkout-timeout counter. SQLite deliberately emits none of these PostgreSQL/RDS pool gauges.

When a normal database-backed API request cannot obtain a connection before `pool_timeout`, the service translates SQLAlchemy `TimeoutError` into HTTP 503 with an explicit temporary database-capacity message instead of reporting an internal 500. The readiness path retains its dependency-unavailable 503 contract and records the same pool-timeout counter when exhaustion is the cause.

The PostgreSQL 16 CI contract fills all five configured `3 + 2` connections, verifies metrics report checked-out capacity of five, zero remaining capacity, utilisation `1.0` and two open overflow connections, then exercises both `/ready` and a database-backed API while saturated. Both return 503 and the timeout counter increases by two. After the held connections are released, the contract verifies checked-out returns to zero, full capacity is available, utilisation returns to `0.0`, readiness returns 200 and a fresh `SELECT 1` succeeds.

These gauges describe one API process. They are not aggregate ECS-service or RDS-instance metrics; production operations still need service-level aggregation, RDS/CloudWatch metrics, dashboards and alert thresholds.


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

The Terraform reference passes the bounded database pool size, overflow, checkout timeout and recycle age into each ECS task alongside the RDS endpoint configuration. Production sizing must compare `desired_count * (pool_size + max_overflow)` with the actual RDS connection limit and leave explicit headroom for non-service connections and scaling/failover behavior.

CloudWatch receives container logs. `/ready` checks database access and writable working storage and is used for ECS and target-group health checks. API Gateway applies a basic request-rate limit in the reference module.

## Validation boundary

The dedicated workflow runs Ruff, strict MyPy, backend tests with the 90% coverage threshold, a PostgreSQL 16 migration-and-test contract including bounded pool exhaustion/recovery, shell syntax validation for the container entrypoint, `terraform fmt -check`, `terraform init -backend=false` and `terraform validate`.

Passing these checks supports claims about tested Python/PostgreSQL behavior, explicit per-task database connection budgets and statically validated Terraform. The OIDC tests use a simulated IdP boundary, including the threaded single-flight cases. These checks do **not** support a claim that the AWS stack has been applied, that the reference pool values have been calibrated against a real RDS instance, that a real IdP integration has been operated, or that single-flight coordination spans multiple service tasks.