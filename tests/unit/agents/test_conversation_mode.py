"""Unit tests for conversation mode parse + turn-scoped tool overlays (Sprint 0 / #616)."""

from __future__ import annotations

import pytest

from octop.infra.agents.conversation_mode import (
    DEFAULT_CONVERSATION_MODE,
    conversation_mode_tools_disabled,
    merge_tools_disabled,
    parse_conversation_mode,
)


def test_parse_conversation_mode_accepts_ask_plan_craft() -> None:
    assert parse_conversation_mode("ask") == "ask"
    assert parse_conversation_mode("plan") == "plan"
    assert parse_conversation_mode("craft") == "craft"


def test_parse_conversation_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        parse_conversation_mode("agent")
    with pytest.raises(ValueError):
        parse_conversation_mode("")
    with pytest.raises(ValueError):
        parse_conversation_mode(123)


def test_parse_conversation_mode_none_defaults_to_craft() -> None:
    assert parse_conversation_mode(None) == "craft"
    assert parse_conversation_mode(None) == DEFAULT_CONVERSATION_MODE


def test_ask_tools_disabled_includes_mutating_builtins() -> None:
    disabled = conversation_mode_tools_disabled("ask")
    for name in (
        "write_file",
        "edit_file",
        "execute",
        "write_env_file",
        "send_file_to_user",
        "browser_use",
        "desktop_screenshot",
        "generate_image",
        "generate_video",
        "mobile_tap",
        "mobile_swipe",
        "mobile_launch_app",
        "mobile_screenshot",
        "mobile_ui_dump",
        "mobile_handoff_to_user",
    ):
        assert name in disabled, name


def test_ask_tools_disabled_keeps_explore_tools_blocks_orchestration_escape() -> None:
    disabled = conversation_mode_tools_disabled("ask")
    for name in ("ls", "read_file", "glob", "grep", "write_todos"):
        assert name not in disabled, name
    assert "search_knowledge" not in disabled
    assert "web_fetch" not in disabled
    # CRITICAL ``task`` must still be turn-blocked so Plan/Ask cannot escape via subagents.
    for name in ("task", "acp_runner", "ask_agent"):
        assert name in disabled, name


def test_craft_tools_disabled_is_empty() -> None:
    assert conversation_mode_tools_disabled("craft") == frozenset()


def test_merge_unions_agent_disabled_with_ask_overlay() -> None:
    agent = frozenset({"web_fetch", "tavily_search"})
    merged = merge_tools_disabled(agent, "ask")
    assert "web_fetch" in merged
    assert "tavily_search" in merged
    assert "write_file" in merged
    assert "execute" in merged
    assert "task" in merged
    # Ask never re-enables: craft merge keeps only agent disables
    assert merge_tools_disabled(agent, "craft") == agent


def test_plan_tools_disabled_matches_ask_overlay() -> None:
    """Plan uses the same denylist as Ask (mutating + no orchestration escape)."""
    ask = conversation_mode_tools_disabled("ask")
    plan = conversation_mode_tools_disabled("plan")
    assert plan == ask


def test_plan_allows_write_todos_and_forbids_mutating_and_delegation() -> None:
    """Plan keeps write_todos; blocks execute/write/edit and task/ACP escape."""
    disabled = conversation_mode_tools_disabled("plan")
    assert "write_todos" not in disabled
    assert "execute" in disabled
    assert "write_file" in disabled
    assert "edit_file" in disabled
    assert "task" in disabled
    assert "acp_runner" in disabled
    assert "ask_agent" in disabled


def test_default_conversation_mode_from_config() -> None:
    from octop.infra.agents.conversation_mode import default_conversation_mode_from_config

    assert default_conversation_mode_from_config(None) == "craft"
    assert default_conversation_mode_from_config({}) == "craft"
    assert default_conversation_mode_from_config({"default_conversation_mode": "ask"}) == "ask"
    with pytest.raises(ValueError):
        default_conversation_mode_from_config({"default_conversation_mode": "agent"})


def test_normalize_config_default_conversation_mode() -> None:
    from octop.infra.agents.conversation_mode import (
        normalize_config_default_conversation_mode,
    )

    assert normalize_config_default_conversation_mode({"x": 1}) == {"x": 1}
    assert normalize_config_default_conversation_mode({"default_conversation_mode": "plan"}) == {
        "default_conversation_mode": "plan"
    }
    cleaned = normalize_config_default_conversation_mode(
        {"default_conversation_mode": None, "x": 1}
    )
    assert "default_conversation_mode" not in cleaned
    assert cleaned["x"] == 1
    with pytest.raises(ValueError):
        normalize_config_default_conversation_mode({"default_conversation_mode": "nope"})


def test_apply_default_conversation_mode() -> None:
    from octop.infra.agents.conversation_mode import apply_default_conversation_mode

    cfg: dict[str, object] = {"x": 1}
    assert apply_default_conversation_mode(cfg, None) == {"x": 1}
    apply_default_conversation_mode(cfg, "ask")
    assert cfg["default_conversation_mode"] == "ask"
