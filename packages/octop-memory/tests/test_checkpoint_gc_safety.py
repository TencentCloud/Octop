"""Guard rails that decide whether deleting a checkpoint is safe.

``prune_checkpoints`` with ``keep_last=1`` deletes a thread's ancestor
snapshots, so everything here protects the one thing that cannot be
rebuilt: the conversation transcript. The happy paths live in
``test_checkpoint_gc.py``; this module covers the refusal branches —
replay failure, an in-flight subgraph, an interrupted turn, a
non-SQLite checkpointer — which are exactly the paths that must fail
*closed* (keep the data) rather than open.
"""

from __future__ import annotations

import sqlite3
import sys
from typing import Any

import pytest

from octop_memory.pipeline.lifecycle.checkpoint_gc import (
    _apply_message_write,
    _ensure_parent_sealed,
    _get_checkpointer_conn,
    _message_has_tool_calls,
    _message_is_ai,
    _messages_omitted,
    _parent_turn_finished,
    _reconstruct_parent_messages,
    _subgraph_newer_than_parent,
    _thread_ns_pairs,
    _victim_checkpoint_ids,
    _walk_parent_message_seed,
)

# ---------------------------------------------------------------------------
# Fakes — these helpers only touch a few attributes of Memory / the saver
# ---------------------------------------------------------------------------


class _Tuple:
    def __init__(
        self,
        *,
        checkpoint: Any = None,
        config: Any = None,
        parent_config: Any = None,
        metadata: Any = None,
        pending_writes: Any = None,
    ) -> None:
        self.checkpoint = checkpoint
        self.config = config
        self.parent_config = parent_config
        self.metadata = metadata
        self.pending_writes = pending_writes


class _Saver:
    """Minimal saver: resolves ``get_tuple`` from a checkpoint_id map."""

    def __init__(self, tuples: dict[str, _Tuple] | None = None) -> None:
        self._tuples = tuples or {}
        self.conn: Any = None

    def get_tuple(self, config: dict[str, Any]) -> _Tuple | None:
        cid = str((config.get("configurable") or {}).get("checkpoint_id") or "")
        return self._tuples.get(cid)


class _Memory:
    def __init__(self, *, tup: Any = None, saver: Any = None, thread_state: Any = None) -> None:
        self._tup = tup
        self._checkpointer = saver or _Saver()
        self._thread_state = thread_state
        self.put_calls: list[Any] = []
        self.raise_on_get_tuple = False
        self.raise_on_put = False

    def _ensure_checkpointer(self) -> None:
        return None

    def get_tuple(self, config: dict[str, Any]) -> Any:
        if self.raise_on_get_tuple:
            raise RuntimeError("get_tuple exploded")
        return self._tup

    def put(self, config: Any, checkpoint: Any, metadata: Any, versions: Any) -> None:
        if self.raise_on_put:
            raise RuntimeError("put exploded")
        self.put_calls.append((config, checkpoint, metadata))

    def get_thread_state(self, thread_id: str) -> Any:
        return self._thread_state


class _State:
    def __init__(self, channel_values: Any) -> None:
        self.channel_values = channel_values


def _checkpoints_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT)")
    return conn


def _add_cp(conn: sqlite3.Connection, thread_id: str, ns: str, cid: str) -> None:
    conn.execute("INSERT INTO checkpoints VALUES (?, ?, ?)", (thread_id, ns, cid))
    conn.commit()


# ---------------------------------------------------------------------------
# Delta-omit detection
# ---------------------------------------------------------------------------


class TestMessagesOmitted:
    def test_versioned_but_not_inlined_is_omitted(self) -> None:
        cp = {"channel_versions": {"messages": "2"}, "channel_values": {}}
        assert _messages_omitted(cp) is True

    def test_inlined_is_not_omitted(self) -> None:
        cp = {"channel_versions": {"messages": "2"}, "channel_values": {"messages": []}}
        assert _messages_omitted(cp) is False

    def test_unversioned_is_not_omitted(self) -> None:
        assert _messages_omitted({"channel_versions": {}, "channel_values": {}}) is False

    def test_missing_keys_are_tolerated(self) -> None:
        assert _messages_omitted({}) is False

    @pytest.mark.parametrize(
        "cp",
        [
            {"channel_versions": "not-a-dict", "channel_values": {}},
            {"channel_versions": {"messages": "2"}, "channel_values": "not-a-dict"},
        ],
    )
    def test_malformed_shapes_do_not_raise(self, cp: dict[str, Any]) -> None:
        """Fixture / hand-written rows must not crash the prune pass."""
        assert _messages_omitted(cp) is False


