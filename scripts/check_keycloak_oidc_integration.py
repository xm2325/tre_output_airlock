from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi.testclient import TestClient

from app.core.auth import _clear_oidc_cache
from app.db import Base, engine
from app.main import app

KEYCLOAK_BASE_URL = os.getenv("AIRLOCK_KEYCLOAK_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
REALM = "airlock-ci"
CLIENT_ID = "airlock-backend"
CLIENT_SECRET = "airlock-ci-secret"
ISSUER = f"{KEYCLOAK_BASE_URL}/realms/{REALM}"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    request = Request(
        url,
        data=urlencode(data).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed CI IdP endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"Expected JSON object from {url}")
    return payload


def _wait_for_keycloak() -> None:
    discovery_url = f"{ISSUER}/.well-known/openid-configuration"
    last_error: Exception | None = None
    for _ in range(60):
        try:
            with urlopen(discovery_url, timeout=2) as response:  # noqa: S310 - fixed CI IdP endpoint
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            # Keycloak can accept then reset connections while its first start-dev
            # build/import is still completing. Treat that as not-ready, not fatal.
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"Keycloak did not become ready: {last_error}")


def _token(username: str, password: str) -> str:
    payload = _post_form(
        TOKEN_URL,
        {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": "openid",
        },
    )
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise AssertionError(f"No access token returned for {username}: {payload}")
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_identity(client: TestClient, token: str, username: str, role: str) -> None:
    response = client.get("/api/v1/me", headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert response.json() == {"name": username, "role": role}


def main() -> None:
    _wait_for_keycloak()

    os.environ["AIRLOCK_AUTH_MODE"] = "oidc_introspection"
    os.environ["AIRLOCK_OIDC_INTROSPECTION_URL"] = f"{ISSUER}/protocol/openid-connect/token/introspect"
    os.environ["AIRLOCK_OIDC_CLIENT_ID"] = CLIENT_ID
    os.environ["AIRLOCK_OIDC_CLIENT_SECRET"] = CLIENT_SECRET
    os.environ["AIRLOCK_OIDC_ROLE_CLAIM"] = "groups"
    os.environ["AIRLOCK_OIDC_SUBJECT_CLAIM"] = "airlock_subject"
    os.environ["AIRLOCK_OIDC_EXPECTED_AUDIENCE"] = "airlock-api"
    os.environ["AIRLOCK_OIDC_EXPECTED_ISSUER"] = ISSUER
    os.environ["AIRLOCK_OIDC_CACHE_TTL_SECONDS"] = "0"
    _clear_oidc_cache()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    researcher = _token("researcher-ci", "researcher-pass")
    reviewer = _token("reviewer-ci", "reviewer-pass")
    admin = _token("admin-ci", "admin-pass")
    unmapped = _token("unmapped-ci", "unmapped-pass")

    with TestClient(app) as client:
        _assert_identity(client, researcher, "researcher-ci", "researcher")
        _assert_identity(client, reviewer, "reviewer-ci", "reviewer")
        _assert_identity(client, admin, "admin-ci", "admin")

        denied = client.get("/api/v1/review-queue", headers=_bearer(researcher))
        assert denied.status_code == 403, denied.text

        reviewer_queue = client.get("/api/v1/review-queue", headers=_bearer(reviewer))
        assert reviewer_queue.status_code == 200, reviewer_queue.text
        assert reviewer_queue.json() == []

        admin_queue = client.get("/api/v1/review-queue", headers=_bearer(admin))
        assert admin_queue.status_code == 200, admin_queue.text
        assert admin_queue.json() == []

        no_role = client.get("/api/v1/me", headers=_bearer(unmapped))
        assert no_role.status_code == 403, no_role.text

        inactive = client.get("/api/v1/me", headers=_bearer("not-a-keycloak-token"))
        assert inactive.status_code == 401, inactive.text

        os.environ["AIRLOCK_OIDC_EXPECTED_AUDIENCE"] = "wrong-audience"
        _clear_oidc_cache()
        wrong_audience = client.get("/api/v1/me", headers=_bearer(reviewer))
        assert wrong_audience.status_code == 401, wrong_audience.text

        os.environ["AIRLOCK_OIDC_EXPECTED_AUDIENCE"] = "airlock-api"
        os.environ["AIRLOCK_OIDC_EXPECTED_ISSUER"] = f"{KEYCLOAK_BASE_URL}/realms/wrong-realm"
        _clear_oidc_cache()
        wrong_issuer = client.get("/api/v1/me", headers=_bearer(reviewer))
        assert wrong_issuer.status_code == 401, wrong_issuer.text

    print(
        "Keycloak OIDC integration verified: real password grants -> RFC7662 introspection -> "
        "issuer/audience validation -> group role mapping -> FastAPI authorization"
    )


if __name__ == "__main__":
    main()
