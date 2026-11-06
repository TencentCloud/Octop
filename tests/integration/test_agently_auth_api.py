"""Agent Mail authorization ownership, persisted isolation and API contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from octop.infra.connectors.crypto import encrypt_credentials
from octop.infra.connectors.gateway import agently_auth
from octop.infra.connectors.gateway.adapters import dingtalk_cli
from tests.support.auth import create_user
from tests.support.fakes import fake_bin_path


@pytest.mark.parametrize("kind", ["agently-cli", "dingtalk-cli"])
async def test_agently_auth_owner_routes_and_isolation(env_with_agent, monkeypatch, kind):
    client, _, admin, _ = env_with_agent
    owner = await create_user(client, admin, username="mail-owner", permissions=[])
    stranger = await create_user(client, admin, username="mail-stranger", permissions=[])
    response = await client.post(
        "/api/connector-instances",
        headers=owner,
        json={
            "kind": kind,
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


async def test_dingtalk_cli_device_auth_and_delete_revokes(env_with_agent, monkeypatch):
    client, _, auth, _ = env_with_agent
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={"kind": "dingtalk-cli", "display_name": "DingTalk", "credentials": {}},
    )
    assert created.status_code == 201, created.text
    instance_id = created.json()["instance_id"]
    idle = {
        "status": "idle",
        "verification_url": None,
        "user_code": None,
        "expires_at": None,
        "error": None,
    }
    authorize = AsyncMock(return_value=idle)
    monkeypatch.setattr(agently_auth, "authorize", authorize)
    started = await client.post(
        f"/api/connector-instances/{instance_id}/agently-auth/start", headers=auth
    )
    assert started.status_code == 200
    assert authorize.await_args.kwargs["kind"] == "dingtalk-cli"
    deleted = await client.delete(f"/api/connector-instances/{instance_id}", headers=auth)
    assert deleted.status_code == 204
    assert authorize.await_args.args[1] == "disconnect"
    assert authorize.await_args.kwargs["kind"] == "dingtalk-cli"
    gone = await client.get(f"/api/connector-instances/{instance_id}", headers=auth)
    assert gone.status_code == 404


@pytest.mark.parametrize("legacy_keys", [("same", "same"), ("a/b", "a?b")])
async def test_dingtalk_legacy_keys_cannot_merge_instance_auth(
    env_with_agent, monkeypatch, legacy_keys
):
    client, server, admin, _ = env_with_agent
    authorize = AsyncMock(
        return_value={
            "status": "idle",
            "verification_url": None,
            "user_code": None,
            "expires_at": None,
            "error": None,
        }
    )
    monkeypatch.setattr(agently_auth, "authorize", authorize)
    keys = []
    for index, legacy_key in enumerate(legacy_keys):
        owner = await create_user(client, admin, username=f"ding-owner-{index}", permissions=[])
        created = await client.post(
            "/api/connector-instances",
            headers=owner,
            json={"kind": "dingtalk-cli", "display_name": "DingTalk", "credentials": {}},
        )
        assert created.status_code == 201, created.text
        instance_id = created.json()["instance_id"]
        # Model rows saved before the fix, including caller-selected/colliding keys.
        blob = encrypt_credentials(
            server.services.secret_repo,
            {"cli_config_key": legacy_key, "instance_id": "forged"},
        )
        server.services.repos.connector_repo.upsert_credentials(
            instance_id=instance_id, blob=blob, expires_at=None
        )
        status = await client.get(
            f"/api/connector-instances/{instance_id}/agently-auth/status", headers=owner
        )
        assert status.status_code == 200, status.text
        creds = authorize.await_args.args[0]
        assert creds["cli_config_key"] == creds["instance_id"] == instance_id
        keys.append(agently_auth._key("dingtalk-cli", creds))
    assert keys[0] != keys[1]


async def test_dingtalk_windows_reports_platform_and_allows_deletion(env_with_agent, monkeypatch):
    client, _, auth, _ = env_with_agent
    monkeypatch.setattr(dingtalk_cli, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(agently_auth, "resolve_binary", lambda _: fake_bin_path("dws"))
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={"kind": "dingtalk-cli", "display_name": "DingTalk", "credentials": {}},
    )
    assert created.status_code == 201, created.text
    instance_id = created.json()["instance_id"]
    base = f"/api/connector-instances/{instance_id}"
    for action in ("start", "status", "refresh", "logout"):
        method = client.get if action == "status" else client.post
        result = await method(f"{base}/agently-auth/{action}", headers=auth)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "error"
        assert "Windows" in result.json()["error"]
    deleted = await client.delete(base, headers=auth)
    assert deleted.status_code == 204, deleted.text
    assert (await client.get(base, headers=auth)).status_code == 404
