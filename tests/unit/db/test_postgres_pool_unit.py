from __future__ import annotations

from typing import Any

from octop.infra.db.pool import _PgConnectionProxy, qmark_to_pyformat


def test_qmark_to_pyformat_replaces_placeholders():
    assert qmark_to_pyformat("SELECT * FROM t WHERE a = ? AND b = ?") == (
        "SELECT * FROM t WHERE a = %s AND b = %s"
    )


def test_qmark_to_pyformat_leaves_percent_alone():
    assert qmark_to_pyformat("SELECT %s") == "SELECT %s"


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _FakeCursor:
        self._conn.cursor_started = True
        return self

    def __exit__(self, *args: object) -> None:
        self._conn.cursor_closed = True

    def executemany(self, sql: str, seq_of_params: Any) -> None:
        self._conn.executemany_calls.append((sql, list(seq_of_params)))


class _FakeConnection:
    """Mirrors the real psycopg API surface for the proxy.

    psycopg ``Connection`` does NOT expose ``executemany``; only the cursor
    does. Anything the proxy delegates must go through explicit methods.
    """

    def __init__(self) -> None:
        self.executemany_calls: list[tuple[str, list[Any]]] = []
        self.cursor_started = False
        self.cursor_closed = False

    def execute(self, sql: str, params: Any = None) -> Any:
        self.executemany_calls.append((sql, [params] if params else []))
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


def test_pg_proxy_executemany_uses_cursor_and_qmark() -> None:
    fake = _FakeConnection()
    proxy = _PgConnectionProxy(fake)
    rows = [("a", 1), ("b", 2)]
    proxy.executemany("INSERT INTO t VALUES (?, ?)", rows)
    assert fake.executemany_calls == [
        ("INSERT INTO t VALUES (%s, %s)", rows),
    ]
    assert fake.cursor_started
    assert fake.cursor_closed


def test_pg_proxy_executemany_accepts_empty_seq() -> None:
    fake = _FakeConnection()
    proxy = _PgConnectionProxy(fake)
    proxy.executemany("INSERT INTO t VALUES (?)", [])
    assert fake.executemany_calls == [("INSERT INTO t VALUES (%s)", [])]
