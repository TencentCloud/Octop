"""Recover legacy SQLite credential storage without changing encrypted payloads."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_mcp_server_configs_for_user
from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo, ConnectorRow
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo


@pytest.fixture
def db(tmp_path: Path) -> Iterator[SqlitePool]:
    pool = SqlitePool(tmp_path / "connectors.db")
    run_migrations(pool)
    with pool.transaction() as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, role, created_at) "
            "VALUES (1, 'owner', 'fixture', 'user', 1)"
        )
    yield pool
    pool.close()


def _seed(repo: ConnectorRepo, instance: str) -> None:
    repo.create(
        instance_id=instance,
        user_id=1,
        kind="tencent-docs",
        display_name=instance,
        mcp_server_name=f"tencent-docs__{instance}",
    )


def _snapshot(db: SqlitePool) -> list[dict[str, object]]:
    with db.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM connectors ORDER BY id")]


def test_legacy_text_keeps_connector_list_and_agent_assembly_usable(db: SqlitePool) -> None:
    repo = ConnectorRepo(db)
    secrets = SecretRepo(db)
    svc = ConnectorService(
        repo=repo,
        secret_repo=secrets,
        settings_repo=SettingsRepo(db),
        config=OctopConfig(),
    )
    _seed(repo, "healthy")
    svc.encrypt_and_store(instance_id="healthy", payload={"token": "healthy-fixture"})
    svc.put_custom_servers(
        1,
        {"legacy": {"transport": "stdio", "command": "fixture-mcp"}},
    )
    parent = repo.get_by_user_kind(1, "custom-mcp")
    assert parent is not None and parent.credential_blob is not None
    original = parent.credential_blob
    with db.transaction() as conn:
        conn.execute(
            "UPDATE connectors SET credential_blob = ? WHERE instance_id = ?",
            (original.decode("ascii"), parent.instance_id),
        )

    before = _snapshot(db)
    assert {row["display_name"] for row in svc.list_instances_for_api(1)} == {
        "healthy",
        "legacy",
    }
    assert svc.decrypt(parent.instance_id)["servers"]["legacy"]["command"] == "fixture-mcp"
    configs = build_mcp_server_configs_for_user(
        svc=svc,
        connector_repo=repo,
        user_id=1,
        agent_id="fixture-agent",
        agent_user_id=1,
        config=OctopConfig(),
    )
    assert set(configs) == {"tencent-docs__healthy", "legacy"}
    # Read compatibility is not a hidden write, rotation or deletion.
    assert _snapshot(db) == before


@pytest.mark.parametrize(
    "wrapper", [bytes, bytearray, memoryview, lambda value: value.decode("ascii")]
)
def test_row_reader_preserves_credential_bytes(db: SqlitePool, wrapper) -> None:
    repo = ConnectorRepo(db)
    _seed(repo, "reader")
    row = _snapshot(db)[0]
    row["credential_blob"] = wrapper(b"fixture-token")
    assert ConnectorRow.from_row(row).credential_blob == b"fixture-token"


@pytest.mark.parametrize("invalid", ["fixture-token", 4, 1.5, None, True])
def test_credential_writer_rejects_nonbinary_without_changing_row(db: SqlitePool, invalid) -> None:
    repo = ConnectorRepo(db)
    _seed(repo, "writer")
    repo.upsert_credentials(instance_id="writer", blob=b"original", expires_at=100)
    before = _snapshot(db)
    with pytest.raises(TypeError):
        repo.upsert_credentials(instance_id="writer", blob=invalid, expires_at=200)
    assert _snapshot(db) == before


@pytest.mark.parametrize("wrapper", [bytes, bytearray, memoryview])
def test_credential_writer_stores_binary_buffers_as_blobs(db: SqlitePool, wrapper) -> None:
    repo = ConnectorRepo(db)
    _seed(repo, "writer")
    repo.upsert_credentials(instance_id="writer", blob=wrapper(b"fixture-token"))
    with db.connect() as conn:
        row = conn.execute(
            "SELECT credential_blob, typeof(credential_blob) FROM connectors"
        ).fetchone()
    assert tuple(row) == (b"fixture-token", "blob")


@pytest.mark.parametrize("encoding", ["UTF-8", "UTF-16le", "UTF-16be"])
def test_startup_repair_preserves_ciphertext_metadata_and_schema_version(
    tmp_path: Path, encoding: str
) -> None:
    pool = SqlitePool(tmp_path / "encoded.db")
    try:
        with pool.connect() as conn:
            conn.execute(f"PRAGMA encoding = '{encoding}'")
        run_migrations(pool)
        with pool.transaction() as conn:
            conn.execute(
                "INSERT INTO users(id, username, password_hash, role, created_at) "
                "VALUES (1, 'owner', 'fixture', 'user', 1)"
            )
        repo = ConnectorRepo(pool)
        secrets = SecretRepo(pool)
        payload = {"token": "fixture-凭据"}
        token = encrypt_credentials(secrets, payload)
        for name in ("legacy", "healthy", "empty"):
            _seed(repo, name)
        repo.upsert_credentials(instance_id="healthy", blob=token)
        with pool.transaction() as conn:
            conn.execute(
                "UPDATE connectors SET credential_blob = ?, updated_at = ? WHERE instance_id = 'legacy'",
                (token.decode("ascii"), "2026-10-27T19:54:22.418170"),
            )
        before = _snapshot(pool)
        with pool.connect() as conn:
            version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]

        run_migrations(pool)

        expected = [dict(row) for row in before]
        expected[0]["credential_blob"] = token
        assert _snapshot(pool) == expected
        assert decrypt_credentials(secrets, repo.get("legacy").credential_blob) == payload
        with pool.connect() as conn:
            types = dict(
                conn.execute("SELECT instance_id, typeof(credential_blob) FROM connectors")
            )
            assert conn.execute("SELECT version FROM _schema_version").fetchone()[0] == version
        assert types == {"legacy": "blob", "healthy": "blob", "empty": "null"}
        run_migrations(pool)
        assert _snapshot(pool) == expected
    finally:
        pool.close()


def test_startup_repair_rolls_back_all_credential_changes_on_failure(db: SqlitePool) -> None:
    repo = ConnectorRepo(db)
    for instance in ("first", "second"):
        _seed(repo, instance)
    with db.transaction() as conn:
        conn.execute("UPDATE connectors SET credential_blob = 'fixture-token'")
        conn.execute(
            "CREATE TRIGGER reject_second BEFORE UPDATE OF credential_blob ON connectors "
            "WHEN OLD.instance_id = 'second' BEGIN SELECT RAISE(ABORT, 'fixture refusal'); END"
        )
    before = _snapshot(db)
    with pytest.raises(sqlite3.IntegrityError, match="fixture refusal"):
        run_migrations(db)
    assert _snapshot(db) == before


def test_legacy_text_does_not_bypass_credential_authentication(db: SqlitePool) -> None:
    repo = ConnectorRepo(db)
    _seed(repo, "invalid")
    with db.transaction() as conn:
        conn.execute("UPDATE connectors SET credential_blob = 'not-an-encrypted-token'")
    with pytest.raises(InvalidToken):
        decrypt_credentials(SecretRepo(db), repo.get("invalid").credential_blob)