# ---------------------------------------------------------------------------
# Message replay
# ---------------------------------------------------------------------------


class TestApplyMessageWrite:
    def test_none_write_leaves_messages_untouched(self) -> None:
        """``add_messages`` raises on a null right side; if that escaped it
        would abort the replay and permanently block pruning this thread.
        """
        from langchain_core.messages import HumanMessage

        existing = [HumanMessage(content="hi", id="m1")]
        assert _apply_message_write(existing, None) == existing

    def test_list_write_appends(self) -> None:
        from langchain_core.messages import HumanMessage

        out = _apply_message_write([], [HumanMessage(content="hi", id="m1")])
        assert [m.content for m in out] == ["hi"]

    def test_add_messages_dedupes_by_id(self) -> None:
        """The real reducer replaces same-id messages instead of appending."""
        from langchain_core.messages import HumanMessage

        first = _apply_message_write([], [HumanMessage(content="hi", id="m1")])
        second = _apply_message_write(first, [HumanMessage(content="edited", id="m1")])
        assert len(second) == 1
        assert second[0].content == "edited"

    def test_falls_back_to_plain_concat_without_langgraph(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "langgraph.graph.message", None)
        assert _apply_message_write(["a"], ["b"]) == ["a", "b"]
        assert _apply_message_write(["a"], "b") == ["a", "b"]
        assert _apply_message_write(["a"], None) == ["a"]


class TestWalkParentMessageSeed:
    def test_returns_messages_from_the_current_tuple(self) -> None:
        tup = _Tuple(checkpoint={"channel_values": {"messages": ["m1"]}}, config={"configurable": {}})
        assert _walk_parent_message_seed(_Saver(), tup) == ["m1"]

    def test_walks_up_to_an_ancestor_that_still_has_messages(self) -> None:
        parent = _Tuple(
            checkpoint={"channel_values": {"messages": ["seed"]}},
            config={"configurable": {"checkpoint_id": "cp-parent"}},
        )
        child = _Tuple(
            checkpoint={"channel_values": {}},
            config={"configurable": {"checkpoint_id": "cp-child"}},
            parent_config={"configurable": {"checkpoint_id": "cp-parent"}},
        )
        saver = _Saver({"cp-parent": parent})
        assert _walk_parent_message_seed(saver, child) == ["seed"]

    def test_self_referencing_parent_does_not_loop_forever(self) -> None:
        looping = _Tuple(
            checkpoint={"channel_values": {}},
            config={"configurable": {"checkpoint_id": "cp-1"}},
            parent_config={"configurable": {"checkpoint_id": "cp-1"}},
        )
        saver = _Saver({"cp-1": looping})
        assert _walk_parent_message_seed(saver, looping) == []

    def test_non_list_messages_yield_empty(self) -> None:
        tup = _Tuple(checkpoint={"channel_values": {"messages": "oops"}}, config={"configurable": {}})
        assert _walk_parent_message_seed(_Saver(), tup) == []

    def test_missing_parent_config_stops_the_walk(self) -> None:
        tup = _Tuple(checkpoint={"channel_values": {}}, config={"configurable": {}}, parent_config=None)
        assert _walk_parent_message_seed(_Saver(), tup) == []


