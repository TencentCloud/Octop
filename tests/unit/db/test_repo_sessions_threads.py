"""tests/unit/test_repo_sessions_threads.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def repos(tmp_path: Path):
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    return SessionRepo(db), ThreadRepo(db)


def test_session_upsert_and_get(repos):
    sessions, threads = repos
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="dashboard", channel_subject_id="1")
    threads.insert(
        thread_id="thr_1",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
    )
    sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_1",
    )
    row = sessions.get(sk)
    assert row is not None
    assert row.thread_id == "thr_1"


def test_session_channel_id_persisted(repos):
    sessions, threads = repos
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_1")
    threads.insert(
        thread_id="thr_im",
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        session_key=sk,
    )
    sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        chat_type="dm",
        thread_id="thr_im",
        channel_id="ch-feishu-1",
    )
    row = sessions.get(sk)
    assert row is not None
    assert row.channel_id == "ch-feishu-1"
    subject = row.to_channel_subject()
    assert subject.metadata["channel_id"] == "ch-feishu-1"


def test_session_to_channel_subject(repos):
    sessions, threads = repos
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    threads.insert(
        thread_id="thr_x",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
    )
    sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_x",
        channel_subject_id="1",
        channel_chat_type="dm",
        channel_metadata={"channel_type": "dashboard", "user_id": 1},
    )
    subject = sessions.get(sk).to_channel_subject()
    assert subject.subject_id == "1"
    assert subject.chat_type == "dm"
    assert subject.metadata["channel_type"] == "dashboard"
    assert subject.metadata["user_id"] == 1


def test_threads_list_by_agent(repos):
    sessions, threads = repos
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="dashboard", channel_subject_id="1")
    for i in range(3):
        threads.insert(
            thread_id=f"thr_{i}",
            agent_id="a1",
            user_id=1,
            channel_type="dashboard",
            session_key=sk,
            title=f"t{i}",
        )
    rows = threads.list_by_agent(agent_id="a1", limit=10)
    assert len(rows) == 3


def test_session_unread_count(repos):
    sessions, threads = repos
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    threads.insert(
        thread_id="thr_u",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
    )
    sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_u",
    )
    assert sessions.get(sk).unread_count == 0
    sessions.increment_unread(sk)
    assert sessions.get(sk).unread_count == 1
    sessions.increment_unread(sk, delta=2)
    assert sessions.get(sk).unread_count == 3
    sessions.clear_unread_for_thread("thr_u")
    assert sessions.get(sk).unread_count == 0


def test_unread_totals_by_agent(repos):
    sessions, threads = repos
    sk1 = ThreadRegistry.make_key(agent_id="a1", channel_type="dashboard", channel_subject_id="1")
    sk2 = ThreadRegistry.make_key(agent_id="a1", channel_type="cron", channel_subject_id="1")
    for sk, thr, channel in (
        (sk1, "thr_a1", "dashboard"),
        (sk2, "thr_a2", "cron"),
    ):
        threads.insert(
            thread_id=thr,
            agent_id="a1",
            user_id=1,
            channel_type=channel,
            session_key=sk,
        )
        sessions.upsert(
            session_key=sk,
            agent_id="a1",
            user_id=1,
            channel_type=channel,
            chat_type="dm",
            thread_id=thr,
        )
    sessions.increment_unread(sk1, delta=2)
    sessions.increment_unread(sk2)
    totals = sessions.unread_totals_by_agent(1, ["a1", "missing"])
    assert totals == {"a1": 3}
    sessions.clear_unread_for_agent("a1", 1)
    assert sessions.get(sk1).unread_count == 0
    assert sessions.get(sk2).unread_count == 0
    assert sessions.unread_totals_by_agent(1, ["a1"]) == {}


def test_unread_counts_for_threads(repos):
    sessions, threads = repos
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    threads.insert(
        thread_id="thr_a",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
    )
    sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_a",
    )
    sessions.increment_unread(sk, delta=2)
    counts = sessions.unread_counts_for_threads(["thr_a", "thr_missing"])
    assert counts == {"thr_a": 2}


def test_threads_pinned_sort_first(repos):
    _sessions, threads = repos
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="dashboard", channel_subject_id="1")
    threads.insert(
        thread_id="thr_old",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
        title="old",
        last_active=1,
    )
    threads.insert(
        thread_id="thr_new",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
        title="new",
        last_active=100,
    )
    threads.set_pinned("thr_old", True)
    rows = threads.list_by_agent(agent_id="a1", limit=10)
    assert rows[0].thread_id == "thr_old"
    assert rows[0].pinned is True
