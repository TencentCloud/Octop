"""Unit tests for Phase 2 proactive care reply tracking and HITL gating."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.care_push import CarePushRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.hitl.store import HitlPendingStore
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.history.projection import TurnHistoryTracker
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "care_reply.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def agent_id(db: SqlitePool) -> str:
    uid = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    aid = new_ulid()
    AgentRepo(db).create(agent_id=aid, user_id=uid, name="bot")
    return aid


def test_mark_replied_updates_latest_push_and_ignores_older_open_pushes(
    db: SqlitePool,
    agent_id: str,
) -> None:
    repo = CarePushRepo(db)
    sk = f"{agent_id}:dashboard:1:dm"

    # First push (2 episodes) went unanswered.
    repo.insert(
        agent_id=agent_id,
        session_key=sk,
        episode_ids=["ep1", "ep2"],
        pushed_at=1_700_000_100,
        thread_id="thr_1",
        message_id="care:push1:assistant",
        care_text="第一条关怀",
    )
    # Second push (1 episode) in the same thread.
    repo.insert(
        agent_id=agent_id,
        session_key=sk,
        episode_ids=["ep3"],
        pushed_at=1_700_000_500,
        thread_id="thr_1",
        message_id="care:push2:assistant",
        care_text="第二条关怀",
    )
    assert repo.count_consecutive_unanswered(agent_id) == 2

    # User replies in thr_1.
    updated = repo.mark_replied_for_thread(
        agent_id=agent_id,
        thread_id="thr_1",
        reply_message_id="human_msg_42",
        replied_at=1_700_000_900,
    )
    assert updated == 1
    assert repo.count_consecutive_unanswered(agent_id) == 0

    by_mid: dict[str, list] = {}
    for rec in repo.list_recent(agent_id):
        by_mid.setdefault(rec.message_id or "", []).append(rec)

    assert len(by_mid["care:push2:assistant"]) == 1
    assert by_mid["care:push2:assistant"][0].status == "replied"
    assert by_mid["care:push2:assistant"][0].replied_at == 1_700_000_900
    assert by_mid["care:push2:assistant"][0].reply_message_id == "human_msg_42"

    assert len(by_mid["care:push1:assistant"]) == 2
    assert all(r.status == "ignored" for r in by_mid["care:push1:assistant"])

    # Another reply on the same thread is a no-op (no open 'sent' push left).
    assert (
        repo.mark_replied_for_thread(
            agent_id=agent_id,
            thread_id="thr_1",
            reply_message_id="human_msg_43",
            replied_at=1_700_001_000,
        )
        == 0
    )


def test_consecutive_unanswered_resets_after_reply_and_counts_new_streak(
    db: SqlitePool,
    agent_id: str,
) -> None:
    repo = CarePushRepo(db)
    sk = f"{agent_id}:dashboard:1:dm"

    repo.insert(
        agent_id=agent_id,
        session_key=sk,
        episode_ids=["ep1"],
        pushed_at=1_700_000_100,
        thread_id="thr_1",
        message_id="care:p1:assistant",
    )
    repo.mark_replied_for_thread(
        agent_id=agent_id,
        thread_id="thr_1",
        replied_at=1_700_000_200,
    )
    repo.insert(
        agent_id=agent_id,
        session_key=sk,
        episode_ids=["ep2", "ep3"],
        pushed_at=1_700_000_300,
        thread_id="thr_1",
        message_id="care:p2:assistant",
    )
    repo.insert(
        agent_id=agent_id,
        session_key=sk,
        episode_ids=["ep4"],
        pushed_at=1_700_000_400,
        thread_id="thr_2",
        message_id="care:p3:assistant",
    )

    # p3 and p2 are unanswered; p1 was replied -> streak must be 2 (not 3 rows).
    assert repo.count_consecutive_unanswered(agent_id) == 2


def test_processor_mark_care_replied_hook(db: SqlitePool, agent_id: str) -> None:
    repo = CarePushRepo(db)
    repo.insert(
        agent_id=agent_id,
        session_key=f"{agent_id}:dashboard:1:dm",
        episode_ids=["ep_hook"],
        pushed_at=1_700_000_100,
        thread_id="thr_care",
        message_id="care:hook:assistant",
        care_text="最近还好吗？",
    )

    proc = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        care_push_repo=repo,
    )
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "id": "user_msg_99", "content": "好多了！"}]}
    )
    # Reply in an unrelated thread does not mark thr_care replied.
    proc._mark_care_replied(agent_id=agent_id, thread_id="thr_other", history_tracker=tracker)
    assert repo.list_recent(agent_id)[0].status == "sent"

    # Reply in thr_care marks it replied with reply_message_id.
    proc._mark_care_replied(agent_id=agent_id, thread_id="thr_care", history_tracker=tracker)
    rec = repo.list_recent(agent_id)[0]
    assert rec.status == "replied"
    assert rec.reply_message_id == "user_msg_99"
    assert rec.replied_at is not None


def test_hitl_store_has_pending_for_agent() -> None:
    store = HitlPendingStore(ttl_seconds=600)
    assert store.has_pending_for_agent("a1") is False

    rec = store.register(
        agent_id="a1",
        user_id=1,
        thread_id="thr_1",
        session_key="a1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "shell", "args": {"cmd": "ls"}}],
        review_configs=None,
    )
    assert store.has_pending_for_agent("a1") is True
    assert store.has_pending_for_agent("a2") is False

    store.mark_resolved(rec.pending_id, status="approved")
    assert store.has_pending_for_agent("a1") is False
