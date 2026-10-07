"""Concurrent team artifacts retain every producer on PostgreSQL."""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from tests.support.postgresql import requires_postgresql

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import PostgresPool, _PgConnectionProxy
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo


@requires_postgresql
@pytest.mark.postgresql
def test_concurrent_team_artifacts_keep_both_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    from psycopg.conninfo import make_conninfo

    conninfo = os.environ["OCTOP_TEST_DATABASE_URL"]
    schema = f"artifact_race_{uuid.uuid4().hex}"
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_conninfo = make_conninfo(conninfo, options=f"-csearch_path={schema}")
    pools = [PostgresPool(scoped_conninfo, min_size=1, max_size=1) for _ in range(2)]
    original_execute = _PgConnectionProxy.execute
    try:
        run_migrations(pools[0])
        user_id = UserRepo(pools[0]).create(username="fixture", password_hash="h", role="user")
        AgentRepo(pools[0]).create(agent_id="host", user_id=user_id, name="Host")
        repo = ThreadRepo(pools[0])
        repo.insert(
            thread_id="room",
            agent_id="host",
            user_id=user_id,
            channel_type="dashboard",
            session_key="fixture",
        )
        read_barrier = threading.Barrier(2)

        class CoordinatedCursor:
            def __init__(self, cursor: Any) -> None:
                self._cursor = cursor

            def fetchone(self) -> Any:
                row = self._cursor.fetchone()
                # Without a lock, force both real reads before either update.
                # With FOR UPDATE, the second read blocks in PostgreSQL until
                # the first transaction commits, so release the first reader.
                with suppress(threading.BrokenBarrierError):
                    read_barrier.wait(timeout=1)
                return row

        def execute(self: _PgConnectionProxy, sql: str, params: Any = None) -> Any:
            cursor = original_execute(self, sql, params)
            if sql.startswith("SELECT artifacts FROM threads WHERE thread_id = ?"):
                return CoordinatedCursor(cursor)
            return cursor

        monkeypatch.setattr(_PgConnectionProxy, "execute", execute)

        def append(index: int) -> None:
            ThreadRepo(pools[index]).append_artifacts(
                "room", [f"outbound/member-{index}.md"], agent_id=f"member-{index}"
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(append, range(2)))
        monkeypatch.setattr(_PgConnectionProxy, "execute", original_execute)
        row = repo.get("room")
        assert row is not None
        assert {(a.agent_id, a.path) for a in row.artifacts} == {
            ("member-0", "outbound/member-0.md"),
            ("member-1", "outbound/member-1.md"),
        }
        original_artifacts = row.artifacts
        repo.append_artifacts("room", ["outbound/member-0.md"], agent_id="member-0")
        repo.append_artifacts("missing", ["outbound/no-thread.md"], agent_id="member-0")
        after_repeat = repo.get("room")
        assert after_repeat is not None
        assert after_repeat.artifacts == original_artifacts
        assert repo.get("missing") is None
    finally:
        for pool in pools:
            pool.close()
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_separate_sqlite_pools_preserve_concurrent_team_artifacts(tmp_path: Path) -> None:
    from octop.infra.db.pool import SqlitePool

    pools = [SqlitePool(tmp_path / "artifact-room.db") for _ in range(2)]
    try:
        run_migrations(pools[0])
        user_id = UserRepo(pools[0]).create(username="fixture", password_hash="h", role="user")
        AgentRepo(pools[0]).create(agent_id="host", user_id=user_id, name="Host")
        repo = ThreadRepo(pools[0])
        repo.insert(
            thread_id="room",
            agent_id="host",
            user_id=user_id,
            channel_type="dashboard",
            session_key="fixture",
        )
        ready = threading.Barrier(2)

        def append(index: int) -> None:
            ready.wait(timeout=10)
            ThreadRepo(pools[index]).append_artifacts(
                "room", [f"outbound/member-{index}.md"], agent_id=f"member-{index}"
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(append, range(2)))
        row = repo.get("room")
        assert row is not None
        assert {(a.agent_id, a.path) for a in row.artifacts} == {
            ("member-0", "outbound/member-0.md"),
            ("member-1", "outbound/member-1.md"),
        }
    finally:
        for pool in pools:
            pool.close()
