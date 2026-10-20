"""Tests for octop_harness.slash runtime dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from octop_harness.slash import (
    BufferSink,
    RuntimeSlashCtx,
    SlashCommand,
    build_runtime_dispatcher,
)


async def test_stop_invokes_cancel_callback() -> None:
    dispatcher = build_runtime_dispatcher()
    cancel = MagicMock()
    sink = BufferSink()
    ctx = RuntimeSlashCtx(
        agent_id="a1",
        thread_id="t1",
        locale="zh",
        cancel_stream=cancel,
    )
    await dispatcher.handle(SlashCommand("stop", ""), ctx, sink)
    cancel.assert_called_once_with("a1", "t1")
    assert "停止" in "\n".join(sink.lines)


async def test_model_set_and_read() -> None:
    dispatcher = build_runtime_dispatcher()
    sink = BufferSink()
    models: dict[str, str] = {}

    def _get(_agent_id: str, thread_id: str) -> str | None:
        return models.get(thread_id)

    def _set(_agent_id: str, thread_id: str, model: str) -> None:
        models[thread_id] = model

    ctx = RuntimeSlashCtx(
        agent_id="a1",
        thread_id="t1",
        locale="en",
        get_thread_model=_get,
        set_thread_model=_set,
    )
    await dispatcher.handle(SlashCommand("model", "openai/gpt-4o"), ctx, sink)
    assert models["t1"] == "openai/gpt-4o"
    assert "openai/gpt-4o" in "\n".join(sink.lines)


async def test_skills_list() -> None:
    dispatcher = build_runtime_dispatcher()
    sink = BufferSink()
    list_skills = AsyncMock(return_value=[{"name": "pdf", "description": "read", "enabled": True}])
    ctx = RuntimeSlashCtx(
        agent_id="a1",
        thread_id="t1",
        locale="zh",
        list_skills=list_skills,
    )
    await dispatcher.handle(SlashCommand("skills", ""), ctx, sink)
    assert "pdf" in "\n".join(sink.lines)
