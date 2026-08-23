from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from threading import Lock
from time import perf_counter, time
from typing import Annotated, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import Depends, Header, HTTPException, status

from app.core.telemetry import telemetry

Role = Literal["researcher", "reviewer", "admin"]
_SUPPORTED_ROLES: frozenset[str] = frozenset({"researcher", "reviewer", "admin"})
_ROLE_PRECEDENCE: tuple[Role, ...] = ("admin", "reviewer", "researcher")


@dataclass(frozen=True)
class Actor:
    name: str
    role: Role


@dataclass(frozen=True)
class OidcIntrospectionSettings:
    introspection_url: str
    client_id: str
    client_secret: str
    role_claim: str
    subject_claim: str
    expected_audience: str | None
    expected_issuer: str | None
    timeout_seconds: float
    cache_ttl_seconds: float
    cache_max_entries: int
    role_map: Mapping[str, Role]


@dataclass(frozen=True)
class CachedActor:
    actor: Actor
    expires_at: float


_OIDC_CACHE: OrderedDict[str, CachedActor] = OrderedDict()
_OIDC_CACHE_LOCK = Lock()


def _http_error(status_code: int, detail: str) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return HTTPException(status_code=status_code, detail=detail, headers=headers)


def _parse_role_map(raw: str) -> dict[str, Role]:
    mapping: dict[str, Role] = {
        "researcher": "researcher",
        "reviewer": "reviewer",
        "admin": "admin",
        "airlock-researcher": "researcher",
        "airlock-reviewer": "reviewer",
        "airlock-admin": "admin",
    }
    if not raw.strip():
        return mapping

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            source, target = (part.strip() for part in item.split(":", 1))
        except ValueError as exc:
            raise ValueError("AIRLOCK_OIDC_ROLE_MAP entries must use source:role syntax") from exc
        if not source or target not in _SUPPORTED_ROLES:
            raise ValueError("AIRLOCK_OIDC_ROLE_MAP contains an unsupported role mapping")
        mapping[source] = cast(Role, target)
    return mapping


def _parse_float_setting(name: str, default: str, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def _parse_int_setting(name: str, default: str, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _load_oidc_settings() -> OidcIntrospectionSettings:
    introspection_url = os.getenv("AIRLOCK_OIDC_INTROSPECTION_URL", "").strip()
    client_id = os.getenv("AIRLOCK_OIDC_CLIENT_ID", "").strip()
    client_secret = os.getenv("AIRLOCK_OIDC_CLIENT_SECRET", "").strip()
    if not introspection_url or not client_id or not client_secret:
        raise ValueError(
            "OIDC introspection mode requires AIRLOCK_OIDC_INTROSPECTION_URL, "
            "AIRLOCK_OIDC_CLIENT_ID and AIRLOCK_OIDC_CLIENT_SECRET"
        )

    timeout_seconds = _parse_float_setting(
        "AIRLOCK_OIDC_TIMEOUT_SECONDS",
        "3.0",
        minimum=0.1,
        maximum=30.0,
    )
    cache_ttl_seconds = _parse_float_setting(
        "AIRLOCK_OIDC_CACHE_TTL_SECONDS",
        "15.0",
        minimum=0.0,
        maximum=60.0,
    )
    cache_max_entries = _parse_int_setting(
        "AIRLOCK_OIDC_CACHE_MAX_ENTRIES",
        "2048",
        minimum=1,
        maximum=10000,
    )

    return OidcIntrospectionSettings(
        introspection_url=introspection_url,
        client_id=client_id,
        client_secret=client_secret,
        role_claim=os.getenv("AIRLOCK_OIDC_ROLE_CLAIM", "groups").strip() or "groups",
        subject_claim=os.getenv("AIRLOCK_OIDC_SUBJECT_CLAIM", "sub").strip() or "sub",
        expected_audience=os.getenv("AIRLOCK_OIDC_EXPECTED_AUDIENCE") or None,
        expected_issuer=os.getenv("AIRLOCK_OIDC_EXPECTED_ISSUER") or None,
        timeout_seconds=timeout_seconds,
        cache_ttl_seconds=cache_ttl_seconds,
        cache_max_entries=cache_max_entries,
        role_map=_parse_role_map(os.getenv("AIRLOCK_OIDC_ROLE_MAP", "")),
    )


def _normalise_claim_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item for item in value.replace(",", " ").split() if item)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _select_role(claims: Mapping[str, object], config: OidcIntrospectionSettings) -> Role:
    external_roles = _normalise_claim_values(claims.get(config.role_claim))
    mapped_roles = {config.role_map[item] for item in external_roles if item in config.role_map}
    for candidate in _ROLE_PRECEDENCE:
        if candidate in mapped_roles:
            return candidate
    raise _http_error(status.HTTP_403_FORBIDDEN, "Authenticated identity has no Airlock role.")


def _validate_expected_claim(
    claims: Mapping[str, object],
    claim_name: str,
    expected: str | None,
) -> None:
    if expected is None:
        return
    values = _normalise_claim_values(claims.get(claim_name))
    if expected not in values:
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED,
            f"Token {claim_name} claim is not accepted.",
        )


def _parse_token_expiry(claims: Mapping[str, object]) -> float | None:
    expiry = claims.get("exp")
    if expiry is None:
        return None
    if not isinstance(expiry, (int, float, str)):
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Token expiry claim is invalid.")
    try:
        parsed = float(expiry)
    except ValueError as exc:
        raise _http_error(
            status.HTTP_401_UNAUTHORIZED,
            "Token expiry claim is invalid.",
        ) from exc
    if not math.isfinite(parsed):
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Token expiry claim is invalid.")
    if parsed <= time():
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Bearer token has expired.")
    return parsed


