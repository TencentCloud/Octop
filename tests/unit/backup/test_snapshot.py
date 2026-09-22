"""Unit tests for SQLite snapshot helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from octop.infra.backup.snapshot import (
    capture_jwt_secret_from_pool,
    capture_users_from_pool,
    infer_owner_user_id,
    prune_users_not_in,
    remap_ownership_to_user,
    restore_jwt_secret_into_pool,
    snapshot_sqlite_file,
    upsert_users_into_pool,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool


@pytest.mark.skipif(os.name == "nt", reason="Windows disallows '?' in path names")
def test_snapshot_sqlite_file_with_special_chars_in_path(tmp_path: Path) -> None:
    """Paths containing URI metacharacters must not alter connect options."""
    tricky_dir = tmp_path / "dir?mode=memory"
    tricky_dir.mkdir()
    source = tricky_dir / "data.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('ok')")

    dest = tmp_path / "backup.db"
    snapshot_sqlite_file(source, dest)

    with sqlite3.connect(dest) as conn:
        row = conn.execute("SELECT v FROM t").fetchone()
    assert row is not None
    assert row[0] == "ok"


def test_jwt_secret_capture_and_restore(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    secret = b"session-jwt-secret-value-32bytes!!"

    assert capture_jwt_secret_from_pool(pool) is None

    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
            ("jwt", secret, 1),
        )
    assert capture_jwt_secret_from_pool(pool) == secret

    # Overwrite with a foreign secret, then restore the captured one.
    with pool.connect() as conn:
        conn.execute("UPDATE secrets SET v = ? WHERE k = ?", (b"foreign", "jwt"))
    restore_jwt_secret_into_pool(pool, secret)
    assert capture_jwt_secret_from_pool(pool) == secret

    # Insert path when the row is missing after a restore wipe.
    with pool.connect() as conn:
        conn.execute("DELETE FROM secrets WHERE k = ?", ("jwt",))
    restore_jwt_secret_into_pool(pool, secret)
    assert capture_jwt_secret_from_pool(pool) == secret
    pool.close()


def test_migration_remap_keeps_knowledge_bases_of_pruned_users(tmp_path: Path) -> None:
    """The archive's placeholder users must not take the imported corpus with them.

    ``knowledge_bases`` owns its rows through ``owner_user_id``, not ``user_id``,
    and ``knowledge_documents`` cascades off it — so a remap that only knows
    ``user_id`` columns leaves the base pointing at a user the restore then
    prunes, and ``ON DELETE CASCADE`` destroys the base and every document.
    """
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    now = 1_700_000_000
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(id, username, role, created_at) VALUES (1, 'admin', 'admin', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO users(id, username, role, created_at) VALUES (2, 'imported', 'user', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO agents(id, agent_id, name, user_id, created_at, updated_at) "
            "VALUES (1, 'ag1', 'imported-agent', 2, ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO knowledge_bases(id, knowledge_base_id, owner_user_id, name, "
            "max_documents, created_at, updated_at) VALUES (1, 'kb1', 2, 'runbook', 100, ?, ?)",
            (now, now),
        )
        for i in range(4):
            conn.execute(
                "INSERT INTO knowledge_documents(id, document_id, kb_id, path, filename, "
                "content_type, byte_size, created_at, updated_at) "
                "VALUES (?, ?, 'kb1', ?, ?, 'text/markdown', 12, ?, ?)",
                (i + 1, f"doc{i}", f"docs/{i}.md", f"{i}.md", now, now),
            )

    # ``restore_system_backup``'s migration tail: re-add the live instance's
    # users, move imported ownership onto the admin, then drop the leftovers.
    saved = [row for row in capture_users_from_pool(pool) if int(str(row[0])) == 1]
    upsert_users_into_pool(pool, saved)
    owner = infer_owner_user_id(saved)
    assert owner is not None
    remap_ownership_to_user(pool, int(owner))
    prune_users_not_in(pool, [row[0] for row in saved])

    with pool.connect() as conn:
        agent_owner = conn.execute("SELECT user_id FROM agents WHERE agent_id = 'ag1'").fetchone()
        base_owner = conn.execute(
            "SELECT owner_user_id FROM knowledge_bases WHERE knowledge_base_id = 'kb1'"
        ).fetchone()
        docs = conn.execute(
            "SELECT COUNT(*) FROM knowledge_documents WHERE kb_id = 'kb1'"
        ).fetchone()
    assert agent_owner is not None and int(agent_owner[0]) == 1
    assert base_owner is not None, "knowledge base cascaded away with the placeholder user"
    assert int(base_owner[0]) == 1
    assert int(docs[0]) == 4
    pool.close()
