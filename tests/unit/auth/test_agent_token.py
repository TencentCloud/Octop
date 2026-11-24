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
from octop.infra.auth.agent_access import agent_request_allowed, mint_agent_token
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
    ],
)
def test_agent_request_boundary(method: str, path: str, allowed: bool) -> None:
    assert agent_request_allowed(method, path) is allowed


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
