"""Custom MCP credentials must stay live after a tool has been loaded."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from octop.config import OctopConfig
from octop.infra.connectors.custom_mcp import CUSTOM_MCP_KIND, shared_mcp_server_name
from octop.infra.connectors.mcp_tool_cache import fingerprint_mcp_spec
from octop.infra.connectors.oauth.mcp import OAuthRefreshRejected
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle
from octop.infra.errors import ErrorCode, OctopError

MCP_URL = "https://oa.example.com/mcp"


@pytest.fixture
def grant(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repos = RepoBundle.from_pool(pool)
    uid = repos.user_repo.create(username="owner", password_hash="x", role="user")
    svc = ConnectorService(
        repo=repos.connector_repo,
        secret_repo=repos.secret_repo,
        settings_repo=repos.settings_repo,
        config=OctopConfig(),
    )
    svc.put_custom_servers(
        uid,
        {"oa": {"transport": "streamable_http", "url": MCP_URL, "headers": {"X-OA": "kept"}}},
    )
    authorize(svc, uid)
    yield svc, uid, repos
    pool.close()


def authorize(svc, uid, *, token="old-access", expires_at=None):
    svc.apply_custom_server_oauth(
        uid,
        "oa",
        {
            "access_token": token,
            "refresh_token": "old-refresh",
            "expires_at": int(time.time()) + 3600 if expires_at is None else expires_at,
            "oauth_client_id": "client",
        },
        issuer="https://oa.example.com",
        resource=MCP_URL,
    )


def refreshed(oauth):
    return {
        **oauth,
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_at": int(time.time()) + 3600,
    }


async def test_loaded_connection_refreshes_before_request(grant, monkeypatch):
    svc, uid, _ = grant
    connection = svc.custom_harness_configs(uid)["oa"]
    # Expire the grant after the connection has already been handed to a tool.
    authorize(svc, uid, expires_at=1)
    refresh = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers["Authorization"])
        assert request.headers["X-OA"] == "kept"
        return httpx.Response(200 if seen[-1] == "Bearer new-access" else 401)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        headers=connection.get("headers"),
        auth=connection.get("auth"),
    ) as client:
        response = await client.post(MCP_URL, json={"method": "tools/call"})

    assert response.status_code == 200
    assert seen == ["Bearer new-access"]
    refresh.assert_awaited_once()
    assert svc.get_custom_servers(uid)["oa"]["oauth"]["refresh_token"] == "new-refresh"


def client_for(connection, handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=connection.get("headers"),
        auth=connection.get("auth"),
    )


@pytest.mark.parametrize("status", [200, 401, 403, 500])
async def test_only_401_refreshes_and_retries_once(grant, monkeypatch, status):
    svc, uid, _ = grant
    refresh = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append((request.headers["Authorization"], request.content))
        return httpx.Response(status)

    async with client_for(svc.custom_harness_configs(uid)["oa"], handle) as client:
        response = await client.post(MCP_URL, json={"method": "tools/call"})
    assert response.status_code == status
    if status == 401:
        assert refresh.await_count == 1
        assert [header for header, _ in seen] == ["Bearer old-access", "Bearer new-access"]
        assert seen[0][1] == seen[1][1]
        assert svc.get_custom_servers_for_api(uid)["oa"]["oauth"] == {
            "configured": False,
            "required": True,
        }
    else:
        assert len(seen) == 1
        refresh.assert_not_awaited()
        assert svc.get_custom_servers_for_api(uid)["oa"]["oauth"]["configured"] is True


async def test_401_can_recover_without_reloading_connection(grant, monkeypatch):
    svc, uid, _ = grant
    refresh = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(401 if seen[-1] == "Bearer old-access" else 200)

    async with client_for(svc.custom_harness_configs(uid)["oa"], handle) as client:
        assert (await client.post(MCP_URL)).status_code == 200
        # The same client also observes a subsequent interactive re-authorization.
        authorize(svc, uid, token="reauthorized")
        assert (await client.post(MCP_URL)).status_code == 200
    assert seen == ["Bearer old-access", "Bearer new-access", "Bearer reauthorized"]
    refresh.assert_awaited_once()


async def test_concurrent_401_responses_reuse_one_rotated_token(grant, monkeypatch):
    svc, uid, _ = grant
    refresh = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    old_requests = 0
    all_rejected = asyncio.Event()

    async def handle(request):
        nonlocal old_requests
        if request.headers["Authorization"] == "Bearer old-access":
            old_requests += 1
            if old_requests == 4:
                all_rejected.set()
            await all_rejected.wait()
            return httpx.Response(401)
        assert request.headers["Authorization"] == "Bearer new-access"
        return httpx.Response(200)

    async with client_for(svc.custom_harness_configs(uid)["oa"], handle) as client:
        responses = await asyncio.wait_for(
            asyncio.gather(*(client.post(MCP_URL) for _ in range(4))), timeout=5
        )
    assert all(response.status_code == 200 for response in responses)
    refresh.assert_awaited_once()


async def test_unknown_expiry_refreshes_on_401_not_on_every_request(grant, monkeypatch):
    svc, uid, _ = grant
    servers = svc.get_custom_servers(uid)
    servers["oa"]["oauth"].pop("expires_at")
    svc._save_custom_servers(uid, servers)
    refresh = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(401 if len(seen) == 2 else 200)

    async with client_for(svc.custom_harness_configs(uid)["oa"], handle) as client:
        assert (await client.post(MCP_URL)).status_code == 200
        refresh.assert_not_awaited()
        assert (await client.post(MCP_URL)).status_code == 200
    assert seen == ["Bearer old-access", "Bearer old-access", "Bearer new-access"]
    refresh.assert_awaited_once()


@pytest.mark.parametrize("failure", [ValueError("offline"), OAuthRefreshRejected("revoked")])
async def test_refresh_failure_marks_reauth_only_when_grant_unusable(grant, monkeypatch, failure):
    svc, uid, _ = grant
    authorize(svc, uid, expires_at=int(time.time()) + 60)
    refresh = AsyncMock(side_effect=failure)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200)

    async with client_for(svc.custom_harness_configs(uid)["oa"], handle) as client:
        if isinstance(failure, OAuthRefreshRejected):
            with pytest.raises(OctopError) as exc:
                await client.post(MCP_URL)
            assert exc.value.code == ErrorCode.CONNECTOR_INVALID_CREDENTIALS
            assert seen == []
            assert svc.get_custom_servers_for_api(uid)["oa"]["oauth"]["required"] is True
        else:
            assert (await client.post(MCP_URL)).status_code == 200
            assert seen == ["Bearer old-access"]
            assert svc.get_custom_servers_for_api(uid)["oa"]["oauth"]["configured"] is True


@pytest.mark.parametrize("has_refresh", [False, True])
async def test_expired_grant_requires_reauth_and_same_connection_recovers(
    grant, monkeypatch, has_refresh
):
    svc, uid, _ = grant
    connection = svc.custom_harness_configs(uid)["oa"]
    authorize(svc, uid, expires_at=1)
    if not has_refresh:
        servers = svc.get_custom_servers(uid)
        servers["oa"]["oauth"].pop("refresh_token")
        svc._save_custom_servers(uid, servers)
    refresh = AsyncMock(side_effect=ValueError("offline"))
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200)

    async with client_for(connection, handle) as client:
        with pytest.raises(OctopError):
            await client.post(MCP_URL)
        assert seen == []
        assert svc.get_custom_servers_for_api(uid)["oa"]["oauth"] == {
            "configured": False,
            "required": True,
        }
        authorize(svc, uid, token="reauthorized")
        assert (await client.post(MCP_URL)).status_code == 200
    assert seen == ["Bearer reauthorized"]
    assert refresh.await_count == int(has_refresh)


async def test_shared_grant_concurrent_refresh_is_serialized_and_encrypted(grant, monkeypatch):
    svc, uid, repos = grant
    viewer = repos.user_repo.create(username="viewer", password_hash="x", role="user")
    svc.patch_custom_server(uid, "oa", shared=True)
    authorize(svc, uid, expires_at=1)
    parent = repos.connector_repo.get_by_user_kind(uid, CUSTOM_MCP_KIND)
    shared_name = shared_mcp_server_name(parent.instance_id, "oa")
    second_svc = ConnectorService(
        repo=repos.connector_repo,
        secret_repo=repos.secret_repo,
        settings_repo=repos.settings_repo,
        config=OctopConfig(),
    )

    async def renew(oauth):
        await asyncio.sleep(0)
        return refreshed(oauth)

    refresh = AsyncMock(side_effect=renew)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200)

    async with (
        client_for(svc.custom_harness_configs(uid)["oa"], handle) as owner_client,
        client_for(second_svc.custom_harness_configs(viewer)[shared_name], handle) as shared_client,
    ):
        await asyncio.gather(
            *[client.post(MCP_URL) for client in [owner_client, shared_client] * 4]
        )
        assert refresh.await_count == 1
        assert seen == ["Bearer new-access"] * 8
        svc.patch_custom_server(uid, "oa", shared=False)
        with pytest.raises(OctopError) as exc:
            await shared_client.post(MCP_URL)
        assert exc.value.code == ErrorCode.FORBIDDEN
    assert len(seen) == 8
    assert svc.get_custom_servers(uid)["oa"]["oauth"]["refresh_token"] == "new-refresh"
    assert b"new-refresh" not in repos.connector_repo.get(parent.instance_id).credential_blob


async def test_refresh_preserves_edits_and_newer_grants(grant, monkeypatch):
    svc, uid, _ = grant
    authorize(svc, uid, expires_at=1)

    async def renew(oauth):
        servers = svc.get_custom_servers(uid)
        servers["oa"]["display_name"] = "Renamed while refreshing"
        servers["other"] = {"transport": "stdio", "command": "example"}
        svc.put_custom_servers(uid, servers)
        authorize(svc, uid, token="reauthorized")
        return refreshed(oauth)

    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", renew)
    await svc.ensure_fresh_custom_servers(uid)
    stored = svc.get_custom_servers(uid)
    assert stored["oa"]["oauth"]["access_token"] == "reauthorized"
    assert stored["oa"]["display_name"] == "Renamed while refreshing"
    assert "other" in stored


async def test_refresh_does_not_restore_a_removed_server(grant, monkeypatch):
    svc, uid, _ = grant
    connection = svc.custom_harness_configs(uid)["oa"]
    authorize(svc, uid, expires_at=1)

    async def renew(oauth):
        svc.put_custom_servers(uid, {})
        return refreshed(oauth)

    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", renew)
    handler = AsyncMock(return_value=httpx.Response(200))
    async with client_for(connection, handler) as client:
        with pytest.raises(OctopError):
            await client.post(MCP_URL)
    handler.assert_not_awaited()
    assert svc.get_custom_servers(uid) == {}


@pytest.mark.parametrize("change", ["disable", "delete", "url"])
async def test_cached_oauth_connection_honors_configuration_changes(grant, change):
    svc, uid, _ = grant
    connection = svc.custom_harness_configs(uid)["oa"]
    servers = svc.get_custom_servers(uid)
    if change == "disable":
        servers["oa"]["enabled"] = False
    elif change == "delete":
        servers.clear()
    else:
        servers["oa"]["url"] = "https://other.example.com/mcp"
    svc.put_custom_servers(uid, servers)
    handler = AsyncMock(return_value=httpx.Response(200))
    async with client_for(connection, handler) as client:
        with pytest.raises(OctopError):
            await client.post(MCP_URL)
    handler.assert_not_awaited()


@pytest.mark.parametrize("oauth_hint", [False, True])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer fixed"}, {"X-API-Key": "fixed"}])
async def test_non_oauth_connections_keep_existing_behavior(
    grant, monkeypatch, headers, oauth_hint
):
    svc, uid, _ = grant
    svc.put_custom_servers(uid, {})
    svc.put_custom_servers(
        uid,
        {
            "oa": {"transport": "streamable_http", "url": MCP_URL, "headers": headers},
            "stdio": {"transport": "stdio", "command": "example", "args": ["--flag"]},
        },
    )
    svc.note_custom_server_oauth_required(uid, "oa", required=oauth_hint)
    configs = svc.custom_harness_configs(uid)
    assert "auth" not in configs["oa"]
    assert configs["stdio"] == {"transport": "stdio", "command": "example", "args": ["--flag"]}
    refresh = AsyncMock()
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    seen = []

    def handle(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(401)

    async with client_for(configs["oa"], handle) as client:
        assert (await client.post(MCP_URL)).status_code == 401
    assert seen == [headers.get("Authorization")]
    refresh.assert_not_awaited()


async def test_actual_cached_mcp_tool_uses_refreshed_credentials(grant, monkeypatch, tmp_path):
    from octop.infra.agents.manager import AgentManager

    svc, uid, _ = grant
    seen = []

    def handle(request):
        if request.method != "POST":
            return httpx.Response(405)
        body = json.loads(request.content)
        method = body["method"]
        seen.append((method, request.headers["Authorization"]))
        if method.startswith("notifications/"):
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "oa", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "employees",
                        "description": "List employees",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        else:
            assert method == "tools/call"
            result = {"content": [{"type": "text", "text": "employee list"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)

    connection = svc.custom_harness_configs(uid)["oa"]
    connection["httpx_client_factory"] = factory
    mgr = object.__new__(AgentManager)
    mgr._mcp_tool_cache = {}
    mgr._mcp_tool_cache_locks = {}
    mgr._mcp_tool_cache_guard = asyncio.Lock()
    mgr._paths = SimpleNamespace(root=tmp_path)
    tools = await mgr._get_or_load_mcp_tools(uid, "oa", connection)
    assert len(tools) == 1
    assert tools[0].name == "oa_employees"
    assert ("tools/list", "Bearer old-access") in seen

    authorize(svc, uid, expires_at=1)
    refresh = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_custom_mcp_oauth", refresh)
    assert "employee list" in str(await tools[0].ainvoke({}))
    assert ("tools/call", "Bearer new-access") in seen
    requests_after_call = list(seen)
    assert await mgr._get_or_load_mcp_tools(uid, "oa", connection) is tools
    assert seen == requests_after_call
    refresh.assert_awaited_once()
    assert fingerprint_mcp_spec(connection) == fingerprint_mcp_spec(
        svc.custom_harness_configs(uid)["oa"]
    )


@pytest.mark.parametrize(
    ("status", "body", "rejected"),
    [
        (400, {"error": "invalid_grant"}, True),
        (401, {"error": "invalid_client"}, True),
        (400, {"error": "unauthorized_client"}, True),
        (503, {"error": "temporarily_unavailable"}, False),
        (400, [], False),
    ],
)
async def test_refresh_grant_rejection_is_distinct_from_transient_failure(
    monkeypatch, status, body, rejected
):
    from octop.infra.connectors.oauth import mcp

    token_url = "https://oa.example.com/token"
    response = httpx.Response(status, json=body, request=httpx.Request("POST", token_url))
    monkeypatch.setattr(mcp, "_ensure_mcp_oauth_url", AsyncMock(return_value=token_url))
    monkeypatch.setattr(mcp, "safe_request", AsyncMock(return_value=response))
    with pytest.raises(ValueError) as exc:
        await mcp.refresh_access_token(
            {"token_endpoint": token_url},
            issuer="https://oa.example.com",
            client_id="client",
            client_secret=None,
            refresh_token="old-refresh",
            resource=MCP_URL,
        )
    assert isinstance(exc.value, OAuthRefreshRejected) is rejected
    assert "old-refresh" not in str(exc.value)
