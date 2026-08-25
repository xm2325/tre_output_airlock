from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_introspection_audience(payload: dict[str, object]) -> None:
    clients = payload.get("clients")
    if not isinstance(clients, list):
        raise RuntimeError("Keycloak CI realm must contain a clients list")
    for client in clients:
        if not isinstance(client, dict) or client.get("clientId") != "airlock-api":
            continue
        mappers = client.setdefault("protocolMappers", [])
        if not isinstance(mappers, list):
            raise RuntimeError("airlock-api protocolMappers must be a list")
        if any(isinstance(item, dict) and item.get("name") == "airlock-api-audience" for item in mappers):
            return
        mappers.append(
            {
                "name": "airlock-api-audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {
                    "included.client.audience": "airlock-api",
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                    "introspection.token.claim": "true",
                },
            }
        )
        return
    raise RuntimeError("Keycloak CI realm is missing the airlock-api client")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare_realm.py <realm-json>")
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Keycloak CI realm must be a JSON object")
    users = payload.get("users")
    if not isinstance(users, list):
        raise RuntimeError("Keycloak CI realm must contain a users list")

    for item in users:
        if not isinstance(item, dict):
            raise RuntimeError("Keycloak CI realm user must be an object")
        username = item.get("username")
        if not isinstance(username, str) or not username:
            raise RuntimeError("Keycloak CI realm user must have a username")
        label = username.removesuffix("-ci").replace("-", " ").title() or "Airlock"
        item["firstName"] = label
        item["lastName"] = "CI"
        item["email"] = f"{username}@example.invalid"
        item["emailVerified"] = True
        item["requiredActions"] = []

    _ensure_introspection_audience(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"normalised {len(users)} Keycloak CI users and access-token audience")


if __name__ == "__main__":
    main()
