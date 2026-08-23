"""Unit tests for harness-agent plugin loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness_agent.plugins import (
    PluginRegistry,
    build_plugin_tools,
    collect_plugin_tool_configs,
    load_plugin_dir,
)
from langchain_core.tools import StructuredTool

from octop.infra.agents.plugin_tool_names import (
    sanitize_plugin_tool_name,
    sanitize_plugin_tool_names,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def test_load_echo_tool_plugin() -> None:
    loaded = load_plugin_dir(_FIXTURE, install_deps=False)
    assert loaded.manifest.id == "echo-tool"
    assert len(loaded.tools) == 1
    assert loaded.tools[0].name == "echo_message"


def test_build_plugin_tools_respects_enabled_flag() -> None:
    load_plugin_dir(_FIXTURE, install_deps=False)
    disabled = build_plugin_tools(
        agent_plugins={"echo-tool": {"tools": {"echo_message": {"enabled": False}}}},
    )
    assert disabled == []
    enabled = build_plugin_tools(
        agent_plugins={"echo-tool": {"tools": {"echo_message": {"enabled": True}}}},
    )
    assert len(enabled) == 1
    assert isinstance(enabled[0], StructuredTool)
    assert enabled[0].name == "echo_message"


def test_expand_plugin_tools_default_on_without_agent_config() -> None:
    """Octop default-on expansion makes tools bind without an agent opt-in."""
    from octop.infra.agents.plugin_tool_defaults import expand_plugin_tools_default_on

    load_plugin_dir(_FIXTURE, install_deps=False)
    expanded = expand_plugin_tools_default_on(
        {},
        registered_tools=[("echo-tool", "echo_message")],
        global_plugins={},
    )
    tools = build_plugin_tools(agent_plugins=expanded, global_plugins={})
    assert len(tools) == 1
    assert tools[0].name == "echo_message"

    still_off = build_plugin_tools(
        agent_plugins=expand_plugin_tools_default_on(
            {},
            registered_tools=[("echo-tool", "echo_message")],
            global_plugins={"echo-tool": False},
        ),
        global_plugins={"echo-tool": False},
    )
    assert still_off == []

    # Explicit opt-out still wins.
    opted_out = expand_plugin_tools_default_on(
        {"echo-tool": {"tools": {"echo_message": {"enabled": False}}}},
        registered_tools=[("echo-tool", "echo_message")],
    )
    assert build_plugin_tools(agent_plugins=opted_out) == []


def test_collect_plugin_tool_configs() -> None:
    cfg = collect_plugin_tool_configs(
        {
            "echo-tool": {
                "tools": {
                    "echo_message": {
                        "enabled": True,
                        "config": {"prefix": ">> "},
                    },
                },
            },
        },
    )
    assert cfg == {"echo_message": {"prefix": ">> "}}


def _make_tool(name: str, description: str = "demo tool") -> StructuredTool:
    def _fn(message: str) -> str:
        return message

    return StructuredTool.from_function(func=_fn, name=name, description=description)


def test_sanitize_ascii_name_passthrough() -> None:
    tool = _make_tool("echo_message", "original description")
    result = sanitize_plugin_tool_names([tool])
    assert result[0].name == "echo_message"
    assert result[0].description == "original description"


def test_sanitize_chinese_name_transliterates_to_pinyin() -> None:
    pytest.importorskip("pypinyin")
    tool = _make_tool("天气查询", "查询指定城市的天气")
    result = sanitize_plugin_tool_names([tool])
    assert result[0].name == "tianqichaxun"
    assert result[0].description == "[原名: 天气查询] 查询指定城市的天气"


def test_sanitize_mixed_name_keeps_ascii_parts() -> None:
    pytest.importorskip("pypinyin")
    assert sanitize_plugin_tool_name("获取weather信息") == "huoquweatherxinxi"


def test_sanitize_collision_gets_suffix() -> None:
    first = sanitize_plugin_tool_name("天气查询")
    second = sanitize_plugin_tool_name("天气查询", used={first})
    assert second != first
    assert second == f"{first}_2"
    # A legal name that is already reserved also gets deduped.
    assert sanitize_plugin_tool_name("echo_message", used={"echo_message"}) == "echo_message_2"


def test_sanitize_truncates_overlong_names() -> None:
    long_name = "很" * 80
    sanitized = sanitize_plugin_tool_name(long_name)
    assert len(sanitized) <= 64


def test_sanitize_falls_back_to_underscores_without_pypinyin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def _blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pypinyin" or name.startswith("pypinyin."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    sanitized = sanitize_plugin_tool_name("天气查询")
    assert sanitized
    assert sanitized.isascii()
    assert all(ch.isalnum() or ch in "_-" for ch in sanitized)


def test_sanitize_plugin_tools_reserved_names() -> None:
    tool = _make_tool("echo_message")
    sanitize_plugin_tool_names([tool], reserved={"echo_message"})
    assert tool.name == "echo_message_2"


def test_build_plugin_tools_then_sanitize_keeps_config_keys_original() -> None:
    pytest.importorskip("pypinyin")
    from harness_agent.plugins.manifest import PluginManifest
    from harness_agent.plugins.registry import LoadedPlugin, ToolRegistration

    manifest = PluginManifest(id="demo", version="1.0.0", name="Demo", kind="tool", entry="main.py")
    PluginRegistry().register(
        LoadedPlugin(
            manifest=manifest,
            source_path=Path("."),
            tools=[
                ToolRegistration(
                    plugin_id="demo",
                    name="发送邮件",
                    fn=lambda to: to,
                    description="发送一封邮件",
                ),
                ToolRegistration(
                    plugin_id="demo",
                    name="echo_message",
                    fn=lambda text: text,
                    description="echo",
                ),
            ],
        ),
    )
    tools = build_plugin_tools(
        agent_plugins={
            "demo": {
                "tools": {
                    "发送邮件": {"enabled": True},
                    "echo_message": {"enabled": True},
                },
            },
        },
    )
    sanitized = sanitize_plugin_tool_names(tools)
    names = {t.name for t in sanitized}
    assert "fasongyoujian" in names  # pinyin of 发送邮件
    assert "echo_message" in names
    descriptions = {t.name: t.description for t in sanitized}
    assert descriptions["fasongyoujian"].startswith("[原名: 发送邮件]")
    # Config lookup still keyed by the original plugin-side name.
    assert collect_plugin_tool_configs(
        {"demo": {"tools": {"发送邮件": {"enabled": True, "config": {"a": 1}}}}},
    ) == {"发送邮件": {"a": 1}}
