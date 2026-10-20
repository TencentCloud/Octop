"""Behaviour parity between the SQLite and Postgres backends.

Both classes implement the same ``MemoryBackend`` protocol, but the SQLite
one is exercised by most of this suite while ``tests/test_postgres.py``
only covered nodes / FTS indexes / namespace isolation — leaving the
Postgres implementation of raw events, candidates, atoms, entities,
pages, journal, meta, episodes and digests unrun.

Divergence between two hand-written SQL implementations is a real bug
class here (a SQLite-only GC pass once ran ``?`` placeholders against
Postgres and poisoned the connection), so every test below runs against
both backends rather than asserting one of them in isolation.

Postgres tests skip when psycopg is missing or no server answers.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from octop_memory.domain.alias import normalize_alias
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import (
    ActiveEntity,
    Alias,
    AtomCard,
    Candidate,
    DigestRecord,
    Entity,
    EntityPage,
    Episode,
    JournalEntry,
    MemoryNode,
    RawEvent,
)

PG_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://localhost/octop_memory_test")


class TestManualDocumentGovernanceParity:
    class Model:
        def call_llm(self, prompt: str, **kwargs: Any) -> str:
            data = json.loads(prompt)
            return json.dumps(
                {
                    "matches": [
                        {
                            "atom_id": atom["id"],
                            "relation": "conflict",
                            "document": "USER.md",
                            "quote": "The user prefers Chinese replies.",
                            "confidence": "high",
                            "same_subject": True,
                            "same_scope": True,
                        }
                        for atom in data["atoms"]
                    ]
                }
            )

    def test_conflict_candidate_deprecation_evidence_and_recall(self, backend: Any) -> None:
        from octop_memory import Memory, MemoryService
        from octop_memory.application.dashboard_data import promote_candidate
        from octop_memory.pipeline.recall import recall_for_prompt

        memory = Memory(namespace="manual_parity", backend=backend)
        memory.store("The user prefers English replies.")
        old = memory.list_atoms()[0]
        service = MemoryService(memory, llm=self.Model())
        docs = {"USER.md": "The user prefers Chinese replies."}
        first = service.reconcile_manual_documents(docs)
        assert first["conflicts"] == 1
        assert memory.get_atom(old.id).deprecated_at is not None
        assert memory.get_raw(old.quote_event_id) is not None
        assert not recall_for_prompt(memory, "English", raw_policy="always").snippets
        assert service.reconcile_manual_documents(docs)["conflicts"] == 1
        candidate = memory.list_candidates(status="conflict")[0]
        assert candidate.payload["demoted_atom_id"] == old.id
        promote_candidate(memory, {"candidate_id": candidate.id})
        assert [a.assertion for a in memory.list_atoms()] == [docs["USER.md"]]

    @pytest.mark.parametrize("filename", ["USER.md", "MEMORY.md"])
    def test_duplicate_uses_session_snapshot_without_deleting_atom(self, backend: Any, filename: str) -> None:
        from octop_memory import Memory, MemoryService

        memory = Memory(namespace="manual_parity", backend=backend)
        memory.store("Aurora uses PostgreSQL.")
        service = MemoryService(memory)
        docs = {filename: "Aurora uses PostgreSQL."}
        assert service.reconcile_manual_documents(docs)["duplicates"] == 1
        assert not service.recall("PostgreSQL", manual_context=docs).snippets
        assert service.recall("PostgreSQL").snippets
        assert len(memory.list_atoms()) == 1

    def test_quarantine_rolls_back_on_failure(self, backend: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        from octop_memory import Memory, MemoryService
        from octop_memory.domain.retention import MANUAL_DOCUMENTS_META_KEY

        memory = Memory(namespace="manual_parity", backend=backend)
        memory.store("The user prefers English replies.")
        raw_ids = {event.id for event in memory.list_raw()}

        def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("candidate write failed")

        monkeypatch.setattr(memory, "add_candidate", fail)
        with pytest.raises(RuntimeError, match="candidate write failed"):
            MemoryService(memory, llm=self.Model()).reconcile_manual_documents(
                {"USER.md": "The user prefers Chinese replies."}
            )
        assert len(memory.list_atoms()) == 1
        assert memory.list_candidates(status="conflict") == []
        assert {event.id for event in memory.list_raw()} == raw_ids
        assert memory.get_meta(MANUAL_DOCUMENTS_META_KEY) is None


class TestRuntimeErrorRetentionParity:
    FAILURE = "Model call failed after 3 attempts with AuthenticationError: 401 token_expired"

    @pytest.mark.parametrize("origin", ["unmarked", "missing", "mixed"])
    def test_unknown_origin_is_review_only_and_never_retired(self, backend: Any, origin: str) -> None:
        from octop_memory import Memory
        from octop_memory.operations.retention import audit_runtime_errors

        memory = Memory(namespace="retention", backend=backend)
        marker = {"octop_runtime_error": True} if origin == "mixed" else {}
        backend.save_raw(_make_raw(event_type="assistant_message", payload=marker, content=self.FAILURE))
        refs = ["raw-1"]
        if origin == "missing":
            refs.append("missing-source")
        elif origin == "mixed":
            backend.save_raw(_make_raw(id="user-context", content="检查一下这个请求"))
            refs.append("user-context")
        backend.save_entity(_make_entity(atom_count=1))
        backend.save_candidate(_make_candidate(status="promoted", raw_event_ids=refs))
        memory.add_atom(_make_atom(raw_event_ids=refs))
        backend.save_candidate(_make_candidate(id="pending", raw_event_ids=refs))
        for apply in (False, True):
            report = audit_runtime_errors(memory, apply=apply)
            assert report.atom_ids == [] and report.candidate_ids == []
            assert report.review_atom_ids == ["atom-1"]
            assert report.review_candidate_ids == ["pending"]
            assert memory.get_atom("atom-1").deprecated_at is None
            assert memory.get_candidate("pending").status == "pending"
            assert not memory.list_journal(action="deprecate")

    def test_capture_and_marked_raw_recall(self, backend: Any) -> None:
        from octop_memory import Memory
        from octop_memory.application.runtime import MemoryRuntime
        from octop_memory.pipeline.recall import recall_for_prompt

        memory = Memory(namespace="retention", backend=backend)
        runtime = MemoryRuntime(memory, config={"capture": {"min_message_chars": 0}})
        result = runtime.capture(
            {
                "events": [
                    {"event_type": "user_message", "content": "401 故障要验证修复成功。"},
                    {
                        "event_type": "assistant_message",
                        "content": self.FAILURE,
                        "payload": {"octop_runtime_error": True},
                    },
                ]
            }
        )
        assert result["accepted"] == 1
        assert result["skipped_runtime_error"] == 1
        backend.save_raw(
            _make_raw(
                event_type="assistant_message",
                content=self.FAILURE,
                payload={"role": "assistant", "octop_runtime_error": True},
            )
        )
        assert not recall_for_prompt(memory, "token_expired", raw_policy="always").snippets
        assert memory.get_raw("raw-1") is not None

    @pytest.mark.parametrize("protection", ["none", "user_source", "manual", "approved", "lesson", "edited", "missing"])
    def test_audit_preview_soft_retirement_and_protections(self, backend: Any, protection: str) -> None:
        from octop_memory import Memory
        from octop_memory.operations.retention import audit_runtime_errors
        from octop_memory.pipeline.recall import recall_for_prompt

        memory = Memory(namespace="retention", backend=backend)
        backend.save_raw(
            _make_raw(
                event_type="assistant_message",
                content=self.FAILURE,
                payload={"role": "assistant", "octop_runtime_error": True},
            )
        )
        refs = ["raw-1"]
        quote_id = "raw-1"
        overrides: dict[str, Any] = {}
        assertion = "Authentication token expired (401, token_expired)"
        if protection == "user_source":
            backend.save_raw(_make_raw(id="request", content="这次认证故障是历史事件。"))
            refs.append("request")
        elif protection == "manual":
            overrides["extractor_version"] = "manual/v1"
        elif protection == "approved":
            overrides["decided_by"] = "user"
        elif protection == "lesson":
            assertion = "Refresh credentials and confirm a successful request."
            backend.save_raw(_make_raw(id="lesson", event_type="assistant_message", payload={}, content=assertion))
            refs.append("lesson")
            quote_id = "lesson"
        elif protection == "missing":
            refs.append("unknown")
        backend.save_entity(_make_entity(atom_count=1))
        backend.upsert_entity_page(_make_page(dirty=False, headline="token_expired"))
        backend.save_candidate(
            _make_candidate(
                status="promoted",
                assertion=assertion,
                verbatim_quote=self.FAILURE,
                raw_event_ids=refs,
                quote_event_id=quote_id,
                **overrides,
            )
        )
        memory.add_atom(
            _make_atom(
                assertion=assertion,
                verbatim_quote=self.FAILURE,
                raw_event_ids=refs,
                quote_event_id=quote_id,
            )
        )
        atom_id = "atom-1"
        if protection == "edited":
            updated = memory.replace_atom("atom-1", assertion="Verified: refresh the token and check success.")
            assert updated is not None
            atom_id = updated.id

        before = audit_runtime_errors(memory)
        expected = ["atom-1"] if protection == "none" else []
        assert before.atom_ids == expected
        assert before.atoms_deprecated == 0
        assert memory.get_atom(atom_id).deprecated_at is None
        result = audit_runtime_errors(memory, apply=True)
        assert result.atoms_deprecated == len(expected)
        assert (memory.get_atom(atom_id).deprecated_at is not None) == bool(expected)
        assert memory.get_raw("raw-1").content == self.FAILURE
        assert audit_runtime_errors(memory, apply=True).atoms_deprecated == 0
        if expected:
            assert memory.get_entity_page("ent-1").dirty
            assert not recall_for_prompt(memory, "token_expired", raw_policy="always").snippets
            assert memory.list_journal(action="deprecate")[0].actor == "rule"

    def test_pending_error_rejected_but_manual_save_stays(self, backend: Any) -> None:
        from octop_memory import Memory
        from octop_memory.operations.retention import audit_runtime_errors

        memory = Memory(namespace="retention", backend=backend)
        backend.save_raw(
            _make_raw(
                event_type="assistant_message",
                content=self.FAILURE,
                payload={"role": "assistant", "octop_runtime_error": True},
            )
        )
        backend.save_candidate(_make_candidate())
        manual = memory.store("记住：401 排障后需要验证请求成功。")
        report = audit_runtime_errors(memory, apply=True)
        assert report.candidates_rejected == 1
        assert memory.get_candidate("cand-1").status == "rejected"
        assert memory.get_atom(manual.atom_id).deprecated_at is None

    def test_promotion_cannot_bypass_runtime_error_gate(self, backend: Any) -> None:
        from octop_memory import Memory

        memory = Memory(namespace="retention", backend=backend)
        backend.save_raw(
            _make_raw(
                event_type="assistant_message",
                content=self.FAILURE,
                payload={"role": "assistant", "octop_runtime_error": True},
            )
        )
        backend.save_candidate(_make_candidate())
        assert memory.promote_candidates().dropped == 1
        assert not memory.list_atoms()

    def test_audit_rolls_back_if_a_decision_cannot_be_journaled(self, backend: Any, monkeypatch: Any) -> None:
        from octop_memory import Memory
        from octop_memory.operations.retention import audit_runtime_errors

        memory = Memory(namespace="retention", backend=backend)
        backend.save_raw(
            _make_raw(
                event_type="assistant_message",
                content=self.FAILURE,
                payload={"role": "assistant", "octop_runtime_error": True},
            )
        )
        backend.save_entity(_make_entity(atom_count=1))
        backend.save_candidate(_make_candidate(status="promoted"))
        memory.add_atom(_make_atom())
        backend.save_candidate(_make_candidate(id="pending"))

        def fail(_: Any) -> None:
            raise RuntimeError("injected journal failure")

        monkeypatch.setattr(memory, "append_journal", fail)
        with pytest.raises(RuntimeError, match="injected journal failure"):
            audit_runtime_errors(memory, apply=True)
        assert memory.get_atom("atom-1").deprecated_at is None
        assert memory.get_candidate("pending").status == "pending"
        assert not memory.list_journal(action="deprecate")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def test_checkpoint_stable_fields_keep_historical_values(backend: Any) -> None:
    """SQLite's new encoding and the unchanged Postgres saver expose the same state."""
    from langgraph.checkpoint.base import empty_checkpoint

    from octop_memory.core import Memory

    memory = Memory(namespace="checkpoint_parity", backend=backend)
    thread = f"parity-stable-{uuid.uuid4().hex}"
    config: Any = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
    expected: list[Any] = []
    configs: list[Any] = []
    try:
        for text in ("old", "old", "new"):
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = {
                "skills_metadata": [{"name": "skill", "description": text * 1000}],
                "memory_contents": {"AGENTS.md": text * 1000},
            }
            checkpoint["channel_versions"] = dict.fromkeys(checkpoint["channel_values"], len(expected) + 1)
            config = memory.put(
                config, checkpoint, {"source": "loop", "step": len(expected)}, checkpoint["channel_versions"]
            )
            configs.append(config)
            expected.append(checkpoint["channel_values"])
        for cfg, values in zip(configs, expected, strict=True):
            result = memory.get_tuple(cfg)
            assert result.checkpoint["channel_values"] == values
        result.checkpoint["channel_values"]["memory_contents"]["AGENTS.md"] = "caller edit"
        assert memory.get_tuple(configs[-1]).checkpoint["channel_values"] == expected[-1]
        history_config = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
        assert [item.checkpoint["channel_values"] for item in memory.list(history_config)] == expected[::-1]
    finally:
        memory.delete_thread(thread)
        if memory._checkpointer_pool is not None:
            memory._checkpointer_pool.close()
        elif memory._checkpointer is not None:
            memory._checkpointer.conn.close()


