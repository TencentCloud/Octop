"""Unit tests for plugin tool default-on / merge helpers."""

from __future__ import annotations

from octop.infra.agents.plugin_tool_defaults import (
    expand_plugin_tools_default_on,
    merge_plugins_tool_settings,
)


def test_merge_preserves_config_when_toggling_enabled() -> None:
    existing = {
        "echo-tool": {
            "tools": {
                "echo_message": {"enabled": False, "config": {"prefix": "hi"}},
            }
        }
    }
    merged = merge_plugins_tool_settings(
        existing,
        {"echo-tool": {"tools": {"echo_message": {"enabled": True}}}},
    )
    tool = merged["echo-tool"]["tools"]["echo_message"]
    assert tool["enabled"] is True
    assert tool["config"] == {"prefix": "hi"}


def test_expand_default_on_fills_missing_tools() -> None:
    out = expand_plugin_tools_default_on(
        {},
        registered_tools=[("echo-tool", "echo_message")],
        global_plugins={"echo-tool": True},
    )
    assert out["echo-tool"]["tools"]["echo_message"]["enabled"] is True
