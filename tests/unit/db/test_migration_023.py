"""Migration 023: ``project_artifacts.comment_id``.

A comment can own attachments; the column is nullable so every existing project
file keeps meaning "not attached to a comment". Additive DDL only — no rebuild, no
``migrate.py`` helper (the 022 precedent).
"""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool


def _version(pool: SqlitePool) -> int:
    with pool.connect() as conn:
        return int(conn.execute("SELECT version FROM _schema_version").fetchone()["version"])


def _columns(pool: SqlitePool, table: str) -> set[str]:
    with pool.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def test_head_is_23(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert _version(pool) == 23


def test_comment_id_exists_and_is_nullable(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert "comment_id" in _columns(pool, "project_artifacts")
    with pool.connect() as conn:
        info = {str(r["name"]): r for r in conn.execute("PRAGMA table_info(project_artifacts)")}
    assert info["comment_id"]["notnull"] == 0, "a file need not belong to a comment"
    assert (info["comment_id"]["type"] or "").upper() == "TEXT"


def test_rerunning_migrations_is_idempotent(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    before = _columns(pool, "project_artifacts")
    run_migrations(pool)
    assert _version(pool) == 23
    assert _columns(pool, "project_artifacts") == before


def test_the_pair_is_self_contained_on_both_dialects() -> None:
    sqlite_sql = Path(
        "src/octop/infra/db/migrations/023_comment_edit_delete_attachments.sql"
    ).read_text(encoding="utf-8")
    pg_sql = Path(
        "src/octop/infra/db/migrations/023_comment_edit_delete_attachments.pg.sql"
    ).read_text(encoding="utf-8")
    assert "ALTER TABLE project_artifacts ADD COLUMN comment_id TEXT;" in sqlite_sql
    assert "ALTER TABLE project_artifacts ADD COLUMN IF NOT EXISTS comment_id TEXT;" in pg_sql, (
        "the PG twin must guard the column"
    )
    for text in (sqlite_sql, pg_sql):
        assert "UPDATE _schema_version SET version = 23;" in text
    for statement in pg_sql.split(";\n"):
        body = "\n".join(
            line for line in statement.splitlines() if not line.strip().startswith("--")
        ).strip()
        if body:
            assert body.upper().startswith(("ALTER TABLE", "UPDATE")), body


def test_no_migrate_helper_was_added() -> None:
    migrate = Path("src/octop/infra/db/migrate.py").read_text(encoding="utf-8")
    assert "comment_id" not in migrate, "023 must slot into the generic SQL path"