@pytest.mark.asyncio
async def test_checkpoint_resume_after_reopen_keeps_completed_work(backend: Any) -> None:
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.types import Command, interrupt

    from octop_memory.core import Memory

    memory = Memory(namespace="resume_parity", backend=backend)
    reopened = None
    completed: list[str] = []
    thread = f"parity-resume-{uuid.uuid4().hex}"
    config: Any = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}

    def prepare(state):
        completed.append("prepared")
        return {"messages": [("ai", "prepared")]}

    def approve(state):
        answer = interrupt("approve")
        return {"messages": [("ai", answer)]}

    builder = StateGraph(MessagesState)
    builder.add_node("prepare", prepare)
    builder.add_node("approve", approve)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "approve")
    builder.add_edge("approve", END)

    def close_saver(instance):
        if instance._checkpointer_pool is not None:
            instance._checkpointer_pool.close()
        elif instance._checkpointer is not None:
            instance._checkpointer.conn.close()

    try:
        graph = builder.compile(checkpointer=memory)
        await graph.ainvoke({"messages": [("human", "hello")]}, config)
        assert (await graph.aget_state(config)).tasks[0].interrupts
        close_saver(memory)
        reopened = Memory(namespace="resume_parity", backend=backend)
        restored = builder.compile(checkpointer=reopened)
        assert (await restored.aget_state(config)).tasks[0].interrupts
        result = await restored.ainvoke(Command(resume="approved"), config)
        assert [m.content for m in result["messages"]] == ["hello", "prepared", "approved"]
        assert completed == ["prepared"]
        assert not (await restored.aget_state(config)).tasks
    finally:
        if reopened is not None:
            await reopened.adelete_thread(thread)
            close_saver(reopened)
        else:
            close_saver(memory)


