"""Octop / octop-harness plugin system."""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

from octop_harness.plugins.context import PluginContext
from octop_harness.plugins.loader import discover_plugin_dirs, load_all, load_plugin_dir, unload_plugin
from octop_harness.plugins.manifest import PluginManifest
from octop_harness.plugins.registry import ChannelRegistration, LoadedPlugin, PluginRegistry
from octop_harness.plugins.tools import build_plugin_tools, collect_plugin_tool_configs, get_tool_config

__all__ = [
    "AgentMiddleware",
    "ChannelRegistration",
    "LoadedPlugin",
    "PluginContext",
    "PluginManifest",
    "PluginRegistry",
    "build_plugin_tools",
    "collect_plugin_tool_configs",
    "discover_plugin_dirs",
    "get_tool_config",
    "load_all",
    "load_plugin_dir",
    "unload_plugin",
]
