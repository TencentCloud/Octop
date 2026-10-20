"""Preemptible cancel for HarnessAgent.stream."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any

import pytest

from octop_harness.agent import HarnessAgent
from octop_harness.request import ChatRequest


def _bare_agent() -> HarnessAgent:
    """Minimal HarnessAgent shell for cancel/stream tests (no graph compile)."""

    class _Config:
        def pick_default_model_ref(self) -> str:
            return "test/model"

    agent = object.__new__(HarnessAgent)
    agent._cancel_events = {}
    agent._thread_models = {}
    agent._agent_id = None
    agent._config = _Config()  # type: ignore[assignment]
    # stream() pins the runtime so a concurrent close() waits for it.
    agent._lifecycle_lock = threading.Lock()
    agent._in_flight = 0
    agent._close_pending = False
    return agent


@pytest.mark.asyncio
async def test_cancel_preempts_blocked_anext() -> None:
    """cancel() must unblock a stream stuck in await, not wait for the next chunk."""
    started = asyncio.Event()

    async def blocked_stream() -> AsyncIterator[str]:
        yield "first"
        started.set()
        await asyncio.Event().wait()  # blocked forever until aclose/cancel
        yield "should-not-appear"

    agent = _bare_agent()
    cancel_event = asyncio.Event()
    agent._cancel_events["t1"] = cancel_event

    chunks: list[str] = []

    async def consume() -> None:
        async for c in agent._iter_until_cancelled(blocked_stream(), cancel_event):
            chunks.append(c)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=1.0)
    agent.cancel("t1")
    await asyncio.wait_for(task, timeout=1.0)

    assert chunks == ["first"]


@pytest.mark.asyncio
async def test_iter_completes_normally_without_cancel() -> None:
    async def short_stream() -> AsyncIterator[str]:
        yield "a"
        yield "b"

    agent = _bare_agent()
    event = asyncio.Event()

    chunks = [c async for c in agent._iter_until_cancelled(short_stream(), event)]
    assert chunks == ["a", "b"]


@pytest.mark.asyncio
async def test_stream_cancel_preempts_blocked_protocol() -> None:
    """stream() + cancel(thread_id) must preempt a blocked protocol.stream await."""
    started = asyncio.Event()

    class _Proto:
        async def stream(
            self,
            _messages: Any,
            _config: Any,
            **_kwargs: Any,
        ) -> AsyncIterator[str]:
            yield "first"
            started.set()
            await asyncio.Event().wait()
            yield "should-not-appear"

    agent = _bare_agent()

    def _prepare_call(
        _request: ChatRequest | str | dict[str, Any],
        _protocol: str | None,
    ) -> tuple[Any, Any, _Proto]:
        return [], {}, _Proto()

    agent._prepare_call = _prepare_call  # type: ignore[method-assign]

    chunks: list[str] = []

    async def consume() -> None:
        async for c in agent.stream({"messages": "hi", "thread_id": "t-e2e"}):
            chunks.append(c)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=1.0)
    agent.cancel("t-e2e")
    await asyncio.wait_for(task, timeout=1.0)

    assert chunks == ["first"]
    assert "t-e2e" not in agent._cancel_events