@pytest.fixture(params=["sqlite", "postgres"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    """Yield each backend in turn against an empty, isolated namespace."""
    if request.param == "sqlite":
        be = SqliteMemoryBackend(namespace="parity", db_path=tmp_path / "parity.sqlite")
        yield be
        be.close()
        return

    request.getfixturevalue("postgres_dsn")
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

    ns = f"parity_{uuid.uuid4().hex[:12]}"
    be = PostgresMemoryBackend(namespace=ns, dsn=PG_DSN)
    try:
        yield be
    finally:
        if not be._closed:
            be.purge_namespace()
        be.close()


def _expect_duplicate(backend: Any) -> type[BaseException]:
    """The error a strict re-insert raises on this backend."""
    if isinstance(backend, SqliteMemoryBackend):
        import sqlite3

        return sqlite3.IntegrityError
    import psycopg

    return psycopg.errors.UniqueViolation


def _recover(backend: Any) -> None:
    """Postgres aborts the whole transaction on error; SQLite does not."""
    if not isinstance(backend, SqliteMemoryBackend):
        # Operation/transaction contexts now return a clean connection.
        assert backend._conn is None


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_raw(**overrides: Any) -> RawEvent:
    base: dict[str, Any] = {
        "id": "raw-1",
        "host": "openclaw",
        "session_id": "sess-1",
        "thread_id": "thr-1",
        "user": "alice",
        "timestamp": _now(),
        "event_type": "user_message",
        "content": "we decided to ship augment mode first",
        "payload": {"role": "user"},
    }
    base.update(overrides)
    return RawEvent(**base)


@pytest.mark.parametrize("rollback", [False, True])
def test_threaded_writes_keep_independent_transaction_boundaries(backend: Any, rollback: bool) -> None:
    """A second thread must not commit or roll back the first thread's writes."""
    from concurrent.futures import ThreadPoolExecutor

    entered, release, other_started, other_done = (threading.Event() for _ in range(4))

    class Rollback(Exception):
        pass

    def owner() -> None:
        try:
            with backend.transaction():
                with backend.transaction():  # Nested writes stay in the outer transaction.
                    backend.save_raw(_make_raw(id="owned"))
                entered.set()
                assert release.wait(timeout=5)
                if rollback:
                    raise Rollback
        except Rollback:
            pass

    def other() -> None:
        other_started.set()
        backend.save_raw(_make_raw(id="independent"))
        other_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(owner)
        assert entered.wait(timeout=5)
        second = pool.submit(other)
        assert other_started.wait(timeout=5)
        try:
            assert not other_done.wait(timeout=0.05)
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert (backend.get_raw("owned") is None) is rollback
    assert backend.get_raw("independent") is not None


def test_failed_standalone_write_does_not_pin_an_aborted_transaction(backend: Any) -> None:
    from concurrent.futures import ThreadPoolExecutor

    backend.save_raw(_make_raw(id="existing"))
    with pytest.raises(_expect_duplicate(backend)):
        backend.save_raw(_make_raw(id="existing"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(backend.save_raw, _make_raw(id="after_failure"))
        pending.result(timeout=5)
    assert backend.get_raw("after_failure") is not None


def _make_candidate(**overrides: Any) -> Candidate:
    base: dict[str, Any] = {
        "id": "cand-1",
        "raw_event_ids": ["raw-1"],
        "candidate_type": "Decision",
        "status": "pending",
        "title": "Augment mode",
        "assertion": "ship augment mode before replace mode",
        "verbatim_quote": "ship augment mode before replace mode",
        "quote_event_id": "raw-1",
        "subject_name": "Octop Memory",
        "subject_entity_type": "Project",
        "target_entity_id": None,
        "confidence": "high",
        "importance": "high",
        "recommended_action": "promote",
        "promotion_reason": "explicit decision",
        "extractor_version": "v2.0",
        "created_at": _now(),
        "session_id": "sess-1",
    }
    base.update(overrides)
    return Candidate(**base)


def _make_atom(**overrides: Any) -> AtomCard:
    base: dict[str, Any] = {
        "id": "atom-1",
        "entity_id": "ent-1",
        "candidate_id": "cand-1",
        "raw_event_ids": ["raw-1"],
        "assertion": "ship augment mode before replace mode",
        "verbatim_quote": "ship augment mode before replace mode",
        "quote_event_id": "raw-1",
        "search_terms": ["augment", "replace"],
        "occurred_at": _now(),
        "confidence": "high",
        "importance": "high",
        "created_at": _now(),
    }
    base.update(overrides)
    return AtomCard(**base)


def _make_entity(**overrides: Any) -> Entity:
    base: dict[str, Any] = {
        "id": "ent-1",
        "entity_type": "Project",
        "canonical_name": "Octop Memory",
        "aliases": ["LCM"],
        "atom_count": 0,
        "created_at": _now(),
    }
    base.update(overrides)
    return Entity(**base)


def _make_page(**overrides: Any) -> EntityPage:
    base: dict[str, Any] = {
        "id": "page-1",
        "entity_id": "ent-1",
        "summary_markdown": "# Octop Memory\n\nA memory plugin.",
        "headline": "memory plugin",
        "topics": ["memory"],
        "dirty": True,
        "regen_attempt_count": 0,
        "summary_version": 1,
        "created_at": _now(),
        "updated_at": _now(),
    }
    base.update(overrides)
    return EntityPage(**base)


def _make_episode(**overrides: Any) -> Episode:
    base: dict[str, Any] = {
        "id": "ep-1",
        "raw_event_ids": ["raw-1"],
        "occurred_at": _now(),
        "summary": "user shipped the augment milestone",
        "verbatim_quote": "we finally shipped it",
        "quote_event_id": "raw-1",
        "emotion": "happy",
        "intensity": 4,
        "people": ["teammate"],
        "topics": ["work"],
        "extractor_version": "ep-v1",
        "created_at": _now(),
        "session_id": "sess-1",
    }
    base.update(overrides)
    return Episode(**base)


def _make_digest(**overrides: Any) -> DigestRecord:
    start = datetime(2026, 6, 22, tzinfo=UTC)
    base: dict[str, Any] = {
        "id": "dig-1",
        "period_kind": "weekly",
        "period_key": "2026-W26",
        "period_start": start,
        "period_end": start + timedelta(days=7),
        "markdown": "## Week 26\n\nShipped augment mode.",
        "episode_ids": ["ep-1"],
        "llm_version": "digest-v1",
        "created_at": _now(),
        "updated_at": _now(),
    }
    base.update(overrides)
    return DigestRecord(**base)


# ---------------------------------------------------------------------------
# L0 raw events
# ---------------------------------------------------------------------------


class TestRawEventParity:
    def test_round_trip_preserves_every_field(self, backend: Any) -> None:
        event = _make_raw()
        backend.save_raw(event)

        loaded = backend.get_raw("raw-1")
        assert loaded is not None
        assert loaded.host == "openclaw"
        assert loaded.session_id == "sess-1"
        assert loaded.thread_id == "thr-1"
        assert loaded.user == "alice"
        assert loaded.event_type == "user_message"
        assert loaded.content == event.content
        assert loaded.payload == {"role": "user"}
        # Timestamps must come back timezone-aware on both backends.
        assert loaded.timestamp.tzinfo is not None

    def test_get_missing_returns_none(self, backend: Any) -> None:
        assert backend.get_raw("nope") is None

    def test_batch_insert(self, backend: Any) -> None:
        backend.save_raw_batch([_make_raw(id=f"raw-{i}") for i in range(5)])
        assert len(backend.list_raw(limit=100)) == 5

    def test_optional_columns_round_trip_as_none(self, backend: Any) -> None:
        backend.save_raw(_make_raw(session_id=None, thread_id=None, user=None, payload={}))
        loaded = backend.get_raw("raw-1")
        assert loaded is not None
        assert loaded.session_id is None
        assert loaded.thread_id is None
        assert loaded.user is None
        assert loaded.payload == {}

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"host": "hermes"}, {"raw-b"}),
            ({"session_id": "s-a"}, {"raw-a"}),
            ({"thread_id": "t-b"}, {"raw-b"}),
            ({"user": "bob"}, {"raw-b"}),
            ({"event_type": "assistant_message"}, {"raw-b"}),
        ],
    )
    def test_list_filters(self, backend: Any, kwargs: dict[str, Any], expected: set[str]) -> None:
        backend.save_raw(
            _make_raw(
                id="raw-a",
                host="openclaw",
                session_id="s-a",
                thread_id="t-a",
                user="alice",
                event_type="user_message",
            )
        )
        backend.save_raw(
            _make_raw(
                id="raw-b",
                host="hermes",
                session_id="s-b",
                thread_id="t-b",
                user="bob",
                event_type="assistant_message",
            )
        )
        assert {e.id for e in backend.list_raw(**kwargs)} == expected

    def test_list_time_window_and_ordering(self, backend: Any) -> None:
        old, new = _now() - timedelta(days=2), _now()
        backend.save_raw(_make_raw(id="old", timestamp=old))
        backend.save_raw(_make_raw(id="new", timestamp=new))

        # Ordered newest-first.
        assert [e.id for e in backend.list_raw()] == ["new", "old"]
        cutoff = _now() - timedelta(days=1)
        assert [e.id for e in backend.list_raw(after=cutoff)] == ["new"]
        assert [e.id for e in backend.list_raw(before=cutoff)] == ["old"]

    def test_search_matches_content(self, backend: Any) -> None:
        backend.save_raw(_make_raw(id="hit", content="kubernetes rollout notes"))
        backend.save_raw(_make_raw(id="miss", content="grocery shopping list"))
        assert {e.id for e in backend.search_raw("kubernetes")} == {"hit"}

    def test_delete_before_returns_count(self, backend: Any) -> None:
        backend.save_raw(_make_raw(id="old", timestamp=_now() - timedelta(days=5)))
        backend.save_raw(_make_raw(id="new", timestamp=_now()))

        deleted = backend.delete_raw_before(_now() - timedelta(days=1))
        assert deleted == 1
        assert {e.id for e in backend.list_raw()} == {"new"}

    def test_get_by_ids_skips_unknown(self, backend: Any) -> None:
        backend.save_raw(_make_raw(id="raw-a"))
        backend.save_raw(_make_raw(id="raw-b"))
        got = backend.get_raw_events_by_ids(["raw-a", "raw-b", "ghost"])
        assert {e.id for e in got} == {"raw-a", "raw-b"}

    def test_get_by_ids_empty_input(self, backend: Any) -> None:
        assert backend.get_raw_events_by_ids([]) == []


