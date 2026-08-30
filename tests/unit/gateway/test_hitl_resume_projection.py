"""Dashboard HITL resume keeps the thread-history projection complete."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


@pytest.mark.asyncio
async def test_hitl_resume_records_final_answer_in_thread_history() -> None:
    messages = [
        HumanMessage(content="plan a trip", id="user-1"),
        AIMessage(
            content="",
            id="ask-1",
            tool_calls=[
                {
                    "name": "ask_user_question",
                    "args": {"questions": []},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="nature, premium, mixed", tool_call_id="call-1", id="answer-1"),
        AIMessage(content="Here is the completed itinerary.", id="final-1"),
    ]

    async def _resume(*_args: object, **_kwargs: object):
        yield {"type": "state_snapshot", "data": {"messages": messages}}
        yield {
            "type": "usage",
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        }

    agent_manager = MagicMock()
    agent_manager.resume_hitl = _resume
    thread_registry = MagicMock()
    history_repo = MagicMock()
    usage_repo = MagicMock()
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=usage_repo,
        thread_message_repo=history_repo,
        gateway=None,
    )

    chunks = [
        chunk
        async for chunk in processor.iter_hitl_resume_chunks(
            agent_id="agent-1",
            thread_id="thread-1",
            user_id=7,
            decisions=[{"type": "respond", "message": "nature, premium, mixed"}],
        )
    ]

    assert [chunk["type"] for chunk in chunks] == ["state_snapshot", "usage"]
    thread_registry.touch_last_active.assert_called_once_with("thread-1")
    history_repo.append_if_ready.assert_called_once()
    thread_id, projected = history_repo.append_if_ready.call_args.args
    assert thread_id == "thread-1"
    assert [item.message_id for item in projected] == [
        "user-1",
        "ask-1",
        "answer-1",
        "final-1",
    ]
    assert json.loads(projected[-1].message_json)["data"]["content"] == (
        "Here is the completed itinerary."
    )
    usage_repo.record.assert_called_once()
