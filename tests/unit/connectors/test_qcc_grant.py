"""Exercise the five real SDK transports with synthetic MCP HTTP responses."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from octop.config import OctopConfig
from octop.infra.connectors import qcc
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo


def service(pool: SqlitePool, repo: ConnectorRepo | None = None) -> ConnectorService:
    return ConnectorService(
        repo=repo or ConnectorRepo(pool),
        secret_repo=SecretRepo(pool),
        settings_repo=SettingsRepo(pool),
        config=OctopConfig(),
    )


@pytest.fixture
def grant(tmp_path: Path):
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    with pool.transaction() as conn:
        conn.execute(
            "INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'qcc-test','x','user',1)"
        )
    repo = ConnectorRepo(pool)
    repo.create(
        instance_id="grant", user_id=1, kind="qcc", display_name="QCC", mcp_server_name="qcc__grant"
    )
    svc = service(pool, repo)
    svc.encrypt_and_store(
        instance_id="grant",
        payload={
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "oauth_client_id": "public-client",
            "expires_at": int(time.time()) + 3600,
        },
    )
    return pool, repo, svc


@pytest.fixture
def mcp_http(monkeypatch: pytest.MonkeyPatch):
    calls = []
    client_class = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) in qcc.RESOURCES.values()
        body = json.loads(request.content)
        calls.append((str(request.url), request.headers["Authorization"], body))
        method = body["method"]
        if method.startswith("notifications/"):
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test", "version": "1"},
            }
        elif method == "tools/list":
            if body.get("params", {}).get("cursor") == "second":
                result = {"tools": [{"name": "detail", "inputSchema": {"type": "object"}}]}
            else:
                result = {
                    "tools": [{"name": "lookup", "inputSchema": {"type": "object"}}],
                    "nextCursor": "second",
                }
        else:
            assert method == "tools/call"
            assert body["params"]["name"] == "lookup"
            assert body["params"]["arguments"] == {"query": "example"}
            result = {"content": [{"type": "text", "text": request.url.path}], "isError": False}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return client_class(transport=httpx.MockTransport(handler), **kwargs)

    async def metadata(method, url, **kwargs):
        assert method == "GET"
        resource = url.split("/")[-2]
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"resource": qcc.RESOURCES[resource], "authorization_servers": [qcc.ISSUER]},
        )

    monkeypatch.setattr(qcc, "safe_request", metadata)
    monkeypatch.setattr(qcc.httpx, "AsyncClient", factory)
    return calls


@pytest.mark.asyncio
async def test_five_servers_list_paginate_and_call(grant, mcp_http):
    _, _, svc = grant
    listed = await svc.handle_qcc_request("grant", {"id": 1, "method": "tools/list"})
    names = [t["name"] for t in listed["result"]["tools"]]
    assert len(names) == len(set(names)) == 10
    for resource in qcc.RESOURCES:
        assert f"{resource}__detail" in names
        result = await svc.handle_qcc_request(
            "grant",
            {
                "id": 2,
                "method": "tools/call",
                "params": {"name": f"{resource}__lookup", "arguments": {"query": "example"}},
            },
        )
        assert result["result"]["content"][0]["text"] == f"/mcp/{resource}/stream"
    assert {url for url, _, _ in mcp_http} == set(qcc.RESOURCES.values())
    assert {auth for _, auth, _ in mcp_http} == {"Bearer old-access"}


@pytest.mark.asyncio
async def test_concurrent_refresh_across_service_instances(grant, monkeypatch):
    pool, repo, svc = grant
    creds = svc.decrypt("grant")
    creds["expires_at"] = 1
    svc.encrypt_and_store(instance_id="grant", payload=creds)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def refresh(**kwargs):
        assert kwargs["creds"]["refresh_token"] == "old-refresh"
        entered.set()
        await release.wait()
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": int(time.time()) + 3600,
        }

    mocked = AsyncMock(side_effect=refresh)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_oauth_credentials", mocked)
    tasks = [
        asyncio.create_task(service(pool, repo).ensure_fresh_credentials("grant", "qcc"))
        for _ in range(10)
    ]
    await entered.wait()
    release.set()
    results = await asyncio.gather(*tasks)
    assert mocked.await_count == 1
    assert all(r["access_token"] == "new-access" for r in results)
    assert svc.decrypt("grant")["refresh_token"] == "new-refresh"
    assert b"new-refresh" not in repo.get("grant").credential_blob


@pytest.mark.asyncio
async def test_restart_restores_rotated_grant(grant, mcp_http):
    pool, _, svc = grant
    creds = svc.decrypt("grant")
    stable_token = creds["internal_token"]
    creds.update(access_token="rotated-access", refresh_token="rotated-refresh")
    svc.encrypt_and_store(instance_id="grant", payload=creds)
    # Reopen the on-disk DB with new repositories and no in-memory OAuth state.
    restarted = service(SqlitePool(pool.path))
    assert restarted.decrypt("grant")["internal_token"] == stable_token
    assert restarted.decrypt("grant")["refresh_token"] == "rotated-refresh"
    result = await restarted.handle_qcc_request("grant", {"id": 1, "method": "tools/list"})
    assert len(result["result"]["tools"]) == 10
    assert {auth for _, auth, _ in mcp_http} == {"Bearer rotated-access"}


@pytest.mark.asyncio
async def test_disconnect_revokes_latest_refresh_and_removes_all_servers(grant, monkeypatch):
    _, repo, svc = grant
    token = svc.decrypt("grant")["internal_token"]
    revoke = AsyncMock()
    monkeypatch.setattr(qcc, "revoke", revoke)
    await svc.disconnect_qcc("grant")
    assert revoke.await_args.args[0]["refresh_token"] == "old-refresh"
    assert repo.get("grant") is None
    assert svc.verify_internal_token("grant", token) is None
    assert await svc.mcp_configs_for_user(1) == {}
    request = AsyncMock()
    monkeypatch.setattr(qcc, "request_resource", request)
    result = await svc.handle_qcc_request("grant", {"id": 1, "method": "tools/list"})
    assert "error" in result
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_revoke_keeps_grant_for_retry(grant, monkeypatch):
    _, repo, svc = grant
    monkeypatch.setattr(qcc, "revoke", AsyncMock(side_effect=ValueError("offline")))
    with pytest.raises(ValueError, match="retry disconnect"):
        await svc.disconnect_qcc("grant")
    assert repo.get("grant") is not None


@pytest.mark.asyncio
async def test_401_refreshes_once_and_retries(grant, monkeypatch):
    _, _, svc = grant
    exc = httpx.HTTPStatusError(
        "unauthorized",
        request=httpx.Request("POST", qcc.RESOURCES["risk"]),
        response=httpx.Response(401),
    )
    request = AsyncMock(side_effect=[exc, {"content": [], "isError": False}])
    refresh = AsyncMock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": int(time.time()) + 3600,
        }
    )
    monkeypatch.setattr(qcc, "request_resource", request)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_oauth_credentials", refresh)
    result = await svc.handle_qcc_request(
        "grant", {"id": 1, "method": "tools/call", "params": {"name": "risk__lookup"}}
    )
    assert "result" in result
    assert [c.args[1] for c in request.await_args_list] == ["old-access", "new-access"]
    assert refresh.await_count == 1


@pytest.mark.asyncio
async def test_unknown_resource_never_receives_token(grant, monkeypatch):
    _, _, svc = grant
    request = AsyncMock()
    monkeypatch.setattr(qcc, "request_resource", request)
    result = await svc.handle_qcc_request(
        "grant", {"id": 1, "method": "tools/call", "params": {"name": "evil__lookup"}}
    )
    assert "error" in result
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_disconnect_waits_for_rotation_without_resurrecting_grant(grant, monkeypatch):
    pool, repo, svc = grant
    creds = svc.decrypt("grant")
    creds["expires_at"] = 1
    svc.encrypt_and_store(instance_id="grant", payload=creds)
    entered, release = asyncio.Event(), asyncio.Event()

    async def refresh(**kwargs):
        entered.set()
        await release.wait()
        return {
            "access_token": "new",
            "refresh_token": "rotated",
            "expires_at": int(time.time()) + 3600,
        }

    monkeypatch.setattr("octop.infra.connectors.service.refresh_oauth_credentials", refresh)
    revoke = AsyncMock()
    monkeypatch.setattr(qcc, "revoke", revoke)
    rotating = asyncio.create_task(svc.ensure_fresh_credentials("grant", "qcc"))
    await entered.wait()
    deleting = asyncio.create_task(service(pool, repo).disconnect_qcc("grant"))
    await asyncio.sleep(0)
    revoke.assert_not_awaited()
    release.set()
    await asyncio.gather(rotating, deleting)
    assert revoke.await_args.args[0]["refresh_token"] == "rotated"
    assert repo.get("grant") is None
    assert await svc.ensure_fresh_credentials("grant", "qcc") == {}


@pytest.mark.asyncio
async def test_repeated_401_stops_after_one_retry(grant, monkeypatch):
    _, _, svc = grant
    exc = httpx.HTTPStatusError(
        "secret-in-error",
        request=httpx.Request("POST", qcc.RESOURCES["risk"]),
        response=httpx.Response(401),
    )
    request = AsyncMock(side_effect=exc)
    refresh = AsyncMock(return_value={"access_token": "new", "expires_at": int(time.time()) + 3600})
    monkeypatch.setattr(qcc, "request_resource", request)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_oauth_credentials", refresh)
    result = await svc.handle_qcc_request(
        "grant", {"id": 1, "method": "tools/call", "params": {"name": "risk__lookup"}}
    )
    assert "error" in result and "secret-in-error" not in json.dumps(result)
    assert request.await_count == 2
    assert refresh.await_count == 1


@pytest.mark.asyncio
async def test_probe_reports_partial_failure(monkeypatch):
    async def request(resource, *args):
        if resource == "risk":
            raise ValueError("secret")
        return {"tools": [{"name": "lookup"}]}

    monkeypatch.setattr(qcc, "request_resource", request)
    result = await qcc.probe("synthetic-token")
    assert result["ok"] is False
    assert result["tool_count"] == 4
    assert result["servers"]["risk"] == {"ok": False}
    assert len(result["servers"]) == 5
    assert "secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_revoke_discovers_validates_and_posts_refresh_token(monkeypatch):
    endpoint = qcc.ISSUER + "/oauth/revoke"
    metadata = AsyncMock(return_value={"revocation_endpoint": endpoint})
    validate = AsyncMock(return_value=endpoint)
    request = AsyncMock(return_value=httpx.Response(200, request=httpx.Request("POST", endpoint)))
    monkeypatch.setattr(qcc, "fetch_authorization_metadata", metadata)
    monkeypatch.setattr(qcc, "_ensure_mcp_oauth_url", validate)
    monkeypatch.setattr(qcc, "safe_request", request)
    await qcc.revoke({"refresh_token": "latest-refresh", "oauth_client_id": "client"})
    metadata.assert_awaited_once_with(qcc.ISSUER)
    validate.assert_awaited_once_with(endpoint, issuer=qcc.ISSUER, field="revocation_endpoint")
    assert request.await_args.kwargs["data"] == {
        "client_id": "client",
        "token": "latest-refresh",
        "token_type_hint": "refresh_token",
    }
    validate.side_effect = ValueError("untrusted endpoint")
    request.reset_mock()
    with pytest.raises(ValueError):
        await qcc.revoke({"refresh_token": "latest-refresh"})
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_mismatch_blocks_bearer_transport(monkeypatch):
    response = httpx.Response(
        200,
        request=httpx.Request("GET", qcc.ISSUER),
        json={"resource": "https://example.com/mcp", "authorization_servers": [qcc.ISSUER]},
    )
    monkeypatch.setattr(qcc, "safe_request", AsyncMock(return_value=response))
    transport = AsyncMock()
    monkeypatch.setattr(qcc, "streamable_http_client", transport)
    with pytest.raises(ValueError, match="metadata mismatch"):
        await qcc.request_resource("risk", "secret", "tools/list", {})
    transport.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_401_requests_share_rotated_token(grant, monkeypatch):
    pool, repo, _ = grant
    arrived = 0
    all_arrived = asyncio.Event()

    async def request(resource, token, method, params):
        nonlocal arrived
        if token == "old-access":
            arrived += 1
            if arrived == 5:
                all_arrived.set()
            await all_arrived.wait()
            raise httpx.HTTPStatusError(
                "expired",
                request=httpx.Request("POST", qcc.RESOURCES[resource]),
                response=httpx.Response(401),
            )
        assert token == "new-access"
        return {"content": []}

    refresh = AsyncMock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": int(time.time()) + 3600,
        }
    )
    monkeypatch.setattr(qcc, "request_resource", request)
    monkeypatch.setattr("octop.infra.connectors.service.refresh_oauth_credentials", refresh)
    results = await asyncio.gather(
        *(
            service(pool, repo)._qcc_request("grant", resource, "tools/call", {"name": "lookup"})
            for resource in qcc.RESOURCES
        )
    )
    assert all(result == {"content": []} for result in results)
    refresh.assert_awaited_once()
