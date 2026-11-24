"""Extension-owned migrations: own namespace, own watermark, run after Octop's."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra import extensions
from octop.infra.db import extension_migrations as em
from octop.infra.db.extension_migrations import ExtensionMigrations, apply, discover
from octop.infra.db.migrate import _current_version, run_migrations
from octop.infra.db.pool import SqlitePool


def _write(directory: Path, name: str, sql: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(sql, encoding="utf-8")


@pytest.fixture()
def mig_dir(tmp_path: Path) -> Path:
    d = tmp_path / "migrations"
    _write(d, "001_rooms.sql", "CREATE TABLE IF NOT EXISTS demo_rooms (id TEXT PRIMARY KEY);\n")
    _write(d, "001_rooms.pg.sql", "CREATE TABLE IF NOT EXISTS demo_rooms (id TEXT PRIMARY KEY);\n")
    _write(d, "002_members.sql", "CREATE TABLE IF NOT EXISTS demo_members (room_id TEXT);\n")
    _write(d, "002_members.pg.sql", "CREATE TABLE IF NOT EXISTS demo_members (room_id TEXT);\n")
    return d


@pytest.fixture()
def with_extension(monkeypatch: pytest.MonkeyPatch, mig_dir: Path) -> Iterator[None]:
    ext = SimpleNamespace(migrations=lambda: ExtensionMigrations("demo", mig_dir))
    entries = [SimpleNamespace(name="demo", load=lambda: ext)]
    monkeypatch.setattr(extensions, "entry_points", lambda group: entries)
    extensions.load_extensions.cache_clear()
    yield
    extensions.load_extensions.cache_clear()


def _tables(db: SqlitePool) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def test_discover_splits_dialects(mig_dir: Path) -> None:
    assert [p.name for _, p in discover(mig_dir, "sqlite")] == ["001_rooms.sql", "002_members.sql"]
    assert [p.name for _, p in discover(mig_dir, "postgresql")] == [
        "001_rooms.pg.sql",
        "002_members.pg.sql",
    ]


def test_duplicate_version_is_an_error(mig_dir: Path) -> None:
    _write(mig_dir, "002_other.sql", "SELECT 1;\n")
    with pytest.raises(RuntimeError, match="Duplicate extension migration 002"):
        discover(mig_dir, "sqlite")


def test_runs_after_core_with_its_own_watermark(with_extension: None, tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    core = _current_version(db)

    assert {"demo_rooms", "demo_members", "_extension_schema"} <= _tables(db)
    assert em.current_version(db, "demo") == 2
    assert _current_version(db) == core

    # A second run changes nothing.
    run_migrations(db)
    assert em.current_version(db, "demo") == 2


def test_only_pending_files_run(mig_dir: Path, tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    assert apply(db, ExtensionMigrations("demo", mig_dir)) == 2
    _write(mig_dir, "003_bad_if_rerun.sql", "CREATE TABLE demo_once (id TEXT);\n")
    assert apply(db, ExtensionMigrations("demo", mig_dir)) == 3
    assert apply(db, ExtensionMigrations("demo", mig_dir)) == 3
    assert "demo_once" in _tables(db)


def test_namespace_is_validated(mig_dir: Path, tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    with pytest.raises(ValueError, match="invalid extension migration namespace"):
        apply(db, ExtensionMigrations("Demo; DROP", mig_dir))


def test_two_extensions_cannot_share_a_namespace(
    monkeypatch: pytest.MonkeyPatch, mig_dir: Path, tmp_path: Path
) -> None:
    spec = ExtensionMigrations("demo", mig_dir)
    entries = [
        SimpleNamespace(name=n, load=lambda: SimpleNamespace(migrations=lambda: spec))
        for n in ("a", "b")
    ]
    monkeypatch.setattr(extensions, "entry_points", lambda group: entries)
    extensions.load_extensions.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="both claim namespace"):
            em.run_extension_migrations(SqlitePool(tmp_path / "octop.db"))
    finally:
        extensions.load_extensions.cache_clear()


class _FakePg:
    """Records statements; enough to check the PostgreSQL path without a server."""

    dialect = "postgresql"

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []
        self.transactions = 0

    @contextmanager
    def connect(self) -> Iterator[Any]:
        yield self

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        self.transactions += 1
        yield self

    def execute(self, sql: str, params: Any = None) -> Any:
        self.statements.append((sql, params))
        return SimpleNamespace(fetchone=lambda: None)


def test_postgresql_applies_each_file_with_its_watermark(mig_dir: Path) -> None:
    pg = _FakePg()
    assert apply(pg, ExtensionMigrations("demo", mig_dir)) == 2  # type: ignore[arg-type]
    # One locked read of the watermark, then one transaction per file.
    assert pg.transactions == 3
    locks = [s for s, _ in pg.statements if s.startswith("SELECT pg_advisory_xact_lock")]
    assert len(locks) == 3
    ddl = [s for s, _ in pg.statements if s.startswith("CREATE TABLE IF NOT EXISTS demo_")]
    assert ddl == [
        "CREATE TABLE IF NOT EXISTS demo_rooms (id TEXT PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS demo_members (room_id TEXT)",
    ]
    marks = [p for s, p in pg.statements if s.startswith("INSERT INTO _extension_schema")]
    assert marks == [("demo", 1), ("demo", 2)]
    assert all("%s" in s for s, p in pg.statements if p)


def _count(db: SqlitePool, table: str) -> int:
    with db.connect() as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _once_dir(tmp_path: Path) -> Path:
    # Not idempotent on purpose: running it twice fails or doubles the row.
    d = tmp_path / "once"
    _write(
        d,
        "001_once.sql",
        "CREATE TABLE demo_once (id INTEGER);\nINSERT INTO demo_once VALUES (1);\n",
    )
    return d


def test_two_connections_apply_each_file_once(tmp_path: Path) -> None:
    import threading

    spec = ExtensionMigrations("demo", _once_dir(tmp_path))
    pools = [SqlitePool(tmp_path / "octop.db"), SqlitePool(tmp_path / "octop.db")]
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def run(db: SqlitePool) -> None:
        start.wait()
        try:
            apply(db, spec)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(db,)) for db in pools]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert _count(pools[0], "demo_once") == 1
    assert em.current_version(pools[1], "demo") == 1


def test_a_stale_version_is_rechecked_under_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = ExtensionMigrations("demo", _once_dir(tmp_path))
    first, second = SqlitePool(tmp_path / "octop.db"), SqlitePool(tmp_path / "octop.db")
    apply(first, spec)
    # The second process read the watermark before the first one committed.
    monkeypatch.setattr(em, "current_version", lambda db, namespace: 0)
    assert apply(second, spec) == 1
    assert _count(second, "demo_once") == 1


def test_a_failed_file_rolls_back_and_can_be_retried(tmp_path: Path) -> None:
    d = tmp_path / "partial"
    _write(d, "001_base.sql", "CREATE TABLE demo_base (id INTEGER);\n")
    _write(
        d,
        "002_half.sql",
        "CREATE TABLE demo_half (id INTEGER);\nINSERT INTO demo_missing VALUES (1);\n",
    )
    db = SqlitePool(tmp_path / "octop.db")
    spec = ExtensionMigrations("demo", d)
    with pytest.raises(Exception, match="demo_missing"):
        apply(db, spec)
    assert "demo_half" not in _tables(db)
    assert em.current_version(db, "demo") == 1

    _write(
        d,
        "002_half.sql",
        "CREATE TABLE demo_half (id INTEGER);\nINSERT INTO demo_half VALUES (1);\n",
    )
    assert apply(db, spec) == 2
    assert _count(db, "demo_half") == 1
