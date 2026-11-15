"""``build_harness_request`` carries per-turn search credentials."""

from __future__ import annotations

from octop.infra.gateway.process.harness_request import build_harness_request


def test_tool_env_lands_in_configurable_for_content_turns() -> None:
    request = build_harness_request(
        thread_id="t1",
        user_id=7,
        source="web",
        text="hi",
        tool_env={"DEEPSEEK_API_KEY": "sk-personal"},
    )
    assert request["configurable"]["tool_env"] == {"DEEPSEEK_API_KEY": "sk-personal"}


def test_tool_env_lands_in_configurable_for_message_list_turns() -> None:
    request = build_harness_request(
        thread_id="t1",
        user_id=7,
        source="web",
        messages=[{"role": "user", "content": "hi"}],
        tool_env={"DEEPSEEK_API_KEY": "sk-personal"},
    )
    assert request["configurable"]["tool_env"] == {"DEEPSEEK_API_KEY": "sk-personal"}


def test_empty_tool_env_is_omitted() -> None:
    request = build_harness_request(
        thread_id="t1",
        user_id=7,
        source="web",
        text="hi",
        tool_env={},
    )
    assert "tool_env" not in request.get("configurable", {})
