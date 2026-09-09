from __future__ import annotations

from typing import Any

import pytest

from octop.mcp.server import build_mcp_server


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def _call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((operation, args, kwargs))
        if operation == "list_connectors":
            return []
        return {"ok": True, "name": operation}

    async def get_status(self) -> dict[str, Any]:
        return await self._call("get_status")

    async def list_connectors(self) -> list[dict[str, Any]]:
        return await self._call("list_connectors")

    async def add_http_mcp_connector(self, **kwargs: Any) -> dict[str, Any]:
        return await self._call("add_http_mcp_connector", **kwargs)

    async def patch_mcp_connector(self, name: str, **kwargs: Any) -> dict[str, Any]:
        return await self._call("patch_mcp_connector", name, **kwargs)

    async def test_mcp_connector(self, name: str) -> dict[str, Any]:
        return await self._call("test_mcp_connector", name)

    async def delete_mcp_connector(self, name: str) -> dict[str, Any]:
        return await self._call("delete_mcp_connector", name)


@pytest.mark.asyncio
async def test_server_exposes_connector_tools_and_annotations() -> None:
    server = build_mcp_server(FakeClient())  # type: ignore[arg-type]
    tools = {tool.name: tool for tool in await server.list_tools()}

    assert set(tools) == {
        "octop_get_status",
        "octop_list_connectors",
        "octop_add_mcp_connector",
        "octop_configure_mcp_connector",
        "octop_test_mcp_connector",
        "octop_delete_mcp_connector",
    }
    assert tools["octop_get_status"].annotations.readOnlyHint is True
    assert tools["octop_add_mcp_connector"].annotations.openWorldHint is True
    assert tools["octop_delete_mcp_connector"].annotations.destructiveHint is True
    assert tools["octop_test_mcp_connector"].annotations.readOnlyHint is False
    assert tools["octop_test_mcp_connector"].annotations.openWorldHint is True


@pytest.mark.asyncio
async def test_add_tool_forwards_connector_configuration() -> None:
    client = FakeClient()
    server = build_mcp_server(client)  # type: ignore[arg-type]

    _content, structured = await server.call_tool(
        "octop_add_mcp_connector",
        {
            "name": "linear",
            "url": "https://linear.test/mcp",
            "display_name": "Linear",
            "default_open": True,
        },
    )

    assert structured == {"ok": True, "name": "add_http_mcp_connector"}
    assert client.calls[-1] == (
        "add_http_mcp_connector",
        (),
        {
            "name": "linear",
            "url": "https://linear.test/mcp",
            "display_name": "Linear",
            "headers": None,
            "enabled": True,
            "default_open": True,
            "shared": False,
        },
    )


@pytest.mark.asyncio
async def test_configure_requires_at_least_one_setting() -> None:
    server = build_mcp_server(FakeClient())  # type: ignore[arg-type]
    with pytest.raises(Exception, match="at least one connector setting"):
        await server.call_tool("octop_configure_mcp_connector", {"name": "linear"})
