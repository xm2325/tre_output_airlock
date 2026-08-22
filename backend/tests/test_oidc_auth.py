from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request

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
    monkeypatch.setenv("AIRLOCK_AUTH_MODE", "oidc_introspection")
    monkeypatch.setenv(
        "AIRLOCK_OIDC_INTROSPECTION_URL",
        "https://example.okta.test/oauth2/default/v1/introspect",
    )
    monkeypatch.setenv("AIRLOCK_OIDC_CLIENT_ID", "airlock-api")
    monkeypatch.setenv("AIRLOCK_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("AIRLOCK_OIDC_EXPECTED_AUDIENCE", "airlock-api")
    monkeypatch.setenv("AIRLOCK_OIDC_EXPECTED_ISSUER", "https://example.okta.test/oauth2/default")
    monkeypatch.setenv("AIRLOCK_OIDC_ROLE_CLAIM", "groups")


def active_claims(groups: list[str]) -> dict[str, object]:
    return {
        "active": True,
        "sub": "researcher-123",
        "aud": ["airlock-api"],
        "iss": "https://example.okta.test/oauth2/default",
        "exp": 4_102_444_800,
        "groups": groups,
    }


def test_oidc_introspection_maps_idp_group_to_airlock_role(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = parse_qs((request.data or b"").decode("ascii"))
        return FakeResponse(active_claims(["airlock-reviewer"]))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"name": "researcher-123", "role": "reviewer"}
    assert captured["url"] == "https://example.okta.test/oauth2/default/v1/introspect"
    assert captured["timeout"] == 3.0
    assert str(captured["authorization"]).startswith("Basic ")
    assert captured["body"] == {
        "token": ["valid-access-token"],
        "token_type_hint": ["access_token"],
    }


def test_oidc_mode_requires_bearer_token(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_inactive_oidc_token_is_401(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setattr(auth, "urlopen", lambda *_args, **_kwargs: FakeResponse({"active": False}))

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer inactive-token"},
    )
    assert response.status_code == 401


def test_authenticated_identity_without_airlock_role_is_403(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setattr(
        auth,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(active_claims(["unrelated-group"])),
    )

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 403


def test_oidc_audience_is_checked(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    claims = active_claims(["airlock-researcher"])
    claims["aud"] = ["different-api"]
    monkeypatch.setattr(auth, "urlopen", lambda *_args, **_kwargs: FakeResponse(claims))

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer wrong-audience-token"},
    )
    assert response.status_code == 401


def test_oidc_upstream_failure_is_503(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)

    def unavailable(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise URLError("identity provider unavailable")

    monkeypatch.setattr(auth, "urlopen", unavailable)
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 503


def test_oidc_configuration_failure_is_503(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AIRLOCK_AUTH_MODE", "oidc_introspection")
    monkeypatch.delenv("AIRLOCK_OIDC_INTROSPECTION_URL", raising=False)
    monkeypatch.delenv("AIRLOCK_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRLOCK_OIDC_CLIENT_SECRET", raising=False)

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 503
