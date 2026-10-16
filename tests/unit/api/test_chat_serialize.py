"""Unit tests for chat SSE / WebSocket chunk serialization."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from octop.api.routers.chat.serialize import _serialize_history_message
from octop.api.routers.chat.sse import json_chunk_default


def test_json_chunk_default_serializes_langchain_messages() -> None:
    chunk = {
        "type": "state_update",
        "node": "BootstrapMiddleware.before_agent",
        "data": {
            "messages": [
                SystemMessage(content="bootstrap"),
                HumanMessage(content="hi"),
                AIMessage(content="hello"),
            ],
        },
    }
    payload = json.dumps(chunk, default=json_chunk_default)
    parsed = json.loads(payload)
    assert parsed["type"] == "state_update"
    assert len(parsed["data"]["messages"]) == 3
    assert parsed["data"]["messages"][0]["content"] == "bootstrap"


def test_json_chunk_default_keeps_tool_message_artifact() -> None:
    """Live WS/SSE frames must carry the offloaded octop_ui payload."""
    msg = ToolMessage(
        content='{"octop_ui": {"renderer": "bilibili_player"}, "data_ref": "artifact"}',
        tool_call_id="call_1",
        name="bilibili_search_anime",
        artifact={"results": [{"season_id": 1, "episodes": [{"index": 1}]}]},
    )
    payload = json.dumps({"type": "tool_result", "messages": [msg]}, default=json_chunk_default)
    parsed = json.loads(payload)
    wire_msg = parsed["messages"][0]
    assert wire_msg["artifact"]["results"][0]["season_id"] == 1
    assert "episodes" not in wire_msg["content"]


def test_serialize_history_message_includes_tool_artifact() -> None:
    msg = ToolMessage(
        content='{"octop_ui": {"renderer": "bilibili_player"}, "data_ref": "artifact"}',
        tool_call_id="call_1",
        name="bilibili_search_anime",
        artifact={"results": [{"season_id": 1}]},
    )
    entry = _serialize_history_message(msg)
    assert entry is not None
    block = entry["content"][0]
    assert block["type"] == "tool_result"
    assert block["artifact"]["results"][0]["season_id"] == 1


def test_serialize_history_message_includes_decision_savings() -> None:
    msg = AIMessage(
        content="done",
        usage_metadata={"input_tokens": 100, "output_tokens": 4, "total_tokens": 104},
        additional_kwargs={"context_usage": {"input_tokens": 100, "decision_saved": 5972}},
    )
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert entry["usage"]["decision_saved"] == 5972


def test_serialize_history_message_keeps_decision_savings_without_provider_usage() -> None:
    msg = AIMessage(
        content="done",
        additional_kwargs={"context_usage": {"decision_saved": 5972}},
    )
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert entry["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "decision_saved": 5972,
    }


def test_serialize_history_message_includes_decision() -> None:
    msg = AIMessage(
        content="done",
        additional_kwargs={
            "octop_decision": {
                "kind": "decision",
                "model": "typesafe/jev-1.13",
                "empty": False,
                "parts": [{"kind": "skill", "kept": [{"name": "pdf", "score": 0.9}]}],
            }
        },
    )
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert entry["decision"]["model"] == "typesafe/jev-1.13"
    assert entry["decision"]["parts"][0]["kept"][0]["name"] == "pdf"


def test_serialize_history_message_omits_artifact_key_when_absent() -> None:
    msg = ToolMessage(content="found", tool_call_id="call_1", name="search")
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert "artifact" not in entry["content"][0]
