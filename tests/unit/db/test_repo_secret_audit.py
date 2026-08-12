"""tests/unit/test_repo_secret_audit.py"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.audit import AuditRepo, AuditRow
from octop.infra.db.repos.secrets import SecretRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def secrets(db: SqlitePool) -> SecretRepo:
    return SecretRepo(db)


@pytest.fixture
def audit(db: SqlitePool) -> AuditRepo:
    return AuditRepo(db)


def test_secret_get_or_create(secrets: SecretRepo):
    val1 = secrets.get_or_create("jwt_secret", lambda: b"initial_value")
    assert val1 == b"initial_value"
    # Second call returns the original value, not a new one
    val2 = secrets.get_or_create("jwt_secret", lambda: b"new_value")
    assert val2 == b"initial_value"


def test_secret_rotate(secrets: SecretRepo):
    secrets.get_or_create("jwt_secret", lambda: b"old_value")
    before = int(time.time())
    secrets.rotate("jwt_secret", b"new_value")
    val = secrets.get("jwt_secret")
    assert val == b"new_value"
    # rotated_at should be set
    with secrets._db.connect() as conn:
        row = conn.execute("SELECT rotated_at FROM secrets WHERE k = ?", ("jwt_secret",)).fetchone()
    assert row["rotated_at"] >= before


def test_audit_write_and_query(audit: AuditRepo):
    audit.write(actor="alice", action="login")
    audit.write(actor="bob", action="login")
    audit.write(actor="alice", action="create_agent", target="agent:1")

    all_rows = audit.query()
    assert len(all_rows) == 3
    # Should be ordered by ts DESC
    assert isinstance(all_rows[0], AuditRow)

    alice_rows = audit.query(actor="alice")
    assert len(alice_rows) == 2
    assert all(r.actor == "alice" for r in alice_rows)

    action_rows = audit.query(action="login")
    assert len(action_rows) == 2
    assert all(r.action == "login" for r in action_rows)


def test_audit_query_target_actions_is_paginated(audit: AuditRepo):
    audit.write(actor="_system", action="cron.run_ok", target="cron-1")
    audit.write(
        actor="_system",
        action="cron.run_failed",
        target="cron-1",
        payload="boom",
    )
    audit.write(actor="alice", action="cron.create", target="cron-1")
    audit.write(actor="_system", action="cron.run_ok", target="cron-2")

    rows, total = audit.query_target_actions(
        target="cron-1",
        actions=("cron.run_ok", "cron.run_failed"),
        limit=1,
        offset=0,
    )

    assert total == 2
    assert len(rows) == 1
    assert rows[0].action == "cron.run_failed"
    assert rows[0].payload == "boom"

    second_page, second_total = audit.query_target_actions(
        target="cron-1",
        actions=("cron.run_ok", "cron.run_failed"),
        limit=1,
        offset=1,
    )
    assert second_total == 2
    assert [row.action for row in second_page] == ["cron.run_ok"]
