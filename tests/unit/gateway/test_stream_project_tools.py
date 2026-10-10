"""tests/unit/gateway/test_stream_project_tools.py"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from langchain_core.messages import ToolMessage
from octop_harness.backends.workspace import BackendWorkspace

from octop.infra.gateway.process import stream_project
from octop.infra.gateway.process.stream_project import enrich_tool_stream_chunk


def test_enrich_tool_stream_chunk_adds_display_name():
    chunk = {"type": "tool_call_chunk", "name": "read_file", "args": "{"}
    out = enrich_tool_stream_chunk(chunk, "zh")
    assert out["display_name"] == "读取文件"
    assert out["name"] == "read_file"


def test_enrich_tool_stream_chunk_ignores_non_tool():
    chunk = {"type": "token", "content": "hi"}
    assert enrich_tool_stream_chunk(chunk, "zh") is chunk


def test_tool_start_event_carries_localized_hint():
    from octop_gateway.models import MessageEvent

    from octop.i18n import channel_tool_hint_start

    label = "读取文件"
    event = MessageEvent.tool_start(
        label,
        tool_hint_text=channel_tool_hint_start(label, "zh"),
    )
    assert event.metadata["tool_hint_text"] == channel_tool_hint_start(label, "zh")
    assert "正在调用工具" in event.metadata["tool_hint_text"]


def _send_file_result(tool_call_id: str, path: Path) -> ToolMessage:
    block = {
        "type": "file",
        "source": {"type": "url", "url": path.as_uri(), "media_type": "text/markdown"},
        "filename": path.name,
    }
    return ToolMessage(content=[block], name="send_file_to_user", tool_call_id=tool_call_id)


async def _delivered_filenames(
    chunks: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
) -> list[str]:
    from octop_gateway.models import MessageEventType

    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(root), virtual_mode=False), str(root)
    )
    monkeypatch.setattr(stream_project, "harness_workspace_for_agent", lambda *_a: workspace)

    async def _chunks() -> AsyncIterator[dict[str, Any]]:
        for chunk in chunks:
            yield chunk

    names: list[str] = []
    async for event in stream_project._project_chunks(
        _chunks(),
        agent_manager=cast(Any, object()),
        agent_id="agent-1",
        locale="en",
        usage_tracker=None,
        history_tracker=None,
        projection_state=None,
        hitl_coordinator=None,
        hitl_ctx=None,
    ):
        if event.type == MessageEventType.MESSAGE:
            names.extend(getattr(part, "filename", "") for part in event.content)
    return names


def _tool_call_chunk(call_id: str, name: str) -> dict[str, Any]:
    return {"type": "tool_call_chunk", "id": call_id, "name": name, "args": "{}", "index": 0}


@pytest.mark.asyncio
async def test_replayed_history_does_not_resend_earlier_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mid-turn history rewrite must not push files delivered in earlier turns."""
    old = tmp_path / "old.md"
    old.write_text("old", encoding="utf-8")
    chunks = [
        _tool_call_chunk("call-read", "read_file"),
        {
            "type": "tool_result",
            "node": "tools",
            "messages": [ToolMessage("x", tool_call_id="call-read", name="read_file")],
        },
        # SummarizationMiddleware / MediaOffloadMiddleware re-emit the whole history.
        {
            "type": "tool_result",
            "node": "SummarizationMiddleware.before_model",
            "messages": [
                _send_file_result("call-old", old),
                ToolMessage("x", tool_call_id="call-read", name="read_file"),
            ],
        },
    ]

    assert await _delivered_filenames(chunks, monkeypatch, tmp_path) == []


@pytest.mark.asyncio
async def test_replay_keeps_pushing_this_turns_new_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = tmp_path / "old.md"
    old.write_text("old", encoding="utf-8")
    new = tmp_path / "new.md"
    new.write_text("new", encoding="utf-8")
    chunks = [
        _tool_call_chunk("call-new", "send_file_to_user"),
        {"type": "tool_result", "node": "tools", "messages": [_send_file_result("call-new", new)]},
        {
            "type": "tool_result",
            "node": "MediaOffloadMiddleware.before_model",
            "messages": [_send_file_result("call-old", old), _send_file_result("call-new", new)],
        },
    ]

    assert await _delivered_filenames(chunks, monkeypatch, tmp_path) == ["new.md"]
