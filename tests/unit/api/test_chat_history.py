"""Unit tests for thread list/history HTTP helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call

import pytest
from langchain_core.messages import HumanMessage

from octop.api.routers.chat import history as history_mod
from octop.api.routers.chat.serialize import (
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    _clamp_history_limit,
    _isolated_sqlite_checkpoint_messages,
    _load_checkpoint_messages,
    _slice_message_page,
)
from octop.infra.db.repos.thread_messages import (
    ThreadProjectionCandidate,
    ThreadProjectionSummary,
)
from octop.infra.db.repos.threads import ThreadRow
from octop.infra.gateway.threads import thread_row_has_messages


def test_clamp_history_limit() -> None:
    assert _clamp_history_limit(0) == 1
    assert _clamp_history_limit(25) == 25
    assert _clamp_history_limit(999) == HISTORY_MAX_LIMIT


def test_slice_message_page_recent() -> None:
    raw = [f"m{i}" for i in range(10)]
    page, has_more = _slice_message_page(raw, limit=3, offset=0)
    assert page == ["m7", "m8", "m9"]
    assert has_more is True


def test_slice_message_page_older() -> None:
    raw = [f"m{i}" for i in range(10)]
    page, has_more = _slice_message_page(raw, limit=3, offset=3)
    assert page == ["m4", "m5", "m6"]
    assert has_more is True


def test_slice_message_page_exhausted() -> None:
    raw = [f"m{i}" for i in range(5)]
    page, has_more = _slice_message_page(raw, limit=25, offset=0)
    assert page == raw
    assert has_more is False


def test_slice_message_page_long_thread_no_gaps_or_overlaps() -> None:
    """Pages from newest to oldest must cover each message exactly once."""
    raw = [f"m{i}" for i in range(100)]
    limit = 25
    offset = 0
    collected: list[str] = []
    while True:
        page, has_more = _slice_message_page(raw, limit=limit, offset=offset)
        assert page
        collected = page + collected
        if not has_more:
            break
        offset += limit
    assert collected == raw


def test_isolated_sqlite_history_supports_pypi_memory_0_9_7(tmp_path: Path) -> None:
    from harness_memory import Memory
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.base import empty_checkpoint

    db_path = tmp_path / "checkpoint.db"
    memory = Memory(
        "agent_test",
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
    )
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {
        "messages": [HumanMessage(content="hi", id="u1"), AIMessage(content="ok", id="a1")]
    }
    checkpoint["channel_versions"] = {"messages": 1}
    memory.put(
        {"configurable": {"thread_id": "thr", "checkpoint_ns": ""}},
        checkpoint,
        {},
        {"messages": 1},
    )
    # Prove the migration opens its own read-only connection rather than using
    # harness-memory 0.9.7's live synchronous saver connection.
    memory._checkpointer.conn.close()
    try:
        harness = SimpleNamespace(_checkpointer_instance=memory)
        messages = _isolated_sqlite_checkpoint_messages(harness, "thr")
    finally:
        memory._backend.close()

    assert messages is not None
    assert [message.id for message in messages] == ["u1", "a1"]


def test_thread_row_has_messages_uses_title_or_last_active() -> None:
    empty = ThreadRow(
        id=1,
        thread_id="thr_empty",
        agent_id="agt",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
        title=None,
        last_active=0,
        created_at=100,
    )
    assert thread_row_has_messages(empty) is False

    titled = ThreadRow(
        id=2,
        thread_id="thr_titled",
        agent_id="agt",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
        title="hello",
        last_active=0,
        created_at=100,
    )
    assert thread_row_has_messages(titled) is True

    active = ThreadRow(
        id=3,
        thread_id="thr_active",
        agent_id="agt",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
        title=None,
        last_active=200,
        created_at=100,
    )
    assert thread_row_has_messages(active) is True


@pytest.mark.asyncio
async def test_list_threads_derives_has_messages_from_db() -> None:
    rows = [
        ThreadRow(
            id=1,
            thread_id="thr_empty",
            agent_id="agt_1",
            user_id=1,
            channel_type="dashboard",
            session_key="sk",
            title=None,
            last_active=0,
            created_at=1,
        ),
        ThreadRow(
            id=2,
            thread_id="thr_used",
            agent_id="agt_1",
            user_id=1,
            channel_type="dashboard",
            session_key="sk2",
            title="hello",
            last_active=5,
            created_at=1,
        ),
    ]
    thread_registry = MagicMock()
    thread_registry.list_threads.return_value = rows
    thread_registry.get_bound_thread_id.return_value = None

    server = MagicMock()
    agent_row = MagicMock(user_id=1)
    server.app_runtime.agent_registry.get_row.return_value = agent_row
    server.app_runtime.agent_registry.get_agent.side_effect = AssertionError(
        "list_threads must not touch harness"
    )
    server.app_runtime.gateway.thread_registry = thread_registry

    user = MagicMock(id=1, is_admin=False)

    out = await history_mod.list_threads("agt_1", limit=10, user=user, server=server)

    assert len(out) == 2
    assert out[0]["has_messages"] is False
    assert out[1]["has_messages"] is True


@pytest.mark.asyncio
async def test_get_thread_history_returns_has_more(monkeypatch: pytest.MonkeyPatch) -> None:
    server = MagicMock()
    row = MagicMock(agent_id="agt_1", user_id=1, artifacts=())
    server.app_runtime.gateway.thread_registry.get_thread.return_value = row

    server.services.thread_message_repo.projection_status.return_value = "ready"
    monkeypatch.setattr(
        history_mod,
        "_load_projected_thread_messages",
        MagicMock(return_value=([{"role": "user", "content": "hi"}], True)),
    )
    out = await history_mod.get_thread_history(
        "agt_1",
        "thr_1",
        limit=HISTORY_DEFAULT_LIMIT,
        offset=0,
        user=MagicMock(id=1),
        server=server,
    )

    assert out["has_more"] is True
    assert out["limit"] == HISTORY_DEFAULT_LIMIT
    assert out["offset"] == 0
    assert out["messages"][0]["role"] == "user"
    assert out["history_loading"] is False


@pytest.mark.asyncio
async def test_get_legacy_history_enqueues_without_reading_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = MagicMock()
    row = MagicMock(agent_id="agt_1", user_id=1, artifacts=())
    server.app_runtime.gateway.thread_registry.get_thread.return_value = row
    server.services.thread_message_repo.projection_status.return_value = "pending"
    server.app_runtime.gateway.history_backfill.enqueue.return_value = True
    load_projection = MagicMock(side_effect=AssertionError("must not read projection yet"))
    monkeypatch.setattr(history_mod, "_load_projected_thread_messages", load_projection)

    out = await history_mod.get_thread_history(
        "agt_1",
        "thr_legacy",
        user=MagicMock(id=1),
        server=server,
    )

    assert out["messages"] == []
    assert out["history_loading"] is True
    assert out["history_status"] == "queued"
    server.app_runtime.gateway.history_backfill.enqueue.assert_called_once()
    load_projection.assert_not_called()


@pytest.mark.asyncio
async def test_history_migration_status_is_scoped_to_effective_user() -> None:
    server = MagicMock()
    server.services.thread_message_repo.migration_summary.return_value = ThreadProjectionSummary(
        pending=2, queued=1, running=1, failed=3
    )
    server.services.thread_message_repo.migration_active_thread_ids.return_value = ["thr_live"]
    queue = server.app_runtime.gateway.history_backfill
    queue.contains.return_value = True
    queue.available_slots = 10
    user = MagicMock(id=7, is_admin=False)

    out = await history_mod.get_history_migration_status(
        "agt_1",
        user=user,
        server=server,
    )

    assert out == {
        "remaining": 7,
        "pending": 2,
        "queued": 1,
        "running": 1,
        "failed": 3,
        "processing": True,
        "agent_busy": False,
        "can_start": True,
    }
    server.services.thread_message_repo.migration_summary.assert_called_once_with(
        agent_id="agt_1",
        user_id=7,
    )


@pytest.mark.asyncio
async def test_start_history_migration_queues_bounded_candidates() -> None:
    server = MagicMock()
    queue = server.app_runtime.gateway.history_backfill
    queue.available_slots = 2
    queue.active_jobs = 0
    queue.enqueue.return_value = True
    repo = server.services.thread_message_repo
    repo.migration_candidates.return_value = [
        ThreadProjectionCandidate(thread_id="thr_a", status="pending"),
        ThreadProjectionCandidate(thread_id="thr_b", status="failed"),
    ]
    repo.migration_summary.return_value = ThreadProjectionSummary(queued=2)
    repo.migration_active_thread_ids.return_value = ["thr_a", "thr_b"]
    queue.contains.side_effect = [False, False, True, True]
    user = MagicMock(id=7, is_admin=False)

    out = await history_mod.start_history_migration(
        "agt_1",
        user=user,
        server=server,
    )

    assert out["accepted"] == 2
    assert out["remaining"] == 2
    repo.migration_candidates.assert_called_once_with(agent_id="agt_1", user_id=7, limit=2)
    assert repo.mark_projection.call_args_list == [
        call("thr_a", "queued"),
        call("thr_b", "queued"),
    ]
    assert queue.enqueue.call_count == 2


@pytest.mark.asyncio
async def test_history_migration_waits_while_agent_is_active() -> None:
    server = MagicMock()
    server.app_runtime.agent_registry.is_agent_active.return_value = True
    server.services.thread_message_repo.migration_summary.return_value = ThreadProjectionSummary(
        pending=1
    )
    server.services.thread_message_repo.migration_active_thread_ids.return_value = []
    server.app_runtime.gateway.history_backfill.available_slots = 10
    server.app_runtime.gateway.history_backfill.contains.return_value = False
    row = MagicMock(agent_id="agt_1", user_id=7, artifacts=())
    server.app_runtime.gateway.thread_registry.get_thread.return_value = row
    server.services.thread_message_repo.projection_status.return_value = "pending"
    user = MagicMock(id=7, is_admin=False)

    status = await history_mod.get_history_migration_status(
        "agt_1",
        user=user,
        server=server,
    )
    history = await history_mod.get_thread_history(
        "agt_1",
        "thr_legacy",
        user=user,
        server=server,
    )

    assert status["agent_busy"] is True
    assert status["can_start"] is False
    assert history["history_status"] == "pending"
    server.app_runtime.gateway.history_backfill.enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_requeues_thread_when_agent_became_busy() -> None:
    server = MagicMock()
    registry = server.app_runtime.agent_registry
    registry.try_begin_history_backfill.return_value = False

    await history_mod._backfill_thread_projection(
        server,
        "agt_1",
        "thr_legacy",
        user=MagicMock(id=7),
    )

    server.services.thread_message_repo.mark_projection.assert_called_once_with(
        "thr_legacy", "pending"
    )
    registry.get_agent.assert_not_called()


@pytest.mark.asyncio
async def test_load_checkpoint_messages_paginates_with_aget_history() -> None:
    full = [HumanMessage(content=f"m{i}", id=f"id-{i}") for i in range(60)]

    class Harness:
        async def aget_history(self, thread_id: str, *, limit: int = 50) -> list[Any]:
            return full[-limit:]

    harness = Harness()
    page0, more0 = await _load_checkpoint_messages(harness, "thr", limit=25, offset=0)
    page1, more1 = await _load_checkpoint_messages(harness, "thr", limit=25, offset=25)
    page2, more2 = await _load_checkpoint_messages(harness, "thr", limit=25, offset=50)

    assert [m.content for m in page0] == [f"m{i}" for i in range(35, 60)]
    assert more0 is True
    assert [m.content for m in page1] == [f"m{i}" for i in range(10, 35)]
    assert more1 is True
    assert [m.content for m in page2] == [f"m{i}" for i in range(0, 10)]
    assert more2 is False
