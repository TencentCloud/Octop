"""Unit tests for system backup archives."""

from __future__ import annotations

import json
import sqlite3
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


def test_legacy_manifest_defaults_plugins_omitted() -> None:
    loaded = BackupManifest.from_dict(
        {
            "manifest_version": 1,
            "octop_version": "0.0.0",
            "schema_version": 1,
            "created_at": "t",
            "home": "/tmp",
        }
    )
    assert loaded.includes_skill_packages is True
    assert loaded.includes_plugins is False
    assert loaded.includes_knowledge is False
    assert loaded.includes_chats is True


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
    plugin_yaml = layout.plugins_dir / "weather" / "plugin.yaml"
    plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
    plugin_yaml.write_text("id: weather\n", encoding="utf-8")
    kb_doc = layout.knowledge_dir / "kb01" / "docs" / "doc1.md"
    kb_doc.parent.mkdir(parents=True, exist_ok=True)
    kb_doc.write_text("# note", encoding="utf-8")
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
    assert result["plugin_files"] == 1
    assert result["knowledge_files"] == 1
    assert (restore_layout.agent_workspace("agent01") / "SOUL.md").read_text(
        encoding="utf-8"
    ) == "# soul"
    assert (
        (restore_layout.skill_packages_dir / "pkg01" / "skills" / "writer" / "SKILL.md")
        .read_text(encoding="utf-8")
        .startswith("---")
    )
    assert (restore_layout.plugins_dir / "weather" / "plugin.yaml").read_text(
        encoding="utf-8"
    ) == "id: weather\n"
    assert (restore_layout.knowledge_dir / "kb01" / "docs" / "doc1.md").read_text(
        encoding="utf-8"
    ) == "# note"
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


