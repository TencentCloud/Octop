"""Ask / Plan / Craft helpers."""

from __future__ import annotations

from octop.infra.agents.conversation_mode import (
    HOST_READ_TOOLS,
    execute_user_message,
    is_plan_execute_utterance,
    plan_relpath_from_artifact,
    resolve_conversation_mode,
    stamp_conversation_mode,
)


def test_resolve_explicit_wins() -> None:
    assert resolve_conversation_mode(explicit="ask", thread_mode="plan") == "ask"
    assert resolve_conversation_mode(explicit="nope", thread_mode="plan") == "craft"


def test_resolve_sticky_when_explicit_absent() -> None:
    assert resolve_conversation_mode(thread_mode="plan") == "plan"
    assert resolve_conversation_mode() == "craft"


def test_plan_relpath_from_artifact() -> None:
    assert (
        plan_relpath_from_artifact("plans/add-ask-plan-modes.md") == "plans/add-ask-plan-modes.md"
    )
    assert plan_relpath_from_artifact("/workspace/plans/foo.md") == "plans/foo.md"
    assert plan_relpath_from_artifact("SOUL.md") == ""
    assert plan_relpath_from_artifact("plans/中文.md") == ""


def test_execute_user_message() -> None:
    assert execute_user_message("plans/foo.md", "zh") == "请按 plans/foo.md 执行"
    assert execute_user_message("plans/foo.md", "en") == "Execute plans/foo.md"


def test_is_plan_execute_utterance() -> None:
    assert is_plan_execute_utterance("按计划执行")
    assert is_plan_execute_utterance("执行计划")
    assert is_plan_execute_utterance("execute the plan")
    assert is_plan_execute_utterance("start executing")
    assert is_plan_execute_utterance("请按 plans/foo.md 执行")
    assert is_plan_execute_utterance("Execute plans/foo.md")
    assert not is_plan_execute_utterance("执行")
    assert not is_plan_execute_utterance("execute")
    assert not is_plan_execute_utterance("帮我看看这个计划写得对不对")
    assert not is_plan_execute_utterance("go")
    assert not is_plan_execute_utterance("start")
    assert not is_plan_execute_utterance("go on")


def test_stamp_ask_clears_skills_and_mcp() -> None:
    request: dict[str, object] = {
        "skills": ["docker"],
        "mcp_servers": ["github"],
        "configurable": {"skills": ["docker"]},
    }
    stamp_conversation_mode(request, "ask")
    assert request["skills"] == []
    assert request["mcp_servers"] == []
    cfg = request["configurable"]
    assert isinstance(cfg, dict)
    assert cfg["conversation_mode"] == "ask"
    assert cfg["conversation_mode_extra_read_tools"] == list(HOST_READ_TOOLS)
    assert cfg["skills"] == []
