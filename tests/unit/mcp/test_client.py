from __future__ import annotations

import httpx
import pytest

from octop.mcp.client import OctopApiClient, OctopApiError


@pytest.mark.asyncio
async def test_status_uses_bearer_auth_and_accepts_sliding_renewal() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] in {"Bearer old-token", "Bearer new-token"}
        if request.url.path == "/api/health":
            return httpx.Response(
                200,
                json={"ok": True, "db": True},
                headers={"X-Octop-Access-Token": "new-token"},
            )
        return httpx.Response(
            200,
            json={"id": 7, "username": "alice", "role": "user", "permissions": []},
        )

    client = OctopApiClient(
        base_url="http://octop.test",
        token="old-token",
        transport=httpx.MockTransport(handler),
    )
    result = await client.get_status()

    assert result["ok"] is True
    assert result["user"]["username"] == "alice"
    assert client.token == "new-token"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_list_connectors_returns_only_safe_fields() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "instance_id": "custom:linear",
                    "kind": "custom-mcp",
                    "display_name": "Linear",
                    "status": "active",
                    "headers": {"Authorization": "Bearer must-not-leak"},
                    "credentials": {"token": "must-not-leak"},
                }
            ],
        )

    client = OctopApiClient(
        base_url="http://octop.test",
        token="token",
        transport=httpx.MockTransport(handler),
    )
    result = await client.list_connectors()

    assert result == [
        {
            "instance_id": "custom:linear",
            "kind": "custom-mcp",
            "display_name": "Linear",
            "status": "active",
        }
    ]
    assert "must-not-leak" not in repr(result)


@pytest.mark.asyncio
async def test_add_http_mcp_connector_preserves_existing_and_redacts_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "servers": {
                        "existing": {
                            "transport": "streamable_http",
                            "url": "https://existing.test/mcp",
                            "enabled": True,
                        }
                    }
                },
            )
        body = request.read().decode()
        assert '"existing"' in body
        assert '"linear"' in body
        return httpx.Response(
            200,
            json={
                "servers": {
                    "existing": {
                        "transport": "streamable_http",
                        "url": "https://existing.test/mcp",
                    },
                    "linear": {
                        "transport": "streamable_http",
                        "url": "https://linear.test/mcp",
                        "headers": {"Authorization": "Bearer must-not-leak"},
                        "enabled": True,
                    },
                }
            },
        )

    client = OctopApiClient(
        base_url="http://octop.test",
        token="token",
        transport=httpx.MockTransport(handler),
    )
    result = await client.add_http_mcp_connector(
        name="linear",
        url="https://linear.test/mcp",
        headers={"Authorization": "Bearer secret"},
    )

    assert result["name"] == "linear"
    assert result["has_headers"] is True
    assert "must-not-leak" not in repr(result)
    assert "secret" not in repr(result)
    assert [request.method for request in requests] == ["GET", "PUT"]


@pytest.mark.asyncio
async def test_add_rejects_duplicate_before_put() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json={"servers": {"linear": {}}})

    client = OctopApiClient(
        base_url="http://octop.test",
        token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ValueError, match="already exists"):
        await client.add_http_mcp_connector(name="linear", url="https://linear.test/mcp")
    assert methods == ["GET"]


@pytest.mark.asyncio
async def test_patch_and_delete_encode_server_name() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path.decode()))
        if request.method == "PATCH":
            return httpx.Response(
                200,
                json={
                    "servers": {
                        "my-server": {
                            "transport": "streamable_http",
                            "url": "https://example.test/mcp",
                            "enabled": False,
                        }
                    }
                },
            )
        return httpx.Response(204)

    client = OctopApiClient(
        base_url="http://octop.test",
        token="token",
        transport=httpx.MockTransport(handler),
    )
    patched = await client.patch_mcp_connector("my-server", enabled=False)
    deleted = await client.delete_mcp_connector("my-server")

    assert patched["enabled"] is False
    assert deleted["deleted"] is True
    assert seen == [
        ("PATCH", "/api/connectors/custom-mcp/servers/my-server"),
        ("DELETE", "/api/connector-instances/custom%3Amy-server"),
    ]


@pytest.mark.asyncio
async def test_api_error_preserves_octop_error_code() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"code": "FORBIDDEN", "message": "permission required"}},
        )

    client = OctopApiClient(
        base_url="http://octop.test",
        token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(OctopApiError, match="403 FORBIDDEN") as captured:
        await client.list_connectors()
    assert captured.value.code == "FORBIDDEN"