def _actor_from_introspection_claims(
    claims: Mapping[str, object],
    config: OidcIntrospectionSettings,
) -> tuple[Actor, float | None]:
    if claims.get("active") is not True:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Bearer token is inactive.")

    token_expiry = _parse_token_expiry(claims)
    _validate_expected_claim(claims, "aud", config.expected_audience)
    _validate_expected_claim(claims, "iss", config.expected_issuer)

    subject = str(claims.get(config.subject_claim, "")).strip()
    if len(subject) < 2 or len(subject) > 200:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Token subject claim is invalid.")

    return Actor(name=subject, role=_select_role(claims, config)), token_expiry


def _cache_key(token: str, config: OidcIntrospectionSettings) -> str:
    contract = json.dumps(
        {
            "aud": config.expected_audience,
            "client_id": config.client_id,
            "iss": config.expected_issuer,
            "role_claim": config.role_claim,
            "role_map": sorted(config.role_map.items()),
            "subject_claim": config.subject_claim,
            "url": config.introspection_url,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    message = f"{contract}\0{token}".encode()
    return hmac.new(config.client_secret.encode(), message, hashlib.sha256).hexdigest()


def _get_cached_actor(token: str, config: OidcIntrospectionSettings) -> Actor | None:
    if config.cache_ttl_seconds == 0:
        telemetry.record_oidc("cache_disabled")
        return None

    key = _cache_key(token, config)
    now = time()
    with _OIDC_CACHE_LOCK:
        cached = _OIDC_CACHE.get(key)
        if cached is None:
            telemetry.record_oidc("cache_miss")
            return None
        if cached.expires_at <= now:
            del _OIDC_CACHE[key]
            telemetry.record_oidc("cache_expired")
            return None
        _OIDC_CACHE.move_to_end(key)
    telemetry.record_oidc("cache_hit")
    return cached.actor


def _store_cached_actor(
    token: str,
    actor: Actor,
    token_expiry: float | None,
    config: OidcIntrospectionSettings,
) -> None:
    if config.cache_ttl_seconds == 0:
        return

    now = time()
    expires_at = now + config.cache_ttl_seconds
    if token_expiry is not None:
        expires_at = min(expires_at, token_expiry)
    if expires_at <= now:
        return

    key = _cache_key(token, config)
    with _OIDC_CACHE_LOCK:
        _OIDC_CACHE[key] = CachedActor(actor=actor, expires_at=expires_at)
        _OIDC_CACHE.move_to_end(key)
        while len(_OIDC_CACHE) > config.cache_max_entries:
            _OIDC_CACHE.popitem(last=False)


def _clear_oidc_cache() -> None:
    with _OIDC_CACHE_LOCK:
        _OIDC_CACHE.clear()


def _introspect_token(token: str, config: OidcIntrospectionSettings) -> tuple[Actor, float | None]:
    credentials = base64.b64encode(
        f"{config.client_id}:{config.client_secret}".encode()
    ).decode("ascii")
    request = Request(
        config.introspection_url,
        data=urlencode({"token": token, "token_type_hint": "access_token"}).encode("ascii"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    started = perf_counter()
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        telemetry.record_oidc("upstream_error", (perf_counter() - started) * 1000)
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Identity provider introspection is unavailable.",
        ) from exc

    if not isinstance(payload, dict):
        telemetry.record_oidc("upstream_invalid", (perf_counter() - started) * 1000)
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Identity provider returned an invalid introspection response.",
        )

    actor, token_expiry = _actor_from_introspection_claims(payload, config)
    telemetry.record_oidc("upstream_success", (perf_counter() - started) * 1000)
    return actor, token_expiry


def _demo_actor(user: str, role: str) -> Actor:
    normalised_role = role.strip().lower()
    if normalised_role not in _SUPPORTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Demo-Role must be researcher, reviewer or admin.",
        )
    normalised_user = user.strip()
    if len(normalised_user) < 2 or len(normalised_user) > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Demo-User must contain between 2 and 120 characters.",
        )
    return Actor(name=normalised_user, role=cast(Role, normalised_role))


def get_actor(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    user: Annotated[str, Header(alias="X-Demo-User")] = "xiaomei-demo",
    role: Annotated[str, Header(alias="X-Demo-Role")] = "reviewer",
) -> Actor:
    mode = os.getenv("AIRLOCK_AUTH_MODE", "demo").strip().lower()
    if mode == "demo":
        return _demo_actor(user, role)
    if mode != "oidc_introspection":
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AIRLOCK_AUTH_MODE must be demo or oidc_introspection.",
        )

    if authorization is None or not authorization.lower().startswith("bearer "):
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "A bearer token is required.")
    token = authorization[7:].strip()
    if not token:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "A bearer token is required.")

    try:
        config = _load_oidc_settings()
    except ValueError as exc:
        raise _http_error(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    cached_actor = _get_cached_actor(token, config)
    if cached_actor is not None:
        return cached_actor

    actor, token_expiry = _introspect_token(token, config)
    _store_cached_actor(token, actor, token_expiry, config)
    return actor


def require_roles(*allowed: Role) -> Callable[..., Actor]:
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(allowed)}.",
            )
        return actor

    return dependency
