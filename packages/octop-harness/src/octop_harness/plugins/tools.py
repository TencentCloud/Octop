"""Build LangChain tools from loaded plugins."""

from __future__ import annotations

import inspect
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.config import get_config

from octop_harness.plugins.registry import PluginRegistry, ToolRegistration


def get_tool_config(tool_name: str) -> dict[str, Any] | None:
    """Return per-invocation tool config from ``RunnableConfig.configurable``.

    Octop injects ``plugin_tool_configs`` when streaming.
    """
    cfg = get_config().get("configurable") or {}
    configs = cfg.get("plugin_tool_configs")
    if not isinstance(configs, dict):
        return None
    entry = configs.get(tool_name)
    return dict(entry) if isinstance(entry, dict) else None


def _tool_enabled(
    plugin_id: str,
    tool_name: str,
    *,
    agent_plugins: dict[str, Any],
    global_plugins: dict[str, bool],
) -> bool:
    """Whether a plugin tool is bound onto an agent.

    Default is **on** once the plugin is globally enabled: missing agent
    config means the tool is available. Agents opt out with
    ``enabled: false``. This matches the product expectation that enabling
    a plugin makes its tools usable without a second per-agent toggle.
    """
    if global_plugins.get(plugin_id) is False:
        return False
    plugin_cfg = agent_plugins.get(plugin_id)
    if not isinstance(plugin_cfg, dict):
        return True
    tools_cfg = plugin_cfg.get("tools")
    if not isinstance(tools_cfg, dict):
        return True
    tool_cfg = tools_cfg.get(tool_name)
    if not isinstance(tool_cfg, dict):
        return True
    if "enabled" not in tool_cfg:
        return True
    return bool(tool_cfg.get("enabled"))


def build_plugin_tools(
    *,
    agent_plugins: dict[str, Any] | None = None,
    global_plugins: dict[str, bool] | None = None,
) -> list[StructuredTool]:
    """Return StructuredTools for enabled plugin tools on this agent."""
    agent_plugins = agent_plugins or {}
    global_plugins = global_plugins or {}
    out: list[StructuredTool] = []
    for reg in PluginRegistry().all_tools():
        if not _tool_enabled(
            reg.plugin_id,
            reg.name,
            agent_plugins=agent_plugins,
            global_plugins=global_plugins,
        ):
            continue
        out.append(_to_structured_tool(reg))
    return out


def _to_structured_tool(reg: ToolRegistration) -> StructuredTool:
    fn = reg.fn
    if inspect.iscoroutinefunction(fn):
        return StructuredTool.from_function(
            coroutine=fn,
            name=reg.name,
            description=reg.description,
        )
    return StructuredTool.from_function(
        func=fn,
        name=reg.name,
        description=reg.description,
    )


def collect_plugin_tool_configs(agent_plugins: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Flatten agent ``config_json.plugins`` into ``{tool_name: config}`` for streaming."""
    if not agent_plugins:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for _plugin_id, plugin_cfg in agent_plugins.items():
        if not isinstance(plugin_cfg, dict):
            continue
        tools_cfg = plugin_cfg.get("tools")
        if not isinstance(tools_cfg, dict):
            continue
        for tool_name, tool_cfg in tools_cfg.items():
            if not isinstance(tool_cfg, dict):
                continue
            config = tool_cfg.get("config")
            if isinstance(config, dict):
                out[str(tool_name)] = dict(config)
    return out
