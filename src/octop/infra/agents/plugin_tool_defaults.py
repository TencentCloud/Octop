"""Default-on semantics for plugin tools on agents.

Harness ``build_plugin_tools`` historically required an explicit
``enabled: true`` in ``config_json.plugins``. Product expectation is the
opposite: once a plugin is globally enabled, its tools are available unless
the agent opts out with ``enabled: false``.

Until ``orcakit-harness-agent`` ships matching defaults, Octop expands the
agent plugins map before calling ``build_plugin_tools``.
"""

from __future__ import annotations

from typing import Any


def merge_plugins_tool_settings(
    existing: object,
    incoming: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Merge plugin tool ``enabled`` / ``config`` without dropping other keys.

    Used by both Admin Plugins and Experts → Tools so they share one storage
    shape under ``config.plugins``.
    """
    out: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    for plugin_id, entry in incoming.items():
        if not isinstance(entry, dict):
            continue
        incoming_tools = entry.get("tools")
        if not isinstance(incoming_tools, dict):
            continue
        plugin_out: dict[str, Any] = (
            dict(out[plugin_id]) if isinstance(out.get(plugin_id), dict) else {}
        )
        tools_out: dict[str, Any] = (
            dict(plugin_out["tools"]) if isinstance(plugin_out.get("tools"), dict) else {}
        )
        for tool_name, tool_body in incoming_tools.items():
            if not isinstance(tool_body, dict):
                continue
            prev = tools_out.get(tool_name)
            merged: dict[str, Any] = dict(prev) if isinstance(prev, dict) else {}
            if "enabled" in tool_body:
                merged["enabled"] = bool(tool_body["enabled"])
            if "config" in tool_body and isinstance(tool_body["config"], dict):
                merged["config"] = tool_body["config"]
            elif "config" not in merged:
                merged["config"] = {}
            tools_out[str(tool_name)] = merged
        plugin_out["tools"] = tools_out
        out[str(plugin_id)] = plugin_out
    return out


def expand_plugin_tools_default_on(
    agent_plugins: dict[str, Any] | None,
    *,
    registered_tools: list[tuple[str, str]],
    global_plugins: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Return an agent plugins map where missing tools default to enabled.

    ``registered_tools`` is a list of ``(plugin_id, tool_name)`` from the
    process plugin registry. Globally disabled plugins are left untouched
    (``build_plugin_tools`` will still skip them).
    """
    global_plugins = global_plugins or {}
    out: dict[str, Any] = {}
    if isinstance(agent_plugins, dict):
        for plugin_id, entry in agent_plugins.items():
            out[str(plugin_id)] = dict(entry) if isinstance(entry, dict) else entry

    for plugin_id, tool_name in registered_tools:
        if global_plugins.get(plugin_id) is False:
            continue
        plugin_entry = out.get(plugin_id)
        if not isinstance(plugin_entry, dict):
            plugin_entry = {"tools": {}}
            out[plugin_id] = plugin_entry
        else:
            plugin_entry = dict(plugin_entry)
            out[plugin_id] = plugin_entry
        tools = plugin_entry.get("tools")
        tools = {} if not isinstance(tools, dict) else dict(tools)
        plugin_entry["tools"] = tools
        existing = tools.get(tool_name)
        if not isinstance(existing, dict):
            tools[tool_name] = {"enabled": True}
        elif "enabled" not in existing:
            tools[tool_name] = {**existing, "enabled": True}
    return out
