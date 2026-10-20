"""Tests for Memory as a LangGraph checkpointer."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, TypedDict

import pytest
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    create_checkpoint,
    empty_checkpoint,
)

from octop_memory.core import Memory


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})


class TestPostgresCheckpointerIsLazy:
    """The Postgres saver owns a ``ConnectionPool``, so it is built on first use.

    Read-only consumers (dashboard RPC, bridge, CLI) construct ``Memory`` and
    never checkpoint; building a pool for them just burns Postgres connections.
    """

    def test_sqlite_saver_is_still_built_eagerly(self, memory: Memory) -> None:
        """A local file handle is cheap — keep SQLite behaviour unchanged."""
        assert memory._checkpointer is not None

    def test_built_once_on_first_use(self, memory: Memory, monkeypatch: pytest.MonkeyPatch) -> None:
        memory._checkpointer = None  # the deferred state a Postgres backend starts in
        builds: list[object] = []

        def _build() -> object:
            saver = object()
            builds.append(saver)
            return saver

        monkeypatch.setattr(memory, "_create_postgres_checkpointer", _build)

        memory._ensure_checkpointer()
        memory._ensure_checkpointer()

        assert len(builds) == 1
        assert memory._checkpointer is builds[0]

    def test_unsupported_backend_still_raises(self, memory: Memory, monkeypatch: pytest.MonkeyPatch) -> None:
        memory._checkpointer = None
        monkeypatch.setattr(memory, "_create_postgres_checkpointer", lambda: None)

        with pytest.raises(ValueError, match=r"does not support checkpointing"):
            memory._ensure_checkpointer()


@pytest.fixture
def pg_memory(postgres_dsn: str):
    """A Postgres-backed ``Memory``; skipped when no server is reachable."""
    ns = f"cp_{uuid.uuid4().hex[:12]}"
    mem = Memory(namespace=ns, backend="postgres", backend_config={"dsn": postgres_dsn})
    try:
        yield mem
    finally:
        mem.backend.purge_namespace()
        mem.backend.close()
        pool = getattr(mem, "_checkpointer_pool", None)
        if pool is not None:
            pool.close()


class TestPostgresCheckpointerReallyBuilds:
    """Runs the real ``_create_postgres_checkpointer``.

    ``TestPostgresCheckpointerIsLazy`` monkeypatches the builder, so it proves
    the caching contract but never executes the pool/saver code. Until
    ``langgraph-checkpoint-postgres`` was a dev dependency the builder could
    only take its ImportError branch here, which is how the whole path shipped
    unexercised — the same trap as ``psycopg`` and ``tests/test_postgres.py``.
    """

    def test_no_pool_until_first_use(self, pg_memory: Memory) -> None:
        assert pg_memory._checkpointer is None
        assert getattr(pg_memory, "_checkpointer_pool", None) is None

    def test_first_use_builds_a_real_saver(self, pg_memory: Memory) -> None:
        from langgraph.checkpoint.postgres import PostgresSaver

        pg_memory._ensure_checkpointer()

        assert isinstance(pg_memory._checkpointer, PostgresSaver)
        assert pg_memory._checkpointer_pool is not None

    def test_checkpoint_round_trips_through_postgres(self, pg_memory: Memory) -> None:
        thread = f"t-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
        checkpoint = create_checkpoint(empty_checkpoint(), None, 1)

        pg_memory.put(config, checkpoint, {"source": "input", "step": 0}, {})
        result = pg_memory.get_tuple(config)

        assert result is not None
        assert result.checkpoint["id"] == checkpoint["id"]


class TestMemoryIsCheckpointer:
    """Verify Memory satisfies the BaseCheckpointSaver protocol."""

    def test_isinstance_base_checkpoint_saver(self, memory: Memory) -> None:
        assert isinstance(memory, BaseCheckpointSaver)

    def test_has_get_tuple(self, memory: Memory) -> None:
        assert hasattr(memory, "get_tuple")
        assert callable(memory.get_tuple)

    def test_has_put(self, memory: Memory) -> None:
        assert hasattr(memory, "put")
        assert callable(memory.put)

    def test_has_put_writes(self, memory: Memory) -> None:
        assert hasattr(memory, "put_writes")
        assert callable(memory.put_writes)

    def test_has_list(self, memory: Memory) -> None:
        assert hasattr(memory, "list")
        assert callable(memory.list)


class TestCheckpointerPutGet:
    """Test put/get_tuple round-trip."""

    def test_put_and_get_tuple(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
        checkpoint = create_checkpoint(empty_checkpoint(), None, 1)
        metadata = {"source": "input", "step": 0}
        result_config = memory.put(config, checkpoint, metadata, {})

        # Result should include checkpoint_id
        assert "checkpoint_id" in result_config["configurable"]

        # Get it back
        result = memory.get_tuple(config)
        assert result is not None
        assert result.checkpoint["id"] == checkpoint["id"]
        assert result.metadata["source"] == "input"

    def test_get_tuple_nonexistent_returns_none(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "nonexistent", "checkpoint_ns": ""}}
        result = memory.get_tuple(config)
        assert result is None


class TestCheckpointerList:
    """Test listing checkpoints for a thread."""

    def test_list_checkpoints_for_thread(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
        for i in range(3):
            checkpoint = create_checkpoint(empty_checkpoint(), None, i + 1)
            metadata = {"source": "input", "step": i}
            memory.put(config, checkpoint, metadata, {})

        results = list(memory.list(config))
        assert len(results) == 3

    def test_list_none_config_lists_all(self, memory: Memory) -> None:
        # Create checkpoints for two different threads
        for thread_id in ("thread-a", "thread-b"):
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            checkpoint = create_checkpoint(empty_checkpoint(), None, 1)
            memory.put(config, checkpoint, {"source": "input", "step": 0}, {})

        results = list(memory.list(None))
        assert len(results) == 2


class TestSharedDB:
    """Test that memory store operations and checkpoint ops don't conflict."""

    def test_store_and_checkpoint_coexist(self, memory: Memory) -> None:
        # Store a memory
        node = memory.store("User prefers dark mode")
        assert node.level == "leaf"

        # Put a checkpoint
        config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
        checkpoint = create_checkpoint(empty_checkpoint(), None, 1)
        metadata = {"source": "input", "step": 0}
        memory.put(config, checkpoint, metadata, {})

        # Both still work
        recalled = memory.recall("dark mode")
        assert len(recalled) >= 1

        result = memory.get_tuple(config)
        assert result is not None
        assert result.checkpoint["id"] == checkpoint["id"]


