"""``agent`` tokens and the ``octop_api`` tool: the conversation's user, inside a boundary."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from langgraph.config import var_child_runnable_config
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import bootstrap_admin

from octop.api.app import build_app
from octop.api.deps import resolve_user_from_token
from octop.infra.agents.octop_api import build_octop_api_tool, is_write_call
from octop.infra.auth.agent_access import agent_request_allowed, mint_agent_token, routed_path
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer


@contextmanager
def _turn(**configurable: object) -> Iterator[None]:
    token = var_child_runnable_config.set({"configurable": configurable})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


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
        yield server
    await server.stop()


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/api/agents", True),
        ("POST", "/api/cron/jobs", True),
        ("DELETE", "/api/agents/a1", True),
        ("GET", "/api/auth/me", True),
        ("POST", "/api/auth/login", False),
        ("GET", "/api/auth/mfa/status", False),
        ("POST", "/api/auth/me", False),
        ("POST", "/api/setup/finish", False),
        ("GET", "/api/admin/security/policy", False),
        ("PUT", "/api/admin/tls/config", False),
        ("POST", "/api/users/2/reset-password", False),
        ("DELETE", "/api/users/2/mfa", False),
        ("GET", "/api/terminal/sessions", False),
        ("POST", "/api/internal/mcp/x/y", False),
        ("GET", "/api/../api/auth/login", False),
        ("GET", "/health", False),
        ("OPTIONS", "/api/agents", False),
        ("GET", "/api/admin/app-config", True),
        ("PUT", "/api/admin/app-config", False),
        ("PUT", "/api/admin/app-config/raw", False),
        ("PUT", "/api/settings/captcha", False),
        ("PUT", "/api/settings/webauthn", False),
    ],
)
def test_agent_request_boundary(method: str, path: str, allowed: bool) -> None:
    assert agent_request_allowed(method, path) is allowed


@pytest.mark.parametrize(
    ("raw", "routed"),
    [
        ("/api/agents?x=1", "/api/agents"),
        ("/api/%61uth/login", "/api/auth/login"),
        ("/api/admin/app-config%2Fraw", "/api/admin/app-config/raw"),
        ("/api/agents/%2e%2e/auth/login", None),
        ("/api//auth/login", None),
        ("/api/auth\\login", None),
        ("/api/agents%00", None),
    ],
)
def test_routed_path(raw: str, routed: str | None) -> None:
    assert routed_path(raw) == routed


def _admin_token(server: OctopServer) -> tuple[int, str]:
    assert server.user_manager is not None and server.services is not None
    user = server.user_manager.get("admin")
    assert user is not None
    return user.id, mint_agent_token(server.services.repos, user_id=user.id, agent_id="main")


@pytest.mark.asyncio
async def test_agent_token_accepted_only_inside_boundary(srv) -> None:
    user_id, token = _admin_token(srv)
    user = resolve_user_from_token(srv, token, method="GET", path="/api/agents")
    assert user.id == user_id
    for kwargs in ({}, {"method": "POST", "path": "/api/auth/login"}):
        with pytest.raises(OctopError) as ei:
            resolve_user_from_token(srv, token, **kwargs)
        assert ei.value.code is ErrorCode.FORBIDDEN


@pytest.mark.asyncio
async def test_agent_token_dies_with_password_change(srv) -> None:
    user_id, token = _admin_token(srv)
    srv.services.user_repo.set_password_hash(user_id, "changed")
    with pytest.raises(OctopError) as ei:
        resolve_user_from_token(srv, token, method="GET", path="/api/agents")
    assert ei.value.code is ErrorCode.AUTH_FAILED


@pytest.mark.asyncio
async def test_tool_calls_api_as_turn_user(srv) -> None:
    user_id, _ = _admin_token(srv)
    tool = build_octop_api_tool(srv.services.repos)
    with _turn(user=user_id, agent_id="main"):
        me = json.loads(await tool.ainvoke({"method": "GET", "path": "/api/auth/me"}))
        blocked = json.loads(await tool.ainvoke({"method": "POST", "path": "/api/auth/login"}))
    assert me["status"] == 200
    assert me["body"]["username"] == "admin"
    assert "not available" in blocked["error"]


@pytest.mark.asyncio
async def test_tool_refuses_without_turn_user(srv) -> None:
    tool = build_octop_api_tool(srv.services.repos)
    with _turn(agent_id="main"):
        out = json.loads(await tool.ainvoke({"method": "GET", "path": "/api/agents"}))
    assert "error" in out


def test_only_writes_need_approval() -> None:
    def req(method: str) -> SimpleNamespace:
        return SimpleNamespace(tool_call={"args": {"method": method, "path": "/api/agents"}})

    assert not is_write_call(req("GET"))
    assert not is_write_call(req("get"))
    assert is_write_call(req("POST"))
    assert is_write_call(req("DELETE"))


@pytest.mark.asyncio
async def test_encoded_login_path_is_refused_by_tool_and_server(srv) -> None:
    from tests.support.auth import TEST_PASSWORD

    user_id, token = _admin_token(srv)
    login = {"username": "admin", "password": TEST_PASSWORD}
    tool = build_octop_api_tool(srv.services.repos)
    with _turn(user=user_id, agent_id="main"):
        out = json.loads(
            await tool.ainvoke({"method": "POST", "path": "/api/%61uth/login", "body": login})
        )
    assert "not available" in out["error"]

    # Even past the tool, the server refuses an agent token on the JWT-exempt
    # login route; the same request without it still signs in.
    app = build_app(srv)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        as_agent = await client.post(
            "/api/%61uth/login", json=login, headers={"Authorization": f"Bearer {token}"}
        )
        as_person = await client.post("/api/%61uth/login", json=login)
    assert as_agent.status_code == 403
    assert as_person.status_code == 200


@pytest.mark.asyncio
async def test_agent_cannot_write_app_config(srv) -> None:
    user_id, token = _admin_token(srv)
    tool = build_octop_api_tool(srv.services.repos)
    with _turn(user=user_id, agent_id="main"):
        read = json.loads(await tool.ainvoke({"method": "GET", "path": "/api/admin/app-config"}))
        structured = json.loads(
            await tool.ainvoke(
                {"method": "PUT", "path": "/api/admin/app-config", "body": {"config": {}}}
            )
        )
        raw = json.loads(
            await tool.ainvoke(
                {"method": "PUT", "path": "/api/admin/app-config/raw", "body": {"text": "{}"}}
            )
        )
    assert read["status"] == 200
    assert "not available" in structured["error"]
    assert "not available" in raw["error"]

    app = build_app(srv)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = {"Authorization": f"Bearer {token}"}
        put_form = await client.put("/api/admin/app-config", json={"config": {}}, headers=headers)
        put_raw = await client.put(
            "/api/admin/app-config/raw", json={"text": "{}"}, headers=headers
        )
    assert put_form.status_code == 403
    assert put_raw.status_code == 403
