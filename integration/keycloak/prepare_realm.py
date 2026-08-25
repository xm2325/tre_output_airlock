from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare_realm.py <realm-json>")
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text(encoding="utf-8"))
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

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"normalised {len(users)} Keycloak CI user profiles")


if __name__ == "__main__":
    main()
