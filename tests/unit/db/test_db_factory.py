"""tests/unit/test_db_factory.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import DatabaseConfig, OctopConfig, load_config
from octop.infra.db.factory import (
    is_database_initialized,
    open_database,
    should_defer_control_plane_db,
)
from octop.infra.utils.paths import PathLayout


def test_legacy_config_without_database_uses_paths_db(tmp_path: Path):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"port": 9000}))
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert cfg.database_in_file is False
    pool = open_database(cfg, paths)
    assert pool.path == paths.db


def test_should_defer_when_sqlite_file_missing(tmp_path: Path):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"port": 8088}))
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert should_defer_control_plane_db(cfg, paths) is True


def test_should_not_defer_when_sqlite_exists(tmp_path: Path):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"port": 8088}))
    (root / "octop.db").write_bytes(b"")
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert should_defer_control_plane_db(cfg, paths) is False


def test_should_not_defer_when_database_env_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"port": 8088}))
    monkeypatch.setenv("OCTOP_DATABASE_SQLITE_PATH", str(root / "env.db"))
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert should_defer_control_plane_db(cfg, paths) is False


def test_should_not_defer_postgresql(tmp_path: Path):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps(
            {
                "database": {
                    "driver": "postgresql",
                    "host": "localhost",
                    "database": "octop",
                    "user": "octop",
                    "password": "x",
                }
            }
        )
    )
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert should_defer_control_plane_db(cfg, paths) is False


def test_sqlite_probe_does_not_create_missing_file(tmp_path: Path):
    from octop.config import DatabaseConfig
    from octop.infra.db.probe import probe_database

    root = tmp_path / ".octop"
    root.mkdir()
    paths = PathLayout(root)
    target = root / "data" / "fresh.db"
    assert not target.exists()
    probe_database(
        DatabaseConfig(driver="sqlite", sqlite_path="data/fresh.db"),
        paths,
    )
    assert not target.exists()
    assert target.parent.is_dir()


def test_config_with_database_section_uses_sqlite_path(tmp_path: Path):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps({"database": {"driver": "sqlite", "sqlite_path": "data/app.db"}})
    )
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert cfg.database_in_file is True
    pool = open_database(cfg, paths)
    assert pool.path == root / "data" / "app.db"


def test_env_sqlite_path_without_database_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"port": 8088}))
    monkeypatch.setenv("OCTOP_DATABASE_SQLITE_PATH", "/tmp/custom-octop.db")
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    assert cfg.database_in_file is False
    pool = open_database(cfg, paths)
    assert pool.path == cfg.database.resolve_sqlite_path(paths.root)


def test_postgresql_returns_postgres_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Unit test without live server: monkeypatch PostgresPool.__init__ to no-op pool.
    from octop.infra.db import factory as factory_mod
    from octop.infra.db.pool import PostgresPool

    created: dict[str, str] = {}

    class FakePool(PostgresPool):
        def __init__(self, conninfo: str, **kwargs: object) -> None:
            created["conninfo"] = conninfo
            self.dialect = "postgresql"

        def close(self) -> None:
            return None

    monkeypatch.setattr(factory_mod, "PostgresPool", FakePool)

    root = tmp_path / ".octop"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps(
            {
                "database": {
                    "driver": "postgresql",
                    "host": "localhost",
                    "database": "octop",
                    "user": "octop",
                    "password": "x",
                }
            }
        )
    )
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    pool = open_database(cfg, paths)
    assert pool.dialect == "postgresql"
    assert "octop" in created["conninfo"]


def test_database_initialized_uses_configured_sqlite_path(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path)
    config = OctopConfig(
        database=DatabaseConfig(driver="sqlite", sqlite_path="custom.db"),
        database_in_file=True,
    )
    assert is_database_initialized(config, paths) is False
    assert not (tmp_path / "custom.db").exists()
    (tmp_path / "custom.db").touch()
    assert is_database_initialized(config, paths) is True


@pytest.mark.parametrize(
    ("table_exists", "has_user", "expected"),
    [(False, False, False), (True, False, False), (True, True, True)],
)
def test_database_initialized_checks_postgres_users(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    table_exists: bool,
    has_user: bool,
    expected: bool,
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace
    from typing import Any

    from octop.infra.db import factory as factory_mod

    queries: list[str] = []
    closed = False

    class FakeConnection:
        def execute(self, sql: str) -> Any:
            queries.append(sql)
            row = ("users",) if table_exists else (None,)
            if sql.startswith("SELECT 1 FROM users"):
                row = (1,) if has_user else None
            return SimpleNamespace(fetchone=lambda: row)

    class FakePool:
        @contextmanager
        def connect(self) -> Any:
            yield FakeConnection()

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(factory_mod, "open_database", lambda _config, _paths: FakePool())
    config = OctopConfig(database=DatabaseConfig(driver="postgresql"))

    assert is_database_initialized(config, PathLayout(tmp_path)) is expected
    assert closed
    assert queries == (
        ["SELECT to_regclass('users')", "SELECT 1 FROM users LIMIT 1"]
        if table_exists
        else ["SELECT to_regclass('users')"]
    )
