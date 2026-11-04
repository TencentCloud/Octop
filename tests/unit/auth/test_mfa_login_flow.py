"""Password login returns mfa_required when a verified factor exists."""

from __future__ import annotations

from pathlib import Path

import httpx
import pyotp
import pytest
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import TEST_PASSWORD, bootstrap_admin

from octop.api.app import build_app
from octop.infra.auth.mfa import totp as totp_mod
from octop.infra.auth.mfa.service import MfaService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer


@pytest.fixture()
async def env(tmp_path: Path):
    server = OctopServer(home=tmp_path)
    await server.start()
    await ensure_control_plane_bound(server)
    app = build_app(server)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await bootstrap_admin(client, tmp_path)
        yield server, client
    await server.stop()


def _enroll_totp(server: OctopServer, user_id: int, username: str) -> str:
    assert server.services is not None
    begun = totp_mod.begin_enroll(
        server.services.user_totp_repo,
        server.services.secret_repo,
        user_id,
        username=username,
    )
    secret = str(begun["secret"])
    code = pyotp.TOTP(secret).now()
    assert totp_mod.confirm_enroll(
        server.services.user_totp_repo,
        server.services.secret_repo,
        user_id,
        code,
    )
    return secret


@pytest.mark.asyncio
async def test_login_mfa_required_then_verify(env) -> None:
    server, client = env
    assert server.user_manager is not None and server.services is not None
    user = server.user_manager.get("admin")
    assert user is not None
    secret = _enroll_totp(server, user.id, user.username)

    r = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": TEST_PASSWORD},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("mfa_required") is True
    assert "access_token" not in body
    assert "mfa_token" in body
    assert "totp" in body["methods"]

    code = pyotp.TOTP(secret).now()
    vr = await client.post(
        "/api/auth/mfa/verify",
        json={"mfa_token": body["mfa_token"], "method": "totp", "code": code},
    )
    assert vr.status_code == 200
    assert "access_token" in vr.json()
    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {vr.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_mfa_throttle_does_not_set_login_lock(env) -> None:
    server, _client = env
    assert server.services is not None and server.user_manager is not None
    user = server.user_manager.get("admin")
    assert user is not None
    row_before = server.services.user_repo.get(user.id)
    assert row_before is not None
    login_locked = row_before.login_locked_until
    for _ in range(5):
        server.services.user_repo.record_mfa_failure(user.id, max_attempts=5, lockout_seconds=900)
    row = server.services.user_repo.get(user.id)
    assert row is not None
    assert row.mfa_locked_until > 0
    assert row.login_locked_until == login_locked


@pytest.mark.asyncio
async def test_recovery_refused_without_verified_factor(env) -> None:
    server, _client = env
    assert server.services is not None and server.user_manager is not None
    user = server.user_manager.get("admin")
    assert user is not None
    mfa = MfaService(server.services)
    assert not mfa.has_verified_factor(user.id)
    with pytest.raises(OctopError) as ei:
        mfa.recovery_regenerate(user, reauth_token="not-a-token")
    assert ei.value.code in {ErrorCode.MFA_REAUTH_REQUIRED, ErrorCode.MFA_INVALID}
