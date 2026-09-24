"""Exercise the five real SDK transports with a stored API Key."""

from __future__ import annotations

import json
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
    svc.encrypt_and_store(instance_id="grant", payload={"api_key": "qcc-api-key"})
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

    qcc.clear_metadata_cache()
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
    assert {auth for _, auth, _ in mcp_http} == {"Bearer qcc-api-key"}


@pytest.mark.asyncio
async def test_restart_restores_api_key(grant, mcp_http):
    pool, _, svc = grant
    creds = svc.decrypt("grant")
    stable_token = creds["internal_token"]
    creds["api_key"] = "rotated-key"
    svc.encrypt_and_store(instance_id="grant", payload=creds)
    restarted = service(SqlitePool(pool.path))
    assert restarted.decrypt("grant")["internal_token"] == stable_token
    assert restarted.decrypt("grant")["api_key"] == "rotated-key"
    result = await restarted.handle_qcc_request("grant", {"id": 1, "method": "tools/list"})
    assert len(result["result"]["tools"]) == 10
    assert {auth for _, auth, _ in mcp_http} == {"Bearer rotated-key"}


@pytest.mark.asyncio
async def test_delete_removes_card_and_gateway_access(grant, monkeypatch):
    _, repo, svc = grant
    token = svc.decrypt("grant")["internal_token"]
    repo.delete("grant")
    assert repo.get("grant") is None
    assert svc.verify_internal_token("grant", token) is None
    assert await svc.mcp_configs_for_user(1) == {}
    request = AsyncMock()
    monkeypatch.setattr(qcc, "request_resource", request)
    result = await svc.handle_qcc_request("grant", {"id": 1, "method": "tools/list"})
    assert "error" in result
    request.assert_not_awaited()


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
async def test_invalid_key_does_not_retry(grant, monkeypatch):
    _, _, svc = grant
    request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "secret-in-error",
            request=httpx.Request("POST", qcc.RESOURCES["risk"]),
            response=httpx.Response(401),
        )
    )
    monkeypatch.setattr(qcc, "request_resource", request)
    result = await svc.handle_qcc_request(
        "grant", {"id": 1, "method": "tools/call", "params": {"name": "risk__lookup"}}
    )
    assert "error" in result and "secret-in-error" not in json.dumps(result)
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_probe_reports_partial_failure(monkeypatch):
    async def request(resource, *args):
        if resource == "risk":
            raise ValueError("secret")
        return {"tools": [{"name": "lookup"}]}

    monkeypatch.setattr(qcc, "request_resource", request)
    result = await qcc.probe("synthetic-token")
    assert result["ok"] is True
    assert result["tool_count"] == 4
    assert result["servers"]["risk"] == {"ok": False}
    assert len(result["servers"]) == 5
    assert "secret" not in json.dumps(result)


def test_select_exposed_tools_prefers_known_suffixes():
    preferred = [
        {"name": "company__get_company_profile"},
        {"name": "company__lookup"},
        {"name": "company__get_change_records"},
    ]
    assert [tool["name"] for tool in qcc.select_exposed_tools(preferred)] == [
        "company__get_company_profile",
        "company__get_change_records",
    ]
    unknown = [{"name": "company__lookup"}, {"name": "company__detail"}]
    assert qcc.select_exposed_tools(unknown) == unknown


def test_bearer_token_prefers_api_key():
    assert qcc.bearer_token({"api_key": "k", "access_token": "legacy"}) == "k"
    assert qcc.bearer_token({"token": "t"}) == "t"
    assert qcc.bearer_token({}) == ""


@pytest.mark.asyncio
async def test_list_keeps_tools_when_one_resource_fails(grant, monkeypatch):
    _, _, svc = grant

    async def request(resource, *_args, **_kwargs):
        if resource == "risk":
            raise ValueError("denied")
        return {"tools": [{"name": "lookup"}]}

    monkeypatch.setattr(qcc, "request_resource", request)
    listed = await svc.handle_qcc_request("grant", {"id": 1, "method": "tools/list"})
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert "risk__lookup" not in names
    assert names == [f"{resource}__lookup" for resource in qcc.RESOURCES if resource != "risk"]


@pytest.mark.asyncio
async def test_resource_metadata_is_cached(mcp_http, monkeypatch):
    fetches: list[str] = []
    original = qcc.safe_request

    async def counted(method, url, **kwargs):
        fetches.append(url)
        return await original(method, url, **kwargs)

    monkeypatch.setattr(qcc, "safe_request", counted)
    await qcc.request_resource("risk", "old-access", "tools/list", {})
    await qcc.request_resource("risk", "old-access", "tools/list", {})
    assert len(fetches) == 1


@pytest.mark.asyncio
async def test_metadata_mismatch_blocks_bearer_transport(monkeypatch):
    qcc.clear_metadata_cache()
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