# ---------------------------------------------------------------------------
# L1 candidates
# ---------------------------------------------------------------------------


class TestCandidateParity:
    def test_round_trip(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate())
        loaded = backend.get_candidate("cand-1")
        assert loaded is not None
        assert loaded.assertion == "ship augment mode before replace mode"
        assert loaded.raw_event_ids == ["raw-1"]
        assert loaded.session_id == "sess-1"
        assert loaded.status == "pending"
        assert loaded.decided_at is None
        assert loaded.payload == {}

    def test_duplicate_id_raises(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate())
        with pytest.raises(_expect_duplicate(backend)):
            backend.save_candidate(_make_candidate())
        _recover(backend)

    def test_list_filters(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate(id="c1", status="pending", session_id="s1"))
        backend.save_candidate(_make_candidate(id="c2", status="promoted", session_id="s2"))
        backend.save_candidate(_make_candidate(id="c3", status="pending", target_entity_id="ent-X"))

        assert {c.id for c in backend.list_candidates(status="pending")} == {"c1", "c3"}
        assert {c.id for c in backend.list_candidates(session_id="s2")} == {"c2"}
        assert {c.id for c in backend.list_candidates(target_entity_id="ent-X")} == {"c3"}

    def test_update_status_writes_decision_fields(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate())
        when = _now()
        ok = backend.update_candidate_status(
            "cand-1",
            status="promoted",
            decided_by="user",
            decided_at=when,
            target_entity_id="ent-9",
            promotion_reason="reviewed",
        )
        assert ok is True

        loaded = backend.get_candidate("cand-1")
        assert loaded is not None
        assert loaded.status == "promoted"
        assert loaded.decided_by == "user"
        assert loaded.decided_at is not None
        assert loaded.target_entity_id == "ent-9"
        assert loaded.promotion_reason == "reviewed"

    def test_update_status_missing_returns_false(self, backend: Any) -> None:
        assert backend.update_candidate_status("ghost", status="promoted") is False

    def test_update_status_leaves_target_entity_untouched_when_unset(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate(target_entity_id="ent-keep"))
        backend.update_candidate_status("cand-1", status="rejected")
        loaded = backend.get_candidate("cand-1")
        assert loaded is not None
        assert loaded.target_entity_id == "ent-keep"

    def test_search_matches_assertion(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate(id="hit", assertion="migrate storage to postgres"))
        backend.save_candidate(_make_candidate(id="miss", assertion="buy more coffee"))
        assert {c.id for c in backend.search_candidates("postgres")} == {"hit"}

    def test_find_duplicate_only_matches_promoted(self, backend: Any) -> None:
        cand = _make_candidate(status="pending")
        backend.save_candidate(cand)
        # Identical `pending` content must not count, or a re-extract would
        # silently drop it.
        assert backend.find_duplicate_candidate(cand.assertion, ["raw-1"], cand.subject_name) is False

        backend.update_candidate_status("cand-1", status="promoted")
        assert backend.find_duplicate_candidate(cand.assertion, ["raw-1"], cand.subject_name) is True

    def test_find_duplicate_needs_the_same_raw_event_set(self, backend: Any) -> None:
        cand = _make_candidate(status="promoted", raw_event_ids=["raw-1", "raw-2"])
        backend.save_candidate(cand)

        assert backend.find_duplicate_candidate(cand.assertion, ["raw-1", "raw-2"], cand.subject_name) is True
        # A subset is a different provenance, so not a duplicate.
        assert backend.find_duplicate_candidate(cand.assertion, ["raw-1"], cand.subject_name) is False

    def test_find_duplicate_with_no_raw_ids_is_false(self, backend: Any) -> None:
        backend.save_candidate(_make_candidate(status="promoted"))
        assert backend.find_duplicate_candidate("ship augment mode before replace mode", [], "Octop Memory") is False


