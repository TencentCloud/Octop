"""Credentials stay usable without leaving their keys in a database copy."""

from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jwt
import pytest
from cryptography.fernet import Fernet

from octop.api.routers.providers import _row_to_dict
from octop.infra.connectors.crypto import decrypt_credentials
from octop.infra.db.credential_cipher import PREFIX, CredentialCipher
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.providers import ProviderRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError


def test_provider_and_secret_writes_are_encrypted(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    try:
        run_migrations(db)
        providers, secrets = ProviderRepo(db), SecretRepo(db)
        pid = providers.create(name="test", kind="openai", api_key="first-api-key")
        assert providers.get(pid).api_key == "first-api-key"
        providers.update(pid, api_key="replacement-api-key")
        assert providers.get_by_name("test").api_key == "replacement-api-key"
        assert providers.list_all()[0].api_key == "replacement-api-key"
        assert secrets.get_or_create("jwt", lambda: b"jwt-original") == b"jwt-original"
        assert secrets.get_or_create("jwt", lambda: b"unused") == b"jwt-original"
        secrets.rotate("jwt", b"jwt-rotated")
        assert secrets.get("jwt") == b"jwt-rotated"
        with db.connect() as conn:
            raw_key = conn.execute("SELECT api_key FROM providers").fetchone()[0]
            raw_secret = bytes(conn.execute("SELECT v FROM secrets WHERE k='jwt'").fetchone()[0])
        assert raw_key.encode().startswith(PREFIX)
        assert raw_secret.startswith(PREFIX)
        assert "replacement-api-key" not in raw_key
        assert b"jwt-rotated" not in raw_secret
    finally:
        db.close()


def test_legacy_migration_preserves_oauth_and_login_and_scrubs_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    db = SqlitePool(path)
    run_migrations(db)
    jwt_key = b"existing-session-signing-secret-with-32-bytes"
    fernet_key = Fernet.generate_key()
    payload = {"access_token": "existing-oauth-token"}
    blob = Fernet(fernet_key).encrypt(json.dumps(payload).encode())
    token = jwt.encode({"sub": "42"}, jwt_key, algorithm="HS256")
    with db.transaction() as conn:
        conn.execute("DELETE FROM secrets")
        conn.execute("INSERT INTO secrets(k,v,created_at) VALUES ('jwt',?,1)", (jwt_key,))
        conn.execute(
            "INSERT INTO secrets(k,v,created_at) VALUES ('connector_fernet',?,1)", (fernet_key,)
        )
        conn.execute(
            "INSERT INTO providers(name,kind,api_key,created_at,updated_at) VALUES ('old','openai',?,1,1)",
            ("legacy-plaintext-provider-key",),
        )
    db.close()
    (tmp_path / "secrets.key").unlink()
    db = SqlitePool(path)
    try:
        run_migrations(db)
        secrets = SecretRepo(db)
        assert jwt.decode(token, secrets.get("jwt"), algorithms=["HS256"])["sub"] == "42"
        assert decrypt_credentials(secrets, blob) == payload
        assert ProviderRepo(db).get_by_name("old").api_key == "legacy-plaintext-provider-key"
        with db.connect() as conn:
            before = list(conn.execute("SELECT k,v FROM secrets ORDER BY k"))
        run_migrations(db)
        with db.connect() as conn:
            assert list(conn.execute("SELECT k,v FROM secrets ORDER BY k")) == before
    finally:
        db.close()
    files = [path, Path(str(path) + "-wal")]
    for file in files:
        if file.exists():
            data = file.read_bytes()
            for value in (jwt_key, fernet_key, b"legacy-plaintext-provider-key"):
                assert value not in data


@pytest.mark.parametrize("failure", ["missing", "wrong", "invalid"])
def test_missing_or_wrong_master_key_does_not_replace_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    path = tmp_path / "octop.db"
    db = SqlitePool(path)
    run_migrations(db)
    ProviderRepo(db).create(name="saved", kind="openai", api_key="keep-this-value")
    db.close()
    with sqlite3.connect(path) as conn:
        before = conn.execute("SELECT api_key FROM providers").fetchone()[0]
    if failure == "missing":
        (tmp_path / "secrets.key").unlink()
    else:
        monkeypatch.setenv(
            "OCTOP_SECRET_KEY", Fernet.generate_key().decode() if failure == "wrong" else "invalid"
        )
    db = SqlitePool(path)
    try:
        with pytest.raises(OctopError) as exc:
            run_migrations(db)
        assert exc.value.code == ErrorCode.SECRET_STORAGE_UNAVAILABLE
        with db.connect() as conn:
            assert conn.execute("SELECT api_key FROM providers").fetchone()[0] == before
        if failure == "missing":
            assert not (tmp_path / "secrets.key").exists()
    finally:
        db.close()


def test_env_reference_is_resolved_without_roundtripping_secret_to_ui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_OCTOP_PROVIDER_KEY", "runtime-only-secret")
    db = SqlitePool(tmp_path / "octop.db")
    try:
        run_migrations(db)
        repo = ProviderRepo(db)
        pid = repo.create(name="env-provider", kind="openai", api_key="env:TEST_OCTOP_PROVIDER_KEY")
        row = repo.get(pid)
        assert row.api_key == "runtime-only-secret"
        assert _row_to_dict(row)["api_key"] == "env:TEST_OCTOP_PROVIDER_KEY"
        repo.update(pid, api_key=_row_to_dict(row)["api_key"])
        with db.connect() as conn:
            assert (
                conn.execute("SELECT api_key FROM providers").fetchone()[0]
                == "env:TEST_OCTOP_PROVIDER_KEY"
            )
        monkeypatch.delenv("TEST_OCTOP_PROVIDER_KEY")
        assert repo.get(pid).api_key is None
        assert _row_to_dict(repo.get(pid))["api_key"] == "env:TEST_OCTOP_PROVIDER_KEY"
    finally:
        db.close()


def test_env_master_key_never_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_SECRET_KEY", Fernet.generate_key().decode())
    cipher = CredentialCipher(tmp_path)
    ciphertext = cipher.encrypt(b"secret")
    assert CredentialCipher(tmp_path).decrypt(ciphertext) == b"secret"
    assert not list(tmp_path.iterdir())


def test_concurrent_file_creation_uses_one_key(tmp_path: Path) -> None:
    def encrypt(_: int) -> bytes:
        return CredentialCipher(tmp_path).encrypt(b"same-deployment")

    with ThreadPoolExecutor(max_workers=8) as workers:
        tokens = list(workers.map(encrypt, range(16)))
    cipher = CredentialCipher(tmp_path)
    assert all(cipher.decrypt(token) == b"same-deployment" for token in tokens)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["secrets.key"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX key file permissions")
def test_private_key_permissions_are_required(tmp_path: Path) -> None:
    key_file = tmp_path / "secrets.key"
    CredentialCipher(tmp_path).encrypt(b"secret")
    assert key_file.stat().st_mode & 0o777 == 0o600
    key_file.chmod(0o644)
    with pytest.raises(OctopError):
        CredentialCipher(tmp_path).encrypt(b"secret")


def test_keyring_backend_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring

    class FakeKeyring:
        __module__ = "keyring.backends.macOS"
        value: str | None = None

        def get_password(self, service: str, account: str) -> str | None:
            assert (service, account) == ("octop", "test-deployment")
            return self.value

        def set_password(self, service: str, account: str, value: str) -> None:
            self.value = value

    backend = FakeKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setenv("OCTOP_SECRET_KEY_KEYRING", "test-deployment")
    token = CredentialCipher(tmp_path).encrypt(b"protected")
    assert CredentialCipher(tmp_path).decrypt(token) == b"protected"
    backend.value = None
    with pytest.raises(OctopError):
        CredentialCipher(tmp_path).decrypt(token)
    assert backend.value is None
    assert not list(tmp_path.iterdir())


def test_insecure_keyring_does_not_fall_back_to_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import keyring
    from keyring.backends.null import Keyring

    monkeypatch.setattr(keyring, "get_keyring", Keyring)
    monkeypatch.setenv("OCTOP_SECRET_KEY_KEYRING", "test-deployment")
    with pytest.raises(OctopError):
        CredentialCipher(tmp_path).encrypt(b"protected")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", [PREFIX + b"corrupt", b"octop:fernet:v2:unknown"])
def test_invalid_ciphertext_never_falls_back_to_plaintext(tmp_path: Path, value: bytes) -> None:
    cipher = CredentialCipher(tmp_path)
    cipher.encrypt(b"seed")
    with pytest.raises(OctopError):
        cipher.decrypt(value)


def test_probe_draft_resolves_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.agents.providers.probe import make_probe_provider_row

    monkeypatch.setenv("TEST_PROBE_KEY", "draft-runtime-secret")
    row = make_probe_provider_row(
        name="test",
        kind="openai",
        api_key="env:TEST_PROBE_KEY",
        base_url=None,
        model_id="test-model",
    )
    assert row.api_key == "draft-runtime-secret"


def test_interrupted_wal_cleanup_is_retried(tmp_path: Path) -> None:
    from octop.infra.db.credential_migration import migrate_credentials

    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    with db.transaction() as conn:
        conn.execute("INSERT INTO secrets(k,v,created_at) VALUES ('jwt',?,1)", (b"legacy-jwt",))
        conn.execute("PRAGMA busy_timeout = 1")
    reader = sqlite3.connect(db.path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT v FROM secrets").fetchall()
        with pytest.raises(OctopError):
            migrate_credentials(db)
        assert SecretRepo(db).get("_credential_storage_v1").endswith(b"cleanup pending")
    finally:
        reader.close()
    try:
        migrate_credentials(db)
        assert not SecretRepo(db).get("_credential_storage_v1").endswith(b"cleanup pending")
        assert SecretRepo(db).get("jwt") == b"legacy-jwt"
    finally:
        db.close()
