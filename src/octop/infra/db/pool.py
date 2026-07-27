"""Database pools: SQLite (default) and PostgreSQL."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


def qmark_to_pyformat(sql: str) -> str:
    """Rewrite ``?`` placeholders to psycopg ``%s`` (no string-literal awareness)."""
    return sql.replace("?", "%s")


@runtime_checkable
class DatabasePool(Protocol):
    dialect: str

    @contextmanager
    def connect(self) -> Iterator[Any]: ...

    @contextmanager
    def transaction(self) -> Iterator[Any]: ...

    def close(self) -> None: ...


class SqlitePool:
    """Single shared SQLite connection guarded by an RLock."""

    dialect: str = "sqlite"

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        first_create = not self.path.exists()
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()
        if first_create and os.name == "posix":
            os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            yield self._conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        self._conn.close()


class _CompatRow(Mapping[str, Any]):
    """Row that supports both ``row["col"]`` and ``row[0]`` like sqlite3.Row."""

    __slots__ = ("_columns", "_values", "_map")

    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._map = dict(zip(self._columns, self._values, strict=True))

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._map[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self) -> Any:
        return self._map.keys()


def _compat_row_factory(cursor: Any) -> Any:
    fields = [d.name for d in cursor.description] if cursor.description else []

    def make(values: Sequence[Any]) -> _CompatRow:
        return _CompatRow(fields, values)

    return make


class _PgConnectionProxy:
    """Expose sqlite-like ``execute`` / ``executescript`` on a psycopg connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = None) -> Any:
        return self._conn.execute(qmark_to_pyformat(sql), params)

    def executescript(self, sql: str) -> None:
        # Used only if something still calls it; prefer migrate splitter.
        for stmt in _split_sql_statements(sql):
            self._conn.execute(stmt)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


_SQL_STMT_RE = re.compile(r";\s*\n")


def _split_sql_statements(sql: str) -> list[str]:
    parts = [p.strip() for p in _SQL_STMT_RE.split(sql)]
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        lines = part.splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        cleaned = "\n".join(lines).strip()
        if cleaned:
            out.append(cleaned)
    return out


class PostgresPool:
    dialect: str = "postgresql"

    def __init__(self, conninfo: str, *, min_size: int = 1, max_size: int = 8) -> None:
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": _compat_row_factory},
            open=True,
        )

    @contextmanager
    def connect(self) -> Iterator[_PgConnectionProxy]:
        with self._pool.connection() as conn:
            yield _PgConnectionProxy(conn)

    @contextmanager
    def transaction(self) -> Iterator[_PgConnectionProxy]:
        with self._pool.connection() as conn, conn.transaction():
            yield _PgConnectionProxy(conn)

    def close(self) -> None:
        self._pool.close()
