"""Agent Mail authorization ownership, persisted isolation and API contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock

from octop.infra.connectors.gateway import agently_auth
from tests.support.auth import create_user


async def test_agently_auth_owner_routes_and_isolation(env_with_agent, monkeypatch):
    client, _, admin, _ = env_with_agent
    owner = await create_user(client, admin, username="mail-owner", permissions=[])
    stranger = await create_user(client, admin, username="mail-stranger", permissions=[])
    response = await client.post(
        "/api/connector-instances",
        headers=owner,
        json={
            "kind": "agently-cli",
            "display_name": "Mail",
            "credentials": {"cli_config_key": "victim"},
        },
    )
    assert response.status_code == 201, response.text
    instance_id = response.json()["instance_id"]
    base = f"/api/connector-instances/{instance_id}/agently-auth"
    result = {
        "status": "idle",
        "verification_url": None,
        "user_code": None,
        "expires_at": None,
        "error": None,
    }
    authorize = AsyncMock(return_value=result)
    monkeypatch.setattr(agently_auth, "authorize", authorize)
    for action in ("start", "status", "logout", "refresh"):
        method = client.get if action == "status" else client.post
        for headers in (stranger, admin):
            denied = await method(f"{base}/{action}", headers=headers)
            assert denied.status_code == 403
        assert authorize.await_count == 0
        allowed = await method(f"{base}/{action}", headers=owner)
        assert allowed.status_code == 200
        assert allowed.json() == result
        creds = authorize.await_args.args[0]
        assert creds["instance_id"] == instance_id
        assert creds["cli_config_key"] != "victim"
        original_key = creds["cli_config_key"]
        authorize.reset_mock()
    updated = await client.patch(
        f"/api/connector-instances/{instance_id}",
        headers=owner,
        json={"credentials": {"cli_config_key": "another-victim"}},
    )
    assert updated.status_code == 200
    await client.get(f"{base}/status", headers=owner)
    assert authorize.await_args.args[0]["cli_config_key"] == original_key
    authorize.reset_mock()
    deleted = await client.delete(f"/api/connector-instances/{instance_id}", headers=owner)
    assert deleted.status_code == 204
    assert authorize.await_args.args[1] == "disconnect"


async def test_agently_auth_rejects_missing_and_other_connector_kinds(env_with_agent, monkeypatch):
    client, _, auth, _ = env_with_agent
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={"kind": "tencent-docs", "display_name": "Docs", "credentials": {"token": "test"}},
    )
    instance_id = created.json()["instance_id"]
    authorize = AsyncMock()
    monkeypatch.setattr(agently_auth, "authorize", authorize)
    for action in ("start", "status", "logout", "refresh"):
        method = client.get if action == "status" else client.post
        wrong = await method(
            f"/api/connector-instances/{instance_id}/agently-auth/{action}", headers=auth
        )
        assert wrong.status_code == 400
        missing = await method(
            f"/api/connector-instances/missing/agently-auth/{action}", headers=auth
        )
        assert missing.status_code == 404
    authorize.assert_not_awaited()
