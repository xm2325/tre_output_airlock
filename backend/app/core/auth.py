from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, status

Role = Literal["researcher", "reviewer", "admin"]


@dataclass(frozen=True)
class Actor:
    name: str
    role: Role


def get_actor(
    user: Annotated[str, Header(alias="X-Demo-User")] = "xiaomei-demo",
    role: Annotated[str, Header(alias="X-Demo-Role")] = "reviewer",
) -> Actor:
    normalised_role = role.strip().lower()
    if normalised_role not in {"researcher", "reviewer", "admin"}:
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
    return Actor(name=normalised_user, role=normalised_role)  # type: ignore[arg-type]


def require_roles(*allowed: Role) -> Callable[..., Actor]:
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(allowed)}.",
            )
        return actor

    return dependency
