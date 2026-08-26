"""Built-in agent tool catalog for tool-settings UI and disable policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Tools that must remain available; ignored if present in ``tools_disabled``.
CRITICAL_TOOLS: frozenset[str] = frozenset(
    {
        "ls",
        "read_file",
        "glob",
        "grep",
        "write_todos",
        "task",
    }
)

# Conditionally loaded tools — marked ``available=false`` when gated off.
_WEB_SEARCH_TOOLS: frozenset[str] = frozenset(
    {
        "tavily_search",
        "brave_search",
        "google_search",
        "kimi_search",
        "searchfree_search",
    }
)
_MEDIA_TOOLS: frozenset[str] = frozenset({"generate_image", "generate_video"})
_MEMORY_TOOLS: frozenset[str] = frozenset({"memory_search", "memory_get"})
_MOBILE_TOOLS: frozenset[str] = frozenset(
    {
        "mobile_screenshot",
        "mobile_tap",
        "mobile_swipe",
        "mobile_launch_app",
        "mobile_ui_dump",
        "mobile_handoff_to_user",
    }
)


@dataclass(frozen=True)
class BuiltinToolEntry:
    name: str
    category: str


# Runtime tool names exposed in the tool-settings dialog (MCP excluded).
BUILTIN_TOOL_CATALOG: tuple[BuiltinToolEntry, ...] = (
    # filesystem / orchestration (critical ones still listed, disableable=false)
    BuiltinToolEntry("ls", "filesystem"),
    BuiltinToolEntry("read_file", "filesystem"),
    BuiltinToolEntry("write_file", "filesystem"),
    BuiltinToolEntry("edit_file", "filesystem"),
    BuiltinToolEntry("glob", "filesystem"),
    BuiltinToolEntry("grep", "filesystem"),
    BuiltinToolEntry("execute", "filesystem"),
    BuiltinToolEntry("write_todos", "orchestration"),
    BuiltinToolEntry("task", "orchestration"),
    # harness builtins
    BuiltinToolEntry("current_time", "misc"),
    BuiltinToolEntry("web_fetch", "web"),
    BuiltinToolEntry("browser_use", "web"),
    BuiltinToolEntry("desktop_screenshot", "web"),
    BuiltinToolEntry("send_file_to_user", "misc"),
    BuiltinToolEntry("read_env_file", "misc"),
    BuiltinToolEntry("write_env_file", "misc"),
    BuiltinToolEntry("tavily_search", "web"),
    BuiltinToolEntry("brave_search", "web"),
    BuiltinToolEntry("google_search", "web"),
    BuiltinToolEntry("kimi_search", "web"),
    BuiltinToolEntry("searchfree_search", "web"),
    BuiltinToolEntry("generate_image", "media"),
    BuiltinToolEntry("generate_video", "media"),
    BuiltinToolEntry("memory_search", "memory"),
    BuiltinToolEntry("memory_get", "memory"),
    BuiltinToolEntry("acp_runner", "misc"),
    # Octop host tools
    BuiltinToolEntry("cronjob_list", "cron"),
    BuiltinToolEntry("cronjob_get", "cron"),
    BuiltinToolEntry("cronjob_create", "cron"),
    BuiltinToolEntry("cronjob_update", "cron"),
    BuiltinToolEntry("cronjob_delete", "cron"),
    BuiltinToolEntry("cronjob_run_now", "cron"),
    BuiltinToolEntry("search_knowledge", "knowledge"),
    BuiltinToolEntry("mobile_screenshot", "mobile"),
    BuiltinToolEntry("mobile_tap", "mobile"),
    BuiltinToolEntry("mobile_swipe", "mobile"),
    BuiltinToolEntry("mobile_launch_app", "mobile"),
    BuiltinToolEntry("mobile_ui_dump", "mobile"),
    BuiltinToolEntry("mobile_handoff_to_user", "mobile"),
    BuiltinToolEntry("agent_list", "teams"),
    BuiltinToolEntry("ask_agent", "teams"),
)


def normalize_tools_disabled(raw: object) -> list[str]:
    """Normalize a config value to a sorted denylist, dropping critical tools."""
    if not isinstance(raw, list):
        return []
    names = {str(x).strip() for x in raw if str(x).strip()}
    return sorted(names - CRITICAL_TOOLS)


def tools_disabled_set(cfg: Mapping[str, Any]) -> set[str]:
    """Return disabled built-in tool names from agent config (critical stripped)."""
    return set(normalize_tools_disabled(cfg.get("tools_disabled")))


def plugin_tool_explicitly_disabled(
    cfg: Mapping[str, Any],
    *,
    plugin_id: str,
    tool_name: str,
) -> bool:
    """True when agent config opts out of a plugin tool with ``enabled: false``."""
    raw_plugins = cfg.get("plugins")
    if not isinstance(raw_plugins, dict):
        return False
    plugin_entry = raw_plugins.get(plugin_id)
    if not isinstance(plugin_entry, dict):
        return False
    tools_map = plugin_entry.get("tools")
    if not isinstance(tools_map, dict):
        return False
    tool_cfg = tools_map.get(tool_name)
    if not isinstance(tool_cfg, dict) or "enabled" not in tool_cfg:
        return False
    return not bool(tool_cfg.get("enabled"))


def plugin_tools_disabled_names(
    cfg: Mapping[str, Any],
    *,
    registered_tools: list[tuple[str, str]],
    global_plugins: Mapping[str, bool] | None = None,
) -> set[str]:
    """Plugin tool names that should be hidden from the model."""
    global_plugins = global_plugins or {}
    out: set[str] = set()
    for plugin_id, tool_name in registered_tools:
        if global_plugins.get(plugin_id) is False:
            continue
        if plugin_tool_explicitly_disabled(cfg, plugin_id=plugin_id, tool_name=tool_name):
            out.add(tool_name)
    return out


def effective_tools_disabled(
    cfg: Mapping[str, Any],
    *,
    registered_plugin_tools: list[tuple[str, str]] | None = None,
    global_plugins: Mapping[str, bool] | None = None,
) -> set[str]:
    """Builtin denylist plus explicitly disabled plugin tool names."""
    disabled = tools_disabled_set(cfg)
    if registered_plugin_tools:
        disabled |= plugin_tools_disabled_names(
            cfg,
            registered_tools=registered_plugin_tools,
            global_plugins=global_plugins,
        )
    return disabled - CRITICAL_TOOLS


def builtin_tool_available(
    name: str,
    *,
    agent_cfg: Mapping[str, Any],
    mobile_enabled: bool = False,
) -> bool:
    """Whether a catalog builtin is expected to be mounted for this agent."""
    if name in _MOBILE_TOOLS:
        return mobile_enabled
    if name in _MEMORY_TOOLS:
        mem = agent_cfg.get("memory")
        if isinstance(mem, dict) and isinstance(mem.get("memory_enabled"), bool):
            return bool(mem["memory_enabled"])
        return True
    if name in _MEDIA_TOOLS:
        media = agent_cfg.get("media_generation")
        if media is False:
            return False
        return not (isinstance(media, dict) and media.get("enabled") is False)
    if name in _WEB_SEARCH_TOOLS:
        return agent_cfg.get("web_search_tools") is not False
    if name == "acp_runner":
        acp = agent_cfg.get("acp")
        if isinstance(acp, dict):
            return bool(acp.get("tool_enabled", False))
        return False
    return True


__all__ = [
    "BUILTIN_TOOL_CATALOG",
    "BuiltinToolEntry",
    "CRITICAL_TOOLS",
    "builtin_tool_available",
    "effective_tools_disabled",
    "normalize_tools_disabled",
    "plugin_tool_explicitly_disabled",
    "plugin_tools_disabled_names",
    "tools_disabled_set",
]
