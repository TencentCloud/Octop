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
    assert pg.transactions == 2
    ddl = [s for s, _ in pg.statements if s.startswith("CREATE TABLE IF NOT EXISTS demo_")]
    assert ddl == [
        "CREATE TABLE IF NOT EXISTS demo_rooms (id TEXT PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS demo_members (room_id TEXT)",
    ]
    marks = [p for s, p in pg.statements if s.startswith("INSERT INTO _extension_schema")]
    assert marks == [("demo", 1), ("demo", 2)]
    assert all("%s" in s for s, p in pg.statements if p)
