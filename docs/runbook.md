# Local operations runbook

## Start

```bash
cp .env.example .env
docker compose up --build
```

Check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

## Common failures

### API is not ready

1. Run `docker compose ps`.
2. Inspect `docker compose logs db api`.
3. Confirm PostgreSQL is healthy.
4. Confirm the database URL uses host `db`, not `localhost`, inside Compose.
5. Run `docker compose run --rm api alembic current`.

### Migration fails

Do not delete a database containing needed records. Capture the migration error, current revision and database backup status. For local synthetic data only, `docker compose down -v` resets all state.

### Review returns HTTP 409

Refresh the item. It was claimed, released, rechecked or decided after the browser loaded it. Claim again if it is still waiting and submit the current `row_version`.

### Recheck returns HTTP 409

The quarantined bytes were retired. Findings and reports remain, but the system cannot scan a file that no longer exists.

### Audit verification fails

Treat this as a high-severity integrity signal. Stop release actions for that submission, preserve logs and database state, and investigate direct data changes or application defects.

## Reset local synthetic state

```bash
docker compose down -v
```

This deletes the local PostgreSQL and quarantine volumes.
