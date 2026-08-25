"""Unit tests for thread list/history HTTP helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from octop.api.routers.chat import history as history_mod
from octop.api.routers.chat.serialize import (
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    _clamp_history_limit,
    _load_checkpoint_messages,
    _slice_message_page,
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

    monkeypatch.setattr(
        history_mod,
        "_load_thread_messages",
        AsyncMock(return_value=([{"role": "user", "content": "hi"}], True)),
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
