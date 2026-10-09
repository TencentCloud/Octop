"""Idempotent data migration; independent of the SQL schema watermark."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from octop.infra.db.credential_cipher import PREFIX, CredentialCipher, storage_error
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import now_ts
from octop.infra.utils.provider_keys import api_key_reference

_CHECK_KEY = "_credential_storage_v1"
_CHECK_VALUE = b"octop credential storage v1"
_CLEANUP_PENDING = b"octop credential storage v1: cleanup pending"


def validate_sqlite_credentials(path: Path, cipher: CredentialCipher) -> None:
    """Check an extracted backup without modifying it or the live database."""
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "secrets" in tables:
            for (value,) in conn.execute("SELECT v FROM secrets"):
                cipher.decrypt(bytes(value))
        if "providers" in tables:
            for (value,) in conn.execute("SELECT api_key FROM providers WHERE api_key IS NOT NULL"):
                cipher.decrypt(value.encode("utf-8"))
    finally:
        conn.close()


def migrate_credentials(db: DatabasePool) -> None:
    """Wrap old provider keys, JWT keys, and connector KEKs in one transaction.

    Validate every existing encrypted value before creating a key or changing a
    row. A missing/wrong key must never be treated as a fresh installation.
    """
    cipher = db.credential_cipher
    changed = False
    with db.transaction() as conn:
        if db.dialect == "postgresql":
            conn.execute("LOCK TABLE secrets, providers IN SHARE ROW EXCLUSIVE MODE")
        secrets = conn.execute("SELECT k, v FROM secrets").fetchall()
        providers = conn.execute("SELECT id, api_key FROM providers").fetchall()
        values = [bytes(r["v"]) for r in secrets]
        values.extend(r["api_key"].encode("utf-8") for r in providers if r["api_key"])
        for value in values:
            if value.startswith(b"octop:fernet:"):
                cipher.decrypt(value)
        for row in secrets:
            value = bytes(row["v"])
            if not value.startswith(PREFIX):
                conn.execute(
                    "UPDATE secrets SET v = ? WHERE k = ?", (cipher.encrypt(value), row["k"])
                )
                changed = True
        for row in providers:
            value = row["api_key"]
            if (
                value
                and not api_key_reference(value)
                and not value.encode("utf-8").startswith(PREFIX)
            ):
                conn.execute(
                    "UPDATE providers SET api_key = ? WHERE id = ?",
                    (cipher.encrypt(value.encode("utf-8")).decode("ascii"), row["id"]),
                )
                changed = True
        check = next((r for r in secrets if r["k"] == _CHECK_KEY), None)
        check_value = cipher.decrypt(bytes(check["v"])) if check is not None else None
        if check_value not in (None, _CHECK_VALUE, _CLEANUP_PENDING):
            raise storage_error()
        cleanup = db.dialect == "sqlite" and (changed or check_value in (None, _CLEANUP_PENDING))
        marker = _CLEANUP_PENDING if cleanup else _CHECK_VALUE
        if check is None:
            conn.execute(
                "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
                (_CHECK_KEY, cipher.encrypt(marker), now_ts()),
            )
        elif cleanup and check_value != _CLEANUP_PENDING:
            conn.execute(
                "UPDATE secrets SET v = ? WHERE k = ?", (cipher.encrypt(marker), _CHECK_KEY)
            )
    if cleanup:
        # Remove legacy plaintext from free pages and the WAL as well as live rows.
        # Upgrades require stopping older Octop processes that share this database.
        with db.connect() as conn:
            conn.execute("VACUUM")
            result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result[0] != 0:
                raise storage_error()
        # Keep the pending marker on failure so the next startup retries cleanup.
        with db.transaction() as conn:
            conn.execute(
                "UPDATE secrets SET v = ? WHERE k = ?", (cipher.encrypt(_CHECK_VALUE), _CHECK_KEY)
            )
