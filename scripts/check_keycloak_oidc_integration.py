from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = os.getenv("AIRLOCK_KEYCLOAK_BASE_URL", "http://127.0.0.1:18080").rstrip("/")
REALM = "airlock-ci"
CLIENT_ID = "airlock-api"
CLIENT_SECRET = "airlock-ci-secret"
TOKEN_URL = f"{BASE_URL}/realms/{REALM}/protocol/openid-connect/token"
INTROSPECTION_URL = f"{TOKEN_URL}/introspect"
ISSUER = f"{BASE_URL}/realms/{REALM}"

# Configure the application before importing modules that materialise runtime settings.
os.environ["AIRLOCK_DATABASE_URL"] = "sqlite:////tmp/airlock-keycloak-integration.db"
os.environ["AIRLOCK_QUARANTINE_DIR"] = "/tmp/airlock-keycloak-integration-quarantine"
os.environ["AIRLOCK_AUTO_CREATE_SCHEMA"] = "true"
os.environ["AIRLOCK_AUTH_MODE"] = "oidc_introspection"
os.environ["AIRLOCK_OIDC_INTROSPECTION_URL"] = INTROSPECTION_URL
os.environ["AIRLOCK_OIDC_CLIENT_ID"] = CLIENT_ID
os.environ["AIRLOCK_OIDC_CLIENT_SECRET"] = CLIENT_SECRET
os.environ["AIRLOCK_OIDC_ROLE_CLAIM"] = "groups"
os.environ["AIRLOCK_OIDC_SUBJECT_CLAIM"] = "username"
os.environ["AIRLOCK_OIDC_EXPECTED_ISSUER"] = ISSUER
os.environ["AIRLOCK_OIDC_CACHE_TTL_SECONDS"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import _clear_oidc_cache  # noqa: E402
from app.main import app  # noqa: E402


def _post_form(url: str, values: dict[str, str]) -> dict[str, object]:
    request = Request(
        url,
        data=urlencode(values).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310 - pinned local CI IdP
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Keycloak returned a non-object token response")
    return payload


def _password_token(username: str, password: str) -> str:
    payload = _post_form(
        TOKEN_URL,
        {
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username": username,
            "password": password,
        },
    )
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Keycloak issued no access token for {username}: {payload}")
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    Path("/tmp/airlock-keycloak-integration.db").unlink(missing_ok=True)
    _clear_oidc_cache()

    credentials = {
        "researcher-ci": ("researcher-pass", "researcher"),
        "reviewer-ci": ("reviewer-pass", "reviewer"),
        "admin-ci": ("admin-pass", "admin"),
    }
    tokens = {
        username: _password_token(username, password)
        for username, (password, _) in credentials.items()
    }

    with TestClient(app) as client:
        for username, (_, expected_role) in credentials.items():
            response = client.get("/api/v1/me", headers=_bearer(tokens[username]))
            assert response.status_code == 200, response.text
            assert response.json() == {"name": username, "role": expected_role}

        researcher_queue = client.get(
            "/api/v1/review-queue",
            headers=_bearer(tokens["researcher-ci"]),
        )
        assert researcher_queue.status_code == 403, researcher_queue.text

        for username in ("reviewer-ci", "admin-ci"):
            queue = client.get("/api/v1/review-queue", headers=_bearer(tokens[username]))
            assert queue.status_code == 200, queue.text
            assert queue.json() == []

        inactive = client.get("/api/v1/me", headers=_bearer("not-a-real-keycloak-token"))
        assert inactive.status_code == 401, inactive.text

        missing = client.get("/api/v1/me")
        assert missing.status_code == 401, missing.text

    print(
        "Keycloak OIDC integration verified: password grants -> real token introspection -> "
        "Airlock actor mapping -> reviewer/admin RBAC with researcher denial"
    )


if __name__ == "__main__":
    main()
