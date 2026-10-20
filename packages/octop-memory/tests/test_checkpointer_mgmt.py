"""Tests for Memory checkpointer management API."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.types import ThreadState, ThreadSummary


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})


def _store_checkpoint(memory: Memory, thread_id: str, step: int = 0) -> None:
    """Helper to store a checkpoint for a given thread."""
    from langgraph.checkpoint.base import create_checkpoint, empty_checkpoint

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    cp = create_checkpoint(empty_checkpoint(), None, step + 1)
    memory.put(config, cp, {"source": "input", "step": step}, {})


class TestListThreads:
    def test_empty_returns_empty_list(self, memory: Memory) -> None:
        threads = memory.list_threads()
        assert threads == []

    def test_returns_threads_with_checkpoints(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1")
        _store_checkpoint(memory, "thread-2")
        _store_checkpoint(memory, "thread-3")

        threads = memory.list_threads()
        assert len(threads) == 3
        thread_ids = {t.thread_id for t in threads}
        assert thread_ids == {"thread-1", "thread-2", "thread-3"}

    def test_returns_thread_summary_type(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1")
        threads = memory.list_threads()
        assert len(threads) == 1
        assert isinstance(threads[0], ThreadSummary)
        assert threads[0].thread_id == "thread-1"
        assert threads[0].checkpoint_id is not None

    def test_respects_limit(self, memory: Memory) -> None:
        for i in range(10):
            _store_checkpoint(memory, f"thread-{i}")

        threads = memory.list_threads(limit=3)
        assert len(threads) == 3

    def test_deduplicates_threads_with_multiple_checkpoints(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1", step=0)
        _store_checkpoint(memory, "thread-1", step=1)
        _store_checkpoint(memory, "thread-1", step=2)

        threads = memory.list_threads()
        assert len(threads) == 1
        assert threads[0].thread_id == "thread-1"


class TestGetThreadState:
    def test_returns_none_for_nonexistent_thread(self, memory: Memory) -> None:
        state = memory.get_thread_state("nonexistent")
        assert state is None

    def test_returns_thread_state(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1")
        state = memory.get_thread_state("thread-1")
        assert state is not None
        assert isinstance(state, ThreadState)
        assert state.thread_id == "thread-1"
        assert state.checkpoint_id is not None

    def test_returns_latest_state(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1", step=0)
        _store_checkpoint(memory, "thread-1", step=1)

        state = memory.get_thread_state("thread-1")
        assert state is not None
        assert state.metadata["step"] == 1


class TestDeleteThread:
    def test_delete_removes_all_checkpoints(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1", step=0)
        _store_checkpoint(memory, "thread-1", step=1)

        memory.delete_thread("thread-1")

        state = memory.get_thread_state("thread-1")
        assert state is None

    def test_delete_nonexistent_thread_does_not_raise(self, memory: Memory) -> None:
        # Should not raise
        memory.delete_thread("nonexistent")

    def test_delete_only_affects_target_thread(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1")
        _store_checkpoint(memory, "thread-2")

        memory.delete_thread("thread-1")

        assert memory.get_thread_state("thread-1") is None
        assert memory.get_thread_state("thread-2") is not None