class TestReconstructParentMessages:
    def test_replays_delta_seed_then_writes(self) -> None:
        from langchain_core.messages import HumanMessage

        saver = _Saver()
        saver.get_delta_channel_history = lambda config, channels: {  # type: ignore[attr-defined]
            "messages": {
                "seed": [HumanMessage(content="seed", id="m1")],
                "writes": [("task", "messages", [HumanMessage(content="written", id="m2")])],
            }
        }
        tup = _Tuple(checkpoint={"channel_values": {}}, config={"configurable": {}})
        out = _reconstruct_parent_messages(_Memory(saver=saver), tup)
        assert [m.content for m in out] == ["seed", "written"]

    def test_applies_pending_writes_on_top(self) -> None:
        from langchain_core.messages import HumanMessage

        saver = _Saver()
        saver.get_delta_channel_history = lambda config, channels: {  # type: ignore[attr-defined]
            "messages": {"seed": [HumanMessage(content="seed", id="m1")], "writes": []}
        }
        tup = _Tuple(
            checkpoint={"channel_values": {}},
            config={"configurable": {}},
            pending_writes=[
                ("task", "messages", [HumanMessage(content="pending", id="m2")]),
                ("task", "other", ["ignored"]),
            ],
        )
        out = _reconstruct_parent_messages(_Memory(saver=saver), tup)
        assert [m.content for m in out] == ["seed", "pending"]

    def test_a_null_message_write_does_not_abort_the_replay(self) -> None:
        """Regression: a null write used to raise out of the reducer, which
        ``_ensure_parent_sealed`` swallowed as "cannot prune".
        """
        from langchain_core.messages import HumanMessage

        saver = _Saver()
        saver.get_delta_channel_history = lambda config, channels: {  # type: ignore[attr-defined]
            "messages": {
                "seed": [HumanMessage(content="seed", id="m1")],
                "writes": [("task", "messages", None)],
            }
        }
        tup = _Tuple(checkpoint={"channel_values": {}}, config={"configurable": {}})
        out = _reconstruct_parent_messages(_Memory(saver=saver), tup)
        assert [m.content for m in out] == ["seed"]

    def test_non_dict_config_is_tolerated(self) -> None:
        tup = _Tuple(checkpoint={"channel_values": {"messages": ["m"]}}, config="not-a-dict")
        assert _reconstruct_parent_messages(_Memory(saver=_Saver()), tup) == ["m"]

    def test_falls_back_to_the_ancestor_walk_without_delta_support(self) -> None:
        tup = _Tuple(checkpoint={"channel_values": {"messages": ["only"]}}, config={"configurable": {}})
        assert _reconstruct_parent_messages(_Memory(saver=_Saver()), tup) == ["only"]


# ---------------------------------------------------------------------------
# Sealing decision — must fail closed
# ---------------------------------------------------------------------------


