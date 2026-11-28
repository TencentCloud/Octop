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


@pytest.mark.asyncio
@pytest.mark.parametrize("configured_env", [{}, {"MCP_EXPLICIT_TOKEN": "allowed"}])
async def test_discovery_only_passes_configured_environment(monkeypatch, configured_env):
    from contextlib import asynccontextmanager

    from octop.infra.connectors import stdio

    monkeypatch.setenv("OCTOP_DATABASE_SECRET", "must-not-leak")
    runtime = StdioRuntime(None, None)
    runtime._spec = AsyncMock(return_value={"command": "test-mcp", "env": configured_env})

    @asynccontextmanager
    async def transport(params):
        assert params.env == configured_env
        assert "OCTOP_DATABASE_SECRET" not in params.env
        yield None, None

    @asynccontextmanager
    async def session(*args):
        yield SimpleNamespace(
            initialize=AsyncMock(),
            list_tools=AsyncMock(return_value=SimpleNamespace(tools=[], nextCursor=None)),
        )

    monkeypatch.setattr(stdio, "stdio_client", transport)
    monkeypatch.setattr(stdio, "ClientSession", session)
    assert await runtime.build_tools(user_id=7, instance=instance("i"), agent_id="a") == []


@pytest.mark.asyncio
async def test_shared_expert_authorization_rechecked(monkeypatch):
    from octop.infra.users import groups

    row = SimpleNamespace(user_id=1, agent_id="a", is_shared=1)
    repos = SimpleNamespace(
        agent_repo=SimpleNamespace(get=lambda _: row),
        user_repo=SimpleNamespace(get=lambda _: SimpleNamespace(role="user")),
    )
    allowed = MagicMock(side_effect=lambda *a, **k: row.is_shared == 1)
    monkeypatch.setattr(groups, "expert_visible_to", allowed)
    runtime = StdioRuntime(None, repos)
    assert await runtime.expert_accessible(2, "a")
    allowed.assert_called_once_with(repos, row, user_id=2, is_admin=False)
    row.is_shared = 0
    assert not await runtime.expert_accessible(2, "a")


@pytest.mark.asyncio
async def test_shared_stdio_alias_uses_viewer_visibility(factory):
    own = {"transport": "stdio", "command": "viewer-cli"}
    shared = {"transport": "stdio", "command": "owner-cli"}
    service = service_for([])
    service.custom_harness_configs = lambda _: {"tool": own, "custom__owner__tool": shared}
    service.shared_custom_harness_aliases = lambda _: {"custom__owner__tool": "tool"}
    loader = StdioMCPTools(service, object())
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset(), _mcp_tools=[])

    def replace(tools):
        agent._mcp_tools = tools
        agent._mcp_tool_name_set = frozenset(t.name for t in tools)

    agent.replace_mcp_tools = MagicMock(side_effect=replace)
    agent.append_mcp_tools = lambda tools: replace([*agent._mcp_tools, *tools])
    factory.return_value.build_tools = AsyncMock(return_value=[SimpleNamespace(name="tool_x")])
    await loader.prepare_tools(
        agent,
        agent_id="a",
        user_id=2,
        names=["tool"],
        custom_configs={"tool": shared},
        load_user={"tool": 1},
    )
    assert (
        factory.return_value.build_tools.call_args.kwargs["instance"].instance_id
        == "custom:custom__owner__tool"
    )
    factory.return_value.build_tools.reset_mock()
    # Removing the viewer-visible shared name must prevent discovery, even if
    # the caller still has an old owner-backed spec and same-named own server.
    service.custom_harness_configs = lambda _: {"tool": own}
    await loader.prepare_tools(
        agent,
        agent_id="a",
        user_id=2,
        names=["tool"],
        custom_configs={"tool": shared},
        load_user={"tool": 1},
    )
    factory.return_value.build_tools.assert_not_awaited()
    await loader.prepare_tools(
        agent,
        agent_id="a",
        user_id=2,
        names=["tool"],
        custom_configs={"tool": own},
        load_user={"tool": 2},
    )
    assert (
        factory.return_value.build_tools.call_args.kwargs["instance"].instance_id == "custom:tool"
    )

    agent.replace_mcp_tools.assert_called_once_with([])
    assert len(agent._mcp_tools) == 1
    assert agent._mcp_attached_user["tool"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("design", [False, True])
async def test_nonowner_calls_own_connector_through_shared_expert(monkeypatch, design):
    from contextlib import asynccontextmanager

    from langchain_core.tools import ToolException
    from mcp import types

    from octop.infra.connectors import open_design, stdio

    row = SimpleNamespace(user_id=1, agent_id="a", is_shared=1)
    repos = SimpleNamespace(
        agent_repo=SimpleNamespace(get=lambda _: row),
        user_repo=SimpleNamespace(get=lambda _: SimpleNamespace(role="user")),
        user_group_repo=MagicMock(),
        user_group_member_repo=MagicMock(),
        resource_group_grant_repo=SimpleNamespace(group_ids=lambda *a: set()),
        settings_repo=SimpleNamespace(get=lambda _: None, set=lambda *a: None),
    )
    service = service_for([instance("i")])
    service.decrypt = lambda _: {"command": sys.executable, "args": [], "env": {}}
    runtime = (open_design.OpenDesignRuntime if design else StdioRuntime)(service, repos)
    module = open_design if design else stdio
    monkeypatch.setattr(
        module, "get_config", lambda: {"configurable": {"user": "2", "thread_id": "t"}}
    )
    result = types.CallToolResult(content=[])
    client = SimpleNamespace(call_tool=AsyncMock(return_value=result))

    @asynccontextmanager
    async def session(*args, **kwargs):
        assert args[:4] == (2, "i", "a", "t")
        yield client

    monkeypatch.setattr(runtime, "session", session)
    assert await runtime.call(2, "i", "a", "list_files", {"project": "p"}) == result
    row.is_shared = 0
    with pytest.raises(ToolException):
        await runtime.call(2, "i", "a", "list_files", {"project": "p"})
    assert client.call_tool.await_count == 1
