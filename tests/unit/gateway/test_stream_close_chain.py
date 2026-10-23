import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from octop_gateway.models import ChannelSubject, InboundMessage, MessageEvent, TextContent

from octop.infra.gateway.channels.telegram_bridge import TelegramBridge, _ButtonReply, _ButtonState


def _bridge_with(inner):
    msg = InboundMessage(
        channel_id="tg",
        channel_type="telegram",
        tenant_id="agent",
        channel_subject=ChannelSubject(subject_id="chat"),
        content=[TextContent(text="hi")],
        metadata={"user_id": "u", "chat_id": "chat"},
    )
    hitl = SimpleNamespace(resolve_ask_pending=lambda *a, **k: None)
    gateway = SimpleNamespace(
        channel_manager=SimpleNamespace(get_channel=lambda _: None),
        processor=SimpleNamespace(hitl_coordinator=hitl),
        thread_registry=SimpleNamespace(get_bound_thread_id=lambda _: None),
        _repos=SimpleNamespace(
            agent_repo=SimpleNamespace(get=lambda _: SimpleNamespace(user_id=1))
        ),
        _agent_manager=SimpleNamespace(cancel_stream=AsyncMock()),
    )
    return TelegramBridge(gateway, inner, "tg"), msg


@pytest.mark.asyncio
async def test_bridge_closes_inner_stream_when_consumer_closes_early():
    closed = asyncio.Event()

    async def inner(msg):
        try:
            yield MessageEvent.text("a")
            yield MessageEvent.text("b")
            await asyncio.sleep(3600)
        finally:
            closed.set()

    bridge, msg = _bridge_with(inner)
    it = bridge(msg)
    first = await it.__anext__()
    assert first.content[0].text == "a"
    assert not closed.is_set()
    await it.aclose()
    assert closed.is_set(), "inner stream must finalize with the outer close"


@pytest.mark.asyncio
async def test_bridge_inner_cancelled_stream_runs_cleanup():
    closed = asyncio.Event()

    async def inner(msg):
        try:
            yield MessageEvent.text("a")
            await asyncio.sleep(3600)
        finally:
            closed.set()

    bridge, msg = _bridge_with(inner)

    async def consume():
        async for _ in bridge(msg):
            await asyncio.sleep(3600)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # 取消传播会打断 finally 中的 await，内层 aclose 由事件循环终结器
    # 异步补完——修复保证它必然被调度（而非留给 GC 悬置）。
    await asyncio.wait_for(closed.wait(), timeout=1)
    assert closed.is_set()


def test_button_validation_failure_is_logged(caplog):
    bridge, msg = _bridge_with(lambda m: None)
    state = _ButtonState(
        owner_id=None,
        thread_id=None,
        pending_id=None,
        question_index=0,
        model_page=None,
        text="",
    )
    reply = _ButtonReply(**msg.model_dump(), button_state=state)
    with caplog.at_level(logging.WARNING, logger="octop.infra.gateway.channels.telegram_bridge"):
        assert bridge._button_reject_reason_call(reply) is not None
    assert any("button reply dropped" in rec.message for rec in caplog.records)
