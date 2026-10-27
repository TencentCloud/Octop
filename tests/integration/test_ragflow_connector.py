"""RAGFlow connector lifecycle through the existing HTTP and MCP surfaces."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from octop.api.routers.internal_mcp import _service
from octop.infra.connectors.gateway.adapters import ragflow
from octop.infra.server import OctopServer
from tests.support.auth import create_user


async def test_ragflow_credentials_edit_probe_and_authenticated_mcp(
    env_with_agent: tuple[httpx.AsyncClient, OctopServer, dict[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, server, auth, _ = env_with_agent
    credentials = {
        "base_url": "http://127.0.0.1:9380/",
        "api_key": "ragflow-synthetic-key",
        "dataset_ids": "ds-1,ds-1",
    }
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={"kind": "ragflow", "display_name": "团队 RAGFlow", "credentials": credentials},
    )
    assert created.status_code == 201, created.text
    instance_id = created.json()["instance_id"]
    path = f"/api/connector-instances/{instance_id}"
    detail = await client.get(path, headers=auth)
    assert detail.status_code == 200
    assert detail.json()["credentials_preview"] == {
        "base_url": "http://127.0.0.1:9380/api/v1",
        "api_key_configured": True,
        "dataset_ids": ["ds-1"],
    }
    assert "ragflow-synthetic-key" not in detail.text
    edited = await client.patch(path, headers=auth, json={"credentials": {"dataset_ids": "ds-2"}})
    assert edited.status_code == 200, edited.text
    service = _service(server)
    stored = service.decrypt(instance_id)
    assert stored["dataset_ids"] == ["ds-2"]
    assert stored["api_key"] == credentials["api_key"]
    calls: list[dict[str, Any]] = []

    def upstream(creds: dict[str, Any], method: str, resource: str, **kwargs: Any) -> Any:
        assert creds["api_key"] == credentials["api_key"]
        calls.append({"method": method, "path": resource, **kwargs})
        if resource == "/datasets":
            return [{"id": "ds-2", "name": "制度"}]
        assert resource == "/retrieval"
        assert kwargs["body"]["dataset_ids"] == ["ds-2"]
        return {
            "total": 1,
            "chunks": [
                {
                    "id": "c1",
                    "dataset_id": "ds-2",
                    "document_id": "doc-1",
                    "content": "请假规定",
                }
            ],
        }

    monkeypatch.setattr(ragflow, "_request", upstream)
    probe = await client.post(f"{path}/test", headers=auth)
    assert probe.status_code == 200
    assert probe.json()["ok"] is True
    assert probe.json()["tool_count"] == 3
    mcp_path = f"/api/internal/mcp/ragflow/{instance_id}"
    token = stored["internal_token"]
    rpc = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search",
            "arguments": {"query": "请假"},
        },
    }
    before = len(calls)
    denied = await client.post(mcp_path, params={"token": "wrong"}, json=rpc)
    assert denied.status_code == 401
    assert len(calls) == before
    response = await client.post(mcp_path, params={"token": token}, json=rpc)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"])["passages"][0]["document_id"] == "doc-1"
    other = await create_user(client, auth, username="ragflow_other")
    assert (await client.get(path, headers=other)).status_code == 403
    assert (await client.delete(path, headers=auth)).status_code == 204
    assert (await client.post(mcp_path, params={"token": token}, json=rpc)).status_code == 404


@pytest.mark.parametrize(("locale", "expected"), [("en", "HTTP 401"), ("zh", "请求失败")])
async def test_ragflow_probe_localizes_errors(
    env_with_agent: tuple[httpx.AsyncClient, OctopServer, dict[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    expected: str,
) -> None:
    client, _, auth, _ = env_with_agent
    original = httpx.Client

    def failing_client(**kwargs: Any) -> httpx.Client:
        return original(transport=httpx.MockTransport(lambda _: httpx.Response(401)), **kwargs)

    monkeypatch.setattr(ragflow.httpx, "Client", failing_client)
    result = await client.post(
        "/api/connectors/test-credentials",
        headers={**auth, "Accept-Language": locale},
        json={
            "kind": "ragflow",
            "credentials": {
                "base_url": "http://127.0.0.1:9380",
                "api_key": "invalid-test-key",
            },
        },
    )
    assert result.status_code == 200
    assert result.json()["ok"] is False
    assert expected in result.json()["error"]
    assert "invalid-test-key" not in result.text


@pytest.mark.parametrize(("locale", "label"), [("en", "Service URL"), ("zh", "服务地址")])
async def test_ragflow_catalog_is_visible_in_both_locales(
    env_with_agent: tuple[httpx.AsyncClient, OctopServer, dict[str, str], str],
    locale: str,
    label: str,
) -> None:
    client, _, auth, _ = env_with_agent
    response = await client.get(
        "/api/connectors/catalog", headers={**auth, "Accept-Language": locale}
    )
    entry = next(row for row in response.json() if row["kind"] == "ragflow")
    assert entry["phase"] == "available"
    assert entry["credential_fields"][0]["label"] == label
