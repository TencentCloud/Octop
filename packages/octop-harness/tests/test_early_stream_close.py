"""Early stream close must finalize nested generators in the consuming task.

Closing an outer async generator does not close the generators it forwards with
``async for`` / ``yield``. Those leftovers used to be finalized in a new task,
so ``session_header_scope`` failed to reset ``harness_session_id``.
"""

from __future__ import annotations

import asyncio
import gc
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.llm.session_header import current_session_id, session_header_scope
from octop_harness.manager import HarnessAgentManager
from octop_harness.request import ChatRequest
from octop_harness.slash.core import RuntimeSlashCtx
from octop_harness.slash.runtime import iter_with_runtime_slash

_THREAD = "t-early"


def _config(tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        default_model="openai/gpt-4o",
        providers=[
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[ModelConfig(id="gpt-4o", enabled=True)],
            )
        ],
    )


class _Proto:
    def __init__(self) -> None:
        self.closed = {"stream": False, "resume": False}

    async def stream(self, messages: Any, config: dict[str, Any], **kwargs: Any) -> AsyncIterator[dict[str, str]]:
        del messages, config, kwargs
        try:
            yield {"type": "token", "content": "1"}
            yield {"type": "token", "content": "2"}
        finally:
            self.closed["stream"] = True

    async def resume_stream(
        self,
        thread_id: str,
        decisions: list[dict[str, Any]],
        config: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, str]]:
        del thread_id, decisions, config, kwargs
        try:
            yield {"type": "token", "content": "1"}
            yield {"type": "token", "content": "2"}
        finally:
            self.closed["resume"] = True


@pytest.fixture
def manager_with_agent(tmp_path: Path) -> tuple[HarnessAgentManager, str, _Proto]:
    with patch("octop_harness.agent.deepagents.create_deep_agent", return_value=MagicMock()):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), init_workspace=False)
    agent_id = next(iter(mgr._registry.agent_ids()))
    proto = _Proto()
    mgr._registry.get(agent_id).agent._protocols["langgraph"] = proto
    return mgr, agent_id, proto


async def _stop_early(gen: AsyncIterator[Any]) -> list[Any]:
    seen: list[Any] = []
    async for chunk in gen:
        seen.append(chunk)
        break
    await gen.aclose()
    return seen


async def _loop_errors_after_gc() -> list[BaseException]:
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


def _session_still_bound() -> bool:
    return current_session_id() == _THREAD


def _slash_ctx() -> RuntimeSlashCtx:
    return RuntimeSlashCtx(agent_id="a1", thread_id=_THREAD, locale="en")


async def test_slash_wrapper_resets_session_on_early_close() -> None:
    async def body(_request: ChatRequest) -> AsyncIterator[int]:
        with session_header_scope(_THREAD):
            yield 1
            yield 2

    gen = iter_with_runtime_slash(ChatRequest(messages="hi", thread_id=_THREAD), ctx=_slash_ctx(), stream=body)
    seen = await _stop_early(gen)

    assert seen == [1]
    assert not _session_still_bound()
    assert await _loop_errors_after_gc() == []


async def test_slash_wrapper_drains_without_loop_error() -> None:
    async def body(_request: ChatRequest) -> AsyncIterator[int]:
        with session_header_scope(_THREAD):
            yield 1
            yield 2

    gen = iter_with_runtime_slash(ChatRequest(messages="hi", thread_id=_THREAD), ctx=_slash_ctx(), stream=body)
    seen = [chunk async for chunk in gen]

    assert seen == [1, 2]
    assert not _session_still_bound()
    assert await _loop_errors_after_gc() == []


async def test_manager_stream_closes_nested_generators(
    manager_with_agent: tuple[HarnessAgentManager, str, _Proto],
) -> None:
    mgr, agent_id, proto = manager_with_agent
    gen = mgr.stream(agent_id, ChatRequest(messages="hi", thread_id=_THREAD))
    seen = await _stop_early(gen)

    assert seen == [{"type": "token", "content": "1"}]
    assert proto.closed["stream"] is True
    assert not _session_still_bound()
    assert await _loop_errors_after_gc() == []


async def test_manager_resume_hitl_closes_nested_generators(
    manager_with_agent: tuple[HarnessAgentManager, str, _Proto],
) -> None:
    mgr, agent_id, proto = manager_with_agent
    gen = mgr.resume_hitl(agent_id, _THREAD, [])
    seen = await _stop_early(gen)

    assert seen == [{"type": "token", "content": "1"}]
    assert proto.closed["resume"] is True
    assert not _session_still_bound()
    assert await _loop_errors_after_gc() == []
