"""Unit tests for JWT auth middleware."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound, write_octop_config
from tests.support.auth import bearer, bootstrap_admin, login

from octop.api.app import build_app
from octop.api.deps import (
    ACCESS_TOKEN_RESPONSE_HEADER,
    decode_token,
    is_jwt_exempt_path,
    maybe_sliding_renew_token,
    sign_token,
)
from octop.infra.server import OctopServer


def test_exempt_paths() -> None:
    assert is_jwt_exempt_path("/api/health")
    assert is_jwt_exempt_path("/api/health/")
    assert is_jwt_exempt_path("/api/setup/status")
    assert is_jwt_exempt_path("/api/auth/login")
    assert is_jwt_exempt_path("/api/docs")
    assert is_jwt_exempt_path("/api/openapi.json")
    assert not is_jwt_exempt_path("/api/auth/me")
    assert not is_jwt_exempt_path("/api/agents")


@pytest.fixture
async def client(tmp_path: Path):
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c, srv, tmp_path
    await srv.stop()


async def test_middleware_blocks_unauthenticated_api(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    r = await c.get("/api/agents")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_middleware_allows_login_without_token(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    r = await c.post("/api/auth/login", json={"username": "admin", "password": "pw"})
    assert r.status_code == 200


async def test_middleware_allows_api_docs_without_token(tmp_path: Path) -> None:
    write_octop_config(tmp_path, enable_api_docs=True)
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            await bootstrap_admin(c, tmp_path)
            r = await c.get("/api/docs")
            assert r.status_code == 200
            spec = await c.get("/api/openapi.json")
            assert spec.status_code == 200
    finally:
        await srv.stop()


async def test_fresh_token_does_not_sliding_renew(client) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    token = await login(c)
    r = await c.get("/api/auth/me", headers=bearer(token))
    assert r.status_code == 200
    assert ACCESS_TOKEN_RESPONSE_HEADER not in r.headers


async def test_near_expiry_token_gets_sliding_renew(client) -> None:
    c, srv, home = client
    await bootstrap_admin(c, home)
    assert srv.user_manager is not None
    assert srv.services is not None
    user = srv.user_manager.get("admin")
    assert user is not None
    secret = srv.services.secret_repo.get("jwt")
    assert secret is not None
    # Remaining life (~60s) is far below default TTL/3 (~8h) → renew.
    short = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role.value,
        ttl_seconds=60,
    )
    r = await c.get("/api/auth/me", headers=bearer(short))
    assert r.status_code == 200
    renewed = r.headers.get(ACCESS_TOKEN_RESPONSE_HEADER)
    assert renewed
    assert renewed != short
    payload = decode_token(secret, renewed)
    assert int(payload["exp"]) - int(payload["iat"]) == srv.services.config.access_token_ttl_seconds


async def test_maybe_sliding_renew_helper_threshold(client) -> None:
    _c, srv, home = client
    await bootstrap_admin(_c, home)
    assert srv.user_manager is not None
    assert srv.services is not None
    user = srv.user_manager.get("admin")
    assert user is not None
    secret = srv.services.secret_repo.get("jwt")
    assert secret is not None
    ttl = srv.services.config.access_token_ttl_seconds
    fresh = sign_token(
        secret, sub=user.id, uname=user.username, role=user.role.value, ttl_seconds=ttl
    )
    assert maybe_sliding_renew_token(srv, fresh, user) is None
    short = sign_token(
        secret, sub=user.id, uname=user.username, role=user.role.value, ttl_seconds=60
    )
    renewed = maybe_sliding_renew_token(srv, short, user)
    assert renewed is not None
    assert renewed != short
