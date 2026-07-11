"""tests/unit/test_db_factory.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import load_config
from octop.infra.db.factory import open_database
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


def test_postgresql_raises_not_implemented(tmp_path: Path):
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
                }
            }
        )
    )
    paths = PathLayout(root)
    cfg = load_config(paths.config)
    with pytest.raises(NotImplementedError, match="PostgreSQL"):
        open_database(cfg, paths)
