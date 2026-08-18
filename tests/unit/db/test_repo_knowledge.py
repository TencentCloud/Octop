"""Unit tests for KnowledgeRepo and migration 005."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def repo(db: SqlitePool) -> KnowledgeRepo:
    return KnowledgeRepo(db)


@pytest.fixture
def owner_id(db: SqlitePool) -> int:
    return UserRepo(db).create(username="owner", password_hash="h", role="user")


def test_knowledge_create_with_icon(repo: KnowledgeRepo, owner_id: int) -> None:
    row = repo.create_base(owner_user_id=owner_id, name="Science", icon_name="flask-conical")
    assert len(row.id) == 6
    assert row.icon_name == "flask-conical"
    repo.update_base(row.id, icon_name="cpu")
    updated = repo.get_base(row.id)
    assert updated is not None
    assert updated.icon_name == "cpu"


def test_knowledge_tables_migrated(db: SqlitePool) -> None:
    with db.connect() as conn:
        names = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        v = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
    assert {
        "knowledge_bases",
        "knowledge_base_members",
        "knowledge_documents",
    }.issubset(names)
    assert v == 7


def test_path_layout_knowledge_dir(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / ".octop")
    assert paths.knowledge_dir == tmp_path / ".octop" / "knowledge"


def test_knowledge_migrate_and_create(
    repo: KnowledgeRepo, owner_id: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout.from_env()
    assert paths.knowledge_dir == tmp_path / "knowledge"

    row = repo.create_base(owner_user_id=owner_id, name="Docs", description="team docs")
    assert row.id
    assert row.owner_user_id == owner_id
    assert row.name == "Docs"
    assert row.description == "team docs"
    assert row.default_open is False
    assert repo.count_documents(row.id) == 0


def test_list_visible_owner_and_shared_base(
    repo: KnowledgeRepo, db: SqlitePool, owner_id: int
) -> None:
    users = UserRepo(db)
    member_id = users.create(username="member", password_hash="h", role="user")
    other_id = users.create(username="other", password_hash="h", role="user")

    kb = repo.create_base(owner_user_id=owner_id, name="Shared", shared=True)
    repo.set_member(kb.id, user_id=member_id, role="viewer")

    owner_visible = {r.id for r in repo.list_visible(owner_id)}
    member_visible = {r.id for r in repo.list_visible(member_id)}
    other_visible = {r.id for r in repo.list_visible(other_id)}

    assert kb.id in owner_visible
    assert kb.id in member_visible
    assert kb.id in other_visible
    assert kb.shared is True


def test_knowledge_document_crud(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    doc = repo.create_document(
        kb_id=kb.id,
        filename="readme.md",
        content_type="text/markdown",
        byte_size=42,
        content_hash="abc",
    )
    assert doc.status == "pending"
    assert repo.count_documents(kb.id) == 1

    listed = repo.list_documents(kb.id)
    assert len(listed) == 1
    assert listed[0].id == doc.id

    repo.update_document(doc.id, status="ready", chunk_count=3)
    updated = repo.get_document(doc.id)
    assert updated is not None
    assert updated.status == "ready"
    assert updated.chunk_count == 3

    repo.delete_document(doc.id)
    assert repo.get_document(doc.id) is None
    assert repo.count_documents(kb.id) == 0


def test_create_document_applies_limit_within_insert_transaction(
    repo: KnowledgeRepo, owner_id: int
) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    repo.create_document(
        kb_id=kb.id,
        filename="first.md",
        content_type="text/markdown",
        byte_size=1,
        max_documents=1,
    )

    with pytest.raises(ValueError, match="at most 1"):
        repo.create_document(
            kb_id=kb.id,
            filename="second.md",
            content_type="text/markdown",
            byte_size=1,
            max_documents=1,
        )

    assert repo.count_documents(kb.id) == 1
