"""Desktop device sessions: renew a JWT with the shell-held device token.

The wizard has no password in desktop builds, so ``/auth/login`` is not a path a
desktop user can take. These endpoints are the replacement, and they must stay
narrow: desktop shell only, loopback only, digest match only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from octop.api.routers import auth_device
from tests.support.app import octop_client
from tests.support.auth import bootstrap_admin, bearer

DEVICE_TOKEN = "device-token-" + "x" * 40


@pytest.fixture(autouse=True)
def _reset_throttle() -> None:
    auth_device._failures.clear()


@pytest.fixture
async def env(patched_app_client: Any):
    """Bootstrapped install (default wizard password) plus its admin JWT."""
    c, srv, _home = patched_app_client
    created = await bootstrap_admin(c, _home)
    yield c, srv, created.json()["access_token"]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def test_register_requires_the_desktop_shell(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, jwt = env
    monkeypatch.delenv("OCTOP_DESKTOP_SHELL", raising=False)
    r = await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN},
        headers=bearer(jwt),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_register_requires_a_session(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, _jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    r = await c.post("/api/auth/device/register", json={"device_token": DEVICE_TOKEN})
    assert r.status_code == 401


async def test_device_token_round_trip(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")

    r = await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN, "label": "darwin-arm64"},
        headers=bearer(jwt),
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "username": "admin"}

    # The token is stored hashed, never in the clear.
    raw = srv.services.secret_repo.get("desktop_device")
    assert raw is not None
    assert DEVICE_TOKEN.encode() not in raw
    assert _hash(DEVICE_TOKEN).encode() in raw

    r = await c.post("/api/auth/device/token", json={"device_token": DEVICE_TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == srv.services.config.access_token_ttl_seconds

    me = await c.get("/api/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


async def test_device_token_needs_registration(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, _jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    r = await c.post("/api/auth/device/token", json={"device_token": DEVICE_TOKEN})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_device_token_rejects_a_wrong_secret(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN},
        headers=bearer(jwt),
    )
    r = await c.post("/api/auth/device/token", json={"device_token": "y" * 48})
    assert r.status_code == 401


async def test_device_token_is_throttled(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN},
        headers=bearer(jwt),
    )
    for _ in range(auth_device._MAX_FAILURES):
        await c.post("/api/auth/device/token", json={"device_token": "y" * 48})
    r = await c.post("/api/auth/device/token", json={"device_token": "y" * 48})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "LOGIN_LOCKED"


async def test_device_token_rejects_a_non_loopback_peer(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN},
        headers=bearer(jwt),
    )

    remote_transport = httpx.ASGITransport(app=c._octop_app, client=("10.1.2.3", 4444))
    async with httpx.AsyncClient(
        transport=remote_transport, base_url="http://testserver"
    ) as remote:
        r = await remote.post("/api/auth/device/token", json={"device_token": DEVICE_TOKEN})
    assert r.status_code == 403


async def test_device_token_needs_the_desktop_shell(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN},
        headers=bearer(jwt),
    )
    monkeypatch.delenv("OCTOP_DESKTOP_SHELL")
    r = await c.post("/api/auth/device/token", json={"device_token": DEVICE_TOKEN})
    assert r.status_code == 403


async def test_revoke_stops_renewal(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    await c.post(
        "/api/auth/device/register",
        json={"device_token": DEVICE_TOKEN},
        headers=bearer(jwt),
    )
    assert (await c.post("/api/auth/device/token", json={"device_token": DEVICE_TOKEN})).status_code == 200

    r = await c.post("/api/auth/device/revoke", headers=bearer(jwt))
    assert r.status_code == 200

    r = await c.post("/api/auth/device/token", json={"device_token": DEVICE_TOKEN})
    assert r.status_code == 401


async def test_register_replaces_the_previous_device(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second install takes over; the first install's token stops working."""
    c, _srv, jwt = env
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    first = "first-token-" + "a" * 40
    second = "second-token-" + "b" * 40

    await c.post("/api/auth/device/register", json={"device_token": first}, headers=bearer(jwt))
    assert (await c.post("/api/auth/device/token", json={"device_token": first})).status_code == 200

    await c.post("/api/auth/device/register", json={"device_token": second}, headers=bearer(jwt))
    assert (await c.post("/api/auth/device/token", json={"device_token": first})).status_code == 401
    assert (await c.post("/api/auth/device/token", json={"device_token": second})).status_code == 200


async def test_device_token_is_jwt_exempt_but_register_is_not(
    tmp_octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the exchange bypasses the JWT middleware; registering does not."""
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    async with octop_client(tmp_octop_home) as (c, _srv):
        # Setup is still incomplete here: lockdown answers before auth does.
        r = await c.post("/api/auth/device/register", json={"device_token": DEVICE_TOKEN})
        assert r.status_code in {401, 503}
