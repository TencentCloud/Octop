"""tests/unit/gateway/test_stream_project_tools.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage
from octop_gateway.models import ImageContent, MessageEventType
from tests.support.fakes import FakeHarnessAgent

from octop.i18n import tr
from octop.infra.gateway.process.stream_project import (
    enrich_tool_stream_chunk,
    project_resume_stream,
    project_stream,
)


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("available,locale", [(True, "zh"), (False, "zh"), (False, "en")])
@pytest.mark.asyncio
async def test_generated_media_projection_uses_workspace_and_user_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, available: bool, locale: str, resume: bool
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    agent = FakeHarnessAgent()
    agent.use_workspace_dir(tmp_path / "workspace")
    path = "generated/images/result.png"
    if available:
        await agent.workspace.aupload_bytes(path, b"PNG")
    result = {
        "type": "tool_result",
        "messages": [
            ToolMessage(
                name="generate_image",
                tool_call_id="generate-1",
                content=json.dumps(
                    {
                        "type": "image_gen_tool_result",
                        "images": [{"path": path, "mediaType": "image/png"}],
                    }
                ),
            )
        ],
    }

    async def stream(*_args, **_kwargs):
        yield {"type": "tool_call_chunk", "name": "generate_image", "args": "{}"}
        yield result
        yield result  # Harness history replay must not resend media or errors.

    manager = MagicMock()
    manager.get_agent.return_value = agent
    manager.stream = stream
    manager.resume_hitl = stream
    events = [
        event
        async for event in (
            project_resume_stream(manager, "agent-1", "thread-1", [], locale=locale)
            if resume
            else project_stream(manager, "agent-1", {}, locale=locale)
        )
    ]
    deliveries = [
        event
        for event in events
        if event.type in {MessageEventType.MESSAGE, MessageEventType.ERROR}
    ]

    assert len(deliveries) == 1
    if available:
        assert deliveries[0].type == MessageEventType.MESSAGE
        part = deliveries[0].content[0]
        assert isinstance(part, ImageContent)
        assert part.data == "UE5H"
        assert not part.url
    else:
        assert deliveries[0].type == MessageEventType.ERROR
        assert deliveries[0].error == tr("channel.media_delivery_failed", locale)
        assert path not in deliveries[0].model_dump_json()


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
