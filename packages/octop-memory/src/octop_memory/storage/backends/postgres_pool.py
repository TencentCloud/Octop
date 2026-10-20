"""Process-local PostgreSQL pools shared across namespaces.

Business SQL and LangGraph use separate session settings and budgets. A lease
owns one reference, so closing an agent cannot close another agent's pool.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolClosed

BUSINESS_POOL_SIZE = 8
CHECKPOINT_POOL_SIZE = 4
POOL_TIMEOUT = 30.0
POOL_MAX_WAITING = 64
POOL_MAX_IDLE = 600.0

type _Connection = psycopg.Connection[dict[str, Any]]
type _Key = tuple[str, tuple[tuple[str, Any], ...], tuple[tuple[str, Any], ...]]


@dataclass
class _Entry:
    pool: ConnectionPool[_Connection]
    refs: int = 0
    initialized: bool = False
    init_lock: threading.Lock = field(default_factory=threading.Lock)


_registry: dict[_Key, _Entry] = {}
_registry_lock = threading.RLock()


def _configure_business(conn: _Connection) -> None:
    # PostgreSQL accepts a search_path before the schema is created. Every
    # namespace uses the same schema; isolation is in SQL predicates.
    conn.execute("SET search_path TO octop_memory, public")
    conn.commit()


def _release(key: _Key, entry: _Entry) -> None:
    with _registry_lock:
        entry.refs -= 1
        if entry.refs == 0:
            del _registry[key]
            entry.pool.close()


class PostgresPoolLease(ConnectionPool[_Connection]):
    """Internal connection/close adapter accepted by LangGraph's type check.

    The base pool stays unopened and owns no connections or worker threads.
    All SQL goes through the shared pool. Each lease serializes close with its
    own outstanding operation, and its finalizer releases exactly one ref.
    """

    def __init__(self, key: _Key, entry: _Entry) -> None:
        super().__init__(min_size=0, max_size=entry.pool.max_size, open=False)
        self._entry = entry
        self._lease_lock = threading.RLock()
        self._release_ref = weakref.finalize(self, _release, key, entry)

    @property
    def closed(self) -> bool:
        return not self._release_ref.alive

    @contextmanager
    def connection(self, timeout: float | None = None) -> Iterator[_Connection]:
        with self._lease_lock:
            if self.closed:
                raise PoolClosed("the memory pool lease is closed")
            with self._entry.pool.connection(timeout=timeout) as conn:
                yield conn

    def close(self, timeout: float = 5.0) -> None:
        with self._lease_lock:
            self._release_ref()

    def get_stats(self) -> dict[str, int]:
        return self._entry.pool.get_stats()

    def initialize(self, setup: Callable[[], None]) -> None:
        """Serialize checkpoint DDL once per live pool; failures can retry."""
        with self._entry.init_lock:
            if not self._entry.initialized:
                setup()
                self._entry.initialized = True


def acquire_pool(
    dsn: str,
    *,
    purpose: Literal["business", "checkpoint"],
    connect_kwargs: dict[str, Any] | None = None,
) -> PostgresPoolLease:
    kwargs = dict(connect_kwargs or {})
    kwargs["row_factory"] = dict_row
    if purpose == "checkpoint":
        kwargs.update(autocommit=True, prepare_threshold=0)
    # Normalize URI/keyword syntax and ordering without logging credentials.
    # Driver options (e.g. context/cursor_factory) remain part of the identity.
    key: _Key = (purpose, tuple(sorted(conninfo_to_dict(dsn).items())), tuple(sorted(kwargs.items())))
    with _registry_lock:
        entry = _registry.get(key)
        if entry is None:
            pool: ConnectionPool[_Connection] = ConnectionPool(
                conninfo=dsn,
                kwargs=kwargs,
                min_size=0,
                max_size=BUSINESS_POOL_SIZE if purpose == "business" else CHECKPOINT_POOL_SIZE,
                timeout=POOL_TIMEOUT,
                max_waiting=POOL_MAX_WAITING,
                max_idle=POOL_MAX_IDLE,
                check=ConnectionPool.check_connection,
                configure=_configure_business if purpose == "business" else None,
                open=True,
            )
            entry = _registry[key] = _Entry(pool)
        entry.refs += 1
        return PostgresPoolLease(key, entry)


@contextmanager
def maintenance_connection(dsn: str) -> Iterator[_Connection]:
    """VACUUM needs autocommit; share the checkpoint budget for maintenance."""
    lease = acquire_pool(dsn, purpose="checkpoint")
    try:
        with lease.connection() as conn:
            yield conn
    finally:
        lease.close()
