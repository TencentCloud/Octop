"""Unit tests for the per-user provider key KV store (SealedUserProviderKeyRepo)."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.crypto.sealed_repos import SealedUserProviderKeyRepo
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def sealed(db: SqlitePool) -> SealedUserProviderKeyRepo:
    return SealedUserProviderKeyRepo(SecretRepo(db))


def test_set_get_roundtrip_stores_sealed(db: SqlitePool, sealed: SealedUserProviderKeyRepo) -> None:
    ts = sealed.set_key(7, "gw", "sk-personal")
    assert isinstance(ts, int)
    assert sealed.get_key(7, "gw") == "sk-personal"
    listed = sealed.list_for_user(7)
    assert [(name, isinstance(updated, int)) for name, updated in listed] == [("gw", True)]
    with db.connect() as conn:
        row = conn.execute(
            "SELECT v FROM secrets WHERE k = ?", ("user_provider_key:7:gw",)
        ).fetchone()
    assert row is not None
    raw = bytes(row["v"])
    assert b"sk-personal" not in raw


def test_upsert_overwrites_and_delete_falls_back(sealed: SealedUserProviderKeyRepo) -> None:
    sealed.set_key(7, "gw", "sk-first")
    ts2 = sealed.set_key(7, "gw", "sk-second")
    assert sealed.get_key(7, "gw") == "sk-second"
    assert sealed.list_for_user(7) == [("gw", ts2)]
    assert sealed.delete_key(7, "gw") is True
    assert sealed.get_key(7, "gw") is None
    assert sealed.delete_key(7, "gw") is False
    assert sealed.list_for_user(7) == []


def test_keys_are_isolated_per_user(sealed: SealedUserProviderKeyRepo) -> None:
    sealed.set_key(7, "gw", "sk-seven")
    sealed.set_key(8, "gw", "sk-eight")
    sealed.set_key(7, "other", "sk-seven-other")

    assert sealed.get_key(7, "gw") == "sk-seven"
    assert sealed.get_key(8, "gw") == "sk-eight"
    assert [name for name, _ts in sealed.list_for_user(7)] == ["gw", "other"]
    assert [name for name, _ts in sealed.list_for_user(8)] == ["gw"]

    assert sealed.delete_for_user(7) == 2
    assert sealed.list_for_user(7) == []
    assert sealed.get_key(8, "gw") == "sk-eight"


def test_delete_for_provider_spans_users(sealed: SealedUserProviderKeyRepo) -> None:
    sealed.set_key(7, "gw", "sk-seven")
    sealed.set_key(8, "gw", "sk-eight")
    sealed.set_key(8, "keep", "sk-keep")

    assert sealed.delete_for_provider("gw") == 2
    assert sealed.get_key(7, "gw") is None
    assert sealed.get_key(8, "gw") is None
    assert sealed.get_key(8, "keep") == "sk-keep"
