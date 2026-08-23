# Project Status

Status date: 24 August 2026  
Target: Genomics England — Software Engineer - Python  
Repository: `xm2325/tre_output_airlock`  
Working branch: `genomics-england-python-backend-v0.4`  
Cycle classification: `GOAL_REACHED`

## Final validated implementation evidence

Validated code commit: `49e7d7025e76ddb9ab8bb25dbeeced1458921ff7`

- `CI` workflow run `32606026115`: SUCCESS.
- `AWS backend service` workflow run `32606026128`: SUCCESS.
- backend tests: 43 passed.
- backend coverage: 91.31% against a 90% gate.
- Ruff: passed.
- MyPy: no issues in 25 source files.
- Terraform backend service: `fmt -check`, `init -backend=false` and `validate` passed.

Commits after the validated code commit in the application-evidence control cycle are documentation/state changes only. They do not strengthen the implementation evidence class and do not replace the validated code/CI record above.

## Current evidence state

| Capability | Evidence class | Evidence boundary |
|---|---|---|
| Python backend | DIRECT | FastAPI service, typed Python, linting, MyPy and automated tests |
| REST APIs | DIRECT | Versioned routes, OpenAPI contract and API tests |
| Relational database / SQL | DIRECT | SQLAlchemy, PostgreSQL Docker path and Alembic migrations |
| AWS RDS | REFERENCE | Private RDS Terraform configuration; not applied to a live AWS account |
| AWS microservice architecture | REFERENCE | API Gateway, VPC Link, internal ALB and ECS Fargate Terraform; statically validated only |
| AWS IAM | REFERENCE | Execution/task-role design and restricted secret access in Terraform; not live IAM evidence |
| Identity / IdP | DIRECT_WITH_MOCKED_EXTERNAL | OIDC introspection adapter with issuer/audience/expiry/role validation; external IdP network boundary mocked; no real Okta tenant |
| Test automation | DIRECT | 43 backend tests, 91.31% coverage and a 90% gate in validated CI |
| Troubleshooting / operational support | DIRECT | Structured logs, readiness, metrics, runbook and explicit failure responses |
| React / TypeScript | DIRECT | Existing frontend implementation and tests |
| Clinical/genomic domain context | SYNTHETIC | FHIR/VCF/OMOP-aligned workflow demonstrated only on synthetic records |
| Lambda / DynamoDB | ABSENT | Additional JD skills only; intentionally not added without a justified service need |

## Cycle decision

`GOAL_REACHED = YES`

The current official Genomics England vacancy was rechecked on 24 August 2026 and still displayed `Apply now`, with the stated deadline of 6 September 2026 at 23:00 UK time.

The repository now supplies strong, reproducible evidence for the core application areas that can be demonstrated safely without external infrastructure: Python backend engineering, REST APIs, PostgreSQL/Alembic persistence, authentication/authorisation behaviour, automated testing, failure semantics and operational behaviour. AWS/RDS/IAM evidence is deliberately bounded as `REFERENCE`; identity is deliberately bounded as `DIRECT_WITH_MOCKED_EXTERNAL`; clinical/genomic examples remain `SYNTHETIC`.

No major P0 gap can be closed safely in one or two cycles with enough expected interview-probability gain to justify delaying application. The strongest remaining evidence upgrades require external AWS or IdP resources, while Lambda and DynamoDB are optional and have no justified role in the current service design.

## Supported application evidence

The repository supports these concise statements:

- Built and tested a typed Python/FastAPI backend with versioned REST APIs, PostgreSQL/Alembic persistence, role-based access control, explicit error semantics and operational telemetry.
- Implemented an OIDC token-introspection adapter with issuer, audience, expiry and group-to-role validation, with failure-path tests; external IdP calls are mocked rather than presented as real Okta integration.
- Used automated CI with Ruff, MyPy and 43 backend tests, reaching 91.31% coverage against a 90% gate.
- Designed and statically validated Terraform for an AWS backend reference architecture using API Gateway, private ECS Fargate, RDS, IAM, Secrets Manager and private networking; this is not a live AWS deployment claim.
- Demonstrated a clinical-genomic data path using FHIR, VCF and OMOP-aligned outputs on synthetic data only.

## Unsupported claims

Do not claim:

- a production Genomics England deployment;
- a live AWS deployment or production operation of ECS, RDS, IAM, API Gateway or Secrets Manager;
- integration with a real Okta tenant;
- handling of real Genomics England, NHS, participant or patient records;
- Lambda or DynamoDB implementation.

## Stop rule

Feature growth stops here. Future cycles should make no project changes unless a regression, stale claim, changed live job requirement or newly material P0 gap appears.

The next action is non-coding: use the evidence above to tailor the CV and the 1,440-character hiring-manager message, then submit before the deadline rather than waiting for optional project work.
