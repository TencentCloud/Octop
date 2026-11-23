"""Cron, memory, and plugin loopback MCP for managed experts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents.acp.cron_mcp import CronScope, handle_cron_mcp
from octop.infra.agents.acp.memory_mcp import handle_memory_mcp, memory_enabled
from octop.infra.agents.acp.plugins_mcp import handle_plugins_mcp, plugin_tools
from octop.infra.agents.acp.turn import attach_managed_turn


class _Cron:
    def __init__(self) -> None:
        self._repos = SimpleNamespace(
            agent_repo=SimpleNamespace(get=lambda _agent_id: SimpleNamespace(user_id=7))
        )

    def list_by_agent(self, agent_id: str, include_disabled: bool = True) -> list[Any]:
        assert agent_id == "GWN"
        assert include_disabled is True
        return [SimpleNamespace(to_public_dict=lambda: {"cron_id": "c1", "name": "喝水"})]


@pytest.mark.asyncio
async def test_cron_list_uses_the_calling_expert() -> None:
    scope = CronScope(user_id=7, agent_id="GWN", thread_id="thr", session_key="dash")
    result = await handle_cron_mcp(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cronjob_list", "arguments": {}},
        },
        scope=scope,
        cron_manager=_Cron(),
    )
    text = result["result"]["content"][0]["text"]
    assert result["result"]["isError"] is False
    assert "c1" in text


def test_memory_stays_off_until_the_expert_enables_it() -> None:
    assert memory_enabled({}) is False
    assert memory_enabled({"memory": {"memory_enabled": False}}) is False
    assert memory_enabled({"memory": {"memory_enabled": True}}) is True


@pytest.mark.asyncio
async def test_memory_call_reports_a_missing_service() -> None:
    result = await handle_memory_mcp(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "memory_search", "arguments": {"query": "hi"}},
        },
        service=None,
    )
    assert result["result"]["isError"] is True


@pytest.mark.asyncio
async def test_plugin_tool_is_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    def ping_host(name: str) -> str:
        """Say hello."""
        return f"hi {name}"

    registration = SimpleNamespace(
        plugin_id="demo",
        name="ping_host",
        fn=ping_host,
        description="Say hello.",
    )

    class Registry:
        def all_tools(self) -> list[Any]:
            return [registration]

        def list_plugins(self) -> list[Any]:
            return [SimpleNamespace(manifest=SimpleNamespace(id="demo"))]

    monkeypatch.setattr("octop_harness.plugins.PluginRegistry", Registry)
    monkeypatch.setattr("octop_harness.plugins.tools.PluginRegistry", Registry)
    manager = SimpleNamespace(
        _plugin_manager=SimpleNamespace(global_enabled_map=lambda: {"demo": True})
    )
    tools = plugin_tools(manager, {})
    assert [tool.name for tool in tools] == ["ping_host"]
    result = await handle_plugins_mcp(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ping_host", "arguments": {"name": "Ada"}},
        },
        tools=tools,
    )
    assert result["result"]["content"][0]["text"] == "hi Ada"


@pytest.mark.asyncio
async def test_managed_turn_adds_cron_memory_and_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    def ping_host(name: str) -> str:
        """Say hello."""
        return name

    registration = SimpleNamespace(
        plugin_id="demo",
        name="ping_host",
        fn=ping_host,
        description="Say hello.",
    )

    class Registry:
        def all_tools(self) -> list[Any]:
            return [registration]

        def list_plugins(self) -> list[Any]:
            return [SimpleNamespace(manifest=SimpleNamespace(id="demo"))]

    monkeypatch.setattr("octop_harness.plugins.PluginRegistry", Registry)
    monkeypatch.setattr("octop_harness.plugins.tools.PluginRegistry", Registry)

    class Manager:
        _connector_svc = SimpleNamespace()
        _cron_manager = object()
        _plugin_manager = SimpleNamespace(global_enabled_map=lambda: {"demo": True})
        _config = SimpleNamespace(
            bind_host="127.0.0.1",
            port=8000,
            tls=SimpleNamespace(enabled=False, cert_file="", key_file=""),
        )

        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="managed")

        def get_config(self, agent_id: str) -> dict[str, Any]:
            return {"memory": {"memory_enabled": True}}

    request: dict[str, Any] = {"user": "7", "thread_id": "thr", "configurable": {"locale": "zh"}}
    await attach_managed_turn(Manager(), "GWN", request)
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    specs = configurable["acp_mcp_servers"]
    assert isinstance(specs, dict)
    assert {"octop-files", "octop-cron", "octop-memory", "octop-plugins"} <= set(specs)
    assert "/api/internal/mcp/cron?token=" in specs["octop-cron"]["url"]
    assert "/api/internal/mcp/memory?token=" in specs["octop-memory"]["url"]
    assert "/api/internal/mcp/plugins?token=" in specs["octop-plugins"]["url"]
    note = str(configurable.get("acp_prompt_note") or "")
    assert "cronjob_create" in note
    assert "CronCreate" in note
    assert "Asia/Shanghai" in note


@pytest.mark.asyncio
async def test_disabled_managed_tools_are_left_off() -> None:
    class Manager:
        _connector_svc = SimpleNamespace()
        _cron_manager = object()
        _config = SimpleNamespace(
            bind_host="127.0.0.1",
            port=8000,
            tls=SimpleNamespace(enabled=False, cert_file="", key_file=""),
        )

        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="managed")

        def get_config(self, agent_id: str) -> dict[str, Any]:
            return {
                "memory": {"memory_enabled": True},
                "tools_disabled": [
                    "send_file_to_user",
                    "cronjob_list",
                    "cronjob_get",
                    "cronjob_create",
                    "cronjob_update",
                    "cronjob_delete",
                    "cronjob_run_now",
                    "memory_save",
                ],
            }

    request: dict[str, Any] = {"user": "7", "thread_id": "thr", "configurable": {"locale": "zh"}}
    await attach_managed_turn(Manager(), "GWN", request)
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    specs = configurable["acp_mcp_servers"]
    assert isinstance(specs, dict)
    assert "octop-files" not in specs
    assert "octop-cron" not in specs
    assert "octop-memory" in specs
    note = str(configurable.get("acp_prompt_note") or "")
    assert "send_file_to_user" not in note
    assert "cronjob_create" not in note
