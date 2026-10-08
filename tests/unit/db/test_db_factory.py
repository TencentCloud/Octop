"""tests/unit/test_db_factory.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import load_config
from octop.infra.db.factory import open_database, should_defer_control_plane_db
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


def _fake_postgres_pool(
    factory_mod: object,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    """Replace ``PostgresPool`` in the factory and record its constructor kwargs."""
    from octop.infra.db.pool import PostgresPool

    created: dict[str, object] = {}

    class FakePool(PostgresPool):
        def __init__(self, conninfo: str, **kwargs: object) -> None:
            created["conninfo"] = conninfo
            created.update(kwargs)
            self.dialect = "postgresql"

        def close(self) -> None:
            return None

    monkeypatch.setattr(factory_mod, "PostgresPool", FakePool)
    return created


def _write_pg_config(root: Path, section: dict[str, object]) -> Path:
    root.mkdir()
    cfg_path = root / "config.json"
    base: dict[str, object] = {
        "driver": "postgresql",
        "host": "localhost",
        "database": "octop",
        "user": "octop",
    }
    cfg_path.write_text(json.dumps({"database": {**base, **section}}), encoding="utf-8")
    return cfg_path


def test_open_database_forwards_pool_policy_to_psycopg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from octop.infra.db import factory as factory_mod

    created = _fake_postgres_pool(factory_mod, monkeypatch)
    cfg_path = _write_pg_config(
        tmp_path / ".octop",
        {"pool_min_size": 3, "pool_max_size": 20, "pool_max_idle_seconds": 5},
    )
    pool = open_database(load_config(cfg_path), PathLayout(cfg_path.parent))
    assert pool.dialect == "postgresql"
    assert created["min_size"] == 3
    assert created["max_size"] == 20
    assert created["max_idle"] == 5.0


def test_open_database_default_policy_leaves_nothing_at_rest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from octop.infra.db import factory as factory_mod

    created = _fake_postgres_pool(factory_mod, monkeypatch)
    cfg_path = _write_pg_config(tmp_path / ".octop", {})
    open_database(load_config(cfg_path), PathLayout(cfg_path.parent))
    assert created["min_size"] == 0
    assert created["max_size"] == 8
    assert created["max_idle"] == 60.0


def test_persist_database_config_preserves_pool_policy(tmp_path: Path):
    """The wizard payload carries no pool fields, so the file's must survive a re-run."""
    from octop.config import parse_database_config
    from octop.infra.db.rebind import persist_database_config

    cfg_path = _write_pg_config(
        tmp_path / ".octop",
        {"pool_min_size": 2, "pool_max_size": 20, "pool_max_idle_seconds": 30},
    )
    payload_only = parse_database_config(
        {
            "driver": "postgresql",
            "host": "localhost",
            "database": "octop",
            "user": "octop",
        }
    )
    assert payload_only.pool_min_size == 0  # the wizard would have reset it

    reloaded = persist_database_config(cfg_path, payload_only)
    db = reloaded.database
    assert (db.pool_min_size, db.pool_max_size, db.pool_max_idle_seconds) == (2, 20, 30.0)
