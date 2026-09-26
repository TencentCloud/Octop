"""Folded v17 migration: databases already at v17 still gain hitl_pending_records.

The HITL pending DDL lives inside the unreleased ``017`` pair. A database that
recorded v17 before the fold skips that file, so ``run_migrations`` must create
the table through the idempotent ensure helper without advancing the watermark.
"""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool


def _schema_version(db: SqlitePool) -> int:
    with db.connect() as conn:
        return int(conn.execute("SELECT version FROM _schema_version").fetchone()[0])


def test_prefold_v17_database_gains_hitl_table_without_version_bump(
    tmp_path: Path,
) -> None:
    db = SqlitePool(tmp_path / "prefold.db")
    run_migrations(db)

    # Recreate a pre-fold v17 database: watermark at 17, table absent.
    with db.connect() as conn:
        conn.execute("DROP TABLE hitl_pending_records")
    assert _schema_version(db) == 17

    run_migrations(db)

    with db.connect() as conn:
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(hitl_pending_records)").fetchall()
        }
        indexes = {
            str(row["name"])
            for row in conn.execute("PRAGMA index_list(hitl_pending_records)").fetchall()
        }
    assert {
        "pending_id",
        "thread_id",
        "session_key",
        "status",
        "ask_question_index",
        "ask_answers",
    }.issubset(columns)
    assert {
        "idx_hitl_pending_records_session",
        "idx_hitl_pending_records_thread",
    }.issubset(indexes)
    assert _schema_version(db) == 17
