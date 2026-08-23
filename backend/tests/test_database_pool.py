from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.pool import QueuePool

from app.core.config import load_database_pool_settings
from app.db import engine


def test_postgresql_queue_pool_budget_and_recovery() -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL pool contract runs in the dedicated PostgreSQL CI job")

    pool_settings = load_database_pool_settings()
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.size() == pool_settings.size
    assert engine.pool.timeout() == pool_settings.timeout_seconds

    connections = []
    connection_budget = pool_settings.size + pool_settings.max_overflow
    try:
        for _ in range(connection_budget):
            connections.append(engine.connect())
        assert engine.pool.checkedout() == connection_budget

        with pytest.raises(SqlAlchemyTimeoutError):
            engine.connect()
    finally:
        for connection in connections:
            connection.close()

    assert engine.pool.checkedout() == 0
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