# ---------------------------------------------------------------------------
# L2 atoms
# ---------------------------------------------------------------------------


class TestAtomParity:
    def test_round_trip(self, backend: Any) -> None:
        backend.save_atom(_make_atom())
        loaded = backend.get_atom("atom-1")
        assert loaded is not None
        assert loaded.entity_id == "ent-1"
        assert loaded.search_terms == ["augment", "replace"]
        assert loaded.superseded_by is None
        assert loaded.deprecated_at is None
        assert loaded.occurred_at.tzinfo is not None

    def test_duplicate_id_raises(self, backend: Any) -> None:
        backend.save_atom(_make_atom())
        with pytest.raises(_expect_duplicate(backend)):
            backend.save_atom(_make_atom())
        _recover(backend)

    def test_list_filters_entity_and_importance(self, backend: Any) -> None:
        backend.save_atom(_make_atom(id="a1", entity_id="ent-1", importance="high"))
        backend.save_atom(_make_atom(id="a2", entity_id="ent-2", importance="low"))

        assert {a.id for a in backend.list_atoms(entity_id="ent-1")} == {"a1"}
        assert {a.id for a in backend.list_atoms(importance="low")} == {"a2"}

    def test_supersede_hides_atom_until_asked(self, backend: Any) -> None:
        backend.save_atom(_make_atom(id="old"))
        backend.save_atom(_make_atom(id="new"))
        assert backend.supersede_atom("old", new_atom_id="new", deprecated_at=_now()) is True

        assert {a.id for a in backend.list_atoms()} == {"new"}
        assert {a.id for a in backend.list_atoms(include_deprecated=True)} == {"old", "new"}

        old = backend.get_atom("old")
        assert old is not None
        assert old.superseded_by == "new"
        assert old.deprecated_at is not None

    def test_supersede_missing_returns_false(self, backend: Any) -> None:
        assert backend.supersede_atom("ghost", new_atom_id="x", deprecated_at=_now()) is False

    def test_deprecate_without_replacement(self, backend: Any) -> None:
        backend.save_atom(_make_atom())
        assert backend.deprecate_atom("atom-1", deprecated_at=_now()) is True

        loaded = backend.get_atom("atom-1")
        assert loaded is not None
        assert loaded.deprecated_at is not None
        assert loaded.superseded_by is None
        assert backend.list_atoms() == []

    def test_deprecate_missing_returns_false(self, backend: Any) -> None:
        assert backend.deprecate_atom("ghost", deprecated_at=_now()) is False

    def test_search_excludes_deprecated_by_default(self, backend: Any) -> None:
        backend.save_atom(_make_atom(id="a1", search_terms=["zzmarker"]))
        backend.save_atom(_make_atom(id="a2", search_terms=["zzmarker"]))
        backend.supersede_atom("a1", new_atom_id="a2", deprecated_at=_now())

        assert {a.id for a in backend.search_atoms("zzmarker")} == {"a2"}
        both = backend.search_atoms("zzmarker", include_deprecated=True)
        assert {a.id for a in both} == {"a1", "a2"}

    def test_find_by_signature(self, backend: Any) -> None:
        atom = _make_atom()
        backend.save_atom(atom)
        hit = backend.find_atom_by_signature(normalize_alias(atom.assertion))
        assert hit is not None
        assert hit.id == "atom-1"
        assert backend.find_atom_by_signature("no such signature") is None

    def test_time_range_search(self, backend: Any) -> None:
        old, new = _now() - timedelta(days=10), _now()
        backend.save_atom(_make_atom(id="old", occurred_at=old))
        backend.save_atom(_make_atom(id="new", occurred_at=new, assertion="a different fact"))

        window = backend.search_atoms_by_time_range(start=_now() - timedelta(days=1), end=_now() + timedelta(minutes=1))
        assert [a.id for a in window] == ["new"]

        scoped = backend.search_atoms_by_time_range(
            start=_now() - timedelta(days=30),
            end=_now() + timedelta(minutes=1),
            entity_id="ent-1",
        )
        # Ordered occurred_at DESC.
        assert [a.id for a in scoped] == ["new", "old"]

    def test_migrate_atoms_to_entity(self, backend: Any) -> None:
        backend.save_atom(_make_atom(id="a1", entity_id="src", assertion="fact one"))
        backend.save_atom(_make_atom(id="a2", entity_id="src", assertion="fact two"))

        moved = backend.migrate_atoms_to_entity("src", "dst")
        assert moved == 2
        assert {a.id for a in backend.list_atoms(entity_id="dst")} == {"a1", "a2"}
        assert backend.list_atoms(entity_id="src") == []

    def test_migrate_deduplicates_colliding_assertions(self, backend: Any) -> None:
        backend.save_atom(_make_atom(id="keeper", entity_id="dst", assertion="same fact"))
        backend.save_atom(_make_atom(id="dupe", entity_id="src", assertion="same fact"))

        backend.migrate_atoms_to_entity("src", "dst")
        dupe = backend.get_atom("dupe")
        assert dupe is not None
        assert dupe.deprecated_at is not None
        assert dupe.superseded_by == "keeper"


