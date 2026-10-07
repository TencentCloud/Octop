"""Exercise batch callers against real PostgreSQL and canonical migrations."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.support.postgresql import requires_postgresql

from octop.infra.backup.chats import capture_chat_tables, restore_preserved_chats
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import PostgresPool
from octop.infra.db.repos.care_push import CarePushRepo

pytestmark = [requires_postgresql, pytest.mark.postgresql]


@pytest.fixture
def pool() -> Iterator[PostgresPool]:
    import psycopg
    from psycopg.conninfo import make_conninfo

    conninfo = os.environ["OCTOP_TEST_DATABASE_URL"]
    schema = f"batch_{uuid.uuid4().hex}"
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    db = PostgresPool(make_conninfo(conninfo, options=f"-csearch_path={schema}"))
    try:
        run_migrations(db)
        yield db
    finally:
        db.close()
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_care_push_batch_persists_all_episode_receipts(pool: PostgresPool) -> None:
    repo = CarePushRepo(pool)
    repo.insert(agent_id="agent", session_key="session", episode_ids=["one", "why?"])
    assert repo.list_pushed_episode_ids("agent") == {"one", "why?"}
    repo.insert(agent_id="agent", session_key="session", episode_ids=[])
    assert repo.list_pushed_episode_ids("agent") == {"one", "why?"}


def test_chat_restore_replays_spooled_batches(pool: PostgresPool, tmp_path: Path) -> None:
    with pool.transaction() as conn:
        user = conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            ("fixture-user", "not-a-real-password", "user", 1),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fixture-agent", user, "Fixture", 1, 1),
        )
        for number in range(2):
            conn.execute(
                "INSERT INTO sessions(session_key, agent_id, user_id, channel_type, "
                "thread_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (f"session-{number}", "fixture-agent", user, "web", f"thread-{number}", 1),
            )
    spool = capture_chat_tables(pool, tmp_path / "chats.sqlite")
    with pool.transaction() as conn:
        conn.execute("DELETE FROM sessions")
    assert restore_preserved_chats(pool, spool) == (2, 0)
    with pool.connect() as conn:
        rows = conn.execute("SELECT session_key FROM sessions ORDER BY session_key").fetchall()
    assert [row[0] for row in rows] == ["session-0", "session-1"]


def test_batch_failure_rolls_back_and_iterator_parameters_work(pool: PostgresPool) -> None:
    import psycopg

    sql = (
        "INSERT INTO care_push_records(id, agent_id, session_key, episode_id, pushed_at) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    with pytest.raises(psycopg.errors.UniqueViolation), pool.transaction() as conn:
        conn.executemany(
            sql,
            [("same", "agent", "session", "one", 1), ("same", "agent", "session", "two", 1)],
        )
    with pool.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM care_push_records").fetchone()[0] == 0
    with pool.transaction() as conn:
        conn.executemany(sql, ((str(i), "agent", "session", str(i), 1) for i in range(2)))
        conn.executemany(sql, [])
    with pool.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM care_push_records").fetchone()[0] == 2
