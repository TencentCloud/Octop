"""Unit tests for the per-user search key KV store (SealedUserSearchKeyRepo)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

from octop.infra.crypto.sealed_repos import SealedUserSearchKeyRepo
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def sealed(db: SqlitePool) -> SealedUserSearchKeyRepo:
    return SealedUserSearchKeyRepo(SecretRepo(db))


def test_set_get_roundtrip_stores_sealed(db: SqlitePool, sealed: SealedUserSearchKeyRepo) -> None:
    ts = sealed.set_env(7, "deepseek", {"DEEPSEEK_API_KEY": "sk-personal"})
    assert isinstance(ts, int)
    assert sealed.get_env(7, "deepseek") == {"DEEPSEEK_API_KEY": "sk-personal"}
    listed = sealed.list_for_user(7)
    assert [(name, isinstance(updated, int)) for name, updated in listed] == [("deepseek", True)]
    with db.connect() as conn:
        row = conn.execute(
            "SELECT v FROM secrets WHERE k = ?", ("user_search_key:7:deepseek",)
        ).fetchone()
    assert row is not None
    raw = bytes(row["v"])
    assert b"sk-personal" not in raw


def test_multi_env_provider_is_stored_atomically(sealed: SealedUserSearchKeyRepo) -> None:
    env = {"GOOGLE_API_KEY": "key", "GOOGLE_CSE_ID": "cse"}
    sealed.set_env(7, "google", env)
    assert sealed.get_env(7, "google") == env


def test_upsert_overwrites_and_delete(sealed: SealedUserSearchKeyRepo) -> None:
    sealed.set_env(7, "deepseek", {"DEEPSEEK_API_KEY": "sk-first"})
    ts2 = sealed.set_env(7, "deepseek", {"DEEPSEEK_API_KEY": "sk-second"})
    assert sealed.get_env(7, "deepseek") == {"DEEPSEEK_API_KEY": "sk-second"}
    assert sealed.list_for_user(7) == [("deepseek", ts2)]
    assert sealed.delete_key(7, "deepseek") is True
    assert sealed.get_env(7, "deepseek") is None
    assert sealed.delete_key(7, "deepseek") is False


def test_keys_are_isolated_per_user(sealed: SealedUserSearchKeyRepo) -> None:
    sealed.set_env(7, "deepseek", {"DEEPSEEK_API_KEY": "sk-seven"})
    sealed.set_env(8, "deepseek", {"DEEPSEEK_API_KEY": "sk-eight"})
    sealed.set_env(7, "tavily", {"TAVILY_API_KEY": "tvly-seven"})

    assert sealed.get_env(7, "deepseek") == {"DEEPSEEK_API_KEY": "sk-seven"}
    assert sealed.get_env(8, "deepseek") == {"DEEPSEEK_API_KEY": "sk-eight"}
    assert [name for name, _ts in sealed.list_for_user(7)] == ["deepseek", "tavily"]

    assert sealed.delete_for_user(7) == 2
    assert sealed.list_for_user(7) == []
    assert sealed.get_env(8, "deepseek") == {"DEEPSEEK_API_KEY": "sk-eight"}


def test_get_all_env_merges_every_provider_in_one_scan(
    sealed: SealedUserSearchKeyRepo,
) -> None:
    sealed.set_env(7, "deepseek", {"DEEPSEEK_API_KEY": "sk-personal"})
    sealed.set_env(7, "google", {"GOOGLE_API_KEY": "g-key", "GOOGLE_CSE_ID": "g-cse"})
    sealed.set_env(8, "tavily", {"TAVILY_API_KEY": "other-user"})

    assert sealed.get_all_env(7) == {
        "DEEPSEEK_API_KEY": "sk-personal",
        "GOOGLE_API_KEY": "g-key",
        "GOOGLE_CSE_ID": "g-cse",
    }
    assert sealed.get_all_env(8) == {"TAVILY_API_KEY": "other-user"}
    assert sealed.get_all_env(9) == {}


def test_corrupt_payload_raises(sealed: SealedUserSearchKeyRepo, db: SqlitePool) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, 0)",
            ("user_search_key:7:deepseek", b"not-encrypted"),
        )
    with pytest.raises(InvalidToken):
        sealed.get_env(7, "deepseek")
