"""Unit tests for system backup archives."""

from __future__ import annotations

import json
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from octop.config import DatabaseConfig
from octop.infra.backup.manifest import MANIFEST_VERSION, BackupManifest
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def layout(tmp_path: Path) -> PathLayout:
    root = tmp_path / ".octop"
    root.mkdir()
    return PathLayout(root)


def test_manifest_roundtrip_includes_driver_fields() -> None:
    m = BackupManifest(
        manifest_version=1,
        octop_version="0.0.0",
        schema_version=1,
        created_at="t",
        home="/tmp",
        db_file="db/octop.dump",
        database_driver="postgresql",
        database_dump_format="pg_custom",
    )
    loaded = BackupManifest.load_text(m.to_json())
    assert loaded.database_driver == "postgresql"
    assert loaded.database_dump_format == "pg_custom"
    assert loaded.db_file == "db/octop.dump"


def test_roundtrip_backup(layout: PathLayout, tmp_path: Path) -> None:
    db_path = layout.db
    pool = SqlitePool(db_path)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "hash", "admin", 1),
        )

    ws = layout.ensure_agent_workspace("agent01")
    (ws / "SOUL.md").write_text("# soul", encoding="utf-8")
    pkg_skill = layout.skill_packages_dir / "pkg01" / "skills" / "writer" / "SKILL.md"
    pkg_skill.parent.mkdir(parents=True, exist_ok=True)
    pkg_skill.write_text("---\nname: writer\ndescription: x\n---\n", encoding="utf-8")
    layout.config.write_text('{"port": 8088}', encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"

    archive = tmp_path / "roundtrip.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    pool.close()

    restore_root = layout.root.parent / "restored"
    restore_layout = PathLayout(restore_root)
    restore_db = restore_layout.db
    restore_pool = SqlitePool(restore_db)
    run_migrations(restore_pool)

    result = restore_system_backup(
        archive,
        paths=restore_layout,
        pool=restore_pool,
        db_config=DatabaseConfig(),
        restore_config=True,
    )
    restore_pool.close()

    assert result["agents"] == 1
    assert result["skill_package_files"] == 1
    assert (restore_layout.agent_workspace("agent01") / "SOUL.md").read_text(
        encoding="utf-8"
    ) == "# soul"
    assert (
        (restore_layout.skill_packages_dir / "pkg01" / "skills" / "writer" / "SKILL.md")
        .read_text(encoding="utf-8")
        .startswith("---")
    )
    assert json.loads(restore_layout.config.read_text(encoding="utf-8"))["port"] == 8088

    with tarfile.open(archive, mode="r:gz") as tf:
        manifest = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["database_driver"] == "sqlite"


def test_backup_packs_config_workspace_dir(layout: PathLayout, tmp_path: Path) -> None:
    db_path = layout.db
    pool = SqlitePool(db_path)
    run_migrations(pool)
    custom = tmp_path / "custom-ws"
    custom.mkdir()
    (custom / "SOUL.md").write_text("# custom", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"
        config_json = json.dumps({"workspace_dir": str(custom)})

    archive = tmp_path / "custom-ws-backup.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    pool.close()

    with tarfile.open(archive, mode="r:gz") as tf:
        names = tf.getnames()
    assert "workspaces/agent01/SOUL.md" in names
    assert not (layout.agent_workspace("agent01") / "SOUL.md").exists()


def test_backup_skips_junk_directories(layout: PathLayout, tmp_path: Path) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    ws = layout.ensure_agent_workspace("agent01")
    (ws / "keep.txt").write_text("ok", encoding="utf-8")
    (ws / "node_modules").mkdir()
    (ws / "node_modules" / "pkg.js").write_text("skip", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("skip", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"

    archive = tmp_path / "skip-junk.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    pool.close()

    with tarfile.open(archive, mode="r:gz") as tf:
        names = set(tf.getnames())
    assert "workspaces/agent01/keep.txt" in names
    assert "workspaces/agent01/node_modules/pkg.js" not in names
    assert "workspaces/agent01/.git/config" not in names


def test_restore_replaces_stale_skill_package_files(layout: PathLayout, tmp_path: Path) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "hash", "admin", 1),
        )

    kept = layout.skill_packages_dir / "kept" / "skills" / "a" / "SKILL.md"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text("---\nname: a\ndescription: keep\n---\n", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"

    archive = tmp_path / "packages.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    pool.close()

    restore_layout = PathLayout(layout.root.parent / "restored-packages")
    restore_pool = SqlitePool(restore_layout.db)
    run_migrations(restore_pool)
    stale = restore_layout.skill_packages_dir / "stale" / "skills" / "old" / "SKILL.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("---\nname: old\ndescription: stale\n---\n", encoding="utf-8")

    restore_system_backup(
        archive,
        paths=restore_layout,
        pool=restore_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    restore_pool.close()

    assert (restore_layout.skill_packages_dir / "kept" / "skills" / "a" / "SKILL.md").is_file()
    assert not (restore_layout.skill_packages_dir / "stale").exists()


def _make_migration_backup(
    layout: PathLayout,
    dest: Path,
    *,
    username: str = "lc_user",
    jwt_secret: bytes | None = b"foreign-jwt-from-migration-backup!!!!",
) -> SqlitePool:
    """Build a fake LightClaw migration backup at *dest*; return source_pool."""
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, "lc_hash", "user", 1),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()[0]
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)"
            " VALUES (?, ?, ?, 1, 1)",
            ("agent-lc", uid, "LC Agent"),
        )
        conn.execute(
            "INSERT INTO channels(channel_id, agent_id, user_id, kind, name, config_json,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, 1)",
            ("migrated-feishu", "agent-lc", uid, "feishu", "feishu", "{}"),
        )
        session_key = f"agent-lc:dashboard:{uid}:dm"
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key,"
            " title, pinned, last_active, created_at)"
            " VALUES (?, ?, ?, 'dashboard', ?, NULL, 0, 1, 1)",
            ("thr-lc", "agent-lc", uid, session_key),
        )
        conn.execute(
            "INSERT INTO sessions(session_key, agent_id, user_id, channel_type, chat_type,"
            " thread_id, updated_at, channel_subject_id, channel_chat_type,"
            " channel_metadata, unread_count)"
            " VALUES (?, ?, ?, 'dashboard', 'dm', ?, 1, ?, 'dm', ?, 0)",
            (
                session_key,
                "agent-lc",
                uid,
                "thr-lc",
                str(uid),
                json.dumps({"channel_type": "dashboard", "user_id": uid, "to_handle": str(uid)}),
            ),
        )
        conn.execute(
            "INSERT INTO cron_jobs(cron_id, agent_id, user_id, schedule_spec, prompt,"
            " session_key, enabled, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 1, 1, 1)",
            ("cron-lc", "agent-lc", uid, "0 * * * *", "ping", session_key),
        )
        if jwt_secret is not None:
            conn.execute(
                "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
                ("jwt", jwt_secret, 1),
            )

    class Row:
        agent_id = "agent-lc"
        name = "LC Agent"

    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=dest,
    )
    # Rewrite octop_version to signal a LightClaw migration backup.
    members: dict[str, bytes] = {}
    with tarfile.open(dest, mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                assert f is not None
                members[m.name] = f.read()
    manifest_obj = json.loads(members["manifest.json"])
    manifest_obj["octop_version"] = manifest_obj["octop_version"] + "-migrated-from-lightclaw"
    members["manifest.json"] = json.dumps(manifest_obj).encode()
    with tarfile.open(dest, mode="w:gz") as tf:
        for name, blob in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            tf.addfile(info, BytesIO(blob))
    return pool


def test_migration_restore_preserves_current_users_and_imported_agents(
    tmp_path: Path,
) -> None:
    """Restoring a LightClaw backup writes back current users without CASCADE-deleting agents.

    Regression guard: with ``PRAGMA foreign_keys = ON`` a bare
    ``DELETE FROM users`` cascades to agents, sessions, threads, … and wipes
    the data that was just restored from the backup.  The upsert+prune strategy
    must not trigger that cascade.

    After restore the expected state is:
    - agents from the backup (``agent-lc``) are present.
    - users table contains only the *current instance* users (``octop_admin``).
    - the LightClaw user (``lc_user``) is gone — replaced by the current users.
    - JWT secret from the *current* instance is kept (session continuity).
    """
    # --- source: simulate a LightClaw migration export with one agent ---
    src_layout = PathLayout(tmp_path / "src")
    src_layout.root.mkdir()
    migration_archive = tmp_path / "migration.tar.gz"
    src_pool = _make_migration_backup(src_layout, migration_archive, username="lc_user")
    src_pool.close()

    # --- target: a fresh Octop instance with its own admin user + JWT ---
    tgt_layout = PathLayout(tmp_path / "tgt")
    tgt_layout.root.mkdir()
    tgt_pool = SqlitePool(tgt_layout.db)
    run_migrations(tgt_pool)
    local_jwt = b"local-octop-jwt-secret-must-survive-restore!!"
    with tgt_pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("octop_admin", "admin_hash", "admin", 2),
        )
        conn.execute(
            "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
            ("jwt", local_jwt, 2),
        )

    result = restore_system_backup(
        migration_archive,
        paths=tgt_layout,
        pool=tgt_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )

    assert result["users_preserved"] is True
    assert result["jwt_preserved"] is True

    with tgt_pool.connect() as conn:
        # The target instance's admin must survive with original password hash.
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("octop_admin",)
        ).fetchone()
        assert row is not None, "octop_admin was deleted — users not preserved"
        assert row[0] == "admin_hash"

        # JWT secret from the current instance must survive (not the foreign backup's).
        jwt_row = conn.execute("SELECT v FROM secrets WHERE k = ?", ("jwt",)).fetchone()
        assert jwt_row is not None, "jwt secret missing after migration restore"
        assert bytes(jwt_row[0]) == local_jwt, "jwt secret replaced by migration backup value"

        # The imported agent from the backup must still exist after users write-back.
        # With the old DELETE-then-INSERT, foreign_keys=ON would cascade-delete this row.
        agent_row = conn.execute(
            "SELECT agent_id, user_id FROM agents WHERE agent_id = ?", ("agent-lc",)
        ).fetchone()
        assert agent_row is not None, (
            "agent-lc was deleted — upsert strategy triggered CASCADE on agents"
        )
        admin_id = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("octop_admin",)
        ).fetchone()[0]
        assert agent_row[1] == admin_id

        # The LightClaw source user must not appear in the target users table.
        lc_row = conn.execute("SELECT id FROM users WHERE username = ?", ("lc_user",)).fetchone()
        assert lc_row is None, "lc_user from backup was not removed after user write-back"

    tgt_pool.close()


