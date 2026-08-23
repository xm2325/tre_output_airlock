from __future__ import annotations

import pytest

from app.core.config import (
    build_database_engine_options,
    build_database_url,
    load_database_pool_settings,
)


def _clear_database_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for name in (
        "AIRLOCK_DATABASE_URL",
        "AIRLOCK_DATABASE_HOST",
        "AIRLOCK_DATABASE_PORT",
        "AIRLOCK_DATABASE_NAME",
        "AIRLOCK_DATABASE_USER",
        "AIRLOCK_DATABASE_PASSWORD",
        "AIRLOCK_DATABASE_POOL_SIZE",
        "AIRLOCK_DATABASE_MAX_OVERFLOW",
        "AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS",
        "AIRLOCK_DATABASE_POOL_RECYCLE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_explicit_database_url_takes_precedence(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("AIRLOCK_DATABASE_URL", "postgresql+psycopg://explicit/db")
    monkeypatch.setenv("AIRLOCK_DATABASE_HOST", "ignored-rds.example")
    assert build_database_url() == "postgresql+psycopg://explicit/db"


def test_default_database_url_remains_local_sqlite(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    assert build_database_url() == "sqlite:///./data/airlock.db"


def test_rds_components_build_postgresql_url_and_escape_credentials(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("AIRLOCK_DATABASE_HOST", "airlock.cluster.example")
    monkeypatch.setenv("AIRLOCK_DATABASE_PORT", "5432")
    monkeypatch.setenv("AIRLOCK_DATABASE_NAME", "research_airlock")
    monkeypatch.setenv("AIRLOCK_DATABASE_USER", "service-user")
    monkeypatch.setenv("AIRLOCK_DATABASE_PASSWORD", "p@ss/word")

    assert build_database_url() == (
        "postgresql+psycopg://service-user:p%40ss%2Fword@"
        "airlock.cluster.example:5432/research_airlock"
    )


def test_partial_rds_configuration_fails_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("AIRLOCK_DATABASE_HOST", "airlock.cluster.example")
    monkeypatch.setenv("AIRLOCK_DATABASE_USER", "service-user")

    with pytest.raises(ValueError, match="RDS-style database configuration"):
        build_database_url()


def test_invalid_database_port_is_rejected(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("AIRLOCK_DATABASE_HOST", "airlock.cluster.example")
    monkeypatch.setenv("AIRLOCK_DATABASE_USER", "service-user")
    monkeypatch.setenv("AIRLOCK_DATABASE_PASSWORD", "secret")
    monkeypatch.setenv("AIRLOCK_DATABASE_NAME", "airlock")
    monkeypatch.setenv("AIRLOCK_DATABASE_PORT", "70000")

    with pytest.raises(ValueError, match="between 1 and 65535"):
        build_database_url()


def test_default_postgresql_pool_contract_is_bounded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)

    pool = load_database_pool_settings()
    assert pool.size == 5
    assert pool.max_overflow == 5
    assert pool.timeout_seconds == 5.0
    assert pool.recycle_seconds == 900

    options = build_database_engine_options("postgresql+psycopg://service@db/airlock")
    assert options == {
        "future": True,
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 5.0,
        "pool_recycle": 900,
    }


def test_postgresql_pool_contract_accepts_valid_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("AIRLOCK_DATABASE_POOL_SIZE", "3")
    monkeypatch.setenv("AIRLOCK_DATABASE_MAX_OVERFLOW", "2")
    monkeypatch.setenv("AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("AIRLOCK_DATABASE_POOL_RECYCLE_SECONDS", "300")

    pool = load_database_pool_settings()
    assert pool.size == 3
    assert pool.max_overflow == 2
    assert pool.timeout_seconds == 0.2
    assert pool.recycle_seconds == 300


def test_sqlite_engine_options_ignore_postgresql_pool_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("AIRLOCK_DATABASE_POOL_SIZE", "not-an-integer")

    assert build_database_engine_options("sqlite:///./data/test.db") == {
        "future": True,
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
    }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AIRLOCK_DATABASE_POOL_SIZE", "0", "between 1 and 20"),
        ("AIRLOCK_DATABASE_MAX_OVERFLOW", "21", "between 0 and 20"),
        ("AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS", "nan", "between 0.1 and 30"),
        ("AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS", "31", "between 0.1 and 30"),
        ("AIRLOCK_DATABASE_POOL_RECYCLE_SECONDS", "29", "between 30 and 3600"),
    ],
)
def test_invalid_postgresql_pool_settings_fail_closed(
    monkeypatch, name: str, value: str, message: str
) -> None:  # type: ignore[no-untyped-def]
    _clear_database_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        load_database_pool_settings()
