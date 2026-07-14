from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path(__file__).parent / ".runtime"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["AIRLOCK_DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["AIRLOCK_QUARANTINE_DIR"] = str(TEST_ROOT / "quarantine")

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
