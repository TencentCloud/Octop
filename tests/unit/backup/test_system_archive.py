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


def test_roundtrip_backup(layout: PathLayout) -> None:
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
    layout.config.write_text('{"port": 8088}', encoding="utf-8")

    class Row:
        agent_id = "agent01"
        name = "Test"

    data, _name = create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
    )
    pool.close()

    restore_root = layout.root.parent / "restored"
    restore_layout = PathLayout(restore_root)
    restore_db = restore_layout.db
    restore_pool = SqlitePool(restore_db)
    run_migrations(restore_pool)

    result = restore_system_backup(
        data,
        paths=restore_layout,
        pool=restore_pool,
        db_config=DatabaseConfig(),
        restore_config=True,
    )
    restore_pool.close()

    assert result["agents"] == 1
    assert (restore_layout.agent_workspace("agent01") / "SOUL.md").read_text(
        encoding="utf-8"
    ) == "# soul"
    assert json.loads(restore_layout.config.read_text(encoding="utf-8"))["port"] == 8088

    with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as tf:
        manifest = json.loads(tf.extractfile("manifest.json").read().decode("utf-8"))
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["database_driver"] == "sqlite"


def test_refuse_cross_engine_restore(layout: PathLayout) -> None:
    pool = SqlitePool(layout.db)
    run_migrations(pool)

    class Row:
        agent_id = "a1"
        name = "n"

    data, _ = create_system_backup(
        paths=layout,
        agent_rows=[Row()],
        pool=pool,
        db_config=DatabaseConfig(),
    )
    # Rewrite manifest to pretend it's a postgres dump.
    members: dict[str, bytes] = {}
    with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                f = tf.extractfile(m)
                assert f is not None
                members[m.name] = f.read()
    manifest = json.loads(members["manifest.json"])
    manifest["database_driver"] = "postgresql"
    members["manifest.json"] = json.dumps(manifest).encode()
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, blob in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(blob)
            tf.addfile(info, BytesIO(blob))
    with pytest.raises(OctopError) as excinfo:
        restore_system_backup(
            buf.getvalue(),
            paths=layout,
            pool=pool,
            db_config=DatabaseConfig(),
        )
    assert excinfo.value.code == ErrorCode.BACKUP_DRIVER_MISMATCH
    pool.close()
