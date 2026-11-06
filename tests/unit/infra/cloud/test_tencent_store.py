"""Cloud login storage: local files on SQLite, shared rows when a secret repo is bound."""

from __future__ import annotations

from pathlib import Path

from octop.infra.cloud.tencent import (
    CloudCredential,
    CloudCredentialStore,
    open_cloud_credential_store,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo


def _credential(secret_id: str = "AKIDtest000000000000") -> CloudCredential:
    return CloudCredential(
        secret_id=secret_id,
        secret_key="secret-key-value",
        token="sts-token",
        expires_at=1793076962.0,
        access_token="access-token-value",
        access_expires_at=1793076958.0,
        refresh_token="refresh-token-value",
        open_id="open-id-value",
        site="cn",
    )


def test_file_store_roundtrip(tmp_path: Path) -> None:
    store = CloudCredentialStore(tmp_path)
    store.save(3, _credential())
    loaded = store.load(3)
    assert loaded is not None
    assert loaded.secret_id == "AKIDtest000000000000"
    assert (tmp_path / "secrets" / "cloud" / "tencent-3.enc").is_file()
    assert store.clear(3) is True
    assert store.load(3) is None


def test_shared_store_adopts_local_file_without_overwriting(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    secrets = SecretRepo(pool)
    root = tmp_path / "home"
    CloudCredentialStore(root).save(7, _credential("AKID-from-disk"))

    shared = CloudCredentialStore(root, secrets)
    assert shared.adopt_local() == 1
    loaded = shared.load(7)
    assert loaded is not None
    assert loaded.refresh_token == "refresh-token-value"
    assert not (root / "secrets" / "cloud" / "tencent-7.enc").exists()

    CloudCredentialStore(root).save(7, _credential("AKID-stale-disk"))
    assert shared.adopt_local() == 0
    again = shared.load(7)
    assert again is not None
    assert again.secret_id == "AKID-from-disk"
    assert not (root / "secrets" / "cloud" / "tencent-7.enc").exists()

    state = shared.new_state(7)
    assert shared.consume_state(7, "wrong") is False
    assert shared.consume_state(7, state) is True
    assert shared.consume_state(7, state) is None

    assert shared.clear(7) is True
    assert shared.load(7) is None


def test_open_uses_files_unless_postgresql(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    secrets = SecretRepo(pool)

    class _Database:
        is_postgresql = False

    class _Config:
        database = _Database()

    file_store = open_cloud_credential_store(tmp_path / "sqlite", _Config(), secrets)
    assert file_store.shared is False

    _Database.is_postgresql = True
    shared = open_cloud_credential_store(tmp_path / "pg", _Config(), secrets)
    assert shared.shared is True