class TestEndToEndWithGraph:
    """Integration test: Memory used as checkpointer in a real LangGraph graph."""

    def test_memory_as_graph_checkpointer(self, memory: Memory) -> None:
        from langgraph.graph import END, START, StateGraph

        class State(TypedDict):
            messages: Annotated[list[str], lambda a, b: a + b]

        def node_a(state: State) -> dict[str, list[str]]:
            return {"messages": ["hello from a"]}

        def node_b(state: State) -> dict[str, list[str]]:
            return {"messages": ["hello from b"]}

        builder = StateGraph(State)
        builder.add_node("a", node_a)
        builder.add_node("b", node_b)
        builder.add_edge(START, "a")
        builder.add_edge("a", "b")
        builder.add_edge("b", END)

        graph = builder.compile(checkpointer=memory)

        config = {"configurable": {"thread_id": "e2e-test"}}
        result = graph.invoke({"messages": []}, config)
        assert "hello from a" in result["messages"]
        assert "hello from b" in result["messages"]

        # Verify checkpoint was stored
        state = memory.get_thread_state("e2e-test")
        assert state is not None
        assert state.thread_id == "e2e-test"

    def test_multiple_invocations_same_thread(self, memory: Memory) -> None:
        from langgraph.graph import END, START, StateGraph

        class State(TypedDict):
            messages: Annotated[list[str], lambda a, b: a + b]

        def echo(state: State) -> dict[str, list[str]]:
            return {"messages": [f"echo:{state['messages'][-1]}"]}

        builder = StateGraph(State)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)

        graph = builder.compile(checkpointer=memory)
        config = {"configurable": {"thread_id": "multi-invoke"}}

        # First invocation
        r1 = graph.invoke({"messages": ["first"]}, config)
        assert "echo:first" in r1["messages"]

        # Second invocation on same thread — state accumulates
        r2 = graph.invoke({"messages": ["second"]}, config)
        assert "echo:second" in r2["messages"]
        # All messages accumulated (first + echo:first + second + echo:second)
        assert len(r2["messages"]) == 4


