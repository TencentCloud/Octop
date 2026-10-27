"""Team dispatch briefing travels through configurable, not the conversation.

Scenario: a team host dispatches work to a member. The briefing must reach the
member's leading system prompt even when the harness bootstrap middleware (which
drops in-conversation system messages on a fresh agent's first turn) runs first,
and it must never be written into the member thread.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from octop.infra.agents.middleware.team_dispatch import (
    CONFIG_KEY,
    TeamDispatchBriefingMiddleware,
    _with_briefing,
)

BRIEFING = "[团队派工，不是用户在直接问你]\n你是这个专家团队的成员。"
_MODEL = FakeListChatModel(responses=["ok"])


def _patch_configurable(monkeypatch: Any, value: Any) -> None:
    monkeypatch.setattr(
        "octop.infra.agents.middleware.team_dispatch.get_config",
        lambda: {"configurable": {} if value is None else {CONFIG_KEY: value}},
    )


def _request(system: str | None, messages: list[Any] | None = None) -> ModelRequest[Any]:
    return ModelRequest(
        model=_MODEL,
        messages=list(messages) if messages else [HumanMessage("任务正文")],
        system_message=SystemMessage(content=system) if system is not None else None,
        tools=[],
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


def test_with_briefing_no_configurable_key_leaves_request_untouched(monkeypatch: Any) -> None:
    """场景：非团队派工轮次没有 briefing。预期：request 原样返回，system prompt 不变。"""
    _patch_configurable(monkeypatch, None)
    req = _request("agent-prompt")

    out = _with_briefing(req)

    assert out is req
    assert out.system_message is not None
    assert out.system_message.text == "agent-prompt"


def test_with_briefing_appends_to_existing_system_prompt(monkeypatch: Any) -> None:
    """场景：成员已有 system prompt。预期：briefing 追加在其后，原文不丢。"""
    _patch_configurable(monkeypatch, BRIEFING)
    req = _request("agent-prompt")

    out = _with_briefing(req)

    text = out.system_message.text if out.system_message else ""
    assert text.startswith("agent-prompt")
    assert "团队派工" in text
    assert out.messages == req.messages


def test_with_briefing_without_system_prompt_becomes_the_system_prompt(monkeypatch: Any) -> None:
    """场景：成员没有 system prompt。预期：briefing 自己成为队首 system。"""
    _patch_configurable(monkeypatch, BRIEFING)
    req = _request(None)

    out = _with_briefing(req)

    assert out.system_message is not None
    assert out.system_message.text.strip().startswith("[团队派工")


def test_with_briefing_blank_value_is_ignored(monkeypatch: Any) -> None:
    """场景：briefing 是空白字符串。预期：不注入空 block，request 不变。"""
    _patch_configurable(monkeypatch, "   \n ")
    req = _request("agent-prompt")

    out = _with_briefing(req)

    assert out is req


def test_with_briefing_is_stateless_across_model_calls(monkeypatch: Any) -> None:
    """场景：一个 turn 内多次 model call 传入各自的 request。预期：每次只加一份，不累积。"""
    _patch_configurable(monkeypatch, BRIEFING)
    base = _request("agent-prompt")

    first = _with_briefing(base)
    second = _with_briefing(base)

    assert (first.system_message.text if first.system_message else "").count("团队派工") == 1
    assert (second.system_message.text if second.system_message else "").count("团队派工") == 1


class _BootstrapLike(AgentMiddleware):
    """Mirror octop_harness BootstrapMiddleware: drop conversation system messages."""

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        messages = [m for m in request.messages if not isinstance(m, SystemMessage)]
        blocks: list[Any] = (
            list(request.system_message.content_blocks) if request.system_message else []
        )
        blocks.append({"type": "text", "text": "\n\n<BOOTSTRAP.md>"})
        return handler(
            request.override(
                system_message=SystemMessage(content_blocks=blocks),
                messages=messages,
            )
        )


class _Capture(AgentMiddleware):
    def __init__(self) -> None:
        self.system = ""
        self.message_types: list[str] = []

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        self.system = request.system_message.text if request.system_message else ""
        self.message_types = [type(m).__name__ for m in request.messages]
        return handler(request)


@tool
def echo(x: str) -> str:
    """Echo back."""
    return x


def test_briefing_survives_bootstrap_on_first_turn(monkeypatch: Any) -> None:
    """场景：首轮 bootstrap 在外层先丢掉对话内 system message。

    预期：briefing 因为走 configurable，不受影响，仍然进入队首 system prompt；
    对话里只剩任务本身，没有 SystemMessage。
    """
    _patch_configurable(monkeypatch, BRIEFING)
    capture = _Capture()
    agent = create_agent(
        model=FakeListChatModel(responses=["ok"]),
        tools=[],
        middleware=[_BootstrapLike(), TeamDispatchBriefingMiddleware(), capture],
        system_prompt="agent-prompt",
    )

    agent.invoke(
        {"messages": [HumanMessage("任务正文")]},
        config={"configurable": {"thread_id": "t~member"}},
    )

    assert "团队派工" in capture.system
    assert "<BOOTSTRAP.md>" in capture.system
    assert "SystemMessage" not in capture.message_types
