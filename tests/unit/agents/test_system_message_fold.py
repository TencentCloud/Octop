from __future__ import annotations

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_anthropic.chat_models import _format_messages
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from octop.infra.agents.middleware.system_messages import (
    SystemMessageFoldMiddleware,
    fold_system_messages,
)


def _request(messages, system: str | None = "member prompt") -> ModelRequest:
    return ModelRequest(
        model=ChatOpenAI(model="qwen3.6-plus", api_key="test"),
        messages=messages,
        system_message=SystemMessage(system) if system is not None else None,
    )


def test_request_without_system_messages_is_untouched() -> None:
    request = _request([HumanMessage("hi")])
    assert fold_system_messages(request) is request


def test_team_briefing_joins_the_member_system_prompt() -> None:
    folded = fold_system_messages(_request([SystemMessage("team briefing"), HumanMessage("task")]))
    assert folded.system_message is not None
    assert folded.system_message.text == "member prompt\n\nteam briefing"
    assert [m.type for m in folded.messages] == ["human"]


def test_later_dispatch_keeps_turn_order_and_every_briefing() -> None:
    folded = fold_system_messages(
        _request(
            [
                SystemMessage("briefing 1"),
                HumanMessage("task 1"),
                AIMessage("done 1"),
                SystemMessage("briefing 2"),
                HumanMessage("task 2"),
            ]
        )
    )
    assert folded.system_message is not None
    assert folded.system_message.text == "member prompt\n\nbriefing 1\n\nbriefing 2"
    assert [m.text for m in folded.messages] == ["task 1", "done 1", "task 2"]


def test_briefing_becomes_the_system_prompt_when_there_is_none() -> None:
    folded = fold_system_messages(
        _request([SystemMessage("team briefing"), HumanMessage("task")], system=None)
    )
    assert folded.system_message is not None
    assert folded.system_message.text == "team briefing"


def test_folded_request_is_accepted_by_the_anthropic_formatter() -> None:
    request = _request(
        [
            SystemMessage("briefing 1"),
            HumanMessage("task 1"),
            AIMessage("done 1"),
            SystemMessage("briefing 2"),
            HumanMessage("task 2"),
        ]
    )
    assert request.system_message is not None
    with pytest.raises(ValueError, match="non-consecutive system messages"):
        _format_messages([request.system_message, *request.messages])

    folded = fold_system_messages(request)
    assert folded.system_message is not None
    system, messages = _format_messages([folded.system_message, *folded.messages])
    assert system
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]


async def test_middleware_hands_the_folded_request_to_the_model() -> None:
    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> str:
        seen.append(request)
        return "ok"

    result = await SystemMessageFoldMiddleware().awrap_model_call(
        _request([SystemMessage("team briefing"), HumanMessage("task")]),
        handler,  # type: ignore[arg-type]
    )
    assert result == "ok"
    assert [m.type for m in seen[0].messages] == ["human"]
