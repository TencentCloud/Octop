"""Whole migration runs serialize across real database connections and processes."""

from __future__ import annotations

import multiprocessing
import os
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from tests.support.postgresql import requires_postgresql

from octop.infra.db import migrate
from octop.infra.db.pool import DatabasePool, PostgresPool, SqlitePool


def _migration_process(backend: str, target: str, barrier: Any, results: Any) -> None:
    pool = (
        PostgresPool(target, min_size=1, max_size=1)
        if backend == "postgresql"
        else SqlitePool(Path(target))
    )
    original = migrate._current_version
    first = True

    def read_version(db: DatabasePool) -> int:
        nonlocal first
        version = original(db)
        if first:
            first = False
            # Without a whole-run guard, both processes read version zero.
            # With the guard, the second process cannot read until the first
            # finishes, so release the first after the bounded rendezvous.
            with suppress(threading.BrokenBarrierError):
                barrier.wait(timeout=1)
        return version

    migrate._current_version = read_version
    try:
        migrate.run_migrations(pool)
        results.put((True, original(pool)))
    except Exception as exc:
        results.put((False, type(exc).__name__))
    finally:
        pool.close()


def _assert_process_migrations(backend: str, target: str) -> None:
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    processes = [
        context.Process(target=_migration_process, args=(backend, target, barrier, results))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=60) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        latest = max(version for version, _ in migrate._discover(backend))
        assert outcomes == [(True, latest), (True, latest)]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=10)
        results.close()
        results.join_thread()


def test_separate_sqlite_processes_migrate_fresh_database(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    # Set up the journal before racing migration SQL, not journal initialization.
    SqlitePool(path).close()
    _assert_process_migrations("sqlite", str(path))


@pytest.fixture
def postgres_targets() -> Iterator[list[str]]:
    import psycopg
    from psycopg.conninfo import make_conninfo

    conninfo = os.environ["OCTOP_TEST_DATABASE_URL"]
    schemas = [f"startup_guard_{uuid.uuid4().hex}" for _ in range(2)]
    with psycopg.connect(conninfo, autocommit=True) as conn:
        for schema in schemas:
            conn.execute(f'CREATE SCHEMA "{schema}"')
    try:
        # Dedicated real advisory-lock sessions inherit this native timeout;
        # failed release must raise rather than hang executor/process cleanup.
        yield [
            make_conninfo(conninfo, options=f"-csearch_path={schema} -clock_timeout=5000")
            for schema in schemas
        ]
    finally:
        with psycopg.connect(conninfo, autocommit=True) as conn:
            for schema in schemas:
                conn.execute(f'DROP SCHEMA "{schema}" CASCADE')


@requires_postgresql
@pytest.mark.postgresql
def test_single_connection_postgres_processes_migrate_fresh_database(
    postgres_targets: list[str],
) -> None:
    _assert_process_migrations("postgresql", postgres_targets[0])


def _assert_guard_cleanup_and_scope(first: DatabasePool, other: DatabasePool) -> None:
    with (
        pytest.raises(RuntimeError, match="migration failure"),
        migrate._migration_guard(first),
    ):
        raise RuntimeError("migration failure")
    # Failure releases the old lock, allowing another connection/thread to retry.
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(migrate.run_migrations, first).result(timeout=30)

    def enter_other_database() -> None:
        with migrate._migration_guard(other):
            pass

    with ThreadPoolExecutor(max_workers=1) as executor, migrate._migration_guard(first):
        # A different SQLite file or PostgreSQL schema is not blocked.
        executor.submit(enter_other_database).result(timeout=10)
    migrate.run_migrations(first)


def test_sqlite_guard_releases_on_failure_and_scopes_by_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real OS file locks with a bounded wait: a broken release must fail the
    # regression rather than leave executor teardown waiting indefinitely.
    monkeypatch.setattr(migrate, "FileLock", partial(FileLock, timeout=5))
    pools = [SqlitePool(tmp_path / name) for name in ("one.db", "two.db")]
    try:
        _assert_guard_cleanup_and_scope(*pools)
    finally:
        for pool in pools:
            pool.close()


@requires_postgresql
@pytest.mark.postgresql
def test_postgres_guard_releases_on_failure_and_scopes_by_schema(
    postgres_targets: list[str],
) -> None:
    pools = [PostgresPool(target, min_size=1, max_size=1) for target in postgres_targets]
    try:
        _assert_guard_cleanup_and_scope(*pools)
    finally:
        for pool in pools:
            pool.close()


@requires_postgresql
@pytest.mark.postgresql
def test_postgres_guard_preserves_connection_password(
    postgres_targets: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import psycopg
    from psycopg.conninfo import make_conninfo

    # Synthetic fixture value only; ConnectionInfo.dsn omits even this value.
    password = "synthetic-migration-fixture"
    pool = PostgresPool(make_conninfo(postgres_targets[0], password=password), max_size=1)
    connect = psycopg.connect
    lock_connections: list[dict[str, Any]] = []

    def connect_with_parameters(conninfo: str, **kwargs: Any) -> Any:
        lock_connections.append(kwargs)
        return connect(conninfo, **kwargs)

    try:
        with pool.connect() as conn:
            assert conn.info.password == password
            assert password not in conn.info.dsn
        monkeypatch.setattr(psycopg, "connect", connect_with_parameters)
        with migrate._migration_guard(pool):
            pass
        assert len(lock_connections) == 1
        assert lock_connections[0]["password"] == password
    finally:
        pool.close()
