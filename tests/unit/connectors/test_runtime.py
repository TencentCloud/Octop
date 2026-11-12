"""All stdio connectors use the existing MCP loading path and scoped sessions."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.connectors.mcp_tool_cache import StdioMCPTools
from octop.infra.connectors.stdio import StdioRuntime


@pytest.fixture
def factory(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr("octop.infra.connectors.builder.create_stdio_runtime", factory)
    return factory


def instance(name: str, kind: str = "open-design") -> SimpleNamespace:
    return SimpleNamespace(instance_id=name, kind=kind, mcp_server_name=name)


def service_for(instances):
    return SimpleNamespace(
        list_user_instances=MagicMock(return_value=instances),
        custom_harness_configs=lambda user: {},
    )


@pytest.mark.asyncio
async def test_prepare_selected_stdio_and_reuses_tools(factory):
    service = service_for(
        [
            instance("selected"),
            instance("other"),
            instance("yuque", "yuque-mcp"),
            instance("mail", "qq-mail"),
        ]
    )
    runtime = StdioMCPTools(service, object())
    factory.return_value.build_tools = AsyncMock(
        side_effect=lambda **kw: [SimpleNamespace(name=kw["instance"].mcp_server_name + "_tool")]
    )
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset())

    def append(tools):
        agent._mcp_tool_name_set |= frozenset(t.name for t in tools)

    agent.append_mcp_tools = MagicMock(side_effect=append)
    for _ in range(2):
        await runtime.prepare_tools(
            agent, agent_id="a", user_id=7, names=["selected", "yuque", "mail"]
        )
    assert factory.return_value.build_tools.await_count == 2
    assert factory.call_args_list[0].args[0] == "open-design"
    assert factory.call_args_list[1].args[0] == "yuque-mcp"
    service.list_user_instances.assert_called_with(
        7, active_only=True, with_credentials=True, include_shared=True
    )
    assert agent.append_mcp_tools.call_count == 2


@pytest.mark.asyncio
async def test_discovery_failure_is_isolated_and_redacted(caplog, factory):
    runtime = StdioMCPTools(service_for([instance("bad"), instance("ok")]), object())
    factory.return_value.build_tools = AsyncMock(side_effect=[RuntimeError("secret"), ["tool"]])
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset(), append_mcp_tools=MagicMock())
    await runtime.prepare_tools(agent, agent_id="a", user_id=7, names=["bad", "ok"])
    agent.append_mcp_tools.assert_called_once_with(["tool"])
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_rebind_and_scoped_close(factory):
    runtime = StdioMCPTools(object(), object())
    runtime.runtime_for("open-design")
    factory.return_value.close = AsyncMock()
    service, repos = object(), object()
    runtime.replace_persistence(service, repos)
    factory.return_value.replace_persistence.assert_called_once_with(service, repos)
    await runtime.close(user_id=7, agent_id="a")
    factory.return_value.close.assert_awaited_once_with(user_id=7, agent_id="a")


@pytest.mark.asyncio
async def test_missing_user_does_not_discover_tools(factory):
    service = service_for([])
    await StdioMCPTools(service, object()).prepare_tools(
        object(), agent_id="a", user_id=None, names=["selected"]
    )
    service.list_user_instances.assert_not_called()
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_plain_stdio_preserves_process_state_without_connector_registration():
    script = str(Path(__file__).resolve().parents[2] / "fixtures" / "open_design_mcp.py")
    servers = {
        name: {"transport": "stdio", "command": sys.executable, "args": [script], "env": {}}
        for name in ("plain-one", "plain-two")
    }
    service = service_for([])
    service.custom_harness_configs = lambda user: servers if user == 7 else {}
    repos = SimpleNamespace(agent_repo=SimpleNamespace(get=lambda _: SimpleNamespace(user_id=None)))
    loader = StdioMCPTools(service, repos)
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset(), tools={})

    def append(tools):
        agent.tools.update({t.name: t for t in tools})
        agent._mcp_tool_name_set = frozenset(agent.tools)

    agent.append_mcp_tools = append
    try:
        await loader.prepare_tools(agent, agent_id="a", user_id=7, names=list(servers))
        assert len(agent.tools) == 12  # Six tools per server, across two discovery pages.
        assert type(loader.runtime_for("custom-mcp")) is StdioRuntime

        async def invoke(server, name, args, *, user="7", thread="t"):
            tool = agent.tools[f"{server}_{name}"]
            return await tool.ainvoke(
                {"name": tool.name, "args": args, "id": "call", "type": "tool_call"},
                config={"configurable": {"user": user, "thread_id": thread}},
            )

        args = {"briefDraftId": "draft", "nonce": "nonce", "answers": {}}
        await invoke("plain-one", "collect_brief", {"projectTitle": "first"})
        await invoke("plain-two", "collect_brief", {"projectTitle": "second"})
        first = await invoke("plain-one", "confirm_brief", args)
        second = await invoke("plain-two", "confirm_brief", args)
        assert first.status == second.status == "success"
        assert "first" in str(first.content) and "second" in str(second.content)
        isolated = await invoke("plain-one", "confirm_brief", args, thread="other")
        assert isolated.status == "error"
        unauthorized = await invoke("plain-one", "confirm_brief", args, user="8")
        assert unauthorized.status == "error"
        await loader.close(agent_id="unrelated")
        assert (await invoke("plain-one", "confirm_brief", args)).status == "success"
        # Changing launch configuration opens a fresh process rather than leaking the old draft.
        servers["plain-one"]["env"] = {"STDIO_TEST_CONFIG": "changed"}
        assert (await invoke("plain-one", "confirm_brief", args)).status == "error"
        servers.clear()
        assert (await invoke("plain-two", "confirm_brief", args)).status == "error"
    finally:
        await loader.close()
    runtime = loader.runtime_for("custom-mcp")
    assert not runtime._clients and not runtime._timers


@pytest.mark.asyncio
async def test_failed_stdio_connection_is_discarded_and_idle_session_closes():
    runtime = StdioRuntime(object(), object())
    failed = SimpleNamespace(call_tool=AsyncMock(side_effect=OSError("closed")), aclose=AsyncMock())
    healthy = SimpleNamespace(aclose=AsyncMock())
    factory = MagicMock(side_effect=[failed, healthy])
    spec = {"transport": "stdio", "command": sys.executable, "args": []}
    with pytest.raises(OSError):
        async with runtime.session(7, "i", "a", "t", spec, client_factory=factory) as client:
            await client.call_tool("test", {})
    failed.aclose.assert_awaited_once()
    assert not runtime._clients and not runtime._timers
    async with runtime.session(7, "i", "a", "t", spec, client_factory=factory) as client:
        assert client is healthy
    await runtime._expire(next(iter(runtime._clients)))
    healthy.aclose.assert_awaited_once()
    assert not runtime._clients and not runtime._timers
