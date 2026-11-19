"""Loopback MCP for the plugin tools enabled on this expert."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.acp.mcp_tools import dispatch

_SCOPES: dict[str, PluginScope] = {}
_TOKENS: dict[tuple[str, tuple[str, ...]], str] = {}

_RESERVED = frozenset(
    {
        "cronjob_list",
        "cronjob_get",
        "cronjob_create",
        "cronjob_update",
        "cronjob_delete",
        "cronjob_run_now",
        "memory_search",
        "memory_get",
        "memory_save",
        "send_file_to_user",
        "ask_agent",
        "agent_list",
        "search_knowledge",
    }
)


@dataclass(frozen=True)
class PluginScope:
    agent_id: str


def plugin_scope(token: str) -> PluginScope | None:
    return _SCOPES.get(token)


def retain_plugin_scope(agent_id: str, tool_names: tuple[str, ...]) -> str:
    """Change the token when the enabled tool set changes, so the session reloads."""
    key = (agent_id, tool_names)
    token = _TOKENS.get(key)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[key] = token
    _SCOPES[token] = PluginScope(agent_id=agent_id)
    return token


def plugin_tools(manager: Any, config: dict[str, Any]) -> list[Any]:
    """Enabled plugin tools, with the same names a native expert would expose."""
    plugin_manager = getattr(manager, "_plugin_manager", None)
    if plugin_manager is None:
        return []
    from octop_harness.plugins import PluginRegistry, build_plugin_tools

    from octop.infra.agents.plugins.plugin_tool_defaults import (
        agent_plugin_enabled,
        expand_plugin_tools_default_on,
    )
    from octop.infra.agents.plugins.plugin_tool_names import sanitize_plugin_tool_names
    from octop.infra.agents.settings.tool_catalog import tools_disabled_set

    global_plugins = plugin_manager.global_enabled_map()
    if not isinstance(global_plugins, dict):
        global_plugins = {}
    registered = [(reg.plugin_id, reg.name) for reg in PluginRegistry().all_tools()]
    agent_plugins = config.get("plugins")
    agent_plugins_map = agent_plugins if isinstance(agent_plugins, dict) else {}
    effective = dict(global_plugins)
    for plugin in PluginRegistry().list_plugins():
        if not agent_plugin_enabled(agent_plugins_map, plugin.manifest.id):
            effective[plugin.manifest.id] = False
    mount = expand_plugin_tools_default_on(
        agent_plugins_map,
        registered_tools=registered,
        global_plugins=effective,
    )
    tools = build_plugin_tools(agent_plugins=mount, global_plugins=effective)
    disabled = tools_disabled_set(config)
    tools = [tool for tool in tools if str(getattr(tool, "name", "")) not in disabled]
    return sanitize_plugin_tool_names(tools, reserved=set(_RESERVED))


def plugin_tool_configs(config: dict[str, Any]) -> dict[str, Any]:
    from octop_harness.plugins import collect_plugin_tool_configs

    plugins = config.get("plugins")
    return collect_plugin_tool_configs(plugins if isinstance(plugins, dict) else None)


async def handle_plugins_mcp(
    body: dict[str, Any],
    *,
    tools: list[Any],
    tool_configs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await dispatch(
        body,
        server_name="octop-plugins",
        tools=tools,
        config={"plugin_tool_configs": tool_configs or {}},
    )
