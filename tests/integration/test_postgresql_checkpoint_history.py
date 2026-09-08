"""Check the native PG history path without opening a SQLite connection."""

from __future__ import annotations

import os
import sqlite3
import uuid
from types import SimpleNamespace

import pytest

from tests.support.postgresql import requires_postgresql


@requires_postgresql
@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_postgres_checkpoint_history_uses_graph_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harness_memory import Memory
    from langgraph.graph import END, START, MessagesState, StateGraph

    from octop.api.routers.chat.serialize import (
        _isolated_sqlite_checkpoint_messages,
        _load_checkpoint_messages,
    )

    memory = Memory(
        namespace=f"history_{uuid.uuid4().hex[:12]}",
        backend="postgres",
        backend_config={"dsn": os.environ["OCTOP_TEST_DATABASE_URL"]},
    )
    thread = f"history-{uuid.uuid4().hex}"
    builder = StateGraph(MessagesState)
    builder.add_node("answer", lambda state: {"messages": [("ai", "saved answer")]})
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    graph = builder.compile(checkpointer=memory)

    def reject_sqlite(*args: object, **kwargs: object) -> None:
        raise AssertionError("PostgreSQL history must not open SQLite")

    try:
        await graph.ainvoke(
            {"messages": [("human", "saved question")]}, {"configurable": {"thread_id": thread}}
        )
        monkeypatch.setattr(sqlite3, "connect", reject_sqlite)
        harness = SimpleNamespace(_checkpointer_instance=memory, graph=graph)
        assert _isolated_sqlite_checkpoint_messages(harness, thread) is None
        messages, has_more = await _load_checkpoint_messages(harness, thread, limit=1)
        assert [message.content for message in messages] == ["saved answer"]
        assert has_more
        messages, has_more = await _load_checkpoint_messages(harness, thread, limit=1, offset=1)
        assert [message.content for message in messages] == ["saved question"]
        assert not has_more
    finally:
        await memory.adelete_thread(thread)
        memory.backend.purge_namespace()
        memory.backend.close()
        if memory._checkpointer_pool is not None:
            memory._checkpointer_pool.close()
