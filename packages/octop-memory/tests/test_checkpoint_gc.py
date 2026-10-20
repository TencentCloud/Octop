"""Tests for checkpoint retention pruning (octop_memory.pipeline.lifecycle.checkpoint_gc)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle.checkpoint_gc import (
    DEFAULT_KEEP_LAST_CHECKPOINTS,
    _cutoff_checkpoint_id,
    prune_checkpoints,
)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})


def _store_checkpoint(memory: Memory, thread_id: str, step: int = 0) -> None:
    """Helper to store a real checkpoint for a given thread via the public API."""
    from langgraph.checkpoint.base import create_checkpoint, empty_checkpoint

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    cp = create_checkpoint(empty_checkpoint(), None, step + 1)
    memory.put(config, cp, {"source": "input", "step": step}, {})


def _checkpoint_ids(memory: Memory, thread_id: str, checkpoint_ns: str | None = None) -> list[str]:
    conn = memory._checkpointer.conn
    if checkpoint_ns is None:
        rows = conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC",
            (thread_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ? "
            "ORDER BY checkpoint_id DESC",
            (thread_id, checkpoint_ns),
        ).fetchall()
    return [r[0] for r in rows]


def _store_parent_with_messages(memory: Memory, thread_id: str, *, tool_calls: bool = False) -> None:
    """Write a parent checkpoint whose channel_values look like a real turn."""
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.base import create_checkpoint, empty_checkpoint

    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    calls = [{"id": "call-1", "name": "bash", "args": {"command": "ls"}}] if tool_calls else []
    base = empty_checkpoint()
    base["channel_values"] = {"messages": [AIMessage(content="done", tool_calls=calls)]}
    cp = create_checkpoint(base, None, 1)
    memory.put(config, cp, {"source": "loop", "step": 1}, {})


def _insert_raw_checkpoint(memory: Memory, thread_id: str, checkpoint_id: str, checkpoint_ns: str = "") -> None:
    """Insert a bare checkpoints/writes row directly, bypassing serialization.

    Used to control``checkpoint_id`` precisely for age-based (``keep_days``)
    tests, where we need rows that look like they were created at a specific
    past instant without waiting in real time.
    """
    conn = memory._checkpointer.conn
    conn.execute(
        "INSERT INTO checkpoints "
        "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
        "VALUES (?, ?, ?, NULL, 'json', X'00', '{}')",
        (thread_id, checkpoint_ns, checkpoint_id),
    )
    conn.execute(
        "INSERT INTO writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value) "
        "VALUES (?, ?, ?, 'task-1', 0, 'chan', 'json', X'00')",
        (thread_id, checkpoint_ns, checkpoint_id),
    )
    conn.commit()


class TestKeepLast:
    def test_keeps_only_newest_n_checkpoints(self, memory: Memory) -> None:
        for step in range(5):
            _store_checkpoint(memory, "thread-1", step=step)
        before = _checkpoint_ids(memory, "thread-1")
        assert len(before) == 5

        stats = prune_checkpoints(memory, keep_last=2, thread_id="thread-1")

        after = _checkpoint_ids(memory, "thread-1")
        assert after == before[:2]
        assert stats.checkpoints_deleted == 3
        # _store_checkpoint only calls memory.put(), never put_writes(), so
        # the writes table stays empty in this scenario.
        assert stats.writes_deleted == 0
        assert stats.dry_run is False

    def test_never_deletes_below_one_survivor(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-1", step=0)
        stats = prune_checkpoints(memory, keep_last=1, thread_id="thread-1")
        assert stats.checkpoints_deleted == 0
        assert len(_checkpoint_ids(memory, "thread-1")) == 1

    def test_only_affects_target_thread(self, memory: Memory) -> None:
        for step in range(3):
            _store_checkpoint(memory, "thread-1", step=step)
        for step in range(3):
            _store_checkpoint(memory, "thread-2", step=step)

        prune_checkpoints(memory, keep_last=1, thread_id="thread-1")

        assert len(_checkpoint_ids(memory, "thread-1")) == 1
        assert len(_checkpoint_ids(memory, "thread-2")) == 3

    def test_scans_all_threads_when_thread_id_omitted(self, memory: Memory) -> None:
        for step in range(3):
            _store_checkpoint(memory, "thread-1", step=step)
        for step in range(3):
            _store_checkpoint(memory, "thread-2", step=step)

        stats = prune_checkpoints(memory, keep_last=1)

        assert stats.threads_scanned == 2
        assert len(_checkpoint_ids(memory, "thread-1")) == 1
        assert len(_checkpoint_ids(memory, "thread-2")) == 1

    def test_dry_run_deletes_nothing(self, memory: Memory) -> None:
        for step in range(5):
            _store_checkpoint(memory, "thread-1", step=step)

        stats = prune_checkpoints(memory, keep_last=2, thread_id="thread-1", dry_run=True)

        assert stats.dry_run is True
        assert stats.checkpoints_deleted == 3
        assert len(_checkpoint_ids(memory, "thread-1")) == 5

    def test_dry_run_counts_writes_rows_too(self, memory: Memory) -> None:
        """dry_run must predict writes_deleted, not silently report 0.

        The real path gets the number from DELETE's rowcount, which a
        preview never executes — so dry_run has to COUNT explicitly.
        Regression test: this used to always report 0, under-reporting
        the blast radius of a prune.
        """
        for i in range(5):
            _insert_raw_checkpoint(memory, "thread-w", f"00000000-0000-6000-8000-00000000000{i}")

        preview = prune_checkpoints(memory, keep_last=2, thread_id="thread-w", dry_run=True)

        assert preview.checkpoints_deleted == 3
        assert preview.writes_deleted == 3, "one writes row per checkpoint in this fixture"

        # The prediction matches what a real prune actually deletes.
        real = prune_checkpoints(memory, keep_last=2, thread_id="thread-w")
        assert real.checkpoints_deleted == preview.checkpoints_deleted
        assert real.writes_deleted == preview.writes_deleted

    def test_get_thread_state_still_works_after_prune(self, memory: Memory) -> None:
        for step in range(5):
            _store_checkpoint(memory, "thread-1", step=step)

        prune_checkpoints(memory, keep_last=2, thread_id="thread-1")

        state = memory.get_thread_state("thread-1")
        assert state is not None
        assert state.metadata["step"] == 4


class TestKeepDays:
    def test_keeps_checkpoints_newer_than_cutoff(self, memory: Memory) -> None:
        now = datetime.now(UTC)
        old_id = _cutoff_checkpoint_id(now - timedelta(days=10))
        recent_id = _cutoff_checkpoint_id(now - timedelta(hours=1))
        _insert_raw_checkpoint(memory, "thread-1", old_id)
        _insert_raw_checkpoint(memory, "thread-1", recent_id)

        stats = prune_checkpoints(memory, keep_days=7, thread_id="thread-1", now=now)

        remaining = _checkpoint_ids(memory, "thread-1")
        assert remaining == [recent_id]
        assert stats.checkpoints_deleted == 1
        # _insert_raw_checkpoint always seeds one writes row per checkpoint.
        assert stats.writes_deleted == 1

    def test_never_deletes_the_last_survivor_even_if_stale(self, memory: Memory) -> None:
        now = datetime.now(UTC)
        old_id = _cutoff_checkpoint_id(now - timedelta(days=365))
        _insert_raw_checkpoint(memory, "thread-1", old_id)

        stats = prune_checkpoints(memory, keep_days=7, thread_id="thread-1", now=now)

        assert stats.checkpoints_deleted == 0
        assert _checkpoint_ids(memory, "thread-1") == [old_id]


class TestCombinedAndValidation:
    def test_or_semantics_between_keep_last_and_keep_days(self, memory: Memory) -> None:
        now = datetime.now(UTC)
        # 3 old checkpoints (beyond keep_days) but within keep_last rank -> survive via rank.
        ids = [_cutoff_checkpoint_id(now - timedelta(days=30 - i)) for i in range(3)]
        for cid in ids:
            _insert_raw_checkpoint(memory, "thread-1", cid)

        stats = prune_checkpoints(memory, keep_last=2, keep_days=1, thread_id="thread-1", now=now)

        remaining = set(_checkpoint_ids(memory, "thread-1"))
        # newest 2 by keep_last survive even though all are older than keep_days=1
        assert remaining == set(sorted(ids, reverse=True)[:2])
        assert stats.checkpoints_deleted == 1

    def test_requires_at_least_one_retention_knob(self, memory: Memory) -> None:
        with pytest.raises(ValueError, match="keep_last and/or keep_days"):
            prune_checkpoints(memory, thread_id="thread-1")

    def test_rejects_keep_last_below_one(self, memory: Memory) -> None:
        with pytest.raises(ValueError, match="keep_last must be >= 1"):
            prune_checkpoints(memory, keep_last=0, thread_id="thread-1")

    def test_rejects_negative_keep_days(self, memory: Memory) -> None:
        with pytest.raises(ValueError, match="keep_days must be >= 0"):
            prune_checkpoints(memory, keep_days=-1, thread_id="thread-1")


class TestCutoffCheckpointIdOrdering:
    def test_cutoff_ids_sort_chronologically(self) -> None:
        base = datetime.now(UTC)
        earlier = _cutoff_checkpoint_id(base - timedelta(days=1))
        later = _cutoff_checkpoint_id(base)
        assert earlier < later


class TestDropSubgraphStreams:
    def test_default_keep_last_is_one(self) -> None:
        assert DEFAULT_KEEP_LAST_CHECKPOINTS == 1

    def test_force_drop_deletes_tools_stream_keeps_latest_parent(self, memory: Memory) -> None:
        for step in range(3):
            _store_checkpoint(memory, "thread-1", step=step)
        for i in range(4):
            _insert_raw_checkpoint(memory, "thread-1", f"00000000-0000-6000-8000-00000000000{i}", "tools:abc")

        stats = prune_checkpoints(
            memory,
            keep_last=1,
            thread_id="thread-1",
            drop_subgraph_streams=True,
            force_drop_subgraphs=True,
        )

        assert len(_checkpoint_ids(memory, "thread-1", "")) == 1
        assert _checkpoint_ids(memory, "thread-1", "tools:abc") == []
        assert stats.streams_dropped == 1
        assert stats.checkpoints_deleted == 2 + 4
        assert memory.get_thread_state("thread-1") is not None

    def test_skips_drop_when_parent_has_tool_calls(self, memory: Memory) -> None:
        _store_parent_with_messages(memory, "hitl-1", tool_calls=True)
        _insert_raw_checkpoint(memory, "hitl-1", "00000000-0000-6000-8000-000000000001", "tools:hitl")

        stats = prune_checkpoints(memory, keep_last=1, thread_id="hitl-1", drop_subgraph_streams=True)

        assert _checkpoint_ids(memory, "hitl-1", "tools:hitl")
        assert stats.streams_dropped == 0

    def test_drops_when_parent_is_final_ai(self, memory: Memory) -> None:
        _store_parent_with_messages(memory, "done-1", tool_calls=False)
        # Older than the real parent put() id so the subgraph-ahead guard
        # does not treat this as an in-flight tool stream.
        _insert_raw_checkpoint(memory, "done-1", "00000000-0000-6000-8000-000000000001", "tools:done")

        stats = prune_checkpoints(memory, keep_last=1, thread_id="done-1", drop_subgraph_streams=True)

        assert _checkpoint_ids(memory, "done-1", "tools:done") == []
        assert stats.streams_dropped == 1
        assert memory.get_thread_state("done-1") is not None

    def test_skips_drop_when_subgraph_is_newer_than_parent(self, memory: Memory) -> None:
        _store_parent_with_messages(memory, "live-1", tool_calls=False)
        _insert_raw_checkpoint(
            memory,
            "live-1",
            "ffffffff-ffff-6fff-8000-ffffffffffff",
            "tools:live",
        )

        stats = prune_checkpoints(memory, keep_last=1, thread_id="live-1", drop_subgraph_streams=True)

        assert _checkpoint_ids(memory, "live-1", "tools:live")
        assert stats.streams_dropped == 0

    def test_dry_run_counts_dropped_stream(self, memory: Memory) -> None:
        _store_checkpoint(memory, "thread-d", step=0)
        _insert_raw_checkpoint(memory, "thread-d", "00000000-0000-6000-8000-000000000001", "tools:dry")

        preview = prune_checkpoints(
            memory,
            keep_last=1,
            thread_id="thread-d",
            drop_subgraph_streams=True,
            force_drop_subgraphs=True,
            dry_run=True,
        )

        assert preview.dry_run is True
        assert preview.streams_dropped == 1
        assert preview.checkpoints_deleted == 1
        assert preview.writes_deleted == 1
        assert _checkpoint_ids(memory, "thread-d", "tools:dry")


def _plain_text(msg: Any) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content)


def _reasoning(msg: Any) -> str:
    kwargs = getattr(msg, "additional_kwargs", None) or {}
    text = kwargs.get("reasoning_content")
    if isinstance(text, str) and text.strip():
        return text.strip()
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("thinking", "reasoning"):
                thinking = block.get("thinking") or block.get("reasoning") or block.get("text")
                if isinstance(thinking, str) and thinking.strip():
                    return thinking.strip()
    return ""


def _parent_messages(memory: Memory, thread_id: str) -> list[Any]:
    tup = memory.get_tuple({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
    assert tup is not None
    values = tup.checkpoint.get("channel_values") or {}
    raw = values.get("messages") or []
    assert isinstance(raw, list)
    return raw


def _store_delta_parent_chain(
    memory: Memory,
    thread_id: str,
    *,
    omit_seed: bool = False,
) -> list[Any]:
    """Parent row 0 holds (or omits) messages; row 1 is a delta omit of messages."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langgraph.checkpoint.base import create_checkpoint, empty_checkpoint

    messages = [
        HumanMessage(content="hi", id="u1"),
        AIMessage(
            content="",
            id="a1",
            additional_kwargs={"reasoning_content": "search first"},
            tool_calls=[{"id": "c1", "name": "search", "args": {"q": "x"}}],
        ),
        ToolMessage(content="result", tool_call_id="c1", name="search", id="t1"),
        AIMessage(
            content=[
                {"type": "thinking", "thinking": "enough evidence"},
                {"type": "text", "text": "done"},
            ],
            id="a2",
            additional_kwargs={"reasoning_content": "enough evidence"},
        ),
    ]
    config0 = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    base = empty_checkpoint()
    versions = {"messages": "0000000000000001", "skills_metadata": "0000000000000001"}
    if omit_seed:
        base["channel_values"] = {"skills_metadata": ["s"]}
    else:
        base["channel_values"] = {"messages": messages, "skills_metadata": ["s"]}
    base["channel_versions"] = dict(versions)
    cp0 = create_checkpoint(base, None, 1)
    saved0 = memory.put(config0, cp0, {"source": "loop", "step": 0}, {})

    cp1 = create_checkpoint(cp0, None, 2)
    cp1["channel_values"] = {"skills_metadata": ["s"]}
    cp1["channel_versions"] = dict(versions)
    memory.put(saved0, cp1, {"source": "loop", "step": 1}, {})
    return messages