def test_migration_restore_remaps_ownership_to_admin_user_id_2(tmp_path: Path) -> None:
    """Migration import assigns agents/channels/cron to the restoring admin (id=2)."""
    src_layout = PathLayout(tmp_path / "src")
    src_layout.root.mkdir()
    migration_archive = tmp_path / "migration-remap.tar.gz"
    src_pool = _make_migration_backup(src_layout, migration_archive, username="lc_user")
    src_pool.close()

    tgt_layout = PathLayout(tmp_path / "tgt")
    tgt_layout.root.mkdir()
    tgt_pool = SqlitePool(tgt_layout.db)
    run_migrations(tgt_pool)
    with tgt_pool.connect() as conn:
        # Leave id=1 unused so the restoring admin is id=2 (the reported bug case).
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at)"
            " VALUES (2, ?, ?, ?, ?)",
            ("octop_admin", "admin_hash", "admin", 2),
        )

    result = restore_system_backup(
        migration_archive,
        paths=tgt_layout,
        pool=tgt_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
        owner_user_id=2,
    )
    assert result["users_preserved"] is True
    assert result["owner_user_id"] == 2
    assert result["ownership_remap"]["old_user_ids"] >= 1

    with tgt_pool.connect() as conn:
        users = conn.execute("SELECT id, username FROM users ORDER BY id").fetchall()
        assert [(r[0], r[1]) for r in users] == [(2, "octop_admin")]

        agent = conn.execute(
            "SELECT user_id FROM agents WHERE agent_id = ?", ("agent-lc",)
        ).fetchone()
        assert agent is not None
        assert agent[0] == 2

        channel = conn.execute(
            "SELECT user_id FROM channels WHERE channel_id = ?", ("migrated-feishu",)
        ).fetchone()
        assert channel is not None
        assert channel[0] == 2

        cron = conn.execute(
            "SELECT user_id, session_key FROM cron_jobs WHERE cron_id = ?", ("cron-lc",)
        ).fetchone()
        assert cron is not None
        assert cron[0] == 2
        assert cron[1] == "agent-lc:dashboard:2:dm"

        session = conn.execute(
            "SELECT user_id, channel_subject_id, channel_metadata FROM sessions"
            " WHERE session_key = ?",
            ("agent-lc:dashboard:2:dm",),
        ).fetchone()
        assert session is not None
        assert session[0] == 2
        assert session[1] == "2"
        meta = json.loads(session[2])
        assert meta["user_id"] == 2
        assert meta["to_handle"] == "2"

        stale = conn.execute(
            "SELECT 1 FROM sessions WHERE session_key = ?",
            ("agent-lc:dashboard:1:dm",),
        ).fetchone()
        assert stale is None

    tgt_pool.close()


