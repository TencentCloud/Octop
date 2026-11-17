"""Skill-package files and knowledge vectors on a live PostgreSQL.

Uses ``OCTOP_TEST_DATABASE_URL``. Drops only ``public.knowledge_files``,
``public.knowledge_chunks``, and ``public.skill_package_files`` (plus the
legacy content schemas). Does not reset the rest of ``public``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.config import DatabaseConfig
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.skill_packages import SkillPackageRepo
from octop.infra.knowledge.blobs import KnowledgeBlobs
from octop.infra.knowledge.pg_index import PgVectorKnowledgeIndex
from octop.infra.skills.skill_package_store import SkillPackageStore
from tests.support.postgresql import requires_postgresql


def _database() -> DatabaseConfig:
    from octop.config import _parse_database_url

    parsed = _parse_database_url(os.environ["OCTOP_TEST_DATABASE_URL"])
    return DatabaseConfig(
        driver="postgresql",
        host=str(parsed["host"]),
        port=int(parsed["port"]),
        database=str(parsed["database"]),
        user=str(parsed.get("user") or "postgres"),
        password=parsed.get("password"),
        url=str(parsed["url"]),
    )


def _reset_content_schemas(database: DatabaseConfig) -> None:
    import psycopg

    with psycopg.connect(database.postgresql_conninfo()) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("DROP TABLE IF EXISTS public.knowledge_chunks")
        conn.execute("DROP TABLE IF EXISTS public.knowledge_files")
        conn.execute("DROP TABLE IF EXISTS public.skill_package_files")
        conn.execute("DROP SCHEMA IF EXISTS octop_skill_packages CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS octop_knowledge CASCADE")
        conn.commit()


@pytest.fixture
def database() -> DatabaseConfig:
    config = _database()
    _reset_content_schemas(config)
    yield config
    _reset_content_schemas(config)


def _store(tmp_path: Path, database: DatabaseConfig) -> SkillPackageStore:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return SkillPackageStore(
        repo=SkillPackageRepo(pool),
        root=tmp_path / "skill-packages",
        database=database,
    )


@requires_postgresql
@pytest.mark.postgresql
def test_legacy_content_tables_move_into_public(database: DatabaseConfig) -> None:
    """Older octop_* schemas are renamed onto the public knowledge_* tables."""
    import psycopg

    from octop.infra.db.file_store import adopt_legacy_content_tables

    with psycopg.connect(database.postgresql_conninfo()) as conn:
        conn.execute("CREATE SCHEMA octop_knowledge")
        conn.execute(
            """
            CREATE TABLE octop_knowledge.chunks (
                kb_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding vector NOT NULL,
                meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                PRIMARY KEY (kb_id, chunk_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO octop_knowledge.chunks
                (kb_id, chunk_id, doc_id, ordinal, text, embedding)
            VALUES ('kb', 'c1', 'd1', 0, 'hello', '[1,0]'::vector)
            """
        )
        conn.commit()

    adopt_legacy_content_tables(database)

    with psycopg.connect(database.postgresql_conninfo()) as conn:
        row = conn.execute("SELECT text FROM public.knowledge_chunks").fetchone()
        assert row is not None
        assert row[0] == "hello"
        assert conn.execute("SELECT to_regclass('octop_knowledge.chunks')").fetchone()[0] is None
        assert (
            conn.execute("SELECT to_regclass('public.knowledge_chunks_pkey')").fetchone()[0]
            is not None
        )
        assert conn.execute("SELECT to_regclass('public.chunks_pkey')").fetchone()[0] is None


@requires_postgresql
@pytest.mark.postgresql
def test_legacy_files_primary_keys_do_not_collide(database: DatabaseConfig) -> None:
    """Two legacy ``files`` tables must not both keep the ``files_pkey`` index."""
    import psycopg

    from octop.infra.db.file_store import adopt_legacy_content_tables

    with psycopg.connect(database.postgresql_conninfo()) as conn:
        conn.execute("CREATE SCHEMA octop_knowledge")
        conn.execute("CREATE SCHEMA octop_skill_packages")
        for schema in ("octop_knowledge", "octop_skill_packages"):
            conn.execute(
                f"""
                CREATE TABLE {schema}.files (
                    path TEXT PRIMARY KEY,
                    content JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.execute(
                f"CREATE INDEX idx_files_path_prefix ON {schema}.files (path text_pattern_ops)"
            )
        conn.execute(
            "INSERT INTO octop_knowledge.files (path, content) VALUES ('/kb/a', '{}'::jsonb)"
        )
        conn.execute(
            "INSERT INTO octop_skill_packages.files (path, content) VALUES ('/pkg/b', '{}'::jsonb)"
        )
        # Matches the failed in-place rename: the table moved, the index name did not.
        conn.execute("ALTER TABLE octop_knowledge.files SET SCHEMA public")
        conn.execute("ALTER TABLE public.files RENAME TO knowledge_files")
        conn.commit()

    adopt_legacy_content_tables(database)

    with psycopg.connect(database.postgresql_conninfo()) as conn:
        knowledge = conn.execute("SELECT path FROM public.knowledge_files").fetchone()
        skill = conn.execute("SELECT path FROM public.skill_package_files").fetchone()
        assert knowledge is not None and knowledge[0] == "/kb/a"
        assert skill is not None and skill[0] == "/pkg/b"
        assert conn.execute("SELECT to_regclass('public.files_pkey')").fetchone()[0] is None
        assert (
            conn.execute("SELECT to_regclass('public.idx_files_path_prefix')").fetchone()[0] is None
        )
        assert (
            conn.execute("SELECT to_regclass('public.knowledge_files_pkey')").fetchone()[0]
            is not None
        )
        assert (
            conn.execute("SELECT to_regclass('public.skill_package_files_pkey')").fetchone()[0]
            is not None
        )
        assert (
            conn.execute("SELECT to_regclass('octop_skill_packages.files')").fetchone()[0] is None
        )
        assert (
            conn.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = 'octop_skill_packages'"
            ).fetchone()
            is None
        )


@requires_postgresql
@pytest.mark.postgresql
def test_skill_package_files_roundtrip_through_postgres(
    tmp_path: Path, database: DatabaseConfig
) -> None:
    origin = _store(tmp_path / "a", database)
    row = origin.create(name="Pkg", description="", created_by="7")
    origin.write_skill(
        row.id,
        "pdf",
        [
            ("SKILL.md", b"---\nname: PDF\n---\nRead PDFs.\n"),
            ("assets/blob.bin", b"\xff\xfe raw"),
            ("notes/", b""),
        ],
    )

    other = _store(tmp_path / "b", database)
    assert other.read_skill_file_bytes(row.id, "pdf", "assets/blob.bin") == b"\xff\xfe raw"
    names = {entry["path"] for entry in other.list_skill_tree(row.id, "pdf")}
    assert "skills/pdf/notes" in names
    assert any(
        entry["is_dir"]
        for entry in other.list_skill_tree(row.id, "pdf")
        if entry["path"].endswith("notes")
    )

    origin.delete_skill(row.id, "pdf")
    assert other.list_skill_summaries(row.id) == []


@requires_postgresql
@pytest.mark.postgresql
def test_knowledge_bytes_and_pgvector_search(
    tmp_path: Path, database: DatabaseConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    blobs = KnowledgeBlobs(database)
    blobs.write("kb1", "doc1", "notes.md", b"# Honey\n")
    reloaded = KnowledgeBlobs(database)
    assert reloaded.read_bytes("kb1", "doc1", "notes.md") == b"# Honey\n"
    local = tmp_path / "knowledge" / "kb1" / "docs" / "doc1.md"
    local.unlink()
    restored = reloaded.ensure_local("kb1", "doc1", "notes.md")
    assert restored.read_bytes() == b"# Honey\n"

    index = PgVectorKnowledgeIndex("kb1", database)
    index.replace_doc_chunks(
        "doc1",
        ["honey bees", "unrelated tax policy"],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        metadata=[{"source": "a"}, {"source": "b"}],
    )
    hits = index.search([0.9, 0.1, 0.0], k=1)
    assert len(hits) == 1
    assert hits[0].text == "honey bees"
    assert hits[0].metadata == {"source": "a"}
    assert hits[0].score > 0.9

    index.delete_doc("doc1")
    assert index.search([1.0, 0.0, 0.0], k=3) == []
    reloaded.delete("kb1", "doc1", "notes.md")
    assert reloaded.exists("kb1", "doc1", "notes.md") is False
