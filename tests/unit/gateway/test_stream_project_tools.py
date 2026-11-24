"""tests/unit/gateway/test_stream_project_tools.py"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage
from octop_gateway.channels.weixin.channel import WeixinAccountConfig, WeixinChannel, WeixinConfig
from octop_gateway.models import ChannelSubject, ImageContent, MessageEventType
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
        yield {
            "type": "tool_call_chunk",
            "name": "generate_image",
            "args": "{}",
            "id": "generate-1",
        }
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


@pytest.mark.parametrize("same_content", [False, True])
@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("upload_failed", [False, True])
@pytest.mark.asyncio
async def test_explicit_send_is_not_suppressed_without_delivery_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    same_content: bool,
    resume: bool,
    upload_failed: bool,
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    agent = FakeHarnessAgent()
    agent.use_workspace_dir(tmp_path / "workspace")
    path = "generated/images/result.png"
    await agent.workspace.aupload_bytes(path, b"PNG")

    generated = {
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
    sent = {
        "type": "tool_result",
        "messages": [
            ToolMessage(
                name="send_file_to_user",
                tool_call_id="send-2",
                content=json.dumps(
                    {
                        "type": "image",
                        "path": path,
                        "filename": "result.png",
                        "source": {
                            "type": "url",
                            "url": path,
                            "media_type": "image/png",
                        },
                    }
                ),
            )
        ],
    }

    async def stream(*_args, **_kwargs):
        await agent.workspace.aupload_bytes(path, b"PNG")
        yield {
            "type": "tool_call_chunk",
            "name": "generate_image",
            "args": "{}",
            "index": 0,
            "id": "generate-1",
        }
        yield generated
        if not same_content:
            await agent.workspace.aupload_bytes(path, b"NEW")
        yield {
            "type": "tool_call_chunk",
            "name": "send_file_to_user",
            "args": "{}",
            "index": 1,
            "id": "send-2",
        }
        yield sent
        yield generated  # History replay is still suppressed by tool-call id.
        yield sent

    manager = MagicMock()
    manager.get_agent.return_value = agent
    manager.stream = stream
    manager.resume_hitl = stream
    for _turn in range(2):
        account = WeixinAccountConfig(account_id="test-account", token="test-token")
        channel = WeixinChannel(MagicMock(), config=WeixinConfig(accounts=[account]))
        channel._mark_content = AsyncMock()
        channel._send_media_fallback_unlocked = AsyncMock()
        item = {"type": 2, "image_item": {"media": {}}}
        channel._upload_media_part = AsyncMock(side_effect=[None if upload_failed else item, item])
        api = SimpleNamespace(
            send_items=AsyncMock(return_value=SimpleNamespace(context_token="", data={}))
        )
        channel._api = AsyncMock(return_value=api)
        subject = ChannelSubject(
            subject_id="test-user", metadata={"account_id": account.account_id}
        )
        media = []
        events = (
            project_resume_stream(manager, "agent-1", "thread-1", [], locale="zh")
            if resume
            else project_stream(manager, "agent-1", {}, locale="zh")
        )
        async for event in events:
            if event.type == MessageEventType.MESSAGE:
                media.extend(part for part in event.content if isinstance(part, ImageContent))
                # Keep projection and real channel delivery interleaved, including
                # the upload-failure fallback that returns without raising.
                await channel._deliver_event(subject, event)

        assert [part.data for part in media] == ["UE5H", "UE5H" if same_content else "TkVX"]
        assert channel._upload_media_part.await_count == 2
        assert channel._send_media_fallback_unlocked.await_count == int(upload_failed)
        assert api.send_items.await_count == (1 if upload_failed else 2)


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
