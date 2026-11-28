"""Gateway shutdown drains in-flight turns before releasing resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.gateway.gateway import Gateway


def _gateway(events: list[str]) -> Gateway:
    gateway = Gateway(agent_manager=MagicMock(), repos=MagicMock())

    processor = MagicMock()
    processor.begin_shutdown = MagicMock(side_effect=lambda: events.append("begin_shutdown"))
    processor.wait_inflight_turns = AsyncMock(
        side_effect=lambda timeout=5.0: events.append(f"wait_inflight_turns:{timeout}")
    )
    processor.flush_unpersisted_turns = AsyncMock(
        side_effect=lambda: events.append("flush_unpersisted_turns")
    )

    channel_manager = AsyncMock()
    channel_manager.stop = AsyncMock(side_effect=lambda: events.append("channel_stop"))

    gateway._processor = processor
    gateway._channel_manager = channel_manager
    return gateway


@pytest.mark.asyncio
async def test_shutdown_drains_and_flushes_in_order() -> None:
    events: list[str] = []
    gateway = _gateway(events)

    assert gateway.is_shutting_down is False
    await gateway.shutdown(drain_timeout=1.5)

    assert events == [
        "begin_shutdown",
        "wait_inflight_turns:1.5",
        "channel_stop",
        "flush_unpersisted_turns",
    ]
    assert gateway.is_shutting_down is True
    assert gateway._processor is None


@pytest.mark.asyncio
async def test_begin_shutdown_is_idempotent() -> None:
    gateway = Gateway(agent_manager=MagicMock(), repos=MagicMock())
    processor = MagicMock()
    gateway._processor = processor

    gateway.begin_shutdown()
    gateway.begin_shutdown()

    assert processor.begin_shutdown.call_count == 1
    assert gateway.is_shutting_down is True


@pytest.mark.asyncio
async def test_shutdown_without_processor_still_closes() -> None:
    gateway = Gateway(agent_manager=MagicMock(), repos=MagicMock())

    await gateway.shutdown()

    assert gateway.is_shutting_down is True
    assert gateway._processor is None