def test_default_backup_omits_chats_and_restore_preserves_current_chats(
    tmp_path: Path,
) -> None:
    source_layout = PathLayout(tmp_path / "source")
    source_layout.root.mkdir()
    source_pool = SqlitePool(source_layout.db)
    run_migrations(source_pool)
    with source_pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at)"
            " VALUES (1, 'alice', 'hash', 'admin', 1)"
        )
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)"
            " VALUES ('agent01', 1, 'Agent', 1, 1)"
        )

    source_ws = source_layout.ensure_agent_workspace("agent01")
    (source_ws / "SOUL.md").write_text("# source", encoding="utf-8")
    source_sessions = source_ws / ".octop" / "sessions"
    source_sessions.mkdir(parents=True)
    (source_sessions / "large.jsonl").write_text("chat", encoding="utf-8")
    (source_ws / ".octop" / "checkpoints.sqlite").write_bytes(b"chat-db")
    user_sessions = source_ws / "project" / "sessions"
    user_sessions.mkdir(parents=True)
    (user_sessions / "notes.txt").write_text("keep", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Agent"
        config_json = '{"system_files_path": ".octop"}'

    archive = tmp_path / "without-chats.tar.gz"
    create_system_backup(
        paths=source_layout,
        agent_rows=[Row()],
        pool=source_pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    source_pool.close()

    with tarfile.open(archive, mode="r:gz") as tf:
        names = set(tf.getnames())
        manifest = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
    assert manifest["includes_chats"] is False
    assert "workspaces/agent01/SOUL.md" in names
    assert "workspaces/agent01/project/sessions/notes.txt" in names
    assert "workspaces/agent01/.octop/sessions/large.jsonl" not in names
    assert "workspaces/agent01/.octop/checkpoints.sqlite" not in names

    target_layout = PathLayout(tmp_path / "target")
    target_layout.root.mkdir()
    target_pool = SqlitePool(target_layout.db)
    run_migrations(target_pool)
    with target_pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at)"
            " VALUES (1, 'alice', 'old-hash', 'admin', 1)"
        )
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)"
            " VALUES ('agent01', 1, 'Old Agent', 1, 1)"
        )
        conn.execute(
            "INSERT INTO sessions(session_key, agent_id, user_id, channel_type, chat_type,"
            " thread_id, updated_at) VALUES ('session-1', 'agent01', 1, 'dashboard',"
            " 'dm', 'thread-1', 1)"
        )
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key,"
            " last_active, created_at) VALUES ('thread-1', 'agent01', 1, 'dashboard',"
            " 'session-1', 1, 1)"
        )
        conn.execute(
            "INSERT INTO thread_messages(thread_id, seq, role, message_json, created_at)"
            " VALUES ('thread-1', 1, 'user', '{\"content\":\"keep\"}', 1)"
        )

    target_sessions = target_layout.ensure_agent_workspace("agent01") / ".octop" / "sessions"
    target_sessions.mkdir(parents=True)
    current_log = target_sessions / "current.jsonl"
    current_log.write_text("keep", encoding="utf-8")

    result = restore_system_backup(
        archive,
        paths=target_layout,
        pool=target_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    assert result["chats_restored"] is False
    assert result["preserved_chat_rows"] >= 3
    with target_pool.connect() as conn:
        message = conn.execute(
            "SELECT message_json FROM thread_messages WHERE thread_id = 'thread-1'"
        ).fetchone()
    target_pool.close()
    assert message is not None
    assert json.loads(message[0])["content"] == "keep"
    assert current_log.read_text(encoding="utf-8") == "keep"


def test_restore_without_chats_remaps_user_ids_by_username(tmp_path: Path) -> None:
    source_layout = PathLayout(tmp_path / "source")
    source_layout.root.mkdir()
    source_pool = SqlitePool(source_layout.db)
    run_migrations(source_pool)
    with source_pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at)"
            " VALUES (1, 'alice', 'hash', 'admin', 1)"
        )
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)"
            " VALUES ('agent01', 1, 'Agent', 1, 1)"
        )

    class Row:
        agent_id = "agent01"
        name = "Agent"

    archive = tmp_path / "remap.tar.gz"
    create_system_backup(
        paths=source_layout,
        agent_rows=[Row()],
        pool=source_pool,
        db_config=DatabaseConfig(),
        dest=archive,
    )
    source_pool.close()

    target_layout = PathLayout(tmp_path / "target")
    target_layout.root.mkdir()
    target_pool = SqlitePool(target_layout.db)
    run_migrations(target_pool)
    with target_pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at)"
            " VALUES (2, 'alice', 'live-hash', 'admin', 1)"
        )
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)"
            " VALUES ('agent01', 2, 'Live Agent', 1, 1)"
        )
        conn.execute(
            "INSERT INTO sessions(session_key, agent_id, user_id, channel_type, chat_type,"
            " thread_id, updated_at, channel_subject_id) VALUES ("
            " 'agent01:dashboard:2:dm', 'agent01', 2, 'dashboard', 'dm', 'thread-1', 1, '2')"
        )
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key,"
            " last_active, created_at) VALUES ('thread-1', 'agent01', 2, 'dashboard',"
            " 'agent01:dashboard:2:dm', 1, 1)"
        )

    result = restore_system_backup(
        archive,
        paths=target_layout,
        pool=target_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    assert result["skipped_chat_rows"] == 0
    with target_pool.connect() as conn:
        session = conn.execute(
            "SELECT user_id, session_key, channel_subject_id FROM sessions"
        ).fetchone()
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key,"
            " last_active, created_at) VALUES ('thread-new', 'agent01', 1, 'dashboard',"
            " 'x', 1, 1)"
        )
        new_pk = conn.execute("SELECT id FROM threads WHERE thread_id = 'thread-new'").fetchone()
        preserved_pk = conn.execute(
            "SELECT id FROM threads WHERE thread_id = 'thread-1'"
        ).fetchone()
    target_pool.close()
    assert session is not None
    assert session[0] == 1
    assert session[1] == "agent01:dashboard:1:dm"
    assert session[2] == "1"
    assert preserved_pk is not None
    assert new_pk is not None
    assert int(new_pk[0]) > int(preserved_pk[0])


