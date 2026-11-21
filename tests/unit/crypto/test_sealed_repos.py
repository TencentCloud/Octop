"""Sealed repos keep secrets encrypted at rest and open them on read."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.crypto.sealed_repos import SealedBackendRepo, SealedProviderRepo
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.backends import BackendRepo
from octop.infra.db.repos.providers import ProviderRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.services import RepoBundle


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_storage_secret_key_encrypted_at_rest(db: SqlitePool) -> None:
    secrets = SecretRepo(db)
    repo = SealedBackendRepo(BackendRepo(db), secrets)
    rid = repo.create(
        name="s3",
        kind="s3",
        access_key="AKIA",
        secret_key="super-secret",
        bucket="b",
        region="us-east-1",
    )
    with db.connect() as conn:
        raw = conn.execute(
            "SELECT secret_key FROM storage_backends WHERE id = ?", (rid,)
        ).fetchone()[0]
    assert raw != "super-secret"
    assert raw.startswith("gAAAA")
    row = repo.get(rid)
    assert row is not None
    assert row.secret_key == "super-secret"


def test_storage_reads_legacy_plaintext(db: SqlitePool) -> None:
    inner = BackendRepo(db)
    rid = inner.create(
        name="legacy",
        kind="s3",
        access_key="AK",
        secret_key="plain-sk",
        bucket="b",
        region="r",
    )
    repo = SealedBackendRepo(inner, SecretRepo(db))
    row = repo.get(rid)
    assert row is not None
    assert row.secret_key == "plain-sk"


def test_provider_api_key_encrypted_at_rest(db: SqlitePool) -> None:
    secrets = SecretRepo(db)
    repo = SealedProviderRepo(ProviderRepo(db), secrets)
    rid = repo.create(name="openai", kind="openai", api_key="sk-test-key")
    with db.connect() as conn:
        raw = conn.execute("SELECT api_key FROM providers WHERE id = ?", (rid,)).fetchone()[0]
    assert raw != "sk-test-key"
    assert raw.startswith("gAAAA")
    row = repo.get(rid)
    assert row is not None
    assert row.api_key == "sk-test-key"


def test_repo_bundle_wires_sealed_repos(db: SqlitePool) -> None:
    bundle = RepoBundle.from_pool(db)
    bid = bundle.storage_backend_repo.create(
        name="cos",
        kind="cos",
        secret_key="bucket-secret",
        bucket="x",
        region="ap",
    )
    with db.connect() as conn:
        raw = conn.execute(
            "SELECT secret_key FROM storage_backends WHERE id = ?", (bid,)
        ).fetchone()[0]
    assert raw != "bucket-secret"
    assert raw.startswith("gAAAA")
    opened = bundle.storage_backend_repo.get(bid)
    assert opened is not None
    assert opened.secret_key == "bucket-secret"
