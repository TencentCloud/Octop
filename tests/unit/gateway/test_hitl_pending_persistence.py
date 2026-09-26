"""Durable HITL pending records — write-through and restart hydration (#782).

Uses the real SQLite pool, migrations, and repo; the store under test is never
mocked. The only fixture surgery is backdating ``created_at`` rows to simulate
records that aged past the TTL while the process was down.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.hitl_pending import HitlPendingRepo
from octop.infra.gateway.hitl.store import HitlPendingRecord, HitlPendingStore

_ACTION_REQUESTS: list[dict[str, Any]] = [
    {"name": "execute", "args": {"command": "ls"}, "description": "run ls"},
]
_REVIEW_CONFIGS: list[dict[str, Any]] = [
    {"action_name": "execute", "allowed_decisions": ["approve", "reject"]},
]


def _make_repo(tmp_path: Path) -> tuple[SqlitePool, HitlPendingRepo]:
    db = SqlitePool(tmp_path / "hitl.db")
    run_migrations(db)
    return db, HitlPendingRepo(db)


def _register(
    store: HitlPendingStore,
    *,
    session_key: str = "sk1",
    thread_id: str = "thr1",
    agent_id: str = "agent1",
    user_id: int = 7,
) -> HitlPendingRecord:
    return store.register(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        session_key=session_key,
        channel_type="feishu",
        action_requests=_ACTION_REQUESTS,
        review_configs=_REVIEW_CONFIGS,
    )


def test_pending_records_survive_restart(tmp_path: Path) -> None:
    _db, repo = _make_repo(tmp_path)
    store = HitlPendingStore()
    store.replace_repo(repo)
    record = _register(store)

    # Simulate a server restart: a fresh store hydrates from the same database.
    restarted = HitlPendingStore()
    restarted.replace_repo(repo)
    restarted.hydrate_from_repo()

    resolved = restarted.resolve_for_session(record.session_key, agent_id=record.agent_id)
    assert resolved is not None
    assert resolved.pending_id == record.pending_id
    assert resolved.status == "pending"
    assert resolved.thread_id == record.thread_id
    assert resolved.user_id == record.user_id
    assert resolved.session_key == record.session_key
    assert resolved.channel_type == record.channel_type
    assert resolved.action_requests == _ACTION_REQUESTS
    assert resolved.review_configs == _REVIEW_CONFIGS
    assert resolved.created_at == record.created_at

    by_id = restarted.get_pending(
        record.pending_id,
        session_key=record.session_key,
        agent_id=record.agent_id,
    )
    assert by_id is not None and by_id.pending_id == record.pending_id

    by_thread = restarted.resolve_pending_for_thread(
        record.thread_id,
        agent_id=record.agent_id,
        user_id=record.user_id,
    )
    assert by_thread is not None and by_thread.pending_id == record.pending_id


def test_duplicate_register_expires_prior_record_in_db(tmp_path: Path) -> None:
    _db, repo = _make_repo(tmp_path)
    store = HitlPendingStore()
    store.replace_repo(repo)
    first = _register(store)
    second = _register(store)

    assert first.status == "expired"

    restarted = HitlPendingStore()
    restarted.replace_repo(repo)
    restarted.hydrate_from_repo()
    # The superseded record must not come back as an actionable card.
    assert (
        restarted.get_pending(
            first.pending_id,
            session_key=first.session_key,
            agent_id=first.agent_id,
        )
        is None
    )
    resolved = restarted.resolve_for_session(second.session_key, agent_id=second.agent_id)
    assert resolved is not None and resolved.pending_id == second.pending_id


def test_mark_resolved_and_ask_answers_write_through(tmp_path: Path) -> None:
    _db, repo = _make_repo(tmp_path)
    store = HitlPendingStore()
    store.replace_repo(repo)
    approval = _register(store)
    ask = _register(store, session_key="sk2", thread_id="thr2")

    store.mark_resolved(approval.pending_id, "approved")
    updated = store.append_ask_answer(ask.pending_id, "blue")
    assert updated is not None
    assert updated.ask_answers == ["blue"]
    assert updated.ask_question_index == 1

    restarted = HitlPendingStore()
    restarted.replace_repo(repo)
    restarted.hydrate_from_repo()
    assert restarted.get(approval.pending_id) is None
    resolved = restarted.resolve_for_session(ask.session_key, agent_id=ask.agent_id)
    assert resolved is not None
    assert resolved.pending_id == ask.pending_id
    assert resolved.ask_answers == ["blue"]
    assert resolved.ask_question_index == 1


def test_hydration_expires_stale_records(tmp_path: Path) -> None:
    db, repo = _make_repo(tmp_path)
    store = HitlPendingStore()
    store.replace_repo(repo)
    stale = _register(store)

    # Age the row past the 30-minute TTL while the process was "down".
    with db.connect() as conn:
        conn.execute(
            "UPDATE hitl_pending_records SET created_at = ?",
            (time.time() - 3600.0,),
        )

    restarted = HitlPendingStore()
    restarted.replace_repo(repo)
    restarted.hydrate_from_repo()
    # A stale card must never resurface as actionable, through any accessor.
    assert restarted.resolve_for_session(stale.session_key) is None
    assert (
        restarted.get_pending(
            stale.pending_id,
            session_key=stale.session_key,
            agent_id=stale.agent_id,
        )
        is None
    )
    assert restarted.list_pending_for_session(stale.session_key) == []
    # The first gc pass after hydration also drops the stale row from SQL.
    assert repo.list_pending() == []


def test_hydration_does_not_override_in_memory_records(tmp_path: Path) -> None:
    _db, repo = _make_repo(tmp_path)
    store = HitlPendingStore()
    record = _register(store)

    # A row with the same pending_id persisted as resolved must not clobber
    # the live in-memory state during hydration.
    repo.upsert(
        pending_id=record.pending_id,
        thread_id=record.thread_id,
        agent_id=record.agent_id,
        user_id=record.user_id,
        session_key=record.session_key,
        channel_type=record.channel_type,
        action_requests=record.action_requests,
        review_configs=record.review_configs,
        created_at=record.created_at,
        status="approved",
        ask_question_index=record.ask_question_index,
        ask_answers=record.ask_answers,
    )
    store.replace_repo(repo)
    store.hydrate_from_repo()

    kept = store.get(record.pending_id)
    assert kept is not None and kept.status == "pending"


def test_gc_deletes_stale_rows_from_db(tmp_path: Path) -> None:
    _db, repo = _make_repo(tmp_path)
    # Negative TTL makes every record stale on the next gc pass, deterministically.
    store = HitlPendingStore(ttl_seconds=-1.0)
    store.replace_repo(repo)
    record = _register(store)

    store.get(record.pending_id)  # triggers gc

    restarted = HitlPendingStore()
    restarted.replace_repo(repo)
    restarted.hydrate_from_repo()
    assert restarted.resolve_for_session(record.session_key) is None


def test_expire_pending_for_thread_writes_through(tmp_path: Path) -> None:
    _db, repo = _make_repo(tmp_path)
    store = HitlPendingStore()
    store.replace_repo(repo)
    record = _register(store)

    store.expire_pending_for_thread(
        record.thread_id,
        agent_id=record.agent_id,
        user_id=record.user_id,
    )

    restarted = HitlPendingStore()
    restarted.replace_repo(repo)
    restarted.hydrate_from_repo()
    assert (
        restarted.resolve_pending_for_thread(
            record.thread_id,
            agent_id=record.agent_id,
        )
        is None
    )