class TestAsyncCheckpointer:
    """Test async checkpointer methods (aget_tuple, aput, aput_writes, alist)."""

    @pytest.mark.asyncio
    async def test_aget_tuple_nonexistent_returns_none(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "async-nonexistent", "checkpoint_ns": ""}}
        result = await memory.aget_tuple(config)
        assert result is None

    @pytest.mark.asyncio
    async def test_aput_and_aget_tuple(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "async-thread", "checkpoint_ns": ""}}
        checkpoint = create_checkpoint(empty_checkpoint(), None, 1)
        metadata = {"source": "input", "step": 0}
        result_config = await memory.aput(config, checkpoint, metadata, {})

        assert "checkpoint_id" in result_config["configurable"]

        result = await memory.aget_tuple(config)
        assert result is not None
        assert result.checkpoint["id"] == checkpoint["id"]

    @pytest.mark.asyncio
    async def test_aput_writes(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "async-writes", "checkpoint_ns": ""}}
        checkpoint = create_checkpoint(empty_checkpoint(), None, 1)
        metadata = {"source": "input", "step": 0}
        result_config = await memory.aput(config, checkpoint, metadata, {})

        # Should not raise
        await memory.aput_writes(result_config, [("messages", "hello")], task_id="task-1")

    @pytest.mark.asyncio
    async def test_alist(self, memory: Memory) -> None:
        config = {"configurable": {"thread_id": "async-list", "checkpoint_ns": ""}}
        for i in range(3):
            checkpoint = create_checkpoint(empty_checkpoint(), None, i + 1)
            metadata = {"source": "input", "step": i}
            await memory.aput(config, checkpoint, metadata, {})

        results = []
        async for item in memory.alist(config):
            results.append(item)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_async_graph_invocation(self, memory: Memory) -> None:
        """Integration test: Memory as checkpointer with async graph execution."""
        from langgraph.graph import END, START, StateGraph

        class State(TypedDict):
            messages: Annotated[list[str], lambda a, b: a + b]

        def echo(state: State) -> dict[str, list[str]]:
            return {"messages": [f"echo:{state['messages'][-1]}"]}

        builder = StateGraph(State)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)

        graph = builder.compile(checkpointer=memory)
        config = {"configurable": {"thread_id": "async-e2e"}}

        # Use ainvoke — this is what was failing before the fix
        result = await graph.ainvoke({"messages": ["hello"]}, config)
        assert "echo:hello" in result["messages"]

        # Verify checkpoint was stored and retrievable via async
        cp = await memory.aget_tuple({"configurable": {"thread_id": "async-e2e", "checkpoint_ns": ""}})
        assert cp is not None

    @pytest.mark.asyncio
    async def test_async_multiple_invocations_same_thread(self, memory: Memory) -> None:
        """State accumulates across async invocations on the same thread."""
        from langgraph.graph import END, START, StateGraph

        class State(TypedDict):
            messages: Annotated[list[str], lambda a, b: a + b]

        def echo(state: State) -> dict[str, list[str]]:
            return {"messages": [f"echo:{state['messages'][-1]}"]}

        builder = StateGraph(State)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)

        graph = builder.compile(checkpointer=memory)
        config = {"configurable": {"thread_id": "async-multi"}}

        r1 = await graph.ainvoke({"messages": ["first"]}, config)
        assert "echo:first" in r1["messages"]

        r2 = await graph.ainvoke({"messages": ["second"]}, config)
        assert "echo:second" in r2["messages"]
        assert len(r2["messages"]) == 4
