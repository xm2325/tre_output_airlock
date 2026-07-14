# Validation record

Validation date: 2026-07-14

## Backend quality

Commands:

```bash
cd backend
uv sync --frozen --all-extras
uv run ruff check app tests alembic
uv run mypy app
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
```

Observed result:

```text
Ruff: passed
MyPy: passed
Tests: 31 passed
Coverage: 91.75%
Coverage requirement: 90%
```

## Frontend quality

Commands:

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run build
npm audit --audit-level=high
```

Observed result:

```text
TypeScript: passed
Vitest: 8 passed
Vite production build: passed
npm audit: 0 vulnerabilities
```

The production bundle was generated successfully. The main JavaScript output was approximately 243 kB before gzip and 73 kB after gzip for the static demo build in this environment.

## Reproducible dependency resolution

The backend lock file was regenerated with `uv 0.10.0` and resolves 71 packages. Local validation used `uv sync --frozen --all-extras`, so the test environment was created from the committed lock file rather than resolving fresh dependency versions.

## Static Pages build

The browser-only demo build completed with:

```bash
VITE_DEMO_MODE=true VITE_BASE_PATH=/tre_output_airlock/ npm run build
```

The static mode stores synthetic records in memory and displays an explicit banner that no backend or real data is connected.

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
PYTHONPATH=. uv run python -m app.evaluation \
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

## OpenAPI snapshot

The committed `docs/openapi.json` was generated from the FastAPI application. CI runs:

```bash
cd backend
uv run python ../scripts/export_openapi.py --check
```

This fails when API schemas change without a refreshed snapshot.

## Dependency audits

`npm audit --audit-level=high` completed successfully with zero reported vulnerabilities after the dependency update. A later repeat request returned a temporary 502 from the configured audit endpoint; no dependencies changed between those runs. The audit remains a required CI step.

`pip-audit` could not complete in this execution environment because DNS resolution for the vulnerability service was unavailable. It remains a required GitHub Actions step, where internet access is expected. This local record does not claim that the Python dependency audit passed.

## Container validation

Docker was not available in this execution environment, so containers were not started locally. CI now starts PostgreSQL, runs Alembic, waits for FastAPI readiness, checks the policy endpoint and frontend, prints service logs on failure, and then removes the stack. The workflow also validates Compose and rebuilds the images.

## Files excluded from public repository

Interview scripts, role-specific answers, CV wording and personal preparation notes are stored in a separate interview pack and are not present in this repository.
