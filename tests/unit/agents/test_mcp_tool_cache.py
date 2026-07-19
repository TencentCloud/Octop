"""Unit tests for custom MCP deferred load + user-level tool cache."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from octop.infra.connectors.mcp_tool_cache import (
    fingerprint_mcp_spec,
    wrap_tools_for_shared_use,
)


def test_fingerprint_stable_and_ignores_enabled() -> None:
    a = fingerprint_mcp_spec(
        {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "pkg"],
            "enabled": True,
        }
    )
    b = fingerprint_mcp_spec(
        {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "pkg"],
            "enabled": False,
        }
    )
    assert a == b
    c = fingerprint_mcp_spec(
        {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "other"],
        }
    )
    assert a != c


@pytest.mark.asyncio
async def test_wrap_tools_serialize_ainvoke() -> None:
    order: list[str] = []

    class _FakeTool:
        name = "demo_tool"
        description = "demo"
        args_schema = None

        async def ainvoke(self, *_a: Any, **_k: Any) -> str:
            order.append("start")
            await asyncio.sleep(0.05)
            order.append("end")
            return "ok"

        def invoke(self, *_a: Any, **_k: Any) -> str:
            return "ok"

    lock = asyncio.Lock()
    wrapped = wrap_tools_for_shared_use([_FakeTool()], lock)
    assert len(wrapped) == 1
    assert isinstance(wrapped[0], BaseTool)
    assert isinstance(wrapped[0], StructuredTool)

    async def _call() -> Any:
        return await wrapped[0].ainvoke({})

    await asyncio.gather(_call(), _call())
    assert order == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_get_or_load_caches_and_reuses() -> None:
    from octop.infra.agents.manager import AgentManager

    mgr = object.__new__(AgentManager)
    mgr._mcp_tool_cache = {}
    mgr._mcp_tool_cache_locks = {}
    mgr._mcp_tool_cache_guard = asyncio.Lock()

    fake = MagicMock()
    fake.name = "s_tool1"
    fake.description = "t"
    fake.args_schema = None
    fake.metadata = None
    fake.ainvoke = AsyncMock(return_value="ok")
    aload = AsyncMock(return_value=[fake])

    spec = {"transport": "stdio", "command": "npx", "args": []}
    with patch("harness_agent.mcp.aload_mcp_tools", aload):
        first = await mgr._get_or_load_mcp_tools(1, "s", spec)
        second = await mgr._get_or_load_mcp_tools(1, "s", spec)

    assert aload.await_count == 1
    assert first is second
    assert isinstance(first[0], StructuredTool)
    assert first[0].name == "s_tool1"


@pytest.mark.asyncio
async def test_get_or_load_misses_on_fingerprint_change() -> None:
    from octop.infra.agents.manager import AgentManager

    mgr = object.__new__(AgentManager)
    mgr._mcp_tool_cache = {}
    mgr._mcp_tool_cache_locks = {}
    mgr._mcp_tool_cache_guard = asyncio.Lock()

    def _tool(name: str) -> MagicMock:
        t = MagicMock()
        t.name = name
        t.description = "t"
        t.args_schema = None
        t.metadata = None
        t.ainvoke = AsyncMock(return_value="ok")
        return t

    aload = AsyncMock(side_effect=[[_tool("s_a")], [_tool("s_b")]])

    with patch("harness_agent.mcp.aload_mcp_tools", aload):
        a = await mgr._get_or_load_mcp_tools(
            1, "s", {"transport": "stdio", "command": "npx", "args": ["a"]}
        )
        b = await mgr._get_or_load_mcp_tools(
            1, "s", {"transport": "stdio", "command": "npx", "args": ["b"]}
        )

    assert aload.await_count == 2
    assert a[0].name == "s_a"
    assert b[0].name == "s_b"
    assert len(mgr._mcp_tool_cache) == 1


@pytest.mark.asyncio
async def test_prepare_chat_mcp_injects_custom_from_cache() -> None:
    from octop.infra.agents.manager import AgentManager

    mgr = object.__new__(AgentManager)
    mgr._mcp_tool_cache = {}
    mgr._mcp_tool_cache_locks = {}
    mgr._mcp_tool_cache_guard = asyncio.Lock()

    tool = MagicMock()
    tool.name = "deepwiki_ask"
    tool.description = "ask"
    tool.args_schema = None
    tool.metadata = None
    tool.ainvoke = AsyncMock(return_value="ok")
    aload = AsyncMock(return_value=[tool])

    agent = MagicMock()
    agent._mcp_tool_name_set = frozenset()
    agent.config.mcp_server_configs = {"deepwiki": {}}
    agent.append_mcp_tools = MagicMock(
        side_effect=lambda tools: setattr(
            agent,
            "_mcp_tool_name_set",
            frozenset(getattr(t, "name", "") for t in tools) | frozenset(agent._mcp_tool_name_set),
        )
    )

    row = MagicMock()
    mgr.get_agent = MagicMock(return_value=agent)
    mgr.get_row = MagicMock(return_value=row)
    mgr._connector_uid_for = MagicMock(return_value=7)
    mgr._connector_svc = MagicMock()
    mgr._connector_svc.custom_harness_configs.return_value = {
        "deepwiki": {
            "transport": "streamable_http",
            "url": "https://mcp.deepwiki.com/mcp",
            "headers": {"Accept": "application/json, text/event-stream"},
        }
    }
    mgr.reload_connectors = AsyncMock()

    with patch("harness_agent.mcp.aload_mcp_tools", aload):
        failed = await mgr.prepare_chat_mcp("A1", ["deepwiki"], connector_user_id=7)
        failed2 = await mgr.prepare_chat_mcp("A1", ["deepwiki"], connector_user_id=7)

    assert failed == []
    assert failed2 == []
    assert aload.await_count == 1
    assert agent.append_mcp_tools.call_count == 1
    mgr.reload_connectors.assert_not_awaited()
    assert agent.config.mcp_server_configs["deepwiki"]["transport"] == "streamable_http"
    injected = agent.append_mcp_tools.call_args.args[0]
    assert isinstance(injected[0], StructuredTool)


def test_wrap_tools_for_shared_use() -> None:
    lock = asyncio.Lock()
    inner = MagicMock()
    inner.name = "x"
    inner.description = "d"
    inner.args_schema = None
    inner.metadata = None
    wrapped = wrap_tools_for_shared_use([inner], lock)
    assert len(wrapped) == 1
    assert isinstance(wrapped[0], StructuredTool)
