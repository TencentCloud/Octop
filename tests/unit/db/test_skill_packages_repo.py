"""Unit tests for SkillPackageRepo and migration 002."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.skill_packages import SkillPackageRepo

_MIGRATIONS = Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations"


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_skill_packages_table_exists(db: SqlitePool) -> None:
    with db.connect() as conn:
        names = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(skill_packages)").fetchall()}
    assert "skill_packages" in names
    assert v == 7
    assert "skill_package_id" in cols


def test_skill_package_repo_create_get(db: SqlitePool) -> None:
    repo = SkillPackageRepo(db)
    row = repo.create(
        id="01TESTPACK000000000000000", name="Office", description="d", created_by="1"
    )
    assert row.pk >= 1
    assert repo.get(row.id).name == "Office"
    assert repo.list_all()[0].id == row.id
    with db.connect() as conn:
        stored = conn.execute(
            "SELECT id, skill_package_id FROM skill_packages WHERE skill_package_id = ?",
            (row.id,),
        ).fetchone()
    assert stored["skill_package_id"] == row.id
    assert int(stored["id"]) == row.pk


def test_legacy_text_pk_skill_packages_keep_public_id(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    with pool.connect() as conn:
        conn.executescript((_MIGRATIONS / "001_initial.sql").read_text())
        conn.executescript((_MIGRATIONS / "002_cron_mcp_and_skill_packages.sql").read_text())
        conn.execute(
            "INSERT INTO skill_packages("
            "id, name, description, created_by, skill_count, icon_name, icon_url, "
            "created_at, updated_at"
            ") VALUES (?, ?, ?, ?, 0, '', '', '1', '1')",
            ("pkgABC", "Office", "d", "1"),
        )
        conn.execute("UPDATE _schema_version SET version = 2")
    run_migrations(pool)
    repo = SkillPackageRepo(pool)
    row = repo.get("pkgABC")
    assert row is not None
    assert row.id == "pkgABC"
    assert row.pk >= 1
    assert row.name == "Office"
