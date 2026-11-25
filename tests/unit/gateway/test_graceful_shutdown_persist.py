"""Shutdown must persist the partial turn before the database closes."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage
from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher

THREAD_ID = "thr_shutdown"


def _messages_repo(tmp_path: Path) -> ThreadMessageRepo:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    user_id = UserRepo(db).create(username="u", password_hash="hash", role="user")
    AgentRepo(db).create(agent_id="agt", user_id=user_id, name="Agent")
    ThreadRepo(db).insert(
        thread_id=THREAD_ID,
        agent_id="agt",
        user_id=user_id,
        channel_type="dashboard",
        session_key="sk",
        last_active=0,
    )
    return ThreadMessageRepo(db)


def _processor(repo: ThreadMessageRepo, *, stream: Any) -> GlobalProcessor:
    agent_manager = MagicMock()
    agent_manager.stream = stream
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.default_mcp_servers = MagicMock(return_value=[])
    agent_manager.default_knowledge_base_ids = MagicMock(return_value=[])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable = MagicMock(return_value=False)
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.providers.resolve_model_for_multimodal_turn = MagicMock(
        side_effect=lambda ref, **_kwargs: ref
    )
    agent_manager.get_thread_model = MagicMock(return_value=None)
    agent_manager.get_row = MagicMock(return_value=None)
    # No file checkpoints: the harness agent exposes no capture hook here.
    agent_manager.get_agent = MagicMock(return_value=SimpleNamespace())

    thread_registry = MagicMock()
    thread_registry.get_thread = MagicMock(
        return_value=SimpleNamespace(
            agent_id="agt",
            conversation_mode=None,
            pending_plan_path=None,
            model_ref=None,
            reasoning_effort=None,
        )
    )
    thread_registry.get_or_create_by_key = AsyncMock(return_value=THREAD_ID)
    thread_registry.get_bound_thread_id = MagicMock(return_value=THREAD_ID)

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=SimpleNamespace(user_id=1))),
        user_repo=MagicMock(
            get=MagicMock(return_value=SimpleNamespace(locale="en", preferences_json=None))
        ),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        thread_message_repo=repo,
        gateway=None,
    )
    processor._schedule_auto_thread_title = MagicMock()  # type: ignore[method-assign]

    async def _build_request(_msg: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"messages": [HumanMessage(content="你好")]}

    processor._build_dashboard_request = _build_request  # type: ignore[method-assign]
    return processor


def _inbound() -> InboundMessage:
    return InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agt",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="你好")],
        metadata={"session_key": "sk", "thread_id": THREAD_ID},
    )


async def _spin(iterations: int = 20) -> None:
    for _ in range(iterations):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_shutdown_persists_partial_turn(tmp_path: Path) -> None:
    """A SIGTERM drain keeps the tokens streamed before the preemption."""
    repo = _messages_repo(tmp_path)
    release = asyncio.Event()
    preempted = asyncio.Event()

    async def _stream(*_args: Any, **_kwargs: Any) -> Any:
        yield {"type": "token", "content": "你好，"}
        yield {"type": "token", "content": "正在生成"}
        await release.wait()

    processor = _processor(repo, stream=_stream)

    def _cancel_stream(_agent_id: str, _thread_id: str) -> None:
        preempted.set()
        release.set()

    processor._agent_manager.cancel_stream = MagicMock(side_effect=_cancel_stream)

    async def _consume() -> list[dict[str, Any]]:
        return [chunk async for chunk in processor.iter_turn_chunks(_inbound())]

    task = asyncio.create_task(_consume())
    await _spin()
    assert not task.done()

    processor.begin_shutdown()
    await asyncio.wait_for(preempted.wait(), timeout=2.0)
    await processor.wait_inflight_turns(timeout=2.0)
    chunks = await asyncio.wait_for(task, timeout=2.0)
    await processor.flush_unpersisted_turns()

    assert chunks[-1]["type"] == "done"
    rows, _has_more = repo.page(THREAD_ID, limit=10)
    roles = [row.role for row in rows]
    assert roles == ["human", "ai"]
    assert "你好，正在生成" in rows[-1].message_json
    # Interrupted turns must not look like a completed reply.
    assert "turn_duration_ms" not in rows[-1].message_json


@pytest.mark.asyncio
async def test_stuck_stream_is_flushed_once(tmp_path: Path) -> None:
    """A stream that ignores preemption is flushed by the drain, exactly once."""
    repo = _messages_repo(tmp_path)
    never = asyncio.Event()

    async def _stream(*_args: Any, **_kwargs: Any) -> Any:
        yield {"type": "token", "content": "半截回复"}
        await never.wait()

    processor = _processor(repo, stream=_stream)
    processor._agent_manager.cancel_stream = MagicMock()

    async def _consume() -> None:
        async for _chunk in processor.iter_turn_chunks(_inbound()):
            pass

    task = asyncio.create_task(_consume())
    await _spin()
    processor.begin_shutdown()

    started = time.monotonic()
    await processor.wait_inflight_turns(timeout=0.05)
    assert time.monotonic() - started < 2.0
    assert processor._inflight_turns, "the stuck turn is still draining"

    await processor.flush_unpersisted_turns()
    rows, _has_more = repo.page(THREAD_ID, limit=10)
    assert [row.role for row in rows] == ["human", "ai"]
    assert "半截回复" in rows[-1].message_json

    # The stream finally runs after the flush: it must not write a second copy.
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    rows, _has_more = repo.page(THREAD_ID, limit=10)
    assert [row.role for row in rows] == ["human", "ai"]


@pytest.mark.asyncio
async def test_new_turn_rejected_while_shutting_down(tmp_path: Path) -> None:
    """Turns arriving after the drain started are refused, not started."""
    repo = _messages_repo(tmp_path)

    async def _stream(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("no turn may start during shutdown")
        yield  # pragma: no cover

    processor = _processor(repo, stream=_stream)
    processor.begin_shutdown()

    chunks = [chunk async for chunk in processor.iter_turn_chunks(_inbound())]

    assert chunks[0]["type"] == "error"
    assert chunks[0]["error_code"] == "SHUTTING_DOWN"
    assert chunks[-1]["type"] == "done"
    rows, _has_more = repo.page(THREAD_ID, limit=10)
    assert rows == []
