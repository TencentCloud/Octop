"""Unit tests for skill package icon columns and get_by_name."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.skill_packages import SkillPackageRepo

_MIGRATIONS = Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations"

_LEGACY_SKILL_PACKAGES_WITHOUT_ICONS = """
CREATE TABLE skill_packages (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL,
  skill_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def test_skill_package_icons_and_get_by_name(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = SkillPackageRepo(pool)
    row = repo.create(
        id="pkg1",
        name="Alpha",
        description="d",
        created_by="1",
        icon_name="zap",
        icon_url="https://cdn.example.com/a.png",
    )
    assert row.icon_name == "zap"
    assert row.icon_url == "https://cdn.example.com/a.png"
    assert repo.get_by_name("Alpha") is not None
    assert repo.get_by_name("Missing") is None


def test_skill_package_duplicate_name_raises_integrity_error(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = SkillPackageRepo(pool)
    repo.create(id="pkg1", name="Alpha", description="d", created_by="1")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(id="pkg2", name="Alpha", description="d", created_by="1")


def test_repair_legacy_schema_ensures_name_unique_index(tmp_path: Path) -> None:
    """Repair path must backfill the name unique index when table exists at version 2."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript((_MIGRATIONS / "001_initial.sql").read_text())
        conn.executescript((_MIGRATIONS / "002_cron_mcp_and_skill_packages.sql").read_text())
        conn.execute("DROP INDEX IF EXISTS idx_skill_packages_name")
    run_migrations(pool)
    with pool.connect() as conn:
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='skill_packages'"
            )
        }
    assert "idx_skill_packages_name" in indexes


def test_migration_002_idempotent_when_icon_columns_already_present(tmp_path: Path) -> None:
    """Partial upgrade: icon columns exist but version still 1 must not fail."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript((_MIGRATIONS / "001_initial.sql").read_text())
        conn.executescript(_LEGACY_SKILL_PACKAGES_WITHOUT_ICONS)
        conn.execute("ALTER TABLE skill_packages ADD COLUMN icon_name TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE skill_packages ADD COLUMN icon_url TEXT NOT NULL DEFAULT ''")
    run_migrations(pool)
    with pool.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_packages)").fetchall()}
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='skill_packages'"
            )
        }
    assert v == 8
    assert "icon_name" in cols
    assert "icon_url" in cols
    assert "skill_package_id" in cols
    assert "idx_skill_packages_name" in indexes


def test_repair_legacy_schema_adds_icon_columns_at_version_2(tmp_path: Path) -> None:
    """Repair path must backfill icon columns when table exists without them."""
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript((_MIGRATIONS / "001_initial.sql").read_text())
        conn.executescript(_LEGACY_SKILL_PACKAGES_WITHOUT_ICONS)
        conn.execute("UPDATE _schema_version SET version = 2")
    run_migrations(pool)
    with pool.connect() as conn:
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_packages)").fetchall()}
    assert v == 8
    assert "icon_name" in cols
    assert "icon_url" in cols
    assert "skill_package_id" in cols
