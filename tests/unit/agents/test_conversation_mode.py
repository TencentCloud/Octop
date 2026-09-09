"""Unit tests for conversation mode parse + turn-scoped tool overlays (Sprint 0 / #616)."""

from __future__ import annotations

import pytest

from octop.infra.agents.conversation_mode import (
    DEFAULT_CONVERSATION_MODE,
    conversation_mode_tools_disabled,
    parse_conversation_mode,
    resolve_conversation_mode,
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
    for name in ("ls", "read_file", "glob", "grep"):
        assert name not in disabled, name
    assert "write_todos" in disabled  # Ask is Q&A only — no plan todos
    assert "search_knowledge" not in disabled
    assert "web_fetch" not in disabled
    # CRITICAL ``task`` must still be turn-blocked so Plan/Ask cannot escape via subagents.
    for name in ("task", "acp_runner", "ask_agent"):
        assert name in disabled, name


def test_craft_tools_disabled_is_empty() -> None:
    assert conversation_mode_tools_disabled("craft") == frozenset()


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
    # Ask is stricter than Plan on write_todos.
    assert "write_todos" in conversation_mode_tools_disabled("ask")


def test_resolve_conversation_mode_priority() -> None:
    """explicit → thread sticky → agent default → craft."""
    assert resolve_conversation_mode(explicit="ask") == "ask"
    assert resolve_conversation_mode(explicit=None, thread_override="plan") == "plan"
    assert (
        resolve_conversation_mode(explicit=None, thread_override=None, agent_default="ask") == "ask"
    )
    assert resolve_conversation_mode(explicit=None) == "craft"
    # Unknown explicit stays craft (compat); does not fall through.
    assert resolve_conversation_mode(explicit="nope", agent_default="ask") == "craft"
    # Explicit craft wins over agent ask.
    assert resolve_conversation_mode(explicit="craft", agent_default="ask") == "craft"


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
