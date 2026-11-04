"""tests/unit/gateway/test_stream_project_tools.py"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.types import Overwrite
from octop_gateway.models import FileContent
from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.protocols.langgraph import LangGraphProtocol

from octop.infra.gateway.process.stream_project import (
    enrich_tool_stream_chunk,
    project_resume_stream,
    project_stream,
)


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


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("message_object", [False, True])
@pytest.mark.parametrize("include_current_file", [False, True])
async def test_project_stream_only_delivers_current_turn_media(
    tmp_path: Path, resume: bool, message_object: bool, include_current_file: bool
) -> None:
    workspace = BackendWorkspace(LocalShellBackend(root_dir=str(tmp_path)), str(tmp_path))
    messages = []
    for call_id, filename in [("prior-call", "prior.txt"), ("current-call", "current.txt")]:
        if call_id == "current-call" and not include_current_file:
            continue
        await workspace.aupload_bytes(filename, filename.encode())
        content = [
            {
                "type": "file",
                "source": {
                    "type": "url",
                    "url": (tmp_path / filename).as_uri(),
                    "media_type": "text/plain",
                },
                "filename": filename,
            }
        ]
        if message_object:
            messages.append(
                ToolMessage(content=content, tool_call_id=call_id, name="send_file_to_user")
            )
        else:
            messages.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": call_id,
                    "name": "send_file_to_user",
                }
            )

    async def graph_stream(*_args, **_kwargs):
        yield {
            "type": "messages",
            "data": (
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "id": "current-call",
                            "name": "send_file_to_user" if include_current_file else "execute",
                            "args": "{",
                            "index": 0,
                        }
                    ],
                ),
                {"langgraph_node": "agent"},
            ),
        }
        yield {
            "type": "messages",
            "data": (
                AIMessageChunk(content="", tool_call_chunks=[{"id": "", "args": "}", "index": 0}]),
                {"langgraph_node": "agent"},
            ),
        }
        replay = {"type": "updates", "data": {"middleware": {"messages": Overwrite(messages)}}}
        yield replay
        yield replay

    protocol = LangGraphProtocol(graph=SimpleNamespace(astream=graph_stream))
    manager = SimpleNamespace(
        stream=lambda *_args: protocol.stream([], {}),
        resume_hitl=lambda *_args: protocol.resume_stream("thread-1", [], {}),
        get_agent=lambda _agent_id: SimpleNamespace(workspace=workspace),
    )
    if resume:
        events = project_resume_stream(manager, "agent-1", "thread-1", [])
    else:
        events = project_stream(manager, "agent-1", {"thread_id": "thread-1"})
    filenames = [
        part.filename
        async for event in events
        for part in event.content
        if isinstance(part, FileContent)
    ]
    assert filenames == (["current.txt"] if include_current_file else [])
