"""Unit tests for ``CarePushRepo`` across both database dialects.

These run without a live PostgreSQL server: ``_FakePgConnection`` reproduces the
surface of ``psycopg.Connection`` that matters here (``execute`` and ``cursor``,
and deliberately no ``executemany``, which psycopg3 only defines on the cursor).
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import pytest

from octop.infra.db.pool import SqlitePool, _PgConnectionProxy
from octop.infra.db.repos.care_push import CarePushRepo

_INSERT_PREFIX = "INSERT INTO care_push_records"


class _FakeCursor:
    """Mirror of the psycopg3 cursor API used by the proxy."""

    def __init__(self) -> None:
        self.batches: list[tuple[str, list[Sequence[Any]]]] = []

    def executemany(self, sql: str, params_seq: Sequence[Any]) -> None:
        self.batches.append((sql, list(params_seq)))


class _FakePgConnection:
    """psycopg3 ``Connection`` surface, minus ``executemany``."""

    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


class _FakePgPool:
    """``DatabasePool`` stand-in that yields the proxy like ``PostgresPool`` does."""

    dialect = "postgresql"

    def __init__(self, conn: _FakePgConnection) -> None:
        self._conn = conn

    @contextmanager
    def transaction(self) -> Iterator[_PgConnectionProxy]:
        yield _PgConnectionProxy(self._conn)


def test_fake_connection_matches_psycopg3_surface() -> None:
    # Guards the reproduction: psycopg3 Connection has no executemany, only Cursor does.
    assert not hasattr(_FakePgConnection, "executemany")
    assert hasattr(_FakeCursor, "executemany")


def test_proxy_executemany_rewrites_placeholders_and_returns_cursor() -> None:
    conn = _FakePgConnection()
    proxy = _PgConnectionProxy(conn)

    cursor = proxy.executemany("INSERT INTO t(a, b) VALUES (?, ?)", [(1, 2), (3, 4)])

    assert cursor is conn.cursor_obj
    assert conn.cursor_obj.batches == [
        ("INSERT INTO t(a, b) VALUES (%s, %s)", [(1, 2), (3, 4)]),
    ]


def test_insert_writes_through_postgres_proxy() -> None:
    conn = _FakePgConnection()
    repo = CarePushRepo(_FakePgPool(conn))

    repo.insert(
        agent_id="agent-1",
        session_key="session-1",
        episode_ids=["episode-1", "episode-2"],
        pushed_at=1_700_000_000,
    )

    assert len(conn.cursor_obj.batches) == 1
    sql, rows = conn.cursor_obj.batches[0]
    assert sql.startswith(_INSERT_PREFIX)
    assert "?" not in sql
    assert [row[1] for row in rows] == ["agent-1", "agent-1"]
    assert [row[2] for row in rows] == ["session-1", "session-1"]
    assert [row[3] for row in rows] == ["episode-1", "episode-2"]
    assert {row[4] for row in rows} == {1_700_000_000}


def test_insert_skips_database_call_when_no_episodes() -> None:
    conn = _FakePgConnection()
    repo = CarePushRepo(_FakePgPool(conn))

    repo.insert(agent_id="agent-1", session_key="session-1", episode_ids=[])

    assert conn.cursor_obj.batches == []


def test_insert_and_dedup_roundtrip_on_sqlite(tmp_path: Any) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    try:
        with pool.connect() as conn:
            conn.execute(
                "CREATE TABLE care_push_records(id TEXT PRIMARY KEY, agent_id TEXT, "
                "session_key TEXT, episode_id TEXT, pushed_at INTEGER)"
            )
        repo = CarePushRepo(pool)
        now = int(time.time())

        repo.insert(agent_id="a", session_key="s", episode_ids=["e1", "e2"], pushed_at=now)

        assert repo.list_pushed_episode_ids("a") == {"e1", "e2"}
        assert repo.list_pushed_episode_ids("other") == set()
    finally:
        pool.close()


if __name__ == "__main__":
    pytest.main([__file__])
