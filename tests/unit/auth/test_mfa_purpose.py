"""Purpose-aware JWT rejection and mfa_version checks."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import bootstrap_admin

from octop.api.app import build_app
from octop.api.deps import resolve_user_from_token
from octop.infra.auth.tokens import (
    PURPOSE_ACCESS,
    PURPOSE_MFA,
    PURPOSE_REAUTH,
    sign_token,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer


@pytest.fixture()
async def srv(tmp_path: Path):
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


@pytest.mark.asyncio
async def test_mfa_and_reauth_purpose_rejected(srv) -> None:
    server, _client = srv
    assert server.user_manager is not None and server.services is not None
    user = server.user_manager.get("admin")
    assert user is not None
    secret = server.services.secret_repo.get("jwt")
    assert secret is not None
    mfa = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_MFA,
        ttl_seconds=60,
        amr="password",
        mfa_version=0,
    )
    reauth = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_REAUTH,
        ttl_seconds=60,
    )
    with pytest.raises(OctopError) as ei:
        resolve_user_from_token(server, mfa)
    assert ei.value.code is ErrorCode.AUTH_FAILED
    with pytest.raises(OctopError) as ei2:
        resolve_user_from_token(server, reauth)
    assert ei2.value.code is ErrorCode.AUTH_FAILED


@pytest.mark.asyncio
async def test_mfa_version_mismatch_rejects_access(srv) -> None:
    server, _client = srv
    assert server.user_manager is not None and server.services is not None
    user = server.user_manager.get("admin")
    assert user is not None
    secret = server.services.secret_repo.get("jwt")
    assert secret is not None
    token = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_ACCESS,
        mfa_version=0,
    )
    server.services.user_repo.bump_mfa_version(user.id)
    with pytest.raises(OctopError) as ei:
        resolve_user_from_token(server, token)
    assert ei.value.code is ErrorCode.AUTH_FAILED


@pytest.mark.asyncio
async def test_query_access_token_rejects_mfa_purpose(srv) -> None:
    server, client = srv
    assert server.user_manager is not None and server.services is not None
    user = server.user_manager.get("admin")
    assert user is not None
    secret = server.services.secret_repo.get("jwt")
    assert secret is not None
    mfa = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_MFA,
        ttl_seconds=60,
        amr="password",
    )
    r = await client.get("/api/auth/me", params={"access_token": mfa})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"
