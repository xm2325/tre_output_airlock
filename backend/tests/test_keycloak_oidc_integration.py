from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.db import engine

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
REALM_PATH = REPOSITORY_ROOT / "infra" / "keycloak" / "airlock-ci-realm.json"
KEYCLOAK_IMAGE = "quay.io/keycloak/keycloak:26.7.2"
KEYCLOAK_PORT = 18081


def test_real_keycloak_oidc_introspection_and_authorisation(tmp_path: Path) -> None:
    if os.getenv("GITHUB_ACTIONS") != "true":
        pytest.skip("Real Keycloak integration is reserved for GitHub Actions CI")
    if engine.dialect.name != "sqlite":
        pytest.skip("Real Keycloak integration runs once in the SQLite backend contract")
    if shutil.which("docker") is None:
        pytest.fail("Docker is required for the GitHub Actions Keycloak integration contract")

    container_name = f"airlock-keycloak-{os.getpid()}"
    child_env = os.environ.copy()
    child_env.update(
        {
            "AIRLOCK_DATABASE_URL": f"sqlite:///{tmp_path / 'keycloak-oidc.db'}",
            "AIRLOCK_QUARANTINE_DIR": str(tmp_path / "quarantine"),
            "AIRLOCK_AUTO_CREATE_SCHEMA": "false",
            "AIRLOCK_KEYCLOAK_BASE_URL": f"http://127.0.0.1:{KEYCLOAK_PORT}",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )

    run_command = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-p",
        f"{KEYCLOAK_PORT}:8080",
        "-e",
        "KC_BOOTSTRAP_ADMIN_USERNAME=admin",
        "-e",
        "KC_BOOTSTRAP_ADMIN_PASSWORD=airlock-admin-ci",
        "-v",
        f"{REALM_PATH}:/opt/keycloak/data/import/airlock-ci-realm.json:ro",
        KEYCLOAK_IMAGE,
        "start-dev",
        "--import-realm",
    ]

    started = subprocess.run(
        run_command,
        cwd=REPOSITORY_ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if started.returncode != 0:
        pytest.fail(f"Keycloak container failed to start:\n{started.stderr}")

    try:
        integration = subprocess.run(
            [sys.executable, "../scripts/check_keycloak_oidc_integration.py"],
            cwd=BACKEND_ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        if integration.returncode != 0:
            logs = subprocess.run(
                ["docker", "logs", container_name],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            pytest.fail(
                "Real Keycloak OIDC integration failed.\n"
                f"stdout:\n{integration.stdout}\n"
                f"stderr:\n{integration.stderr}\n"
                f"Keycloak logs:\n{logs.stdout}\n{logs.stderr}"
            )
        assert "Keycloak OIDC integration verified" in integration.stdout
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
