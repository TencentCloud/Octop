"""Octop host-side plugin management."""

from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.agents.plugins.plugin_tool_defaults import (
    agent_plugin_enabled,
    expand_plugin_tools_default_on,
    merge_plugins_enabled_settings,
    merge_plugins_tool_settings,
)
from octop.infra.agents.plugins.plugin_tool_names import (
    extract_original_plugin_label,
    sanitize_plugin_tool_name,
    sanitize_plugin_tool_names,
)

__all__ = [
    "PluginManager",
    "agent_plugin_enabled",
    "expand_plugin_tools_default_on",
    "extract_original_plugin_label",
    "merge_plugins_enabled_settings",
    "merge_plugins_tool_settings",
    "sanitize_plugin_tool_name",
    "sanitize_plugin_tool_names",
]