class TestSealParentBeforePrune:
    def test_delta_omit_inlines_messages_and_keeps_tools(self, memory: Memory) -> None:
        expected = _store_delta_parent_chain(memory, "thr-delta")
        assert "messages" not in (
            memory.get_tuple({"configurable": {"thread_id": "thr-delta"}}).checkpoint.get("channel_values") or {}
        )

        stats = prune_checkpoints(memory, keep_last=1, thread_id="thr-delta")

        assert stats.parents_sealed == 1
        assert stats.parent_prunes_skipped == 0
        assert len(_checkpoint_ids(memory, "thr-delta", "")) == 1
        got = _parent_messages(memory, "thr-delta")
        assert [type(m).__name__ for m in got] == [type(m).__name__ for m in expected]
        assert got[2].content == "result"
        assert _plain_text(got[-1]) == "done"
        assert _reasoning(got[1]) == "search first"
        assert _reasoning(got[-1]) == "enough evidence"
        values = memory.get_tuple({"configurable": {"thread_id": "thr-delta"}}).checkpoint.get("channel_values")
        assert values.get("skills_metadata") == ["s"]

    def test_unreplayable_delta_skips_ancestor_delete(self, memory: Memory) -> None:
        _store_delta_parent_chain(memory, "thr-broken", omit_seed=True)
        before = _checkpoint_ids(memory, "thr-broken", "")
        assert len(before) == 2

        stats = prune_checkpoints(memory, keep_last=1, thread_id="thr-broken")

        assert stats.parents_sealed == 0
        assert stats.parent_prunes_skipped == 1
        assert stats.checkpoints_deleted == 0
        assert _checkpoint_ids(memory, "thr-broken", "") == before

    def test_dry_run_delta_does_not_write_seal(self, memory: Memory) -> None:
        _store_delta_parent_chain(memory, "thr-dry")
        before = _checkpoint_ids(memory, "thr-dry", "")

        stats = prune_checkpoints(memory, keep_last=1, thread_id="thr-dry", dry_run=True)

        assert stats.dry_run is True
        assert stats.parents_sealed == 1
        assert _checkpoint_ids(memory, "thr-dry", "") == before
        values = memory.get_tuple({"configurable": {"thread_id": "thr-dry"}}).checkpoint.get("channel_values")
        assert "messages" not in (values or {})

    def test_drops_tools_stream_after_seal(self, memory: Memory) -> None:
        _store_delta_parent_chain(memory, "thr-tools")
        _insert_raw_checkpoint(memory, "thr-tools", "00000000-0000-6000-8000-000000000001", "tools:x")

        stats = prune_checkpoints(
            memory,
            keep_last=1,
            thread_id="thr-tools",
            drop_subgraph_streams=True,
        )

        assert stats.parents_sealed == 1
        assert _checkpoint_ids(memory, "thr-tools", "tools:x") == []
        assert stats.streams_dropped == 1
        got = _parent_messages(memory, "thr-tools")
        assert _plain_text(got[-1]) == "done"
        assert got[2].content == "result"
        assert _reasoning(got[1]) == "search first"
        assert _reasoning(got[-1]) == "enough evidence"

    def test_seal_drop_then_vacuum_keeps_tools_and_thinking(self, memory: Memory) -> None:
        """Deleted tools:* pages can be reclaimed without dropping the sealed transcript."""
        from octop_memory.pipeline.lifecycle.vacuum import nudge_vacuum

        _store_delta_parent_chain(memory, "thr-vac")
        fat = b"x" * 80_000
        conn = memory._checkpointer.conn
        conn.execute(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
            "VALUES (?, ?, ?, NULL, 'json', ?, '{}')",
            ("thr-vac", "tools:fat", "00000000-0000-6000-8000-000000000001", fat),
        )
        conn.commit()

        stats = prune_checkpoints(
            memory,
            keep_last=1,
            thread_id="thr-vac",
            drop_subgraph_streams=True,
        )
        assert stats.parents_sealed == 1
        assert stats.streams_dropped == 1
        assert _checkpoint_ids(memory, "thr-vac", "tools:fat") == []

        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        assert freelist > 0

        vac = nudge_vacuum(memory)
        got = _parent_messages(memory, "thr-vac")
        assert [type(m).__name__ for m in got] == [
            "HumanMessage",
            "AIMessage",
            "ToolMessage",
            "AIMessage",
        ]
        assert got[2].content == "result"
        assert _plain_text(got[-1]) == "done"
        assert _reasoning(got[1]) == "search first"
        assert _reasoning(got[-1]) == "enough evidence"
        assert vac.auto_vacuum_enabled is True
        assert vac.pages_reclaimed > 0
