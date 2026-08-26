from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REALM_PATH = Path(__file__).resolve().parents[2] / "infra" / "keycloak" / "airlock-ci-realm.json"


def _by_key(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item[key]): item for item in items}


def test_keycloak_realm_fixture_preserves_identity_contract() -> None:
    realm = json.loads(REALM_PATH.read_text(encoding="utf-8"))
    assert realm["realm"] == "airlock-ci"
    assert realm["enabled"] is True
    assert realm["sslRequired"] == "none"  # CI-only loopback provider.

    groups = {item["name"] for item in realm["groups"]}
    assert groups == {"airlock-researcher", "airlock-reviewer", "airlock-admin"}

    clients = _by_key(realm["clients"], "clientId")
    backend = clients["airlock-backend"]
    assert backend["publicClient"] is False
    assert backend["standardFlowEnabled"] is False
    assert backend["directAccessGrantsEnabled"] is True
    assert backend["secret"] == "${AIRLOCK_KC_CLIENT_SECRET}"
    assert clients["airlock-api"]["bearerOnly"] is True

    mappers = _by_key(backend["protocolMappers"], "name")
    assert mappers["airlock-groups"]["config"]["claim.name"] == "groups"
    assert mappers["airlock-groups"]["config"]["introspection.token.claim"] == "true"
    assert mappers["airlock-subject"]["config"]["claim.name"] == "airlock_subject"
    assert mappers["airlock-api-audience"]["config"]["included.client.audience"] == "airlock-api"
    assert (
        mappers["airlock-backend-audience"]["config"]["included.client.audience"]
        == "airlock-backend"
    )

    users = _by_key(realm["users"], "username")
    assert users["researcher-ci"]["groups"] == ["/airlock-researcher"]
    assert users["reviewer-ci"]["groups"] == ["/airlock-reviewer"]
    assert users["admin-ci"]["groups"] == ["/airlock-admin"]
    assert "groups" not in users["unmapped-ci"]

    expected_password_placeholders = {
        "researcher-ci": "${AIRLOCK_KC_RESEARCHER_PASSWORD}",
        "reviewer-ci": "${AIRLOCK_KC_REVIEWER_PASSWORD}",
        "admin-ci": "${AIRLOCK_KC_ADMIN_PASSWORD}",
        "unmapped-ci": "${AIRLOCK_KC_UNMAPPED_PASSWORD}",
    }
    for username, placeholder in expected_password_placeholders.items():
        user = users[username]
        assert user["email"] == f"{username}@example.invalid"
        assert user["firstName"]
        assert user["lastName"] == "CI"
        assert user["requiredActions"] == []
        assert user["credentials"] == [
            {"type": "password", "value": placeholder, "temporary": False}
        ]
