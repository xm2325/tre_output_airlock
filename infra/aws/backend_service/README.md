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
ECS Fargate service (FastAPI)
     |              |               |
     |              |               +--> external OIDC/Okta-style introspection over HTTPS
     |              |
     |              +--> encrypted EFS working-file volume
     |
     +--> private RDS PostgreSQL
              |
              +--> RDS-managed master secret in Secrets Manager
```

The service tasks run only in private subnets and receive no public IP. The database is not publicly reachable. Security-group rules allow API Gateway VPC Link -> internal load balancer -> ECS -> RDS/EFS along the required ports.

## Identity and secrets

The application uses `AIRLOCK_AUTH_MODE=oidc_introspection`. API Gateway does not make the application authorisation decision: the backend sends bearer tokens to the configured OAuth2/OIDC introspection endpoint and validates token activity, expiry, optional issuer/audience and the configured group claim before mapping it to `researcher`, `reviewer` or `admin` RBAC.

The ECS execution role can read only three declared runtime secret resources:

1. the RDS-managed master-user secret;
2. the IdP introspection client secret;
3. the Airlock decision-report signing secret.

The application task role intentionally has no AWS API permissions because the current service does not call AWS control-plane APIs at runtime.

## PostgreSQL / RDS contract

The container receives the RDS host, port and database name as ordinary environment values. Username and password are injected from the RDS-managed Secrets Manager secret. `app.core.config.build_database_url()` builds a `postgresql+psycopg` URL at runtime and URL-escapes credentials.

RDS settings in this reference include encrypted storage, private subnet placement, automated backups and production deletion protection. `database_multi_az` is configurable because the cheapest development shape is not the same as a production availability choice.

## Database migrations

The local Docker Compose path still runs Alembic automatically. The ECS service sets:

```text
AIRLOCK_RUN_MIGRATIONS=false
AIRLOCK_AUTO_CREATE_SCHEMA=false
```

A deployment pipeline should run a one-off ECS task using the emitted task definition and override the container command with:

```text
alembic upgrade head
```

Only after that task succeeds should the ECS service be updated. This avoids concurrent schema migrations when several Fargate tasks start during a rolling deployment.

## Durable working files

The current Airlock service performs file checks that need a filesystem path. The reference service therefore mounts encrypted EFS at `/mnt/airlock` and points the quarantine directory at `/mnt/airlock/quarantine`. A future production design may instead replace this adapter with object storage and malware-scanning services.

## API Gateway and microservice boundary

API Gateway exposes the service through a managed public HTTPS endpoint and forwards requests through a VPC Link to an internal Application Load Balancer. The backend remains a separately deployable REST service with its own database, identity boundary, task identity, health checks, logs and release lifecycle.

## Validation

The repository CI runs:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

for this directory. Validation proves Terraform configuration consistency; it does not prove that the module was applied to a real AWS account.

## Required inputs

At minimum supply:

- existing VPC ID and CIDR;
- two or more private subnet IDs with outbound access to the IdP;
- immutable Airlock container image reference;
- OIDC introspection URL, client ID, expected audience and issuer;
- Secrets Manager ARN for the OIDC client secret;
- Secrets Manager ARN for the report-signing secret.

See `variables.tf` for the full contract.
