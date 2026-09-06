"""Unit tests for plugin tool default-on / merge helpers."""

from __future__ import annotations

from octop.infra.agents.plugin_tool_defaults import (
    agent_plugin_enabled,
    expand_plugin_tools_default_on,
    merge_plugins_enabled_settings,
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


def test_agent_plugin_enabled_defaults_true_when_missing() -> None:
    assert agent_plugin_enabled({}, "echo-tool") is True
    assert agent_plugin_enabled({"echo-tool": {"tools": {}}}, "echo-tool") is True
    assert agent_plugin_enabled({"echo-tool": {"enabled": False}}, "echo-tool") is False


def test_plugin_level_toggle_preserves_tool_config() -> None:
    existing = {
        "echo-tool": {
            "tools": {
                "echo_message": {
                    "enabled": False,
                    "config": {"prefix": "kept"},
                }
            }
        }
    }
    disabled = merge_plugins_enabled_settings(existing, {"echo-tool": False})
    assert disabled["echo-tool"]["enabled"] is False
    assert disabled["echo-tool"]["tools"] == existing["echo-tool"]["tools"]
    enabled = merge_plugins_enabled_settings(disabled, {"echo-tool": True})
    assert enabled["echo-tool"]["tools"] == existing["echo-tool"]["tools"]
