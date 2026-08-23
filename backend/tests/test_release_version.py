from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.policy import API_VERSION
from app.main import app
from app.version import __version__


def repository_version() -> str:
    return (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()


def test_runtime_version_matches_repository_release(client: TestClient) -> None:
    expected = repository_version()

    assert expected == "0.7.0"
    assert __version__ == expected
    assert API_VERSION == expected
    assert app.version == expected

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == expected
