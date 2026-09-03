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
        "knowledge_documents",
    }.issubset(names)
    assert v == 12
    assert "knowledge_base_members" not in names
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(knowledge_bases)").fetchall()}
    assert "knowledge_base_id" in cols
    assert "max_documents" in cols


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

    owner_visible = {r.id for r in repo.list_visible(owner_id)}
    member_visible = {r.id for r in repo.list_visible(member_id)}
    other_visible = {r.id for r in repo.list_visible(other_id)}

    assert kb.id in owner_visible
    assert kb.id in member_visible
    assert kb.id in other_visible
    assert kb.shared is True


def test_knowledge_folders_and_nested_documents(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Nested")
    folder = repo.ensure_folder(kb.id, "notes/law")
    assert folder.is_dir is True
    assert folder.path == "notes/law"
    doc = repo.create_document(
        kb_id=kb.id,
        filename="act.md",
        path="notes/law/act.md",
        content_type="text/markdown",
        byte_size=4,
    )
    assert doc.path == "notes/law/act.md"
    children = repo.list_children(kb.id, "notes")
    assert {row.path for row in children} == {"notes/law"}
    nested = repo.list_children(kb.id, "notes/law")
    assert [row.path for row in nested] == ["notes/law/act.md"]
    removed = repo.delete_document(folder.id)
    assert {row.path for row in removed} == {"notes/law", "notes/law/act.md"}
    assert repo.count_documents(kb.id) == 0


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

    assert repo.count_documents(kb.id) == 1


def test_migration_007_rebuilds_text_primary_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "octop.db"
    pool = SqlitePool(db_path)
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute("UPDATE _schema_version SET version = 6")
        conn.executescript(
            """
            CREATE TABLE knowledge_bases (
              id TEXT PRIMARY KEY,
              owner_user_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              default_open INTEGER NOT NULL DEFAULT 0,
              shared INTEGER NOT NULL DEFAULT 0,
              icon_name TEXT NOT NULL DEFAULT '',
              embedding_model TEXT NOT NULL DEFAULT '',
              embedding_dim INTEGER NOT NULL DEFAULT 0,
              doc_count INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE knowledge_base_members (
              kb_id TEXT NOT NULL,
              user_id INTEGER NOT NULL,
              role TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              PRIMARY KEY (kb_id, user_id)
            );
            CREATE TABLE knowledge_documents (
              id TEXT PRIMARY KEY,
              kb_id TEXT NOT NULL,
              filename TEXT NOT NULL,
              content_type TEXT NOT NULL,
              byte_size INTEGER NOT NULL,
              content_hash TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending',
              error_message TEXT NOT NULL DEFAULT '',
              chunk_count INTEGER NOT NULL DEFAULT 0,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            INSERT INTO users(username, password_hash, role, created_at)
            VALUES ('owner', 'h', 'user', 1);
            INSERT INTO knowledge_bases(
              id, owner_user_id, name, description, default_open, shared, icon_name,
              embedding_model, embedding_dim, doc_count, created_at, updated_at
            ) VALUES ('kbabcd', 1, 'Docs', '', 0, 0, '', '', 0, 1, 1, 1);
            INSERT INTO knowledge_documents(
              id, kb_id, filename, content_type, byte_size, content_hash, status,
              error_message, chunk_count, created_at, updated_at
            ) VALUES ('doc1', 'kbabcd', 'a.md', 'text/markdown', 1, '', 'ready', '', 1, 1, 1);
            """
        )
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    base = repo.get_base("kbabcd")
    assert base is not None
    assert base.pk >= 1
    assert base.id == "kbabcd"
    doc = repo.get_document("doc1")
    assert doc is not None
    assert doc.path == "a.md"
    assert doc.is_dir is False
    with pool.connect() as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "knowledge_base_members" not in tables


def test_rename_folder_updates_descendant_paths(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    folder = repo.ensure_folder(kb.id, "notes/law")
    doc = repo.create_document(
        kb_id=kb.id,
        filename="act.md",
        path="notes/law/act.md",
        content_type="text/markdown",
        byte_size=4,
    )
    renamed = repo.rename_document(kb.id, folder.id, "legal")
    assert renamed is not None
    assert renamed.is_dir is True
    assert renamed.filename == "legal"
    assert renamed.path == "notes/legal"

    children = repo.list_children(kb.id, "notes")
    assert {row.path for row in children} == {"notes/legal"}
    nested = repo.list_children(kb.id, "notes/legal")
    assert [row.path for row in nested] == ["notes/legal/act.md"]
    moved = repo.get_document(doc.id)
    assert moved is not None
    assert moved.path == "notes/legal/act.md"
    assert moved.filename == "act.md"


def test_rename_root_folder(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    folder = repo.ensure_folder(kb.id, "notes")
    renamed = repo.rename_document(kb.id, folder.id, "chapters")
    assert renamed is not None
    assert renamed.path == "chapters"
    assert renamed.filename == "chapters"


def test_rename_file_updates_path_and_filename(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    doc = repo.create_document(
        kb_id=kb.id,
        filename="readme.md",
        content_type="text/markdown",
        byte_size=4,
    )
    renamed = repo.rename_document(kb.id, doc.id, "guide.md")
    assert renamed is not None
    assert renamed.filename == "guide.md"
    assert renamed.path == "guide.md"


def test_rename_document_missing_or_wrong_kb_returns_none(
    repo: KnowledgeRepo, owner_id: int
) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    other = repo.create_base(owner_user_id=owner_id, name="Other")
    folder = repo.ensure_folder(kb.id, "notes")
    assert repo.rename_document("missing-kb", folder.id, "x") is None
    assert repo.rename_document(other.id, folder.id, "x") is None
    assert repo.rename_document(kb.id, "missing-doc", "x") is None


def test_update_base_persists_max_documents(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    assert kb.max_documents == 100
    repo.update_base(kb.id, max_documents=42)
    refreshed = repo.get_base(kb.id)
    assert refreshed is not None
    assert refreshed.max_documents == 42
    repo.update_base(kb.id, description="unchanged")
    assert repo.get_base(kb.id).max_documents == 42  # type: ignore[union-attr]


def test_create_document_uses_kb_max_documents_for_limit(
    repo: KnowledgeRepo, owner_id: int
) -> None:
    # The repo enforces whatever max_documents the caller passes (the service
    # layer forwards kb.max_documents). A cap of 2 must reject the 3rd.
    kb = repo.create_base(owner_user_id=owner_id, name="Tiny", max_documents=2)
    assert kb.max_documents == 2
    for i in range(2):
        repo.create_document(
            kb_id=kb.id,
            filename=f"d{i}.md",
            content_type="text/markdown",
            byte_size=2,
            max_documents=kb.max_documents,
        )
    with pytest.raises(ValueError, match="at most 2 documents"):
        repo.create_document(
            kb_id=kb.id,
            filename="d2.md",
            content_type="text/markdown",
            byte_size=2,
            max_documents=kb.max_documents,
        )


def test_create_document_zero_max_means_unlimited(repo: KnowledgeRepo, owner_id: int) -> None:
    kb = repo.create_base(owner_user_id=owner_id, name="Unbounded", max_documents=0)
    assert kb.max_documents == 0
    for i in range(150):
        repo.create_document(
            kb_id=kb.id,
            filename=f"d{i:03}.md",
            content_type="text/markdown",
            byte_size=2,
            max_documents=kb.max_documents,
        )
    assert repo.get_base(kb.id).doc_count == 150  # type: ignore[union-attr]
