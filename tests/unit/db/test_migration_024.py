"""Migration 024: ``project_comments.mentions``.

The dashboard submits structured mentions and the server stores them verbatim
(design P1 = (c)), so this is a plain nullable TEXT column — no parsing, no
server-side derivation. Additive DDL only, no ``migrate.py`` helper.
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


def test_head_is_24(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert _version(pool) == 24


def test_mentions_exists_and_is_nullable(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    assert "mentions" in _columns(pool, "project_comments")
    with pool.connect() as conn:
        info = {str(r["name"]): r for r in conn.execute("PRAGMA table_info(project_comments)")}
    assert info["mentions"]["notnull"] == 0, "a comment need not mention anybody"
    assert (info["mentions"]["type"] or "").upper() == "TEXT"


def test_rerunning_migrations_is_idempotent(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    before = _columns(pool, "project_comments")
    run_migrations(pool)
    assert _version(pool) == 24
    assert _columns(pool, "project_comments") == before


def test_the_pair_is_self_contained_on_both_dialects() -> None:
    sqlite_sql = Path("src/octop/infra/db/migrations/024_comment_mentions.sql").read_text(
        encoding="utf-8"
    )
    pg_sql = Path("src/octop/infra/db/migrations/024_comment_mentions.pg.sql").read_text(
        encoding="utf-8"
    )
    assert "ALTER TABLE project_comments ADD COLUMN mentions TEXT;" in sqlite_sql
    assert "ALTER TABLE project_comments ADD COLUMN IF NOT EXISTS mentions TEXT;" in pg_sql, (
        "the PG twin must guard the column"
    )
    for text in (sqlite_sql, pg_sql):
        assert "UPDATE _schema_version SET version = 24;" in text
    for statement in pg_sql.split(";\n"):
        body = "\n".join(
            line for line in statement.splitlines() if not line.strip().startswith("--")
        ).strip()
        if body:
            assert body.upper().startswith(("ALTER TABLE", "UPDATE")), body


def test_no_migrate_helper_was_added() -> None:
    migrate = Path("src/octop/infra/db/migrate.py").read_text(encoding="utf-8")
    assert "mentions" not in migrate, "024 must slot into the generic SQL path"
