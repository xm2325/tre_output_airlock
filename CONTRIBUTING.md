# Contributing

This is a synthetic portfolio repository. Contributions must not include real participant, patient, clinical or confidential data.

## Local checks

```bash
make install
make validate
```

`pip-audit` requires network access. Docker changes should also pass:

```bash
docker compose config --quiet
docker compose build
```

## Change expectations

- Add or update tests for behavioural changes.
- Regenerate the OpenAPI schema after API changes with `make openapi`.
- Add a benchmark case when a rule or policy action changes.
- Add an Alembic revision for schema changes.
- Update the policy version when release behaviour changes.
- Avoid writing matched identifiers or raw file content to logs, errors or evidence.
- Record important design choices in an ADR.

## Pull requests

Keep changes focused. Explain the problem, state transition or threat being addressed, validation performed and remaining limits.
