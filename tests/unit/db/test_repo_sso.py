"""Tests for OIDC SSO repository access."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.sso import SsoRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "sso.db")
    run_migrations(pool)
    return pool


def test_login_code_single_consume(db: SqlitePool) -> None:
    repo = SsoRepo(db)
    now = int(time.time())
    provider = repo.upsert_provider(
        enabled=True,
        display_name="OneID",
        issuer="https://idp.example.com",
        client_id="client-id",
        client_secret_enc=b"encrypted-secret",
        scopes="openid profile email",
        dashboard_origin="https://octop.example.com",
    )
    repo.create_login_state(
        state="state-1",
        provider_id=provider.id,
        nonce="nonce-1",
        code_verifier="verifier-1",
        redirect_after="/chat",
        expires_at=now + 60,
    )
    repo.attach_login_code(
        "state-1",
        login_code="login-code-1",
        user_id=1,
        expires_at=now + 60,
    )

    assert repo.consume_login_code("login-code-1") == {"user_id": 1}
    assert repo.consume_login_code("login-code-1") is None


def test_provider_state_lookup_and_expiry_cleanup(db: SqlitePool) -> None:
    repo = SsoRepo(db)
    now = int(time.time())
    provider = repo.upsert_provider(
        enabled=True,
        display_name="OneID",
        issuer="https://idp.example.com",
        client_id="client-id",
        client_secret_enc=b"encrypted-secret",
        scopes="openid profile email",
        dashboard_origin="https://octop.example.com",
    )
    updated = repo.upsert_provider(
        enabled=False,
        display_name="Updated OneID",
        issuer="https://idp.example.com",
        client_id="client-id-2",
        client_secret_enc=None,
        scopes="openid",
        dashboard_origin=None,
    )
    repo.create_login_state(
        state="active-state",
        provider_id=provider.id,
        nonce="nonce-1",
        code_verifier="verifier-1",
        redirect_after="/chat",
        expires_at=now + 60,
    )
    repo.create_login_state(
        state="expired-state",
        provider_id=provider.id,
        nonce="nonce-2",
        code_verifier="verifier-2",
        redirect_after="/chat",
        expires_at=now,
    )

    assert repo.get_provider() == updated
    assert updated.client_secret_enc == b"encrypted-secret"
    claimed = repo.take_login_state("active-state")
    assert claimed is not None
    assert claimed.state == "active-state"
    assert claimed.consumed_at is not None
    assert repo.take_login_state("active-state") is None
    assert repo.take_login_state("expired-state") is None

    repo.delete_expired(now)

    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT state FROM sso_login_states WHERE state = ?", ("expired-state",)
            ).fetchone()
            is None
        )