# ---------------------------------------------------------------------------
# L3 entities + aliases
# ---------------------------------------------------------------------------


class TestEntityParity:
    def test_round_trip(self, backend: Any) -> None:
        backend.save_entity(_make_entity())
        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.canonical_name == "Octop Memory"
        assert loaded.aliases == ["LCM"]
        assert loaded.atom_count == 0
        assert loaded.last_promoted_at is None

    def test_find_by_name_is_case_insensitive(self, backend: Any) -> None:
        backend.save_entity(_make_entity())
        hit = backend.find_entity_by_name("octop memory")
        assert hit is not None
        assert hit.id == "ent-1"

    def test_find_by_name_honours_type_filter(self, backend: Any) -> None:
        backend.save_entity(_make_entity(id="proj", entity_type="Project", canonical_name="Foo"))
        backend.save_entity(_make_entity(id="task", entity_type="Task", canonical_name="Foo"))

        proj = backend.find_entity_by_name("Foo", entity_type="Project")
        assert proj is not None
        assert proj.id == "proj"

    def test_list_filters_by_type(self, backend: Any) -> None:
        backend.save_entity(_make_entity(id="proj", entity_type="Project", canonical_name="A"))
        backend.save_entity(_make_entity(id="task", entity_type="Task", canonical_name="B"))
        assert {e.id for e in backend.list_entities(entity_type="Task")} == {"task"}

    def test_bump_atom_count_up_and_down(self, backend: Any) -> None:
        backend.save_entity(_make_entity(atom_count=5))
        when = _now()
        assert backend.bump_entity_atom_count("ent-1", delta=2, last_promoted_at=when) is True
        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.atom_count == 7
        assert loaded.last_promoted_at is not None

        backend.bump_entity_atom_count("ent-1", delta=-3)
        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.atom_count == 4

    def test_bump_missing_returns_false(self, backend: Any) -> None:
        assert backend.bump_entity_atom_count("ghost", delta=1) is False

    def test_rename_canonical_name(self, backend: Any) -> None:
        backend.save_entity(_make_entity())
        assert backend.update_entity_canonical_name("ent-1", "Octop Memory Core") is True
        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.canonical_name == "Octop Memory Core"
        assert backend.update_entity_canonical_name("ghost", "X") is False


class TestAliasParity:
    def test_save_and_resolve(self, backend: Any) -> None:
        backend.save_entity(_make_entity())
        backend.save_alias(
            Alias(alias="lcm", entity_id="ent-1", entity_type="Project", created_by="rule", created_at=_now())
        )
        hit = backend.find_entity_by_alias("lcm")
        assert hit is not None
        assert hit.id == "ent-1"

    def test_resolve_unknown(self, backend: Any) -> None:
        assert backend.find_entity_by_alias("nope") is None

    def test_duplicate_alias_is_a_no_op(self, backend: Any) -> None:
        backend.save_entity(_make_entity())
        alias = Alias(alias="lcm", entity_id="ent-1", entity_type="Project", created_by="rule", created_at=_now())
        backend.save_alias(alias)
        backend.save_alias(alias)
        assert len(backend.list_aliases(entity_id="ent-1")) == 1

    def test_created_by_is_preserved(self, backend: Any) -> None:
        backend.save_entity(_make_entity())
        backend.save_alias(
            Alias(alias="lcm", entity_id="ent-1", entity_type="Project", created_by="user", created_at=_now())
        )
        rows = backend.list_aliases(entity_id="ent-1")
        assert [r.created_by for r in rows] == ["user"]


# ---------------------------------------------------------------------------
# L3 entity pages
# ---------------------------------------------------------------------------


class TestEntityPageParity:
    def test_upsert_replaces_in_place(self, backend: Any) -> None:
        backend.upsert_entity_page(_make_page())
        backend.upsert_entity_page(_make_page(headline="updated headline", summary_version=2))

        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.headline == "updated headline"
        assert page.summary_version == 2
        assert len(backend.list_dirty_entity_pages()) == 1

    def test_get_missing_returns_none(self, backend: Any) -> None:
        assert backend.get_entity_page("ghost") is None

    def test_mark_dirty_creates_stub_when_absent(self, backend: Any) -> None:
        backend.mark_entity_page_dirty("ent-new", when=_now())
        page = backend.get_entity_page("ent-new")
        assert page is not None
        assert page.dirty is True
        assert page.summary_markdown == ""

    def test_regen_clears_dirty_and_bumps_version(self, backend: Any) -> None:
        backend.upsert_entity_page(_make_page())
        ok = backend.apply_entity_page_regen(
            "ent-1",
            summary_markdown="# new body",
            headline="new headline",
            topics=["a", "b"],
            when=_now(),
        )
        assert ok is True

        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is False
        assert page.summary_markdown == "# new body"
        assert page.topics == ["a", "b"]
        assert page.summary_version == 2
        assert page.regen_attempt_count == 0
        assert page.last_regen_at is not None
        assert backend.list_dirty_entity_pages() == []

    def test_regen_failure_keeps_old_body_and_stays_dirty(self, backend: Any) -> None:
        backend.upsert_entity_page(_make_page())
        assert backend.record_entity_page_regen_failure("ent-1", when=_now()) is True

        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is True
        assert page.regen_attempt_count == 1
        assert page.summary_markdown.startswith("# Octop Memory")
        assert page.summary_version == 1

    def test_user_edit_bumps_version_without_dirtying(self, backend: Any) -> None:
        backend.upsert_entity_page(_make_page(dirty=False))
        assert backend.apply_entity_page_user_edit("ent-1", summary_markdown="# mine", when=_now()) is True

        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.summary_markdown == "# mine"
        assert page.dirty is False
        assert page.summary_version == 2
        assert page.last_user_edit_at is not None

    def test_page_mutations_on_missing_row_return_false(self, backend: Any) -> None:
        assert (
            backend.apply_entity_page_regen("ghost", summary_markdown="x", headline="y", topics=[], when=_now())
            is False
        )
        assert backend.record_entity_page_regen_failure("ghost", when=_now()) is False
        assert backend.apply_entity_page_user_edit("ghost", summary_markdown="x", when=_now()) is False


