"""Persistent MCP state, task ownership and resource access."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from octop_harness import ManagedMCPClient


@pytest.mark.asyncio
async def test_stateful_stdio_session_resources_and_close() -> None:
    client = ManagedMCPClient(
        {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(Path(__file__).parent / "fixtures" / "stateful_mcp.py")],
        }
    )
    async with client:
        tools = await client.get_tools()
        assert {t.name for t in tools.tools} == {"collect", "confirm"}
        await asyncio.create_task(client.call_tool("collect", {"title": "demo"}))
        result = await asyncio.create_task(client.call_tool("confirm", {}))
        assert not result.isError
        assert result.structuredContent == {"title": "demo"}
        resources = await client.list_resources()
        assert str(resources.resources[0].uri) == "memory://brief"
        resource = await client.read_resource("memory://brief")
        assert resource.contents[0].text == "demo"
    await client.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        await client.get_tools()


@pytest.mark.asyncio
async def test_start_failure_is_reported_and_closes() -> None:
    client = ManagedMCPClient({"transport": "stdio", "command": sys.executable, "args": ["-c", "pass"]})
    try:
        with pytest.raises(BaseExceptionGroup):
            await client.get_tools()
    finally:
        await client.aclose()
