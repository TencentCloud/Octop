"""Auto thread tags — vocabulary lookup for the auto-tagger."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def db_and_threads(tmp_path: Path) -> tuple[SqlitePool, ThreadRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    return db, ThreadRepo(db)


def _insert(threads: ThreadRepo, thread_id: str, **kwargs: object) -> None:
    threads.insert(
        thread_id=thread_id,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=ThreadRegistry.dashboard_key(agent_id="a1", user_id=1),
        **kwargs,
    )


def test_list_tags_empty_db(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    assert threads.list_tags(agent_id="a1", user_id=1) == []


def test_list_tags_merges_dedupes_and_sorts(
    db_and_threads: tuple[SqlitePool, ThreadRepo],
):
    _db, threads = db_and_threads
    _insert(threads, "thr_1", tags=["b", "a"])
    _insert(threads, "thr_2", tags=["b", "c"])
    _insert(threads, "thr_3", tags=["a", "a", " "])
    assert threads.list_tags(agent_id="a1", user_id=1) == ["a", "b", "c"]


def test_list_tags_chinese_roundtrip(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    _db, threads = db_and_threads
    _insert(threads, "thr_1", tags=["工作"])
    _insert(threads, "thr_2", tags=["学习"])
    assert threads.list_tags(agent_id="a1", user_id=1) == ["学习", "工作"]


def test_list_tags_skips_empty_and_malformed_rows(
    db_and_threads: tuple[SqlitePool, ThreadRepo],
):
    db, threads = db_and_threads
    _insert(threads, "thr_default")
    _insert(threads, "thr_ok", tags=["keep"])
    with db.transaction() as conn:
        conn.execute("UPDATE threads SET tags = '' WHERE thread_id = 'thr_default'")
        conn.execute("UPDATE threads SET tags = 'not-json' WHERE thread_id = 'thr_ok'")
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key, tags, last_active, created_at) "
            "VALUES ('thr_empty_arr', 'a1', 1, 'dashboard', 'k', '[]', 1, 1)"
        )
    assert threads.list_tags(agent_id="a1", user_id=1) == []


def test_list_tags_scoped_per_user(db_and_threads: tuple[SqlitePool, ThreadRepo]):
    db, threads = db_and_threads
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) "
            "VALUES ('u2', 'h', 'user', 1)"
        )
    _insert(threads, "thr_1", tags=["mine"])
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key, tags, last_active, created_at) "
            "VALUES ('thr_other', 'a1', 2, 'dashboard', 'k', '[\"theirs\"]', 1, 1)"
        )
    assert threads.list_tags(agent_id="a1", user_id=1) == ["mine"]
    assert threads.list_tags(agent_id="a1", user_id=2) == ["theirs"]