def test_restore_skips_chat_workspace_files_when_manifest_omits_chats(
    tmp_path: Path,
) -> None:
    layout = PathLayout(tmp_path / "src")
    layout.root.mkdir()
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "hash", "admin", 1),
        )

    class Row:
        agent_id = "agent01"
        name = "Agent"
        config_json = '{"system_files_path": ".octop"}'

    archive = tmp_path / "inject-chats.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_workspaces=True,
        include_chats=False,
    )
    pool.close()

    members: dict[str, bytes] = {}
    with tarfile.open(archive, mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                assert f is not None
                members[m.name] = f.read()
    members["workspaces/agent01/.octop/sessions/injected.jsonl"] = b"overwrite-me"
    with tarfile.open(archive, mode="w:gz") as tf:
        for name, blob in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            tf.addfile(info, BytesIO(blob))

    target = PathLayout(tmp_path / "tgt")
    target.root.mkdir()
    target_pool = SqlitePool(target.db)
    run_migrations(target_pool)
    keep = target.ensure_agent_workspace("agent01") / ".octop" / "sessions" / "current.jsonl"
    keep.parent.mkdir(parents=True)
    keep.write_text("keep", encoding="utf-8")
    restore_system_backup(
        archive,
        paths=target,
        pool=target_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    target_pool.close()
    assert keep.read_text(encoding="utf-8") == "keep"
    assert not (
        target.ensure_agent_workspace("agent01") / ".octop" / "sessions" / "injected.jsonl"
    ).exists()


def test_sqlite_strip_chats_reclaims_pages(tmp_path: Path) -> None:
    from octop.infra.backup.chats import strip_chat_tables_from_sqlite_file
    from octop.infra.backup.snapshot import snapshot_sqlite_file

    layout = PathLayout(tmp_path / "home")
    layout.root.mkdir()
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at)"
            " VALUES (1, 'alice', 'hash', 'admin', 1)"
        )
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at)"
            " VALUES ('agent01', 1, 'Agent', 1, 1)"
        )
        conn.execute(
            "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, session_key,"
            " last_active, created_at) VALUES ('t1', 'agent01', 1, 'dashboard', 's', 1, 1)"
        )
        payload = "x" * 2048
        for seq in range(400):
            conn.execute(
                "INSERT INTO thread_messages(thread_id, seq, role, message_json, created_at)"
                " VALUES ('t1', ?, 'user', ?, 1)",
                (seq, json.dumps({"content": payload})),
            )
    snap = tmp_path / "snap.db"
    snapshot_sqlite_file(pool.path, snap)
    pool.close()
    before = snap.stat().st_size
    strip_chat_tables_from_sqlite_file(snap)
    after = snap.stat().st_size
    assert after < before
    conn = sqlite3.connect(snap)
    count = conn.execute("SELECT COUNT(*) FROM thread_messages").fetchone()[0]
    conn.close()
    assert count == 0


def test_backup_can_omit_config_and_workspaces(layout: PathLayout, tmp_path: Path) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    layout.config.write_text('{"port": 8088}', encoding="utf-8")
    workspace = layout.ensure_agent_workspace("agent01")
    (workspace / "SOUL.md").write_text("# soul", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Agent"

    archive = tmp_path / "database-only.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_config=False,
        include_workspaces=False,
        include_skill_packages=False,
        include_plugins=False,
        include_knowledge=False,
    )
    pool.close()

    with tarfile.open(archive, mode="r:gz") as tf:
        names = set(tf.getnames())
        manifest = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
    assert manifest["includes_config"] is False
    assert manifest["includes_skill_packages"] is False
    assert manifest["includes_plugins"] is False
    assert manifest["includes_knowledge"] is False
    assert manifest["agents"][0]["workspace_included"] is False
    assert "config/config.json" not in names
    assert "workspaces/agent01/SOUL.md" not in names


def test_backup_can_include_skill_packages_and_plugins_without_workspaces(
    layout: PathLayout, tmp_path: Path
) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    workspace = layout.ensure_agent_workspace("agent01")
    (workspace / "SOUL.md").write_text("# soul", encoding="utf-8")
    pkg = layout.skill_packages_dir / "pkg01" / "skills" / "a" / "SKILL.md"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    pkg.write_text("---\nname: a\ndescription: x\n---\n", encoding="utf-8")
    plugin = layout.plugins_dir / "weather" / "plugin.yaml"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.write_text("id: weather\n", encoding="utf-8")
    kb_doc = layout.knowledge_dir / "kb01" / "docs" / "doc1.md"
    kb_doc.parent.mkdir(parents=True, exist_ok=True)
    kb_doc.write_text("# note", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Agent"

    archive = tmp_path / "dirs-only.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_config=False,
        include_workspaces=False,
        include_skill_packages=True,
        include_plugins=True,
        include_knowledge=True,
    )
    pool.close()

    with tarfile.open(archive, mode="r:gz") as tf:
        names = set(tf.getnames())
        manifest = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
    assert manifest["includes_skill_packages"] is True
    assert manifest["includes_plugins"] is True
    assert manifest["includes_knowledge"] is True
    assert manifest["agents"][0]["workspace_included"] is False
    assert "workspaces/agent01/SOUL.md" not in names
    assert "skill-packages/pkg01/skills/a/SKILL.md" in names
    assert "plugins/weather/plugin.yaml" in names
    assert "knowledge/kb01/docs/doc1.md" in names


