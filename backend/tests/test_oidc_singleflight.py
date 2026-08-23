from __future__ import annotations

import json
import time as clock
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError, Event, Lock
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request

from fastapi import HTTPException

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


def configure_oidc(monkeypatch, *, cache_ttl: str = "15") -> None:  # type: ignore[no-untyped-def]
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
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_TTL_SECONDS", cache_ttl)
    monkeypatch.setenv("AIRLOCK_OIDC_CACHE_MAX_ENTRIES", "2048")


def active_claims(subject: str = "researcher-123") -> dict[str, object]:
    return {
        "active": True,
        "sub": subject,
        "aud": ["airlock-api"],
        "iss": "https://example.okta.test/oauth2/default",
        "exp": 4_102_444_800,
        "groups": ["airlock-reviewer"],
    }


def wait_for_joiners(expected_delta: int, baseline: int) -> None:
    deadline = clock.monotonic() + 2.0
    while clock.monotonic() < deadline:
        with auth.telemetry.lock:
            current = auth.telemetry.oidc_count["singleflight_join"]
        if current - baseline >= expected_delta:
            return
        clock.sleep(0.01)
    raise AssertionError(f"expected {expected_delta} single-flight joiners")


def actor_for(token: str) -> auth.Actor:
    return auth.get_actor(authorization=f"Bearer {token}")


def status_for(token: str) -> int:
    try:
        actor_for(token)
    except HTTPException as exc:
        return exc.status_code
    return 200


def test_concurrent_same_token_collapses_to_one_upstream_call(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    workers = 8
    start = Barrier(workers + 1)
    leader_entered = Event()
    release_upstream = Event()
    call_lock = Lock()
    calls = 0

    with auth.telemetry.lock:
        baseline_joiners = auth.telemetry.oidc_count["singleflight_join"]

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        with call_lock:
            calls += 1
        leader_entered.set()
        if not release_upstream.wait(timeout=2.0):
            raise TimeoutError("test did not release the upstream response")
        return FakeResponse(active_claims())

    def worker() -> auth.Actor:
        start.wait(timeout=2.0)
        return actor_for("shared-token")

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker) for _ in range(workers)]
        start.wait(timeout=2.0)
        assert leader_entered.wait(timeout=2.0)
        wait_for_joiners(workers - 1, baseline_joiners)
        release_upstream.set()
        actors = [future.result(timeout=2.0) for future in futures]

    assert calls == 1
    assert {actor.name for actor in actors} == {"researcher-123"}
    assert {actor.role for actor in actors} == {"reviewer"}
    assert len(auth._OIDC_INFLIGHT) == 0


def test_different_tokens_are_not_serialised_by_singleflight_lock(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    upstream_barrier = Barrier(2)
    call_lock = Lock()
    seen_tokens: list[str] = []

    def fake_urlopen(request: Request, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        token = parse_qs((request.data or b"").decode("ascii"))["token"][0]
        with call_lock:
            seen_tokens.append(token)
        try:
            upstream_barrier.wait(timeout=2.0)
        except BrokenBarrierError as exc:
            raise AssertionError("different tokens were serialised before reaching the IdP") from exc
        return FakeResponse(active_claims(subject=f"subject-{token}"))

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(actor_for, "token-a")
        second = pool.submit(actor_for, "token-b")
        actors = [first.result(timeout=3.0), second.result(timeout=3.0)]

    assert sorted(seen_tokens) == ["token-a", "token-b"]
    assert {actor.name for actor in actors} == {"subject-token-a", "subject-token-b"}


def test_concurrent_upstream_failure_is_shared_but_not_cached(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch)
    workers = 5
    start = Barrier(workers + 1)
    leader_entered = Event()
    release_upstream = Event()
    call_lock = Lock()
    calls = 0

    with auth.telemetry.lock:
        baseline_joiners = auth.telemetry.oidc_count["singleflight_join"]

    def unavailable(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        with call_lock:
            calls += 1
        leader_entered.set()
        if not release_upstream.wait(timeout=2.0):
            raise TimeoutError("test did not release the upstream failure")
        raise URLError("identity provider unavailable")

    def worker() -> int:
        start.wait(timeout=2.0)
        return status_for("failing-shared-token")

    monkeypatch.setattr(auth, "urlopen", unavailable)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker) for _ in range(workers)]
        start.wait(timeout=2.0)
        assert leader_entered.wait(timeout=2.0)
        wait_for_joiners(workers - 1, baseline_joiners)
        release_upstream.set()
        statuses = [future.result(timeout=2.0) for future in futures]

    assert statuses == [503] * workers
    assert calls == 1
    assert len(auth._OIDC_CACHE) == 0
    assert len(auth._OIDC_INFLIGHT) == 0

    assert status_for("failing-shared-token") == 503
    assert calls == 2


def test_disabled_cache_still_collapses_only_concurrent_requests(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    configure_oidc(monkeypatch, cache_ttl="0")
    workers = 4
    start = Barrier(workers + 1)
    leader_entered = Event()
    release_upstream = Event()
    call_lock = Lock()
    calls = 0

    with auth.telemetry.lock:
        baseline_joiners = auth.telemetry.oidc_count["singleflight_join"]

    def fake_urlopen(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        with call_lock:
            calls += 1
        leader_entered.set()
        if not release_upstream.wait(timeout=2.0):
            raise TimeoutError("test did not release the upstream response")
        return FakeResponse(active_claims())

    def worker() -> auth.Actor:
        start.wait(timeout=2.0)
        return actor_for("no-cache-concurrent-token")

    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker) for _ in range(workers)]
        start.wait(timeout=2.0)
        assert leader_entered.wait(timeout=2.0)
        wait_for_joiners(workers - 1, baseline_joiners)
        release_upstream.set()
        assert all(future.result(timeout=2.0).role == "reviewer" for future in futures)

    assert calls == 1
    assert len(auth._OIDC_CACHE) == 0

    assert actor_for("no-cache-concurrent-token").role == "reviewer"
    assert calls == 2