class TestEnsureParentSealed:
    def test_absent_parent_does_not_block_prune(self) -> None:
        decision = _ensure_parent_sealed(_Memory(tup=None), "t1", dry_run=False)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is True
        assert decision.sealed is False

    def test_get_tuple_failure_does_not_block_prune(self) -> None:
        mem = _Memory(tup=None)
        mem.raise_on_get_tuple = True
        decision = _ensure_parent_sealed(mem, "t1", dry_run=False)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is True

    def test_inlined_parent_needs_no_sealing(self) -> None:
        tup = _Tuple(checkpoint={"channel_versions": {"messages": "1"}, "channel_values": {"messages": ["m"]}})
        decision = _ensure_parent_sealed(_Memory(tup=tup), "t1", dry_run=False)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is True
        assert decision.sealed is False

    def test_empty_replay_blocks_prune(self) -> None:
        """A delta-omit parent whose transcript cannot be rebuilt must keep
        its ancestors — deleting them would lose the messages for good.
        """
        tup = _Tuple(
            checkpoint={"channel_versions": {"messages": "2"}, "channel_values": {}},
            config={"configurable": {}},
        )
        decision = _ensure_parent_sealed(_Memory(tup=tup), "t1", dry_run=False)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is False
        assert decision.sealed is False

    def test_replay_exception_blocks_prune(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import octop_memory.pipeline.lifecycle.checkpoint_gc as gc_mod

        def _boom(*_a: Any, **_k: Any) -> list[Any]:
            raise RuntimeError("replay exploded")

        monkeypatch.setattr(gc_mod, "_reconstruct_parent_messages", _boom)
        tup = _Tuple(
            checkpoint={"channel_versions": {"messages": "2"}, "channel_values": {}},
            config={"configurable": {}},
        )
        decision = _ensure_parent_sealed(_Memory(tup=tup), "t1", dry_run=False)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is False

    def test_seal_write_failure_blocks_prune(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import octop_memory.pipeline.lifecycle.checkpoint_gc as gc_mod

        monkeypatch.setattr(gc_mod, "_reconstruct_parent_messages", lambda *_a, **_k: ["m"])
        mem = _Memory(
            tup=_Tuple(
                checkpoint={"channel_versions": {"messages": "2"}, "channel_values": {}},
                config={"configurable": {}},
            )
        )
        mem.raise_on_put = True
        decision = _ensure_parent_sealed(mem, "t1", dry_run=False)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is False
        assert decision.sealed is False

    def test_dry_run_reports_sealing_without_writing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import octop_memory.pipeline.lifecycle.checkpoint_gc as gc_mod

        monkeypatch.setattr(gc_mod, "_reconstruct_parent_messages", lambda *_a, **_k: ["m"])
        mem = _Memory(
            tup=_Tuple(
                checkpoint={"channel_versions": {"messages": "2"}, "channel_values": {}},
                config={"configurable": {}},
            )
        )
        decision = _ensure_parent_sealed(mem, "t1", dry_run=True)  # type: ignore[arg-type]
        assert decision.can_prune_ancestors is True
        assert decision.sealed is True
        assert mem.put_calls == []


# ---------------------------------------------------------------------------
# In-flight turn detection
# ---------------------------------------------------------------------------


class TestParentTurnFinished:
    def test_absent_state_is_not_finished(self) -> None:
        assert _parent_turn_finished(_Memory(thread_state=None), "t1") is False  # type: ignore[arg-type]

    def test_interrupted_turn_is_not_finished(self) -> None:
        """HITL: an interrupt means the graph is parked waiting on the user."""
        state = _State({"__interrupt__": [{"value": "approve?"}], "messages": ["m"]})
        assert _parent_turn_finished(_Memory(thread_state=state), "t1") is False  # type: ignore[arg-type]

    def test_empty_messages_is_not_finished(self) -> None:
        memory = _Memory(thread_state=_State({"messages": []}))
        assert _parent_turn_finished(memory, "t1") is False  # type: ignore[arg-type]

    def test_trailing_tool_call_is_not_finished(self) -> None:
        state = _State({"messages": [{"type": "ai", "tool_calls": [{"id": "c1"}]}]})
        assert _parent_turn_finished(_Memory(thread_state=state), "t1") is False  # type: ignore[arg-type]

    def test_trailing_human_message_is_not_finished(self) -> None:
        state = _State({"messages": [{"type": "human"}]})
        assert _parent_turn_finished(_Memory(thread_state=state), "t1") is False  # type: ignore[arg-type]

    def test_trailing_final_ai_reply_is_finished(self) -> None:
        state = _State({"messages": [{"type": "ai"}]})
        assert _parent_turn_finished(_Memory(thread_state=state), "t1") is True  # type: ignore[arg-type]


class TestMessageShapeHelpers:
    @pytest.mark.parametrize(
        ("msg", "expected"),
        [
            ({"tool_calls": [{"id": "c1"}]}, True),
            ({"tool_calls": []}, False),
            ({}, False),
        ],
    )
    def test_tool_calls_on_dicts(self, msg: dict[str, Any], expected: bool) -> None:
        assert _message_has_tool_calls(msg) is expected

    def test_tool_calls_on_objects(self) -> None:
        from langchain_core.messages import AIMessage

        assert _message_has_tool_calls(AIMessage(content="x", tool_calls=[])) is False
        with_calls = AIMessage(
            content="x",
            tool_calls=[{"id": "c1", "name": "bash", "args": {}}],
        )
        assert _message_has_tool_calls(with_calls) is True

    @pytest.mark.parametrize(
        ("msg", "expected"),
        [
            ({"type": "ai"}, True),
            ({"type": "AIMessage"}, True),
            ({"type": "human"}, False),
            ({}, False),
        ],
    )
    def test_is_ai_on_dicts(self, msg: dict[str, Any], expected: bool) -> None:
        assert _message_is_ai(msg) is expected

    def test_is_ai_on_objects(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        assert _message_is_ai(AIMessage(content="x")) is True
        assert _message_is_ai(HumanMessage(content="x")) is False


# ---------------------------------------------------------------------------
# Subgraph / stream bookkeeping
# ---------------------------------------------------------------------------


class TestSubgraphNewerThanParent:
    def test_no_parent_row_is_treated_as_unsafe(self) -> None:
        """No parent snapshot means we cannot reason about ordering, so the
        conservative answer keeps the subgraph rows.
        """
        conn = _checkpoints_conn()
        _add_cp(conn, "t1", "tools:1", "cp-5")
        assert _subgraph_newer_than_parent(conn, "t1") is True

    def test_subgraph_ahead_of_parent(self) -> None:
        conn = _checkpoints_conn()
        _add_cp(conn, "t1", "", "cp-3")
        _add_cp(conn, "t1", "tools:1", "cp-9")
        assert _subgraph_newer_than_parent(conn, "t1") is True

    def test_subgraph_behind_parent(self) -> None:
        conn = _checkpoints_conn()
        _add_cp(conn, "t1", "", "cp-9")
        _add_cp(conn, "t1", "tools:1", "cp-3")
        assert _subgraph_newer_than_parent(conn, "t1") is False

    def test_other_threads_do_not_leak_in(self) -> None:
        conn = _checkpoints_conn()
        _add_cp(conn, "t1", "", "cp-5")
        _add_cp(conn, "t2", "tools:1", "cp-9")
        assert _subgraph_newer_than_parent(conn, "t1") is False


class TestThreadNsPairs:
    def test_scoped_to_one_thread(self) -> None:
        conn = _checkpoints_conn()
        _add_cp(conn, "t1", "", "cp-1")
        _add_cp(conn, "t1", "tools:1", "cp-2")
        _add_cp(conn, "t2", "", "cp-3")

        assert sorted(_thread_ns_pairs(conn, thread_id="t1")) == [("t1", ""), ("t1", "tools:1")]

    def test_all_streams(self) -> None:
        conn = _checkpoints_conn()
        _add_cp(conn, "t1", "", "cp-1")
        _add_cp(conn, "t2", "", "cp-2")
        assert sorted(_thread_ns_pairs(conn, thread_id=None)) == [("t1", ""), ("t2", "")]


class TestVictimSelection:
    def test_empty_stream_has_no_victims(self) -> None:
        conn = _checkpoints_conn()
        assert _victim_checkpoint_ids(conn, "t1", "", keep_last=1, cutoff_id=None) == []

    def test_latest_checkpoint_always_survives(self) -> None:
        """Even a cutoff far in the future must not erase the only usable state."""
        conn = _checkpoints_conn()
        for cid in ("cp-1", "cp-2", "cp-3"):
            _add_cp(conn, "t1", "", cid)

        victims = _victim_checkpoint_ids(conn, "t1", "", keep_last=None, cutoff_id="cp-9")
        assert "cp-3" not in victims
        assert sorted(victims) == ["cp-1", "cp-2"]

    def test_keep_last_and_cutoff_union(self) -> None:
        conn = _checkpoints_conn()
        for cid in ("cp-1", "cp-2", "cp-3", "cp-4"):
            _add_cp(conn, "t1", "", cid)

        # keep_last spares cp-4; cutoff spares cp-2 and above.
        victims = _victim_checkpoint_ids(conn, "t1", "", keep_last=1, cutoff_id="cp-2")
        assert victims == ["cp-1"]


class TestCheckpointerConnRequirement:
    def test_non_sqlite_checkpointer_raises_instead_of_silently_skipping(self) -> None:
        class _NotASaver:
            conn = "definitely not a sqlite3.Connection"

        with pytest.raises(RuntimeError, match="requires the SQLite checkpointer"):
            _get_checkpointer_conn(_Memory(saver=_NotASaver()))  # type: ignore[arg-type]

    def test_missing_conn_attribute_raises(self) -> None:
        class _NoConn:
            pass

        with pytest.raises(RuntimeError, match="PostgreSQL checkpoint pruning is not yet supported"):
            _get_checkpointer_conn(_Memory(saver=_NoConn()))  # type: ignore[arg-type]