# ---------------------------------------------------------------------------
# M4 thread active-entity stack
# ---------------------------------------------------------------------------


class TestActiveEntityParity:
    def test_upsert_refreshes_rather_than_duplicates(self, backend: Any) -> None:
        first, second = _now() - timedelta(minutes=5), _now()
        backend.upsert_active_entity(ActiveEntity(thread_id="t1", entity_id="e1", last_seen_at=first))
        backend.upsert_active_entity(ActiveEntity(thread_id="t1", entity_id="e1", last_seen_at=second))

        rows = backend.list_active_entities("t1")
        assert len(rows) == 1
        assert rows[0].last_seen_at >= first

    def test_list_is_newest_first_and_thread_scoped(self, backend: Any) -> None:
        base = _now()
        backend.upsert_active_entity(
            ActiveEntity(thread_id="t1", entity_id="old", last_seen_at=base - timedelta(minutes=2))
        )
        backend.upsert_active_entity(ActiveEntity(thread_id="t1", entity_id="new", last_seen_at=base))
        backend.upsert_active_entity(ActiveEntity(thread_id="t2", entity_id="other", last_seen_at=base))

        assert [r.entity_id for r in backend.list_active_entities("t1")] == ["new", "old"]
        assert [r.entity_id for r in backend.list_active_entities("t2")] == ["other"]

    def test_evict_trims_to_keep(self, backend: Any) -> None:
        base = _now()
        for i in range(5):
            backend.upsert_active_entity(
                ActiveEntity(thread_id="t1", entity_id=f"e{i}", last_seen_at=base + timedelta(seconds=i))
            )
        removed = backend.evict_active_entities("t1", keep=2)
        assert removed == 3
        assert [r.entity_id for r in backend.list_active_entities("t1")] == ["e4", "e3"]

    def test_source_round_trips(self, backend: Any) -> None:
        backend.upsert_active_entity(
            ActiveEntity(thread_id="t1", entity_id="e1", last_seen_at=_now(), source="query_mention")
        )
        assert backend.list_active_entities("t1")[0].source == "query_mention"


# ---------------------------------------------------------------------------
# L4 journal + meta
# ---------------------------------------------------------------------------


def _make_journal(**overrides: Any) -> JournalEntry:
    base: dict[str, Any] = {
        "id": "j1",
        "timestamp": _now(),
        "action": "promote",
        "actor": "auto",
        "target_atom_id": "atom-1",
        "target_candidate_id": "cand-1",
        "after": {"id": "atom-1"},
        "note": "auto promotion",
    }
    base.update(overrides)
    return JournalEntry(**base)


class TestJournalParity:
    def test_append_and_round_trip_json_columns(self, backend: Any) -> None:
        backend.append_journal(_make_journal(before={"status": "pending"}))
        rows = backend.list_journal()
        assert len(rows) == 1
        assert rows[0].before == {"status": "pending"}
        assert rows[0].after == {"id": "atom-1"}
        assert rows[0].note == "auto promotion"

    def test_null_json_columns_stay_none(self, backend: Any) -> None:
        backend.append_journal(_make_journal(before=None, after=None))
        rows = backend.list_journal()
        assert rows[0].before is None
        assert rows[0].after is None

    def test_list_filters(self, backend: Any) -> None:
        backend.append_journal(_make_journal(id="j1", action="promote", target_entity_id="ent-1"))
        backend.append_journal(_make_journal(id="j2", action="reject", target_entity_id="ent-2"))

        assert {r.id for r in backend.list_journal(action="promote")} == {"j1"}
        assert {r.id for r in backend.list_journal(target_entity_id="ent-2")} == {"j2"}

    def test_delete_respects_actions_and_cutoff(self, backend: Any) -> None:
        old, new = _now() - timedelta(days=30), _now()
        backend.append_journal(_make_journal(id="stale", action="gc_raw", timestamp=old))
        backend.append_journal(_make_journal(id="fresh", action="gc_raw", timestamp=new))
        backend.append_journal(_make_journal(id="decision", action="promote", timestamp=old))

        cutoff = _now() - timedelta(days=14)
        dry = backend.delete_journal(actions=["gc_raw"], before=cutoff, limit=100, dry_run=True)
        assert dry == 1
        assert len(backend.list_journal()) == 3

        deleted = backend.delete_journal(actions=["gc_raw"], before=cutoff, limit=100)
        assert deleted == 1
        assert {r.id for r in backend.list_journal()} == {"fresh", "decision"}


class TestMetaParity:
    def test_missing_key_is_none(self, backend: Any) -> None:
        assert backend.get_meta("nope") is None

    def test_set_then_overwrite(self, backend: Any) -> None:
        backend.set_meta("k", "v1")
        assert backend.get_meta("k") == "v1"
        backend.set_meta("k", "v2")
        assert backend.get_meta("k") == "v2"


# ---------------------------------------------------------------------------
# M5 episodes + digests
# ---------------------------------------------------------------------------


