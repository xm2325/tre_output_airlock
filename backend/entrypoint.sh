#!/bin/sh
set -eu

if [ "${AIRLOCK_RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
