"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

from octop_gateway.models import InboundMessage, MessageEvent


async def echo_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    """Simple echo processor for testing."""
    yield MessageEvent.text(f"Echo: {msg.text}")
    yield MessageEvent.completed()


async def noop_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    """Processor that yields nothing."""
    yield MessageEvent.completed()
