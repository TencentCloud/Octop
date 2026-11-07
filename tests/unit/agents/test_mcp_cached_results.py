"""Cached MCP tools must keep the adapter's result protocol in a real graph."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from mcp.types import CallToolResult, TextContent, Tool

from octop.infra.agents.manager import AgentManager
from octop.infra.connectors.mcp_tool_cache import wrap_tools_for_shared_use


def _adapter(session: Any, name: str = "lookup") -> Any:
    return convert_mcp_tool_to_langchain_tool(
        session,
        Tool(
            name=name,
            description="Look up a record",
            inputSchema={"type": "object", "properties": {"key": {"type": "string"}}},
        ),
    )


def _graph(tools: list[Any]) -> Any:
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile(checkpointer=InMemorySaver())


def _input(name: str = "lookup", call_id: str = "call-1") -> dict[str, Any]:
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": name, "args": {"key": "record"}, "id": call_id}],
            )
        ]
    }


def _manager(root: Path) -> AgentManager:
    manager = object.__new__(AgentManager)
    manager._mcp_tool_cache = {}
    manager._mcp_tool_cache_locks = {}
    manager._mcp_tool_cache_guard = asyncio.Lock()
    manager._paths = MagicMock(root=root)
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_mcp_structured_result_survives_graph_checkpoint(cached: bool) -> None:
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(
            content=[TextContent(type="text", text="Found record")],
            structuredContent={"record": {"id": 42, "labels": ["agent", "mcp"]}},
        )
    )
    tool = _adapter(session)
    tools = wrap_tools_for_shared_use([tool], asyncio.Lock()) if cached else [tool]
    graph = _graph(tools)
    config = {"configurable": {"thread_id": "result-thread"}}
    result = await graph.ainvoke(_input(), config)
    message = result["messages"][-1]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-1"
    assert message.status == "success"
    assert message.content[0]["text"] == "Found record"
    assert message.artifact == {
        "structured_content": {"record": {"id": 42, "labels": ["agent", "mcp"]}}
    }
    checkpoint = await graph.aget_state(config)
    assert checkpoint.values["messages"][-1].artifact == message.artifact
    session.call_tool.assert_awaited_once()
    assert session.call_tool.call_args.args == ("lookup", {"key": "record"})


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_mcp_execution_error_remains_error_message(cached: bool) -> None:
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(
            content=[TextContent(type="text", text="Record unavailable")], isError=True
        )
    )
    tool = _adapter(session)
    tools = wrap_tools_for_shared_use([tool], asyncio.Lock()) if cached else [tool]
    graph = _graph(tools)
    result = await graph.ainvoke(_input(), {"configurable": {"thread_id": "error-thread"}})
    message = result["messages"][-1]
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert message.tool_call_id == "call-1"
    assert message.content[0]["text"] == "Record unavailable"


@pytest.mark.asyncio
async def test_cached_mcp_transport_failure_releases_lock() -> None:
    session = MagicMock()
    session.call_tool = AsyncMock(
        side_effect=[
            OSError("connection lost"),
            CallToolResult(content=[TextContent(type="text", text="Recovered")]),
        ]
    )
    lock = asyncio.Lock()
    tool = wrap_tools_for_shared_use([_adapter(session)], lock)[0]
    with pytest.raises(OSError, match="connection lost"):
        await tool.ainvoke({"key": "record"})
    assert not lock.locked()
    result = await asyncio.wait_for(tool.ainvoke({"key": "record"}), timeout=2)
    assert result[0]["text"] == "Recovered"


@pytest.mark.asyncio
async def test_shared_user_cache_serializes_and_preserves_each_call(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    waiting = asyncio.Event()
    calls: list[str] = []

    class ObservedLock(asyncio.Lock):
        async def acquire(self) -> bool:
            if self.locked():
                waiting.set()
            return await super().acquire()

    manager._mcp_tool_cache_locks[(7, "server")] = ObservedLock()

    async def deliver(name: str, arguments: dict[str, Any], **kwargs: Any) -> CallToolResult:
        calls.append(name)
        if len(calls) == 1:
            entered.set()
            await release.wait()
        return CallToolResult(
            content=[TextContent(type="text", text=name)], structuredContent={"tool": name}
        )

    session = MagicMock(call_tool=deliver)
    tools = [_adapter(session), _adapter(session, "other")]
    spec = {"transport": "stdio", "command": "synthetic-mcp"}
    with patch("octop_harness.mcp.aload_mcp_tools", AsyncMock(return_value=tools)) as load:
        first = await manager._get_or_load_mcp_tools(7, "server", spec)
        second = await manager._get_or_load_mcp_tools(7, "server", spec)
    assert first is second
    load.assert_awaited_once()
    graph = _graph(first)
    a = asyncio.create_task(
        graph.ainvoke(_input(), {"configurable": {"thread_id": "agent-a-thread"}})
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    b = asyncio.create_task(
        graph.ainvoke(_input("other", "call-2"), {"configurable": {"thread_id": "agent-b-thread"}})
    )
    try:
        await asyncio.wait_for(waiting.wait(), timeout=2)
        assert calls == ["lookup"]
    finally:
        release.set()
    results = await asyncio.wait_for(asyncio.gather(a, b), timeout=2)
    assert calls == ["lookup", "other"]
    for result, name, call_id in zip(
        results, ["lookup", "other"], ["call-1", "call-2"], strict=True
    ):
        message = result["messages"][-1]
        assert message.tool_call_id == call_id
        assert message.artifact == {"structured_content": {"tool": name}}


@pytest.mark.asyncio
async def test_cancelled_mcp_execution_does_not_poison_shared_cache() -> None:
    entered = asyncio.Event()
    calls = 0

    async def deliver(*args: Any, **kwargs: Any) -> CallToolResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.Event().wait()
        return CallToolResult(
            content=[TextContent(type="text", text="Next turn")], structuredContent={"turn": 2}
        )

    lock = asyncio.Lock()
    tools = wrap_tools_for_shared_use([_adapter(MagicMock(call_tool=deliver))], lock)
    graph = _graph(tools)
    task = asyncio.create_task(
        graph.ainvoke(_input(), {"configurable": {"thread_id": "cancelled-thread"}})
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not lock.locked()
    result = await asyncio.wait_for(
        graph.ainvoke(_input(), {"configurable": {"thread_id": "next-thread"}}), timeout=2
    )
    assert result["messages"][-1].artifact == {"structured_content": {"turn": 2}}


def test_sync_cached_mcp_keeps_result_protocol() -> None:
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(
            content=[TextContent(type="text", text="Sync result")], structuredContent={"id": 42}
        )
    )
    original = _adapter(session)
    wrapped = wrap_tools_for_shared_use([original], asyncio.Lock())[0]
    call = {"name": "lookup", "args": {"key": "record"}, "id": "sync-call", "type": "tool_call"}
    message = wrapped.invoke(call)
    assert message.tool_call_id == "sync-call"
    assert message.artifact == {"structured_content": {"id": 42}}
    assert original.func is None
    assert wrapped.response_format == original.response_format
    assert wrapped.handle_tool_error == original.handle_tool_error


@pytest.mark.asyncio
async def test_cached_tool_preserves_injected_config_and_original_callable() -> None:
    received: list[RunnableConfig] = []

    async def lookup(key: str, config: RunnableConfig) -> str:
        received.append(config)
        return key

    original = StructuredTool.from_function(coroutine=lookup, description="Config-aware lookup")
    wrapped = wrap_tools_for_shared_use([original], asyncio.Lock())[0]
    assert original.coroutine is lookup
    assert "config" not in wrapped.tool_call_schema.model_fields
    await wrapped.ainvoke({"key": "record"}, {"configurable": {"thread_id": "caller-thread"}})
    assert received[0]["configurable"]["thread_id"] == "caller-thread"


@pytest.mark.asyncio
async def test_user_scoped_cache_does_not_share_result_producers(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    spec = {"transport": "stdio", "command": "synthetic-mcp"}
    sessions = [MagicMock(), MagicMock()]
    for session, owner in zip(sessions, [7, 8], strict=True):
        session.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text=str(owner))],
                structuredContent={"owner": owner},
            )
        )
    with patch(
        "octop_harness.mcp.aload_mcp_tools",
        AsyncMock(side_effect=[[_adapter(session)] for session in sessions]),
    ) as load:
        first = await manager._get_or_load_mcp_tools(7, "server", spec)
        second = await manager._get_or_load_mcp_tools(8, "server", spec)
    assert first is not second
    assert load.await_count == 2
    for tools, owner in zip([first, second], [7, 8], strict=True):
        result = await _graph(tools).ainvoke(
            _input(), {"configurable": {"thread_id": f"owner-{owner}"}}
        )
        assert result["messages"][-1].artifact == {"structured_content": {"owner": owner}}
