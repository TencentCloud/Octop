"""Unit tests for memory MCP token helpers, schema v26, and the repo."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from octop.infra.agents.memory_tokens import (
    TOKEN_PREFIX,
    generate_token,
    hash_token,
    token_hint,
    token_matches,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.memory_mcp_tokens import MemoryMcpTokenRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def repo(db: SqlitePool) -> MemoryMcpTokenRepo:
    return MemoryMcpTokenRepo(db)


def _user(db: SqlitePool, username: str = "alice") -> int:
    return UserRepo(db).create(username=username, password_hash="h", role="user")


def _issue(
    repo: MemoryMcpTokenRepo,
    user_id: int,
    *,
    name: str = "codex@macbook",
    expert_ids: list[str] | None = None,
) -> tuple[str, str]:
    """Create a token; return ``(plaintext, token_id)``."""
    plaintext, digest = generate_token()
    token_id = new_ulid()
    repo.create(
        user_id=user_id,
        name=name,
        expert_ids=expert_ids,
        token_id=token_id,
        token_hash=digest,
        token_hint=token_hint(plaintext),
    )
    return plaintext, token_id


def test_generate_token_prefix_and_digest() -> None:
    plaintext, digest = generate_token()
    assert plaintext.startswith(TOKEN_PREFIX)
    assert len(plaintext) > len(TOKEN_PREFIX) + 32
    assert digest == hash_token(plaintext)
    assert len(digest) == 64
    assert plaintext != generate_token()[0]


def test_token_matches_compares_digests() -> None:
    plaintext, digest = generate_token()
    assert token_matches(plaintext, digest)
    assert not token_matches(plaintext + "x", digest)


def test_token_hint_masks_middle() -> None:
    plaintext, _ = generate_token()
    hint = token_hint(plaintext)
    assert hint == f"{plaintext[:9]}…{plaintext[-4:]}"
    assert "…" in hint
    assert hint.startswith(TOKEN_PREFIX)


def test_schema_v26_creates_table(db: SqlitePool) -> None:
    with db.connect() as conn:
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        indexes = {
            r["name"] for r in conn.execute("PRAGMA index_list(memory_mcp_tokens)").fetchall()
        }
        columns = {
            r["name"] for r in conn.execute("PRAGMA table_info(memory_mcp_tokens)").fetchall()
        }
    assert version == 26
    assert "memory_mcp_tokens" in tables
    assert "idx_memory_mcp_tokens_user" in indexes
    assert {
        "id",
        "token_id",
        "user_id",
        "name",
        "expert_ids",
        "disabled_clients",
        "client_stats",
        "token_hash",
        "token_hint",
        "created_at",
        "last_used_at",
        "revoked_at",
    } == columns


def test_create_persists_digest_only(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    plaintext, token_id = _issue(repo, user_id)

    row = repo.get_for_user(token_id, user_id=user_id)
    assert row is not None
    assert row.token_id == token_id
    assert row.user_id == user_id
    assert row.name == "codex@macbook"
    assert row.expert_ids is None
    assert row.token_hash == hash_token(plaintext)
    assert row.token_hint == token_hint(plaintext)
    assert row.last_used_at is None
    assert row.revoked_at is None
    datetime.fromisoformat(row.created_at.replace("Z", "+00:00"))

    with db.connect() as conn:
        stored = conn.execute(
            "SELECT * FROM memory_mcp_tokens WHERE token_id = ?", (token_id,)
        ).fetchone()
    assert plaintext not in json.dumps(dict(stored))


def test_expert_ids_json_round_trip(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    _, token_id = _issue(repo, user_id, expert_ids=["expert-a", "expert-b"])

    row = repo.get_for_user(token_id, user_id=user_id)
    assert row is not None
    assert row.expert_ids == ["expert-a", "expert-b"]

    with db.connect() as conn:
        raw = conn.execute(
            "SELECT expert_ids FROM memory_mcp_tokens WHERE token_id = ?", (token_id,)
        ).fetchone()["expert_ids"]
    assert json.loads(raw) == ["expert-a", "expert-b"]


def test_list_for_user_newest_first_and_scoped(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    alice = _user(db, "alice")
    bob = _user(db, "bob")
    _, first = _issue(repo, alice, name="first")
    _, second = _issue(repo, alice, name="second")
    _issue(repo, bob, name="bob-token")

    rows = repo.list_for_user(alice)
    assert [row.token_id for row in rows] == [second, first]
    assert repo.list_for_user(bob)[0].name == "bob-token"


def test_get_by_token_hash_returns_revoked_row(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    plaintext, token_id = _issue(repo, user_id)
    assert repo.revoke(token_id, user_id=user_id) is True

    row = repo.get_by_token_hash(hash_token(plaintext))
    assert row is not None
    assert row.token_id == token_id
    assert row.revoked_at is not None
    assert repo.get_by_token_hash(hash_token("omcp_unknown")) is None


def test_get_for_user_hides_other_users_tokens(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    alice = _user(db, "alice")
    bob = _user(db, "bob")
    _, token_id = _issue(repo, alice)
    assert repo.get_for_user(token_id, user_id=bob) is None


def test_revoke_is_idempotent(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    alice = _user(db, "alice")
    bob = _user(db, "bob")
    _, token_id = _issue(repo, alice)

    assert repo.revoke(token_id, user_id=bob) is False
    assert repo.revoke(token_id, user_id=alice) is True
    assert repo.revoke(token_id, user_id=alice) is False
    row = repo.get_for_user(token_id, user_id=alice)
    assert row is not None
    assert row.revoked_at is not None


def test_any_active_ignores_revoked(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    assert repo.any_active() is False
    _, token_id = _issue(repo, user_id)
    assert repo.any_active() is True
    repo.revoke(token_id, user_id=user_id)
    assert repo.any_active() is False


def test_touch_sets_last_used_at(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    _, token_id = _issue(repo, user_id)
    repo.touch(token_id)

    row = repo.get_for_user(token_id, user_id=user_id)
    assert row is not None
    assert row.last_used_at is not None
    datetime.fromisoformat(row.last_used_at.replace("Z", "+00:00"))


def test_update_disabled_clients_round_trip(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    _, token_id = _issue(repo, user_id)
    row = repo.get_for_user(token_id, user_id=user_id)
    assert row is not None
    assert row.disabled_clients is None

    updated = repo.update(
        token_id,
        user_id=user_id,
        name=row.name,
        expert_ids=row.expert_ids,
        disabled_clients=["codex", "cursor"],
    )
    assert updated is not None
    assert updated.disabled_clients == ["codex", "cursor"]
    stored = repo.get_for_user(token_id, user_id=user_id)
    assert stored is not None
    assert stored.disabled_clients == ["codex", "cursor"]

    # An empty list is the same as "no restriction".
    cleared = repo.update(
        token_id,
        user_id=user_id,
        name=row.name,
        expert_ids=row.expert_ids,
        disabled_clients=[],
    )
    assert cleared is not None
    assert cleared.disabled_clients is None

    repo.update(
        token_id,
        user_id=user_id,
        name=row.name,
        expert_ids=row.expert_ids,
        disabled_clients=["kiro"],
    )
    released = repo.update(
        token_id, user_id=user_id, name="renamed", expert_ids=None, disabled_clients=None
    )
    assert released is not None
    assert released.disabled_clients is None


def test_record_client_merges_counts(db: SqlitePool, repo: MemoryMcpTokenRepo) -> None:
    user_id = _user(db)
    _, token_id = _issue(repo, user_id)

    repo.record_client(token_id, "codex", now="2026-01-01T00:00:00Z")
    repo.record_client(token_id, "codex", now="2026-01-02T00:00:00Z")
    repo.record_client(token_id, "cursor", now="2026-01-03T00:00:00Z")

    row = repo.get_for_user(token_id, user_id=user_id)
    assert row is not None
    assert row.client_stats == {
        "codex": {
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-02T00:00:00Z",
            "count": 2,
        },
        "cursor": {
            "first_seen": "2026-01-03T00:00:00Z",
            "last_seen": "2026-01-03T00:00:00Z",
            "count": 1,
        },
    }

    with db.connect() as conn:
        raw = conn.execute(
            "SELECT client_stats FROM memory_mcp_tokens WHERE token_id = ?", (token_id,)
        ).fetchone()["client_stats"]
    assert json.loads(raw)["codex"]["count"] == 2


def test_record_client_ignores_missing_and_revoked_tokens(
    db: SqlitePool, repo: MemoryMcpTokenRepo
) -> None:
    user_id = _user(db)
    _, token_id = _issue(repo, user_id)

    repo.record_client("tok_missing", "codex")  # no row: still a no-op
    repo.revoke(token_id, user_id=user_id)
    repo.record_client(token_id, "codex")

    row = repo.get_for_user(token_id, user_id=user_id)
    assert row is not None
    assert row.client_stats is None
