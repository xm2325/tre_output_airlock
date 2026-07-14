# Validation record

Validation date: 2026-07-14

## Backend quality

Commands:

```bash
cd backend
python -m ruff check app tests alembic
python -m mypy app
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
```

Observed result:

```text
Ruff: passed
MyPy: passed
Tests: 29 passed
Coverage: 92.44%
Coverage requirement: 90%
```

## Frontend quality

Commands:

```bash
cd frontend
npm install --no-audit --no-fund
npm run typecheck
npm test
npm run build
npm audit --audit-level=high
```

Observed result:

```text
TypeScript: passed
Vitest: 4 passed
Vite production build: passed
npm audit: 0 vulnerabilities
```

The production bundle was generated successfully. The main JavaScript output was approximately 234 kB before gzip and 71 kB after gzip in this environment.

## Database migration

A clean temporary SQLite database was migrated through Alembic:

```text
revision: 0001 (head)
tables: alembic_version, audit_events, findings, submissions
```

Docker Compose uses PostgreSQL and runs the same migration before API startup.

## Synthetic benchmark

Command:

```bash
cd backend
PYTHONPATH=. python -m app.evaluation \
  --manifest ../benchmark/manifest.json \
  --samples ../samples \
  --output ../benchmark/results.json
```

Observed result:

```text
Cases: 9
Expected workflow decisions: 9/9
Unsafe synthetic cases routed to REVIEW or BLOCK: 8/8
Automation rate: 0.667
```

These results verify known synthetic code paths only. They do not estimate performance on real research outputs or prove disclosure-control safety.

## OpenAPI schema generation

CI generates the FastAPI OpenAPI schema into a temporary file:

```bash
cd backend
python ../scripts/export_openapi.py --output /tmp/openapi.json
```

This verifies that the application can construct and serialise its API schema.

## Dependency audits

`npm audit --audit-level=high` completed successfully with zero reported vulnerabilities after the dependency update. A later repeat request returned a temporary 502 from the configured audit endpoint; no dependencies changed between those runs. The audit remains a required CI step.

`pip-audit` could not complete in this execution environment because DNS resolution for the vulnerability service was unavailable. It remains a required GitHub Actions step, where internet access is expected. This local record does not claim that the Python dependency audit passed.

## Container validation

Docker was not available in this execution environment, so containers were not started locally. The Compose file and workflow YAML were parsed, and CI includes both `docker compose config --quiet` and `docker compose build`.

