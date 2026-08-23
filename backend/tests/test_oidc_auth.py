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
    monkeypatch.setenv("AIRLOCK_OIDC_ROLE_CLAIM", "groups")
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_TTL_SECONDS", "15")
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_MAX_ENTRIES", "2048")


def active_claims(groups: list[str], *, exp: float = 4_102_444_800) -> dict[str, object]:
    return {
        "active": True,
        "sub": "researcher-123",
        "aud": ["airlock-api"],
        "iss": "https://example.okta.test/oauth2/default",
        "exp": exp,
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


def test_oidc_cache_reuses_only_successful_active_token(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    calls = 0

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse(active_claims(["airlock-reviewer"]))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    headers = {"Authorization": "Bearer cacheable-token"}

    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert calls == 1
    assert all("cacheable-token" not in key for key in auth._OIDC_CACHE)


def test_oidc_cache_ttl_expiry_rechecks_idp(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    clock = [1_000.0]
    calls = 0
    monkeypatch.setattr(auth, "time", lambda: clock[0])

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse(active_claims(["airlock-reviewer"], exp=2_000.0))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    headers = {"Authorization": "Bearer ttl-token"}

    assert client.get("/api/v1/me", headers=headers).status_code == 200
    clock[0] = 1_014.0
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert calls == 1

    clock[0] = 1_016.0
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert calls == 2


def test_oidc_cache_never_outlives_token_expiry(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    clock = [1_000.0]
    calls = 0
    monkeypatch.setattr(auth, "time", lambda: clock[0])

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse(active_claims(["airlock-researcher"], exp=1_005.0))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    headers = {"Authorization": "Bearer short-lived-token"}

    assert client.get("/api/v1/me", headers=headers).status_code == 200
    clock[0] = 1_004.0
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert calls == 1

    clock[0] = 1_006.0
    expired = client.get("/api/v1/me", headers=headers)
    assert expired.status_code == 401
    assert calls == 2


def test_oidc_cache_is_bounded_and_evicts_least_recently_used_entry(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_MAX_ENTRIES", "2")
    calls = 0

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse(active_claims(["airlock-reviewer"]))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    for token in ("token-one", "token-two", "token-three"):
        response = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    assert len(auth._OIDC_CACHE) == 2
    assert client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer token-one"},
    ).status_code == 200
    assert calls == 4


def test_inactive_oidc_token_is_not_cached(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    calls = 0

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse({"active": False})

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    headers = {"Authorization": "Bearer inactive-token"}

    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert calls == 2
    assert len(auth._OIDC_CACHE) == 0


def test_oidc_cache_can_be_disabled(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_TTL_SECONDS", "0")
    calls = 0

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse(active_claims(["airlock-reviewer"]))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    headers = {"Authorization": "Bearer no-cache-token"}

    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert calls == 2


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


def test_oidc_upstream_failure_is_503_and_is_not_cached(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    calls = 0

    def unavailable(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise URLError("identity provider unavailable")

    monkeypatch.setattr(auth, "urlopen", unavailable)
    headers = {"Authorization": "Bearer upstream-failure-token"}
    assert client.get("/api/v1/me", headers=headers).status_code == 503
    assert client.get("/api/v1/me", headers=headers).status_code == 503
    assert calls == 2


def test_oidc_configuration_failure_is_503(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    auth._clear_oidc_cache()
    monkeypatch.setenv("AIRLOCK_AUTH_MODE", "oidc_introspection")
    monkeypatch.delenv("AIRLOCK_OIDC_INTROSPECTION_URL", raising=False)
    monkeypatch.delenv("AIRLOCK_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRLOCK_OIDC_CLIENT_SECRET", raising=False)

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 503


def test_oidc_cache_ttl_above_security_cap_is_rejected(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_TTL_SECONDS", "61")

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 503
    assert "60" in response.json()["detail"]
