"""Unit tests for PublishedExpertRepo and migration 006."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.published_experts import PublishedExpertRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_published_experts_table_exists(db: SqlitePool) -> None:
    with db.connect() as conn:
        names = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(published_experts)").fetchall()}
    assert "published_experts" in names
    assert v == 7
    assert "published_expert_id" in cols


def test_published_expert_repo_create_get_list_delete(db: SqlitePool) -> None:
    repo = PublishedExpertRepo(db)
    row = repo.create(
        id="01TESTEXPERT000000000000",
        slug="office-helper",
        name="Office Helper",
        description="Helps with office tasks",
        created_by="user-1",
        source_agent_id="agent-abc",
        icon_name="briefcase",
        color="#336699",
    )
    assert row.slug == "office-helper"
    assert row.pk >= 1
    assert row.name == "Office Helper"
    assert row.source_agent_id == "agent-abc"
    assert row.icon_name == "briefcase"
    assert row.color == "#336699"

    fetched = repo.get(row.id)
    assert fetched is not None
    assert fetched.slug == "office-helper"

    by_slug = repo.get_by_slug("office-helper")
    assert by_slug is not None
    assert by_slug.id == row.id

    listed = repo.list_all()
    assert len(listed) == 1
    assert listed[0].id == row.id

    repo.delete(row.id)
    assert repo.get(row.id) is None
    assert repo.list_all() == []


def test_published_expert_repo_unique_slug(db: SqlitePool) -> None:
    repo = PublishedExpertRepo(db)
    repo.create(
        id="01TESTEXPERT000000000001",
        slug="duplicate-slug",
        name="First",
        created_by="user-1",
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(
            id="01TESTEXPERT000000000002",
            slug="duplicate-slug",
            name="Second",
            created_by="user-2",
        )


def test_published_expert_repo_get_by_source_and_update_meta(db: SqlitePool) -> None:
    repo = PublishedExpertRepo(db)
    row = repo.create(
        id="01TESTEXPERT000000000003",
        slug="from-source",
        name="From Source",
        created_by="user-1",
        source_agent_id="agent-xyz",
        icon_name="old",
        color="#111111",
    )
    assert repo.get_by_source_agent_id("agent-xyz") is not None
    assert repo.get_by_source_agent_id("agent-xyz").id == row.id
    assert repo.get_by_source_agent_id("missing") is None

    updated = repo.update_snapshot_meta(
        row.id,
        icon_name="search",
        color="#abcdef",
    )
    assert updated.icon_name == "search"
    assert updated.color == "#abcdef"
    assert updated.updated_at >= row.updated_at
    assert updated.updated_at >= row.created_at


def test_legacy_text_pk_published_experts_keep_public_id(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    migrations = Path(__file__).resolve().parents[3] / "src/octop/infra/db/migrations"
    with pool.connect() as conn:
        conn.executescript((migrations / "001_initial.sql").read_text())
        conn.executescript((migrations / "005_shared_experts_sso_knowledge.sql").read_text())
        conn.execute(
            "INSERT INTO published_experts("
            "id, slug, name, description, created_by, source_agent_id, "
            "icon_name, color, created_at, updated_at"
            ") VALUES (?, ?, ?, '', ?, NULL, '', '', 1, 1)",
            ("expABC", "office-helper", "Office Helper", "user-1"),
        )
        conn.execute("UPDATE _schema_version SET version = 5")
    run_migrations(pool)
    repo = PublishedExpertRepo(pool)
    row = repo.get("expABC")
    assert row is not None
    assert row.id == "expABC"
    assert row.pk >= 1
    assert row.slug == "office-helper"
