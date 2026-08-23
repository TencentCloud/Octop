"""Unit tests for built-in tool catalog / tools_disabled normalization."""

from __future__ import annotations

from octop.infra.agents.tool_catalog import (
    BUILTIN_TOOL_CATALOG,
    CRITICAL_TOOLS,
    builtin_tool_available,
    effective_tools_disabled,
    normalize_tools_disabled,
    plugin_tools_disabled_names,
    tools_disabled_set,
)


def test_critical_tools_are_in_catalog() -> None:
    names = {e.name for e in BUILTIN_TOOL_CATALOG}
    assert names >= CRITICAL_TOOLS


def test_normalize_strips_critical_and_sorts() -> None:
    assert normalize_tools_disabled(["web_fetch", "read_file", "execute", "ls"]) == [
        "execute",
        "web_fetch",
    ]


def test_tools_disabled_set_from_config() -> None:
    assert tools_disabled_set({"tools_disabled": ["execute", "task"]}) == {"execute"}
    assert tools_disabled_set({}) == set()
    assert tools_disabled_set({"tools_disabled": "nope"}) == set()


def test_plugin_tools_disabled_names() -> None:
    cfg = {
        "plugins": {
            "demo": {"tools": {"greet": {"enabled": False}, "wave": {"enabled": True}}},
        }
    }
    registered = [("demo", "greet"), ("demo", "wave"), ("other", "x")]
    assert plugin_tools_disabled_names(cfg, registered_tools=registered) == {"greet"}


def test_effective_tools_disabled_merges_builtin_and_plugin() -> None:
    cfg = {
        "tools_disabled": ["web_fetch", "ls"],
        "plugins": {"demo": {"tools": {"greet": {"enabled": False}}}},
    }
    out = effective_tools_disabled(
        cfg,
        registered_plugin_tools=[("demo", "greet")],
        global_plugins={"demo": True},
    )
    assert out == {"web_fetch", "greet"}


def test_plugin_tools_ignored_when_plugin_globally_disabled() -> None:
    cfg = {"plugins": {"demo": {"tools": {"greet": {"enabled": False}}}}}
    assert (
        plugin_tools_disabled_names(
            cfg,
            registered_tools=[("demo", "greet")],
            global_plugins={"demo": False},
        )
        == set()
    )


def test_builtin_tool_available_gates() -> None:
    assert builtin_tool_available("web_fetch", agent_cfg={}) is True
    assert builtin_tool_available("mobile_tap", agent_cfg={}, mobile_enabled=False) is False
    assert builtin_tool_available("mobile_tap", agent_cfg={}, mobile_enabled=True) is True
    assert (
        builtin_tool_available(
            "acp_runner",
            agent_cfg={"acp": {"tool_enabled": False}},
        )
        is False
    )
    assert (
        builtin_tool_available(
            "generate_image",
            agent_cfg={"media_generation": False},
        )
        is False
    )
    assert (
        builtin_tool_available(
            "tavily_search",
            agent_cfg={"web_search_tools": False},
        )
        is False
    )
