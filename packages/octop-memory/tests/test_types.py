"""Tests for octop_memory.types."""

from __future__ import annotations

from datetime import UTC, datetime

from octop_memory.types import (
    MemoryNode,
    ThreadState,
    ThreadSummary,
)


class TestMemoryNode:
    def test_create_leaf(self) -> None:
        node = MemoryNode(
            id="n1",
            parent_id="branch1",
            level="leaf",
            content="Discussed memory system design",
            topic="octop-harness",
            conversation_id="conv1",
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
            atom_id="atom1",
        )
        assert node.level == "leaf"
        assert node.parent_id == "branch1"
        assert node.atom_id == "atom1"

    def test_create_root(self) -> None:
        node = MemoryNode(
            id="root",
            parent_id=None,
            level="root",
            content="Global overview",
            topic=None,
            conversation_id=None,
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            updated_at=datetime(2026, 5, 24, tzinfo=UTC),
        )
        assert node.parent_id is None
        assert node.level == "root"


class TestThreadSummary:
    def test_create_thread_summary(self) -> None:
        ts = ThreadSummary(
            thread_id="t1",
            checkpoint_id="cp-001",
            created_at=datetime(2026, 5, 25, tzinfo=UTC),
            updated_at=datetime(2026, 5, 25, tzinfo=UTC),
        )
        assert ts.thread_id == "t1"
        assert ts.checkpoint_id == "cp-001"

    def test_thread_summary_optional_timestamps(self) -> None:
        ts = ThreadSummary(
            thread_id="t2",
            checkpoint_id="cp-002",
            created_at=None,
            updated_at=None,
        )
        assert ts.created_at is None
        assert ts.updated_at is None


class TestThreadState:
    def test_create_thread_state(self) -> None:
        state = ThreadState(
            thread_id="t1",
            checkpoint_id="cp-001",
            channel_values={"messages": [{"role": "user", "content": "hi"}]},
            metadata={"source": "input"},
            created_at=datetime(2026, 5, 25, tzinfo=UTC),
        )
        assert state.thread_id == "t1"
        assert state.channel_values["messages"][0]["role"] == "user"
        assert state.metadata["source"] == "input"

    def test_thread_state_optional_created_at(self) -> None:
        state = ThreadState(
            thread_id="t2",
            checkpoint_id="cp-002",
            channel_values={},
            metadata={},
            created_at=None,
        )
        assert state.created_at is None
