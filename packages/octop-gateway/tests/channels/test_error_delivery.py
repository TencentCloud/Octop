"""Every built-in adapter delivers host failures and terminates the failed turn.

Only outbound platform calls are mocked; channel processing, buffering, stream
termination and success/failure finalization are real. No SDK connects anywhere.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop_gateway.channels import _CLASS_NAMES, SUPPORTED_CHANNEL_KINDS, _load_channel
from octop_gateway.constraints import ChannelConstraints, TypingKeepalive
from octop_gateway.models import ChannelSubject, InboundMessage, MessageEvent, TextContent

ERROR = "模型服务鉴权失败。请检查 API Key 是否正确、是否过期。"
TIMEOUT_ERROR = "请求超时，请稍后重试。"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [*sorted(SUPPORTED_CHANNEL_KINDS), "qq-stream"])
@pytest.mark.parametrize("partial", [False, True], ids=["before-output", "after-partial-output"])
@pytest.mark.parametrize("mode", ["auth", "timeout"])
@pytest.mark.parametrize("ending", ["completed", "eof", "hang", "cleanup-hang"])
async def test_error_is_visible_terminal_and_next_turn_recovers(
    kind: str, partial: bool, mode: str, ending: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = True
    host_finalized = False
    tail_entered = False
    keepalives: list[TypingKeepalive] = []
    streaming = kind == "qq-stream"
    kind = kind.removesuffix("-stream")
    error = ERROR if mode == "auth" else TIMEOUT_ERROR

    async def processor(_message: InboundMessage) -> AsyncIterator[MessageEvent]:
        nonlocal host_finalized, tail_entered
        if failed:
            if partial:
                yield MessageEvent.delta("处理到一半。\n\n")
            try:
                if mode == "timeout":
                    raise TimeoutError("simulated provider timeout")
                raise PermissionError("simulated provider 401")
            except (PermissionError, TimeoutError):
                # The host maps provider exceptions to ERROR then COMPLETED.
                yield MessageEvent.error_event(error)
                tail_entered = True
                if ending == "hang":
                    await asyncio.Event().wait()
            finally:
                try:
                    if ending == "cleanup-hang":
                        await asyncio.Event().wait()
                finally:
                    assert all(keepalive._task is None for keepalive in keepalives)
                    host_finalized = True
            if ending == "eof":
                return
        else:
            yield MessageEvent.text("恢复成功。")
        yield MessageEvent.completed()

    module = importlib.import_module(f"octop_gateway.channels.{kind}")
    config_type = getattr(module, _CLASS_NAMES[kind].replace("Channel", "Config"))
    config = config_type.from_dict(
        {
            "media_dir": str(tmp_path),
            "c2c_streaming": streaming,
            "stream_throttle_ms": 0,
            "stream_hold_keepalive_s": 0,
            "show_thinking": False,
            "show_tool_hints": False,
            "show_typing": False,
        }
    )
    channel = _load_channel(kind)(
        processor=processor,
        config=config,
        constraints=ChannelConstraints(
            reply_timeout=0, typing_keepalive_interval=0.001, show_thinking=False, show_tool_hints=False
        ),
    )

    def track_keepalive(**kwargs: Any) -> TypingKeepalive:
        keepalive = TypingKeepalive(**kwargs)
        keepalives.append(keepalive)
        return keepalive

    monkeypatch.setattr("octop_gateway.channel.TypingKeepalive", track_keepalive)
    sent = AsyncMock()
    monkeypatch.setattr(channel, "_send_text", sent)
    monkeypatch.setattr(channel, "_acquire_rate_slot", AsyncMock())
    monkeypatch.setattr(channel, "_send_typing_indicator", AsyncMock())
    finalized = MagicMock(wraps=channel._finalize_inbound)
    monkeypatch.setattr(channel, "_finalize_inbound", finalized)
    subject = ChannelSubject(
        subject_id="1001",
        chat_type="direct",
        metadata={
            "msg_id": "inbound-1",
            "user_openid": "1001",
            "msg_type": "c2c",
        },
    )
    message = InboundMessage(
        channel_id=channel.channel_id,
        channel_type=kind,
        channel_subject=subject,
        content=[TextContent(text="模拟故障验证")],
        metadata={**subject.metadata, "session_id": "session-1", "task_id": "task-1", "message_id": "message-1"},
    )
    monkeypatch.setattr(channel, "parse_inbound", lambda _payload: message)
    ws = MagicMock(reply_stream=AsyncMock())
    frames: list[Any] = []
    a2a = AsyncMock()
    if kind == "wecom":
        channel._ws_client = ws
        message.metadata.update({"_ws_client": ws, "_frame": {"body": {}}})
    elif kind == "qq":

        async def send_frame(frame: Any) -> str:
            frames.append(frame)
            return "outbound-1"

        monkeypatch.setattr(channel, "_send_stream_frame", send_frame)
    elif kind == "xiaoyi":
        channel._connected = True
        monkeypatch.setattr(channel, "_send_to_session", a2a)

    monkeypatch.setattr("octop_gateway.utils.STREAM_CLOSE_TIMEOUT", 0.02, raising=False)
    await asyncio.wait_for(channel.handle_inbound(message), timeout=0.5)
    if kind == "wecom":
        assert ws.reply_stream.await_args.kwargs["finish"] is True
        assert ws.reply_stream.await_args.kwargs["content"] == error
    elif kind == "xiaoyi":
        wire = [json.loads(call.args[1]["msgDetail"])["result"] for call in a2a.await_args_list]
        assert any(error in json.dumps(result, ensure_ascii=False) for result in wire)
        assert [result["status"]["state"] for result in wire if result["kind"] == "status-update"] == ["failed"]
        assert wire[-1]["final"] is True
    else:
        assert sent.await_args.args[1] == error
    if kind != "wecom":
        assert finalized.call_args.kwargs["processing_succeeded"] is False
    assert host_finalized
    assert not tail_entered
    if kind == "qq":
        assert channel._active_c2c_stream is None
        if streaming:
            assert channel._should_stream_c2c(subject)

    failed = False
    await asyncio.wait_for(channel.handle_inbound(message), timeout=3)
    if kind == "wecom":
        assert ws.reply_stream.await_args.kwargs["finish"] is True
        assert "恢复成功" in ws.reply_stream.await_args.kwargs["content"]
    elif kind == "xiaoyi":
        wire = [json.loads(call.args[1]["msgDetail"])["result"] for call in a2a.await_args_list]
        assert [result["status"]["state"] for result in wire if result["kind"] == "status-update"][-1] == "completed"
    elif kind == "qq" and frames:
        assert "恢复成功" in str(frames[-1])
    else:
        assert "恢复成功" in sent.await_args.args[1]
    if kind != "wecom":
        assert finalized.call_args.kwargs["processing_succeeded"] is True
    print(
        json.dumps(
            {
                "channel": kind,
                "streaming": streaming,
                "partial": partial,
                "mode": mode,
                "ending": ending,
                "error": error,
                "failure_visible": True,
                "failure_terminated": True,
                "recovery_succeeded": True,
            },
            ensure_ascii=False,
        )
    )
