from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.pool import QueuePool

from app.core.config import load_database_pool_settings
from app.db import database_pool_snapshot, engine


def _metric_value(payload: str, name: str) -> float:
    prefix = f"{name} "
    for line in payload.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    raise AssertionError(f"Metric {name!r} not found")


def test_sqlite_does_not_publish_postgresql_pool_metrics(client: TestClient) -> None:
    if engine.dialect.name == "postgresql":
        pytest.skip("SQLite-specific metrics boundary runs in the standard backend job")

    assert database_pool_snapshot() is None
    payload = client.get("/metrics")
    assert payload.status_code == 200
    assert "airlock_database_pool_" not in payload.text


def test_postgresql_queue_pool_budget_observability_and_recovery(client: TestClient) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL pool contract runs in the dedicated PostgreSQL CI job")

    pool_settings = load_database_pool_settings()
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.size() == pool_settings.size
    assert engine.pool.timeout() == pool_settings.timeout_seconds

    before = client.get("/metrics").text
    timeout_baseline = _metric_value(before, "airlock_database_pool_checkout_timeouts_total")
    connection_budget = pool_settings.size + pool_settings.max_overflow
    assert _metric_value(before, "airlock_database_pool_capacity") == connection_budget

    connections = []
    try:
        for _ in range(connection_budget):
            connections.append(engine.connect())
        assert engine.pool.checkedout() == connection_budget

        saturated = client.get("/metrics").text
        assert _metric_value(saturated, "airlock_database_pool_checked_out") == connection_budget
        assert _metric_value(saturated, "airlock_database_pool_available") == 0
        assert _metric_value(saturated, "airlock_database_pool_utilisation_ratio") == 1.0
        assert _metric_value(saturated, "airlock_database_pool_overflow_open") == (
            pool_settings.max_overflow
        )

        readiness = client.get("/ready")
        assert readiness.status_code == 503
        assert readiness.json()["detail"] == "Service dependencies are not ready."

        database_api = client.get("/api/v1/metrics")
        assert database_api.status_code == 503
        assert database_api.json()["detail"] == (
            "Database connection capacity is temporarily unavailable."
        )

        after_timeouts = client.get("/metrics").text
        assert _metric_value(
            after_timeouts, "airlock_database_pool_checkout_timeouts_total"
        ) == timeout_baseline + 2
        assert 'path="/api/v1/metrics",status="503"' in after_timeouts

        with pytest.raises(SqlAlchemyTimeoutError):
            engine.connect()
    finally:
        for connection in connections:
            connection.close()

    recovered = client.get("/metrics").text
    assert _metric_value(recovered, "airlock_database_pool_checked_out") == 0
    assert _metric_value(recovered, "airlock_database_pool_available") == connection_budget
    assert _metric_value(recovered, "airlock_database_pool_utilisation_ratio") == 0.0
    assert client.get("/ready").status_code == 200

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
