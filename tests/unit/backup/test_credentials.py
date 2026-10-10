"""Backup key separation and preflight checks before destructive restore."""

from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from octop.config import DatabaseConfig
from octop.infra.backup.manifest import BackupManifest
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.providers import ProviderRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


def make_archive(tmp_path: Path) -> tuple[Path, PathLayout, SqlitePool]:
    paths = PathLayout(tmp_path / "source")
    db = SqlitePool(paths.db)
    run_migrations(db)
    ProviderRepo(db).create(name="source", kind="openai", api_key="backup-api-key")
    SecretRepo(db).get_or_create("jwt", lambda: b"backup-jwt")
    paths.config.write_text('{"port": 9876}')
    (paths.root / "env").write_text(
        f'OCTOP_SECRET_KEY="{os.environ["OCTOP_SECRET_KEY"]}"\n'
        "OCTOP_SECRET_KEY_KEYRING=source-deployment\nOTHER_SETTING=value\n"
    )
    archive = tmp_path / "backup.tar.gz"
    create_system_backup(
        paths=paths, agent_rows=[], pool=db, db_config=DatabaseConfig(), dest=archive
    )
    return archive, paths, db


def test_backup_excludes_master_key_and_restores_with_matching_key(tmp_path: Path) -> None:
    archive, _, source = make_archive(tmp_path)
    source.close()
    key = os.environ["OCTOP_SECRET_KEY"].encode()
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if member.isfile():
                assert key not in tf.extractfile(member).read()
        env = tf.extractfile("config/env").read()
        assert b"OCTOP_SECRET_KEY" not in env
        assert b"OTHER_SETTING=value" in env
        manifest = json.loads(tf.extractfile("manifest.json").read())
        assert manifest["secrets_key_id"]
    paths = PathLayout(tmp_path / "target")
    db = SqlitePool(paths.db)
    try:
        run_migrations(db)
        (paths.root / "env").write_text("OCTOP_SECRET_KEY_KEYRING=target-deployment\n")
        restore_system_backup(archive, paths=paths, pool=db, db_config=DatabaseConfig())
        assert ProviderRepo(db).get_by_name("source").api_key == "backup-api-key"
        assert SecretRepo(db).get("jwt") == b"backup-jwt"
        assert "target-deployment" in (paths.root / "env").read_text()
        assert "source-deployment" not in (paths.root / "env").read_text()
    finally:
        db.close()


@pytest.mark.parametrize("remove_manifest_key_id", [False, True])
def test_wrong_backup_key_fails_before_database_or_config_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remove_manifest_key_id: bool,
) -> None:
    archive, _, source = make_archive(tmp_path)
    source.close()
    if remove_manifest_key_id:
        # Even a missing/tampered manifest must not bypass SQLite ciphertext validation.
        with tarfile.open(archive) as tf:
            files = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
        manifest = json.loads(files["manifest.json"])
        manifest.pop("secrets_key_id")
        files["manifest.json"] = json.dumps(manifest).encode()
        with tarfile.open(archive, "w:gz") as tf:
            for name, blob in files.items():
                item = tarfile.TarInfo(name)
                item.size = len(blob)
                tf.addfile(item, io.BytesIO(blob))
    monkeypatch.setenv("OCTOP_SECRET_KEY", Fernet.generate_key().decode())
    paths = PathLayout(tmp_path / "target")
    db = SqlitePool(paths.db)
    try:
        run_migrations(db)
        ProviderRepo(db).create(name="keep", kind="openai", api_key="keep-key")
        paths.config.write_text('{"port": 1234}')
        with pytest.raises(OctopError) as exc:
            restore_system_backup(archive, paths=paths, pool=db, db_config=DatabaseConfig())
        assert exc.value.code == ErrorCode.SECRET_STORAGE_UNAVAILABLE
        assert ProviderRepo(db).get_by_name("keep").api_key == "keep-key"
        assert ProviderRepo(db).get_by_name("source") is None
        assert paths.config.read_text() == '{"port": 1234}'
    finally:
        db.close()


def test_legacy_plaintext_backup_is_upgraded_on_restore(tmp_path: Path) -> None:
    paths = PathLayout(tmp_path / "source")
    db = SqlitePool(paths.db)
    run_migrations(db)
    with db.transaction() as conn:
        conn.execute("DELETE FROM secrets")
        conn.execute("INSERT INTO secrets(k,v,created_at) VALUES ('jwt',?,1)", (b"legacy-jwt",))
        conn.execute(
            "INSERT INTO providers(name,kind,api_key,created_at,updated_at) VALUES ('old','openai',?,1,1)",
            ("old-api-key",),
        )
        schema = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
    db.close()
    manifest = BackupManifest(
        manifest_version=1,
        octop_version="1.0.2b6",
        schema_version=schema,
        created_at="",
        home="",
    )
    blob = manifest.to_json().encode()
    archive = tmp_path / "legacy.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        item = tarfile.TarInfo("manifest.json")
        item.size = len(blob)
        tf.addfile(item, io.BytesIO(blob))
        tf.add(paths.db, arcname="db/octop.db")
    paths = PathLayout(tmp_path / "target")
    db = SqlitePool(paths.db)
    try:
        run_migrations(db)
        restore_system_backup(archive, paths=paths, pool=db, db_config=DatabaseConfig())
        assert SecretRepo(db).get("jwt") == b"legacy-jwt"
        assert ProviderRepo(db).get_by_name("old").api_key == "old-api-key"
        with db.connect() as conn:
            assert (
                bytes(conn.execute("SELECT v FROM secrets WHERE k='jwt'").fetchone()[0])
                != b"legacy-jwt"
            )
    finally:
        db.close()


def test_private_key_file_is_excluded_even_inside_a_backed_up_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OCTOP_SECRET_KEY")
    paths = PathLayout(tmp_path / "home")
    key_path = paths.plugins_dir / "deployment.key"
    monkeypatch.setenv("OCTOP_SECRET_KEY_FILE", str(key_path))
    db = SqlitePool(paths.db)
    try:
        run_migrations(db)
        (paths.plugins_dir / "keep.txt").write_text("keep")
        archive = tmp_path / "backup.tar.gz"
        create_system_backup(
            paths=paths,
            agent_rows=[],
            pool=db,
            db_config=DatabaseConfig(),
            dest=archive,
            include_plugins=True,
        )
        with tarfile.open(archive) as tf:
            assert "plugins/keep.txt" in tf.getnames()
            assert "plugins/deployment.key" not in tf.getnames()
            key = key_path.read_bytes()
            assert all(key not in tf.extractfile(m).read() for m in tf.getmembers() if m.isfile())
        with pytest.raises(OctopError):
            restore_system_backup(archive, paths=paths, pool=db, db_config=DatabaseConfig())
        assert key_path.read_bytes() == key
    finally:
        db.close()
