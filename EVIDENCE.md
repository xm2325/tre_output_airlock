# Evidence Matrix

Target: Genomics England — Software Engineer - Python  
Branch: `genomics-england-python-backend-v0.4`

| JD requirement | Direct repository evidence | Validation | Claim level | CV-ready |
|---|---|---|---|---|
| Python backend engineering | FastAPI backend with typed service, route, policy, storage and audit modules | Ruff + MyPy + pytest CI | DIRECT | YES |
| Scalable/service-oriented backend design | Separately deployable API service, health/readiness endpoints, request IDs, telemetry and container path | CI and container checks | DIRECT/LOCAL | YES, with scope stated |
| REST APIs | FastAPI routes and committed OpenAPI contract | API tests and OpenAPI checks | DIRECT | YES |
| Relational DB / SQL | SQLAlchemy models, PostgreSQL Docker service and Alembic migration | migration and integration checks | DIRECT | YES |
| AWS RDS | Private encrypted RDS configuration in `infra/aws/backend_service` | Terraform fmt/init/validate | REFERENCE | YES only as reference design, not deployment |
| AWS microservices | API Gateway -> VPC Link -> internal ALB -> ECS Fargate service | Terraform validation | REFERENCE | YES only as tested infrastructure design |
| AWS IAM | Execution/task-role separation and restricted secret access in Terraform | Terraform validation | REFERENCE | YES only as IAM design/configuration |
| Identity / Okta-like IdP integration | OIDC token-introspection adapter, issuer/audience/expiry checks and role mapping | `test_oidc_auth.py`; latest backend suite 43/43 | DIRECT WITH MOCKED NETWORK | YES: implemented/tested OIDC introspection adapter; NO real Okta claim |
| Test automation / TDD | pytest suite, coverage gate and CI | 43 passed; 91.31% coverage; 90% gate | DIRECT | YES |
| Troubleshooting / operational support | structured logs, readiness, metrics, runbook and explicit failure responses | tests/CI | DIRECT/DEMO | YES, describe as project evidence |
| React / JavaScript | React + TypeScript frontend | frontend CI/tests in repository | DIRECT | YES |
| API Gateway | Terraform backend-service module | Terraform validation | REFERENCE | YES only as reference infrastructure |
| Lambda | No current direct implementation | none | ABSENT | NO |
| DynamoDB | No current direct implementation | none | ABSENT | NO |
| Genomic/health-data context | FHIR, VCF, OMOP-aligned clinical-genomic pipeline | pipeline tests/CI | DIRECT ON SYNTHETIC DATA | YES, must say synthetic |

## Verified current CI evidence

Code commit: `49e7d7025e76ddb9ab8bb25dbeeced1458921ff7`

- `CI` workflow: success.
- `AWS backend service` workflow: success.
- Backend: 43 tests passed.
- Coverage: 91.31%, above the 90% gate.
- Ruff: passed.
- MyPy: no issues in 25 source files.
- Terraform backend service: format, initialisation without a backend, and validation passed.

## Supported CV claims

The repository supports claims such as:

- Built and tested a Python/FastAPI backend with REST APIs, PostgreSQL/Alembic persistence, role-based access control, operational telemetry and automated CI.
- Implemented an OIDC token-introspection adapter with issuer, audience, expiry and group-to-role validation, covered by automated tests.
- Designed and statically validated Terraform for an AWS backend reference architecture using API Gateway, private ECS Fargate, RDS, IAM, Secrets Manager and private networking.
- Built a synthetic clinical-genomic ingestion path covering FHIR, VCF, OMOP-aligned outputs, data-quality checks and lineage.

## Claims not currently supported

Do **not** claim that this repository proves:

- a production Genomics England deployment;
- a live AWS deployment of the backend-service Terraform;
- production operation of ECS, RDS, IAM, API Gateway or Secrets Manager;
- integration with a real Okta tenant;
- use of real participant or patient records;
- Lambda or DynamoDB implementation.

## Evidence rule for future cycles

When a new capability is added, move it to `CV-ready = YES` only after the implementation and its validation evidence both exist. Reference architecture stays labelled `REFERENCE` until a safe applied environment has been run and recorded.