class TestEpisodeParity:
    def test_round_trip(self, backend: Any) -> None:
        backend.save_episode(_make_episode())
        loaded = backend.get_episode("ep-1")
        assert loaded is not None
        assert loaded.emotion == "happy"
        assert loaded.intensity == 4
        assert loaded.people == ["teammate"]
        assert loaded.topics == ["work"]
        assert loaded.raw_event_ids == ["raw-1"]
        assert loaded.digest_ids == []
        assert loaded.session_id == "sess-1"

    def test_naive_timestamps_are_normalized_to_utc(self, backend: Any) -> None:
        backend.save_episode(
            _make_episode(
                occurred_at=datetime(2026, 6, 20, 22, 0),
                created_at=datetime(2026, 6, 20, 22, 1),
            )
        )

        loaded = backend.get_episode("ep-1")

        assert loaded is not None
        assert loaded.occurred_at == datetime(2026, 6, 20, 22, 0, tzinfo=UTC)
        assert loaded.created_at == datetime(2026, 6, 20, 22, 1, tzinfo=UTC)

    def test_duplicate_id_raises(self, backend: Any) -> None:
        backend.save_episode(_make_episode())
        with pytest.raises(_expect_duplicate(backend)):
            backend.save_episode(_make_episode())
        _recover(backend)

    def test_list_filters(self, backend: Any) -> None:
        backend.save_episode(_make_episode(id="e1", emotion="happy", session_id="s1"))
        backend.save_episode(_make_episode(id="e2", emotion="sad", session_id="s2"))

        assert {e.id for e in backend.list_episodes(emotion="sad")} == {"e2"}
        assert {e.id for e in backend.list_episodes(session_id="s1")} == {"e1"}

    def test_search_matches_summary(self, backend: Any) -> None:
        backend.save_episode(_make_episode(id="hit", summary="user celebrated the kubernetes launch"))
        backend.save_episode(_make_episode(id="miss", summary="user bought groceries"))
        assert {e.id for e in backend.search_episodes("kubernetes")} == {"hit"}

    def test_range_is_half_open_and_ascending(self, backend: Any) -> None:
        start = datetime(2026, 6, 1, tzinfo=UTC)
        backend.save_episode(_make_episode(id="inside-1", occurred_at=start + timedelta(days=1)))
        backend.save_episode(_make_episode(id="inside-2", occurred_at=start + timedelta(days=2)))
        backend.save_episode(_make_episode(id="on-end", occurred_at=start + timedelta(days=3)))

        got = backend.list_episodes_in_range(start=start, end=start + timedelta(days=3))
        assert [e.id for e in got] == ["inside-1", "inside-2"]


class TestDigestParity:
    def test_upsert_is_keyed_on_period(self, backend: Any) -> None:
        backend.upsert_digest(_make_digest())
        backend.upsert_digest(_make_digest(id="dig-2", markdown="rewritten"))

        got = backend.get_digest("weekly", "2026-W26")
        assert got is not None
        assert got.markdown == "rewritten"
        assert len(backend.list_digests()) == 1

    def test_get_missing_returns_none(self, backend: Any) -> None:
        assert backend.get_digest("weekly", "1999-W01") is None

    def test_list_filters_by_kind(self, backend: Any) -> None:
        backend.upsert_digest(_make_digest(id="w", period_kind="weekly", period_key="2026-W26"))
        backend.upsert_digest(_make_digest(id="m", period_kind="monthly", period_key="2026-06"))

        assert [d.period_key for d in backend.list_digests(period_kind="monthly")] == ["2026-06"]

    def test_episode_ids_round_trip(self, backend: Any) -> None:
        backend.upsert_digest(_make_digest(episode_ids=["ep-1", "ep-2"]))
        got = backend.get_digest("weekly", "2026-W26")
        assert got is not None
        assert got.episode_ids == ["ep-1", "ep-2"]


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_backend_implements_every_protocol_method(self, backend: Any) -> None:
        """Neither backend inherits from ``MemoryBackend``, so nothing else
        checks that both actually implement it — a method added to one
        backend and forgotten on the other would otherwise only surface at
        runtime, on whichever install used the other backend.
        """
        from octop_memory.storage.backends import MemoryBackend

        assert isinstance(backend, MemoryBackend)

        declared = sorted(
            name for name, value in vars(MemoryBackend).items() if not name.startswith("_") and callable(value)
        )
        assert declared, "protocol introspection found no methods — the check would pass vacuously"
        assert [name for name in declared if not callable(getattr(backend, name, None))] == []


class TestCountStatsParity:
    def test_counts_reflect_rows(self, backend: Any) -> None:
        assert backend.count_stats()["raw_events"] == 0

        backend.save_raw(_make_raw())
        backend.save_atom(_make_atom())
        backend.save_entity(_make_entity())
        backend.mark_entity_page_dirty("ent-1", when=_now())

        stats = backend.count_stats()
        assert stats["raw_events"] == 1
        assert stats["atoms"] == 1
        assert stats["entities"] == 1
        assert stats["dirty_pages"] == 1


class TestTransactionParity:
    def test_commits_on_success(self, backend: Any) -> None:
        with backend.transaction():
            backend.save_raw(_make_raw(id="r1"))
            backend.save_raw(_make_raw(id="r2"))
        assert len(backend.list_raw()) == 2

    def test_rolls_back_on_exception(self, backend: Any) -> None:
        with pytest.raises(RuntimeError), backend.transaction():
            backend.save_raw(_make_raw(id="r1"))
            raise RuntimeError("boom")
        assert backend.list_raw() == []

    def test_is_reentrant(self, backend: Any) -> None:
        with backend.transaction(), backend.transaction():
            backend.save_raw(_make_raw(id="r1"))
        assert len(backend.list_raw()) == 1


class TestMemoryNodeParity:
    def test_leaf_projects_atom_assertion_into_content(self, backend: Any) -> None:
        atom = _make_atom()
        backend.save_atom(atom)
        backend.save_node(
            MemoryNode(
                id="node-leaf",
                parent_id=None,
                level="leaf",
                content="",
                topic=None,
                conversation_id=None,
                created_at=_now(),
                updated_at=_now(),
                atom_id="atom-1",
            )
        )
        node = backend.get_node("node-leaf")
        assert node is not None
        assert node.content == atom.assertion

    def test_lookup_by_atom_id(self, backend: Any) -> None:
        backend.save_atom(_make_atom())
        backend.save_node(
            MemoryNode(
                id="node-leaf",
                parent_id=None,
                level="leaf",
                content="",
                topic=None,
                conversation_id=None,
                created_at=_now(),
                updated_at=_now(),
                atom_id="atom-1",
            )
        )
        found = backend.get_node_by_atom_id("atom-1")
        assert found is not None
        assert found.id == "node-leaf"

    def test_delete_cascade_removes_children(self, backend: Any) -> None:
        backend.save_node(
            MemoryNode(
                id="root",
                parent_id=None,
                level="root",
                content="Global",
                topic=None,
                conversation_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        backend.save_node(
            MemoryNode(
                id="branch",
                parent_id="root",
                level="branch",
                content="Work",
                topic=None,
                conversation_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        assert backend.delete_node("root", cascade=True) is True
        assert backend.get_node("branch") is None
