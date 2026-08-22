from __future__ import annotations

import pytest

from app.core.config import build_database_url


def _clear_database_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for name in (
        "AIRLOCK_DATABASE_URL",
        "AIRLOCK_DATABASE_HOST",
        "AIRLOCK_DATABASE_PORT",
        "AIRLOCK_DATABASE_NAME",
        "AIRLOCK_DATABASE_USER",
        "AIRLOCK_DATABASE_PASSWORD",
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
