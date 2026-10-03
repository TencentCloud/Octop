"""Agent Mail authorization ownership, persisted isolation and API contracts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from octop.infra.connectors.gateway import agently_auth
from octop.infra.connectors.service import ConnectorService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout
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


async def test_agently_delete_failure_and_concurrent_login(env_with_agent, monkeypatch):
    client, server, auth, _ = env_with_agent
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={"kind": "agently-cli", "display_name": "Mail"},
    )
    instance_id = created.json()["instance_id"]
    repo = server.services.repos.connector_repo
    service = ConnectorService(
        repo=repo,
        secret_repo=server.services.secret_repo,
        settings_repo=server.services.settings_repo,
        config=server.services.config,
    )
    owner_id = repo.get(instance_id).user_id
    creds = service.decrypt(instance_id)
    directory = PathLayout.from_env().ensure_connector_cli_instance_dir(
        "agently-cli", creds["cli_config_key"]
    )
    attachment = directory / "attachment.txt"
    attachment.write_text("keep on failure", encoding="utf-8")
    monkeypatch.setattr(agently_auth, "_command", AsyncMock(side_effect=ValueError("fake failure")))
    failed = await client.delete(f"/api/connector-instances/{instance_id}", headers=auth)
    assert failed.status_code == 400
    assert repo.get(instance_id) is not None
    assert attachment.is_file()

    entered, release = asyncio.Event(), asyncio.Event()

    async def command(_creds, action):
        if action == "logout":
            entered.set()
            await release.wait()
        return {"logged_in": False}

    login = AsyncMock()
    monkeypatch.setattr(agently_auth, "_command", command)
    monkeypatch.setattr(agently_auth, "_login", login)
    deleting = asyncio.create_task(
        client.delete(f"/api/connector-instances/{instance_id}", headers=auth)
    )
    await asyncio.wait_for(entered.wait(), 5)
    starting = asyncio.create_task(
        service.agently_auth_for_instance(instance_id, owner_id, "start")
    )
    await asyncio.sleep(0)
    release.set()
    assert (await deleting).status_code == 204
    assert repo.get(instance_id) is None
    assert not directory.exists()
    with pytest.raises(OctopError) as error:
        await starting
    assert error.value.code == ErrorCode.CONNECTOR_NOT_FOUND
    login.assert_not_awaited()


async def test_agently_catalog_and_probe_follow_request_locale(env, monkeypatch):
    from octop.i18n import tr
    from octop.infra.connectors.gateway.adapters import agently_cli

    client, _, auth = env
    monkeypatch.setattr(agently_cli, "read_auth_status", lambda _: {"logged_in": False})
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={
            "kind": "agently-cli",
            "display_name": "Localized Mail",
            "credentials": {},
        },
    )
    instance_id = created.json()["instance_id"]
    for locale in ("en", "zh"):
        headers = {**auth, "Accept-Language": locale}
        catalog = (await client.get("/api/connectors/catalog", headers=headers)).json()
        entry = next(item for item in catalog if item["kind"] == "agently-cli")
        info = (await client.get("/api/connectors/auth/agently-cli/info", headers=headers)).json()
        assert entry["auth_hint"] == info["auth_hint"] == tr("connector.agently.auth_hint", locale)
        result = (
            await client.post(f"/api/connector-instances/{instance_id}/test", headers=headers)
        ).json()
        assert result == {"ok": False, "error": tr("connector.agently.login_required", locale)}
