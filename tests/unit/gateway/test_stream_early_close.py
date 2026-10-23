"""Early exit from a projected turn must close the harness stream in-task."""

from __future__ import annotations

import asyncio
import gc
from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import Any
from unittest.mock import MagicMock

from octop.infra.gateway.hitl.coordinator import iter_with_session_auto_approve
from octop.infra.gateway.process.stream_project import _project_chunks, project_stream

_BOUND = ContextVar("octop_test_stream_scope", default="")


def _manager() -> MagicMock:
    manager = MagicMock()
    manager.get_agent.side_effect = KeyError("missing")
    return manager


async def _source() -> AsyncIterator[dict[str, Any]]:
    token = _BOUND.set("th")
    try:
        yield {"type": "token", "content": "hi"}
        yield {"type": "hitl_required", "request": {}}
        yield {"type": "done"}
    finally:
        _BOUND.reset(token)


async def _loop_errors() -> list[BaseException]:
    loop = asyncio.get_running_loop()
    errors: list[BaseException] = []

    def handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            errors.append(exc)

    previous = loop.get_exception_handler()
    loop.set_exception_handler(handler)
    try:
        gc.collect()
        await asyncio.sleep(0.05)
    finally:
        loop.set_exception_handler(previous)
    return errors


async def test_hitl_return_closes_source_before_gc() -> None:
    gen = _project_chunks(
        _source(),
        agent_manager=_manager(),
        agent_id="a1",
        locale="en",
        usage_tracker=None,
        history_tracker=None,
        projection_state=None,
        hitl_coordinator=None,
        hitl_ctx=None,
    )
    seen = [event async for event in gen]

    assert [event.type for event in seen] == ["delta"]
    assert _BOUND.get() == ""
    assert await _loop_errors() == []


async def test_project_stream_aclose_closes_source() -> None:
    manager = _manager()
    manager.stream = lambda *_args, **_kwargs: _source()
    gen = project_stream(manager, "a1", {"thread_id": "th"})
    async for _event in gen:
        break
    await gen.aclose()

    assert _BOUND.get() == ""
    assert await _loop_errors() == []


async def test_auto_approve_wrapper_closes_source() -> None:
    gen = iter_with_session_auto_approve(
        _source(),
        thread_id="th",
        policies=None,
        resume=lambda _decisions: _source(),
    )
    async for _chunk in gen:
        break
    await gen.aclose()

    assert _BOUND.get() == ""
    assert await _loop_errors() == []
