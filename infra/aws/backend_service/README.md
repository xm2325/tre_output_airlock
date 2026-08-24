# AWS backend-service reference deployment

This Terraform module maps the tested Airlock FastAPI/PostgreSQL application to an AWS deployment shape relevant to backend platform engineering. It is **reference infrastructure** and is not presented as evidence of a live Genomics England, NHS or production deployment.

## Architecture

```text
research client
     |
     | HTTPS
     v
API Gateway HTTP API
     |
     | VPC Link
     v
internal ALB
     |
     v
ECS Fargate API service (FastAPI)
     |              |               |
     |              |               +--> external OIDC/Okta-style introspection over HTTPS
     |              |
     |              +--> encrypted EFS working-file volume
     |
     +--> private RDS PostgreSQL
              |        |
              |        +--> Submission + ScanJob + transactional OutboxEvent
              |
              +--> RDS-managed master secret in Secrets Manager

independent ECS outbox publisher
     |
     | sqs:SendMessage only
     v
encrypted SQS scan queue ---- redrive ----> encrypted SQS DLQ
     |
     | receive/delete/change-visibility only
     v
independent ECS scan workers
     |
     +--> shared EFS quarantine file
     +--> RDS durable job/submission/audit state
```

The API, publisher and worker tasks run only in private subnets and receive no public IP. The database is not publicly reachable. Security-group rules allow API Gateway VPC Link -> internal load balancer -> API ECS tasks and allow the service tasks to reach RDS/EFS on the required ports.

## Asynchronous scan hand-off

The AWS reference sets `AIRLOCK_SCAN_MODE=queued`. An upload request stores the quarantine file and commits the submission, `ScanJob`, `OutboxEvent`, idempotency state and hash-linked queue audit in PostgreSQL before returning HTTP 202. It does **not** call SQS from the request transaction and does not run the disclosure checker in the API process.

A separate publisher process claims committed outbox rows and sends their versioned payloads to SQS. Independent worker tasks receive those messages, claim the durable scan job, execute the same scanning application service used by synchronous/recheck paths, commit findings/decision/audit/job completion, and only then delete the SQS receipt.

The delivery contract is deliberately **at-least-once**:

- if SQS accepts a message but the publisher crashes before the outbox `PUBLISHED` commit, an expired claim can be reclaimed and the message sent again;
- if a worker commits a completed scan but crashes before deleting the SQS receipt, the message can be delivered again;
- a redelivered message for a durable `COMPLETED` job is acknowledged without a second scan or duplicate completion audit;
- a failed scan returns the job to `QUEUED`, records the failure and leaves the message available for visibility-timeout/redrive retry.

This is not a distributed exactly-once guarantee. Production would still require queue-age/DLQ alarms, autoscaling and back-pressure tests, poison-message/runbook validation and controlled DLQ replay.

## Identity, secrets and least-privilege roles

The API uses `AIRLOCK_AUTH_MODE=oidc_introspection`. API Gateway does not make the application authorisation decision: the backend sends bearer tokens to the configured OAuth2/OIDC introspection endpoint and validates token activity, expiry, optional issuer/audience and the configured group claim before mapping it to `researcher`, `reviewer` or `admin` RBAC.

The API ECS execution role can read only three declared runtime secret resources:

1. the RDS-managed master-user secret;
2. the IdP introspection client secret;
3. the Airlock decision-report signing secret.

Runtime task roles are split by responsibility:

- **API task role:** intentionally no SQS API permissions;
- **publisher task role:** `sqs:SendMessage` only on the scan queue;
- **worker task role:** queue receive/delete/change-visibility/attribute access needed for consumption;
- **async execution role:** only the RDS runtime secret required to start publisher/worker containers, plus standard ECS image/log permissions.

This separation prevents the public-facing API task from receiving broad queue privileges merely because background processes use SQS.

## PostgreSQL / RDS contract

The containers receive the RDS host, port and database name as ordinary environment values. Username and password are injected from the RDS-managed Secrets Manager secret. `app.core.config.build_database_url()` builds a `postgresql+psycopg` URL at runtime and URL-escapes credentials.

RDS settings in this reference include encrypted storage, private subnet placement, automated backups and production deletion protection. `database_multi_az` is configurable because the cheapest development shape is not the same as a production availability choice.

The database pool budget is per process/task. Production sizing must therefore account for the API, publisher and worker task counts together, plus migration/admin/monitoring headroom against the deployed RDS `max_connections`.

## Database migrations

The local Docker Compose path still runs Alembic automatically. The ECS services set:

```text
AIRLOCK_RUN_MIGRATIONS=false
AIRLOCK_AUTO_CREATE_SCHEMA=false
```

A deployment pipeline should run a one-off ECS task using the emitted API task definition and override the container command with:

```text
alembic upgrade head
```

Only after that task succeeds should the ECS services be updated. This avoids concurrent schema migrations when several Fargate tasks start during a rolling deployment.

## Durable working files

The current Airlock service performs file checks that need a filesystem path. The reference services therefore mount encrypted EFS at `/mnt/airlock` and point the quarantine directory at `/mnt/airlock/quarantine`. API and worker tasks see the same durable quarantine path. A future production design may instead replace this adapter with object storage and malware-scanning services.

## API Gateway and microservice boundary

API Gateway exposes only the FastAPI service through a managed public HTTPS endpoint and forwards requests through a VPC Link to an internal Application Load Balancer. Publisher and worker services have no load balancer or public route. Each role has its own ECS service/task identity, logs and release lifecycle while sharing the PostgreSQL and EFS durability boundaries needed by the demonstrated workflow.

## Validation

The repository CI runs:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

for this directory. A dedicated PostgreSQL 16 workflow applies Alembic through `0004(head)` and runs the backend contract. A separate PostgreSQL 16 plus Moto SQS-compatible integration creates queue/DLQ state through boto3, publishes a committed outbox event over HTTP, consumes it with the production SQS adapter, commits scan completion, deletes the receipt and deliberately replays the same payload to verify idempotent completion.

These checks demonstrate code/configuration contracts and SQS-compatible transport behaviour. They do **not** prove that this Terraform module was applied to a real AWS account, nor do they establish production queue throughput, latency or recovery characteristics.

## Required inputs

At minimum supply:

- existing VPC ID and CIDR;
- two or more private subnet IDs with outbound access to the IdP and AWS service endpoints/NAT as required;
- immutable Airlock container image reference;
- OIDC introspection URL, client ID, expected audience and issuer;
- Secrets Manager ARN for the OIDC client secret;
- Secrets Manager ARN for the report-signing secret.

Queue and DLQ resources are created by this module. See `variables.tf` for the full contract, including API/publisher/worker desired counts and queue claim/visibility settings.
