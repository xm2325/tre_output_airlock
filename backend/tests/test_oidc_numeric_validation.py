from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.core.auth as auth


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def configure_oidc(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    auth._clear_oidc_cache()
    monkeypatch.setenv("AIRLOCK_AUTH_MODE", "oidc_introspection")
    monkeypatch.setenv(
        "AIRLOCK_OIDC_INTROSPECTION_URL",
        "https://example.okta.test/oauth2/default/v1/introspect",
    )
    monkeypatch.setenv("AIRLOCK_OIDC_CLIENT_ID", "airlock-api")
    monkeypatch.setenv("AIRLOCK_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AIRLOCK_OIDC_EXPECTED_AUDIENCE", "airlock-api")
    monkeypatch.setenv("AIRLOCK_OIDC_EXPECTED_ISSUER", "https://example.okta.test/oauth2/default")


def valid_claims(expiry: object) -> dict[str, object]:
    return {
        "active": True,
        "sub": "researcher-123",
        "aud": ["airlock-api"],
        "iss": "https://example.okta.test/oauth2/default",
        "exp": expiry,
        "groups": ["airlock-reviewer"],
    }


def test_non_finite_cache_ttl_is_rejected(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_TTL_SECONDS", "nan")

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 503
    assert "AIRLOCK_OIDC_CACHE_TTL_SECONDS" in response.json()["detail"]


def test_non_finite_token_expiry_is_rejected(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setattr(
        auth,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(valid_claims("inf")),
    )

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer invalid-expiry-token"},
    )

    assert response.status_code == 401
    assert "expiry claim is invalid" in response.json()["detail"].lower()
    assert len(auth._OIDC_CACHE) == 0
