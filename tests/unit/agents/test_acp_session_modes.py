"""Managed experts pick an ACP session mode per underlying agent."""

from octop.infra.agents.acp.session_modes import (
    approval_for_session,
    resolve_managed_session_mode,
    session_modes,
    yolo_session_mode_id,
)


def test_codebuddy_modes_include_plan_and_yolo() -> None:
    ids = [mode.id for mode in session_modes("codebuddy")]
    assert ids == ["default", "acceptEdits", "plan", "auto", "bypassPermissions"]
    assert yolo_session_mode_id("codebuddy") == "bypassPermissions"
    assert session_modes("claude_code") == session_modes("codebuddy")


def test_opencode_modes_are_its_primary_agents() -> None:
    assert [mode.id for mode in session_modes("opencode")] == ["build", "plan"]
    assert session_modes("cursor_cli") == []


def test_qwen_code_modes_match_advertised_ids() -> None:
    assert [mode.id for mode in session_modes("qwen_code")] == [
        "plan",
        "default",
        "auto-edit",
        "auto",
        "yolo",
    ]
    assert yolo_session_mode_id("qwen_code") == "yolo"


def test_explicit_plan_beats_a_yolo_expert_default() -> None:
    config = {
        "managed_runner": "codebuddy",
        "managed_permission_mode": "yolo",
        "managed_session_mode": "bypassPermissions",
    }
    assert resolve_managed_session_mode(explicit="plan", config=config) == "plan"
    assert resolve_managed_session_mode(stored="craft", config=config) == "bypassPermissions"
    assert (
        resolve_managed_session_mode(
            config={"managed_runner": "codebuddy", "managed_permission_mode": "yolo"}
        )
        == "bypassPermissions"
    )
    assert yolo_session_mode_id("codex") == "full-access"


def test_approval_follows_the_mode_when_the_agent_publishes_one() -> None:
    assert approval_for_session("full-access", "ask", runner="codex") == "yolo"
    assert approval_for_session("plan", "yolo", runner="codebuddy") == "ask"
    assert approval_for_session("build", "yolo", runner="opencode") == "yolo"
    assert approval_for_session("", "yolo", runner="cursor_cli") == "yolo"
