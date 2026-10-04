"""Unit tests for chat SSE / WebSocket chunk serialization."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from octop.api.routers.chat.serialize import (
    _iter_session_jsonl_sources,
    _serialize_history_message,
)
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


def test_serialize_history_message_omits_artifact_key_when_absent() -> None:
    msg = ToolMessage(content="found", tool_call_id="call_1", name="search")
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert "artifact" not in entry["content"][0]


class _SessionRegistry:
    """Registry stub: no live workspace, so the on-disk fallback is exercised."""

    def __init__(self, workspace_dir: Path) -> None:
        self._workspace_dir = workspace_dir

    def workspace_for_agent(self, agent_id: str) -> None:
        return None

    def resolve_workspace_dir(self, agent_id: str) -> Path:
        return self._workspace_dir


class _SessionServer:
    def __init__(self, workspace_dir: Path) -> None:
        self.app_runtime = type(
            "_Runtime",
            (),
            {"agent_registry": _SessionRegistry(workspace_dir)},
        )()


@pytest.mark.asyncio
async def test_local_session_log_fallback_reads_off_the_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The on-disk ``sessions/*.jsonl`` fallback must not read on the event loop.

    The workspace-backend branch above it already runs in ``asyncio.to_thread``;
    reading every session file synchronously on the loop stalls every other
    request while chat history loads.
    """
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s1.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    server = _SessionServer(tmp_path)

    read_threads: list[str] = []
    real_read_text = Path.read_text

    def _spy(self: Path, *args: Any, **kwargs: Any) -> str:
        read_threads.append(threading.current_thread().name)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _spy)

    sources = await _iter_session_jsonl_sources(server, "agent", user=object())

    assert sources == [("s1.jsonl", '{"a": 1}\n')]
    event_loop_thread = threading.current_thread().name
    assert read_threads, "the fallback should have read at least one session log"
    assert all(name != event_loop_thread for name in read_threads)
