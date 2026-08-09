"""Unit tests for SkillPackageRepo and migration 002."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.skill_packages import SkillPackageRepo


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
    assert "skill_packages" in names
    assert v == 4


def test_skill_package_repo_create_get(db: SqlitePool) -> None:
    repo = SkillPackageRepo(db)
    row = repo.create(
        id="01TESTPACK000000000000000", name="Office", description="d", created_by="1"
    )
    assert repo.get(row.id).name == "Office"
    assert repo.list_all()[0].id == row.id