def test_restore_without_skill_packages_keeps_live_files(
    layout: PathLayout, tmp_path: Path
) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "hash", "admin", 1),
        )

    class Row:
        agent_id = "agent01"
        name = "Test"

    archive = tmp_path / "no-packages.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_skill_packages=False,
        include_plugins=False,
        include_knowledge=False,
    )
    pool.close()

    restore_layout = PathLayout(layout.root.parent / "restored-keep-dirs")
    restore_pool = SqlitePool(restore_layout.db)
    run_migrations(restore_pool)
    kept_pkg = restore_layout.skill_packages_dir / "kept" / "skills" / "a" / "SKILL.md"
    kept_pkg.parent.mkdir(parents=True, exist_ok=True)
    kept_pkg.write_text("keep-pkg", encoding="utf-8")
    kept_plugin = restore_layout.plugins_dir / "local" / "plugin.yaml"
    kept_plugin.parent.mkdir(parents=True, exist_ok=True)
    kept_plugin.write_text("id: local\n", encoding="utf-8")
    kept_kb = restore_layout.knowledge_dir / "kb01" / "docs" / "keep.md"
    kept_kb.parent.mkdir(parents=True, exist_ok=True)
    kept_kb.write_text("keep-kb", encoding="utf-8")

    restore_system_backup(
        archive,
        paths=restore_layout,
        pool=restore_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    restore_pool.close()

    assert kept_pkg.read_text(encoding="utf-8") == "keep-pkg"
    assert kept_plugin.read_text(encoding="utf-8") == "id: local\n"
    assert kept_kb.read_text(encoding="utf-8") == "keep-kb"


def test_restore_replaces_stale_plugin_files(layout: PathLayout, tmp_path: Path) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "hash", "admin", 1),
        )

    kept = layout.plugins_dir / "weather" / "plugin.yaml"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text("id: weather\n", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"

    archive = tmp_path / "plugins.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_workspaces=False,
        include_skill_packages=False,
        include_plugins=True,
        include_knowledge=False,
    )
    pool.close()

    restore_layout = PathLayout(layout.root.parent / "restored-plugins")
    restore_pool = SqlitePool(restore_layout.db)
    run_migrations(restore_pool)
    stale = restore_layout.plugins_dir / "stale" / "plugin.yaml"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("id: stale\n", encoding="utf-8")

    restore_system_backup(
        archive,
        paths=restore_layout,
        pool=restore_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    restore_pool.close()

    assert (restore_layout.plugins_dir / "weather" / "plugin.yaml").is_file()
    assert not (restore_layout.plugins_dir / "stale").exists()


def test_restore_replaces_stale_knowledge_files(layout: PathLayout, tmp_path: Path) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)
    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("alice", "hash", "admin", 1),
        )

    kept = layout.knowledge_dir / "kb01" / "docs" / "a.md"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text("# keep", encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"

    archive = tmp_path / "knowledge.tar.gz"
    create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
        dest=archive,
        include_workspaces=False,
        include_skill_packages=False,
        include_plugins=False,
        include_knowledge=True,
    )
    pool.close()

    restore_layout = PathLayout(layout.root.parent / "restored-knowledge")
    restore_pool = SqlitePool(restore_layout.db)
    run_migrations(restore_pool)
    stale = restore_layout.knowledge_dir / "stale" / "docs" / "old.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("# stale", encoding="utf-8")

    restore_system_backup(
        archive,
        paths=restore_layout,
        pool=restore_pool,
        db_config=DatabaseConfig(),
        restore_config=False,
    )
    restore_pool.close()

    assert (restore_layout.knowledge_dir / "kb01" / "docs" / "a.md").read_text(
        encoding="utf-8"
    ) == "# keep"
    assert not (restore_layout.knowledge_dir / "stale").exists()


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
        include_chats=True,
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
