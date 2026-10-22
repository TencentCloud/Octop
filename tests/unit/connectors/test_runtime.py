"""Connector runtime assembly stays outside AgentManager."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.connectors import managed
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.runtime import ConnectorRuntime


@pytest.fixture
def factory(monkeypatch):
    factory = MagicMock()
    handler = replace(managed._HANDLERS["open-design"], create_runtime=factory)
    monkeypatch.setitem(managed._HANDLERS, "open-design", handler)
    return factory


def instance(name: str, kind: str = "open-design") -> SimpleNamespace:
    return SimpleNamespace(instance_id=name, kind=kind, mcp_server_name=name)


@pytest.mark.asyncio
async def test_prepare_only_selected_tools_and_reuses_loaded_tools(factory) -> None:
    service = SimpleNamespace(
        list_user_instances=MagicMock(
            return_value=[instance("selected"), instance("other"), instance("mail", "qq-mail")]
        )
    )
    runtime = ConnectorRuntime(service, object())
    factory.return_value.build_tools = AsyncMock(
        return_value=[SimpleNamespace(name="selected_tool")]
    )
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset())

    def append(tools: list[SimpleNamespace]) -> None:
        agent._mcp_tool_name_set = frozenset(t.name for t in tools)

    agent.append_mcp_tools = MagicMock(side_effect=append)
    for _ in range(2):
        await runtime.prepare_tools(agent, agent_id="a", user_id=7, names=["selected", "mail"])
    factory.return_value.build_tools.assert_awaited_once_with(
        user_id=7, instance=service.list_user_instances.return_value[0], agent_id="a"
    )
    service.list_user_instances.assert_called_with(
        7, active_only=True, with_credentials=True, include_shared=True
    )
    agent.append_mcp_tools.assert_called_once()


@pytest.mark.asyncio
async def test_discovery_failure_does_not_block_other_instances(caplog, factory) -> None:
    service = SimpleNamespace(
        list_user_instances=lambda *a, **kw: [instance("bad"), instance("ok")]
    )
    runtime = ConnectorRuntime(service, object())
    factory.return_value.build_tools = AsyncMock(side_effect=[RuntimeError("secret"), ["tool"]])
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset(), append_mcp_tools=MagicMock())
    await runtime.prepare_tools(agent, agent_id="a", user_id=7, names=["bad", "ok"])
    agent.append_mcp_tools.assert_called_once_with(["tool"])
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_rebind_and_scoped_close(factory) -> None:
    runtime = ConnectorRuntime(object(), object())
    factory.return_value.close = AsyncMock()
    service, repos = object(), object()
    runtime.replace_persistence(service, repos)
    factory.return_value.replace_persistence.assert_called_once_with(service, repos)
    await runtime.close(user_id=7, agent_id="a")
    factory.return_value.close.assert_awaited_once_with(user_id=7, agent_id="a")


@pytest.mark.asyncio
async def test_missing_user_does_not_discover_tools(factory) -> None:
    service = SimpleNamespace(list_user_instances=MagicMock())
    runtime = ConnectorRuntime(service, object())
    await runtime.prepare_tools(object(), agent_id="a", user_id=None, names=["selected"])
    service.list_user_instances.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_dispatches_second_handler_without_product_branches(monkeypatch, factory):
    from octop.config import OctopConfig
    from octop.infra.connectors import runtime as dispatch
    from octop.infra.connectors.builder import (
        build_http_mcp_spec,
        build_mcp_server_configs_for_user,
        validate_create_credentials,
    )

    entry = replace(
        get_catalog_entry("open-design"), kind="second-product", runtime_handler="session-handler"
    )
    second = MagicMock()
    second.build_tools = AsyncMock(return_value=["second-tool"])
    second.close = AsyncMock()
    second.start = AsyncMock()
    second.shutdown = AsyncMock()
    handler = managed.ManagedHandler(
        connection_spec=MagicMock(return_value={"transport": "stdio", "command": "second"}),
        normalize_credentials=MagicMock(return_value={"command": "second"}),
        create_runtime=MagicMock(return_value=second),
    )
    monkeypatch.setitem(managed._HANDLERS, "session-handler", handler)
    original_lookup = get_catalog_entry

    def lookup(kind):
        return entry if kind == entry.kind else original_lookup(kind)

    monkeypatch.setattr(dispatch, "get_catalog_entry", lookup)
    monkeypatch.setattr(dispatch, "list_catalog", lambda: [get_catalog_entry("open-design"), entry])
    monkeypatch.setattr("octop.infra.connectors.builder.get_catalog_entry", lookup)
    selected = instance("selected", entry.kind)
    service = SimpleNamespace(
        list_user_instances=MagicMock(return_value=[selected]),
        custom_harness_configs=lambda user: {},
    )
    runtime = ConnectorRuntime(service, object())
    agent = SimpleNamespace(_mcp_tool_name_set=frozenset(), append_mcp_tools=MagicMock())
    await runtime.prepare_tools(agent, agent_id="a", user_id=7, names=["selected"])
    agent.append_mcp_tools.assert_called_once_with(["second-tool"])
    factory.return_value.build_tools.assert_not_called()
    assert validate_create_credentials(entry.kind, {}) == {"command": "second"}
    assert (
        build_http_mcp_spec(entry=entry, instance_id="selected", creds={}, config=OctopConfig())[
            "command"
        ]
        == "second"
    )
    # The host owns managed sessions; Harness receives only their selection name.
    monkeypatch.setattr(
        "octop.infra.connectors.builder._iter_active_connectors", lambda *a: [(selected, entry, {})]
    )
    configs = build_mcp_server_configs_for_user(
        svc=service,
        connector_repo=MagicMock(),
        user_id=7,
        agent_id="a",
        agent_user_id=7,
        config=OctopConfig(),
        log=False,
    )
    assert configs == {"selected": {}}
    factory.return_value.start = AsyncMock()
    factory.return_value.shutdown = AsyncMock()
    factory.return_value.close = AsyncMock()
    await runtime.start()
    await runtime.close(user_id=7, agent_id="a")
    await runtime.shutdown()
    second.start.assert_awaited_once()
    second.close.assert_awaited_once_with(user_id=7, agent_id="a")
    second.shutdown.assert_awaited_once()
    runtime.replace_persistence(service, "new-repos")
    second.replace_persistence.assert_called_once_with(service, "new-repos")


def test_unregistered_managed_handler_is_rejected():
    entry = replace(get_catalog_entry("open-design"), runtime_handler="unknown")
    with pytest.raises(ValueError, match="unregistered managed MCP handler"):
        managed.managed_handler(entry)
