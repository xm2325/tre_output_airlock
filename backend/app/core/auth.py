from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from time import time
from typing import Annotated, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import Depends, Header, HTTPException, status

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
    role_map: Mapping[str, Role]


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


def _load_oidc_settings() -> OidcIntrospectionSettings:
    introspection_url = os.getenv("AIRLOCK_OIDC_INTROSPECTION_URL", "").strip()
    client_id = os.getenv("AIRLOCK_OIDC_CLIENT_ID", "").strip()
    client_secret = os.getenv("AIRLOCK_OIDC_CLIENT_SECRET", "").strip()
    if not introspection_url or not client_id or not client_secret:
        raise ValueError(
            "OIDC introspection mode requires AIRLOCK_OIDC_INTROSPECTION_URL, "
            "AIRLOCK_OIDC_CLIENT_ID and AIRLOCK_OIDC_CLIENT_SECRET"
        )

    timeout_raw = os.getenv("AIRLOCK_OIDC_TIMEOUT_SECONDS", "3.0").strip()
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise ValueError("AIRLOCK_OIDC_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("AIRLOCK_OIDC_TIMEOUT_SECONDS must be in (0, 30]")

    return OidcIntrospectionSettings(
        introspection_url=introspection_url,
        client_id=client_id,
        client_secret=client_secret,
        role_claim=os.getenv("AIRLOCK_OIDC_ROLE_CLAIM", "groups").strip() or "groups",
        subject_claim=os.getenv("AIRLOCK_OIDC_SUBJECT_CLAIM", "sub").strip() or "sub",
        expected_audience=os.getenv("AIRLOCK_OIDC_EXPECTED_AUDIENCE") or None,
        expected_issuer=os.getenv("AIRLOCK_OIDC_EXPECTED_ISSUER") or None,
        timeout_seconds=timeout_seconds,
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


def _actor_from_introspection_claims(
    claims: Mapping[str, object],
    config: OidcIntrospectionSettings,
) -> Actor:
    if claims.get("active") is not True:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Bearer token is inactive.")

    expiry = claims.get("exp")
    if expiry is not None:
        try:
            if float(expiry) <= time():
                raise _http_error(status.HTTP_401_UNAUTHORIZED, "Bearer token has expired.")
        except (TypeError, ValueError) as exc:
            raise _http_error(
                status.HTTP_401_UNAUTHORIZED,
                "Token expiry claim is invalid.",
            ) from exc

    _validate_expected_claim(claims, "aud", config.expected_audience)
    _validate_expected_claim(claims, "iss", config.expected_issuer)

    subject = str(claims.get(config.subject_claim, "")).strip()
    if len(subject) < 2 or len(subject) > 200:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "Token subject claim is invalid.")

    return Actor(name=subject, role=_select_role(claims, config))


def _introspect_token(token: str, config: OidcIntrospectionSettings) -> Actor:
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
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Identity provider introspection is unavailable.",
        ) from exc

    if not isinstance(payload, dict):
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Identity provider returned an invalid introspection response.",
        )
    return _actor_from_introspection_claims(payload, config)


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
    return _introspect_token(token, config)


def require_roles(*allowed: Role) -> Callable[..., Actor]:
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(allowed)}.",
            )
        return actor

    return dependency