def test_migration_restore_via_none_autodetect(tmp_path: Path) -> None:
    """preserve_users=None auto-detects the migration flag from octop_version."""
    src_layout = PathLayout(tmp_path / "src")
    src_layout.root.mkdir()
    migration_archive = tmp_path / "migration-auto.tar.gz"
    src_pool = _make_migration_backup(src_layout, migration_archive, username="lc_auto")
    src_pool.close()

    tgt_layout = PathLayout(tmp_path / "tgt")
    tgt_layout.root.mkdir()
    tgt_pool = SqlitePool(tgt_layout.db)
    run_migrations(tgt_pool)
    with tgt_pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("local_admin", "lhash", "admin", 3),
        )

    # preserve_users=None — should auto-detect and preserve
    result = restore_system_backup(
        migration_archive,
        paths=tgt_layout,
        pool=tgt_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
        preserve_users=None,
    )
    assert result["users_preserved"] is True

    with tgt_pool.connect() as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE username = ?", ("local_admin",)
        ).fetchone()
        assert row is not None, "local_admin was lost after auto-detect migration restore"

    tgt_pool.close()


def test_refuse_cross_engine_restore(layout: PathLayout, tmp_path: Path) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)

    class Row:
        agent_id = "a1"
        name = "n"

    archive = tmp_path / "cross-engine.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    # Rewrite manifest to pretend it's a postgres dump.
    members: dict[str, bytes] = {}
    with tarfile.open(archive, mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                assert f is not None
                members[m.name] = f.read()
    manifest = json.loads(members["manifest.json"])
    manifest["database_driver"] = "postgresql"
    members["manifest.json"] = json.dumps(manifest).encode()
    with tarfile.open(archive, mode="w:gz") as tf:
        for name, blob in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            tf.addfile(info, BytesIO(blob))
    with pytest.raises(OctopError) as excinfo:
        restore_system_backup(
            archive,
            paths=layout,
            pool=pool,
            db_config=DatabaseConfig(),
        )
    assert excinfo.value.code == ErrorCode.BACKUP_DRIVER_MISMATCH
    pool.close()
