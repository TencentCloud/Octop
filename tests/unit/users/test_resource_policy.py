"""tests/unit/users/test_resource_policy.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.usage import UsageRepo
from octop.infra.db.repos.user_policies import UserPolicyRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.resource_policy import (
    POLICY_TOKEN_QUOTA,
    POLICY_WORKSPACE_ROOT_DIR,
    assert_backend_within_user_root,
    assert_token_quota_available,
    normalize_workspace_root_dir,
    public_policy_fields,
)


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_normalize_workspace_root_dir_unlimited() -> None:
    assert normalize_workspace_root_dir(None) is None
    assert normalize_workspace_root_dir("  ") is None


def test_normalize_workspace_root_dir_must_be_directory(tmp_path: Path) -> None:
    root = tmp_path / "jail"
    root.mkdir()
    assert normalize_workspace_root_dir(str(root)) == root.resolve().as_posix()
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(OctopError) as exc:
        normalize_workspace_root_dir(str(file_path))
    assert exc.value.code is ErrorCode.WORKSPACE_ROOT_RESTRICTED


def test_assert_backend_within_user_root(tmp_path: Path) -> None:
    jail = tmp_path / "jail"
    nested = jail / "proj"
    outside = tmp_path / "other"
    jail.mkdir()
    nested.mkdir()
    outside.mkdir()
    allowed = jail.resolve().as_posix()
    assert_backend_within_user_root(
        {"type": "local_shell", "root_dir": nested.as_posix(), "virtual_mode": True},
        allowed,
    )
    with pytest.raises(ValueError, match="path outside allowed workspace root"):
        assert_backend_within_user_root(
            {"type": "local_shell", "root_dir": outside.as_posix(), "virtual_mode": True},
            allowed,
        )
    assert_backend_within_user_root(
        {"type": "docker"},
        allowed,
    )


def test_assert_token_quota_available(db: SqlitePool) -> None:
    users = UserRepo(db)
    policies = UserPolicyRepo(db)
    usage = UsageRepo(db)
    uid = users.create(username="alice", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=uid, name="a")
    assert_token_quota_available(policies, usage, uid)
    policies.set(uid, POLICY_TOKEN_QUOTA, "10")
    usage.record(
        agent_id="a1",
        user_id=uid,
        input_tokens=6,
        output_tokens=4,
        model="m",
        thread_id="t1",
    )
    with pytest.raises(OctopError) as exc:
        assert_token_quota_available(policies, usage, uid)
    assert exc.value.code is ErrorCode.TOKEN_QUOTA_EXCEEDED
    assert exc.value.details["used"] == 10
    assert exc.value.details["quota"] == 10
    policies.set(uid, POLICY_TOKEN_QUOTA, "11")
    assert_token_quota_available(policies, usage, uid)


def test_user_policy_repo_named_rows(db: SqlitePool, tmp_path: Path) -> None:
    users = UserRepo(db)
    policies = UserPolicyRepo(db)
    uid = users.create(username="alice", password_hash="h", role="user")
    jail = tmp_path / "jail"
    jail.mkdir()

    assert policies.list_for_user(uid) == []
    policies.merge(
        uid,
        {POLICY_WORKSPACE_ROOT_DIR: str(jail), POLICY_TOKEN_QUOTA: "42"},
    )
    kv = policies.enabled_values(uid)
    assert kv[POLICY_WORKSPACE_ROOT_DIR] == str(jail)
    assert kv[POLICY_TOKEN_QUOTA] == "42"
    assert public_policy_fields(policies.list_for_user(uid)) == {
        "workspace_root_dir": str(jail),
        "token_quota": 42,
    }
    root = policies.get(uid, POLICY_WORKSPACE_ROOT_DIR)
    assert root is not None
    assert root.policy_id
    assert root.enabled is True

    with db.connect() as conn:
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        policy_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(user_policies)").fetchall()
        }
    assert "workspace_root_dir" not in user_columns
    assert "token_quota" not in user_columns
    assert policy_columns == {
        "id",
        "policy_id",
        "user_id",
        "name",
        "enabled",
        "value",
        "created_at",
        "updated_at",
    }

    policies.set(uid, "future_flag", "1")
    policies.merge(uid, {POLICY_WORKSPACE_ROOT_DIR: None, POLICY_TOKEN_QUOTA: None})
    assert policies.enabled_values(uid) == {"future_flag": "1"}
    disabled = {row.name: row.enabled for row in policies.list_for_user(uid)}
    assert disabled[POLICY_WORKSPACE_ROOT_DIR] is False
    assert disabled[POLICY_TOKEN_QUOTA] is False
    assert disabled["future_flag"] is True

    other = users.create(username="bob", password_hash="h", role="user")
    policies.merge(other, {POLICY_WORKSPACE_ROOT_DIR: str(jail), POLICY_TOKEN_QUOTA: "7"})
    mapped = policies.enabled_values_by_user_ids([uid, other, uid + 99])
    assert mapped[uid] == {"future_flag": "1"}
    assert mapped[other][POLICY_TOKEN_QUOTA] == "7"
    assert uid + 99 not in mapped


def test_migration_moves_legacy_user_columns_to_policy_table(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "legacy.db")
    run_migrations(db)
    users = UserRepo(db)
    uid = users.create(username="alice", password_hash="h", role="user")
    with db.connect() as conn:
        conn.execute("ALTER TABLE users ADD COLUMN workspace_root_dir TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN token_quota INTEGER")
        conn.execute(
            "UPDATE users SET workspace_root_dir = ?, token_quota = ? WHERE id = ?",
            (tmp_path.as_posix(), 99, uid),
        )

    run_migrations(db)

    kv = UserPolicyRepo(db).enabled_values(uid)
    assert kv[POLICY_WORKSPACE_ROOT_DIR] == tmp_path.as_posix()
    assert kv[POLICY_TOKEN_QUOTA] == "99"
    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "workspace_root_dir" not in columns
    assert "token_quota" not in columns
    assert "user_policies" in tables
    assert "user_resource_policies" not in tables


def test_migration_moves_wide_resource_policy_table(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "wide.db")
    run_migrations(db)
    users = UserRepo(db)
    uid = users.create(username="alice", password_hash="h", role="user")
    with db.connect() as conn:
        conn.execute("DROP TABLE user_policies")
        conn.execute(
            """
            CREATE TABLE user_resource_policies (
              user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              workspace_root_dir TEXT,
              token_quota INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO user_resource_policies(user_id, workspace_root_dir, token_quota) "
            "VALUES (?, ?, ?)",
            (uid, tmp_path.as_posix(), 12),
        )

    run_migrations(db)

    kv = UserPolicyRepo(db).enabled_values(uid)
    assert kv[POLICY_WORKSPACE_ROOT_DIR] == tmp_path.as_posix()
    assert kv[POLICY_TOKEN_QUOTA] == "12"
    with db.connect() as conn:
        tables = {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(user_policies)")}
    assert "user_policies" in tables
    assert "user_resource_policies" not in tables
    assert "policy_id" in cols


def test_migration_rebuilds_legacy_kv_table(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "kv.db")
    run_migrations(db)
    users = UserRepo(db)
    uid = users.create(username="alice", password_hash="h", role="user")
    with db.connect() as conn:
        conn.execute("DROP TABLE user_policies")
        conn.execute(
            """
            CREATE TABLE user_policies (
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              key TEXT NOT NULL,
              value TEXT NOT NULL,
              PRIMARY KEY (user_id, key)
            )
            """
        )
        conn.execute(
            "INSERT INTO user_policies(user_id, key, value) VALUES (?, ?, ?)",
            (uid, POLICY_TOKEN_QUOTA, "8"),
        )

    run_migrations(db)

    row = UserPolicyRepo(db).get(uid, POLICY_TOKEN_QUOTA)
    assert row is not None
    assert row.enabled is True
    assert row.value == "8"
    assert row.policy_id
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_policies)")}
    assert "key" not in cols
    assert "policy_id" in cols
