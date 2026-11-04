"""Shared fixtures for integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from octop.api.app import build_app
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from tests.support.app import octop_client
from tests.support.auth import (
    auth_header,
    bootstrap_admin,
    create_agent,
    create_provider,
    create_user,
    resolve_user_id,
    seed_openai_provider,
)
from tests.support.fakes import FakeHarnessAgent
from tests.support.harness import patch_harness
from tests.support.scenarios import bootstrap_boundary_env

__all__ = [
    "bootstrap_admin",
    "patch_harness",
]


@pytest.fixture(autouse=True)
def _disable_remote_market(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep expert/plugin bootstrap off the public market during integration tests."""
    monkeypatch.setenv("OCTOP_PORTAL_ORIGIN", "")


@pytest.fixture
async def app_client(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, Path]]:
    """HTTP client + server before setup wizard completes."""
    async with octop_client(tmp_octop_home, patch_llm=False) as (client, srv):
        yield client, srv, tmp_octop_home


@pytest.fixture
async def patched_app_client(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, Path]]:
    """HTTP client + server with harness patched (pre-setup wizard tests)."""
    async with octop_client(tmp_octop_home) as (client, srv):
        yield client, srv, tmp_octop_home


@pytest.fixture
async def env(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str]]]:
    """Admin-authenticated client (no shared provider pre-seeded)."""
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        yield client, srv, auth


@pytest.fixture
async def env_admin_client(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str]]]:
    """``(client, admin auth)`` — no server handle."""
    client, _srv, auth = env
    yield client, auth


@pytest.fixture
async def env_with_provider(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str]]]:
    """``env`` plus a shared OpenAI provider for agent CRUD tests."""
    client, srv, auth = env
    await seed_openai_provider(client, auth)
    yield client, srv, auth


@pytest.fixture
async def env_with_agent(
    env_with_provider: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], str]]:
    """``env_with_provider`` plus a default test agent."""
    client, srv, auth = env_with_provider
    agent_id = await create_agent(client, auth)
    yield client, srv, auth, agent_id


@pytest.fixture
async def env_with_main_agent(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], str]]:
    """``env`` plus the bootstrap ``main`` agent."""
    client, srv, auth = env
    agents = (await client.get("/api/agents", headers=auth)).json()
    assert agents, "bootstrap should have created the main agent"
    yield client, srv, auth, agents[0]["agent_id"]


@pytest.fixture
async def env_with_provider_record(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], int]]:
    """``env`` plus a created OpenAI provider; yields provider row id."""
    client, srv, auth = env
    row = await create_provider(
        client,
        auth,
        api_key="sk-x",
        base_url="https://api.openai.com/v1",
    )
    yield client, srv, auth, row["id"]


@pytest.fixture
async def env_alice_bob_agent(
    env_with_provider: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], dict[str, str], str]]:
    """Two regular users plus alice-owned agent (channels / cron isolation)."""
    from tests.support.auth import ensure_users

    client, srv, admin_auth = env_with_provider
    users = await ensure_users(client, admin_auth, "alice", "bob")
    r = await client.post(
        "/api/agents",
        headers=users["alice"],
        json={
            "name": "alice-channels-bot",
            "config": {
                "providers": ["openai"],
                "default_model": "openai:gpt-4o-mini",
            },
        },
    )
    r.raise_for_status()
    agent_id = r.json()["agent_id"]
    yield client, srv, users["alice"], users["bob"], agent_id


@pytest.fixture
async def env_admin_alice(
    env_with_provider: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], dict[str, str]]]:
    client, srv, admin_auth = env_with_provider
    alice_auth = await create_user(client, admin_auth, username="alice")
    yield client, srv, admin_auth, alice_auth


@pytest.fixture
async def env_usage(
    env_admin_alice: tuple[httpx.AsyncClient, OctopServer, dict[str, str], dict[str, str]],
) -> AsyncIterator[
    tuple[httpx.AsyncClient, OctopServer, dict[str, str], dict[str, str], dict[str, int]]
]:
    client, srv, admin_auth, alice_auth = env_admin_alice
    alice_id = await resolve_user_id(client, admin_auth, "alice")
    yield client, srv, admin_auth, alice_auth, {"alice_id": alice_id}


@pytest.fixture
async def env_boundary(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[
    tuple[
        httpx.AsyncClient,
        OctopServer,
        dict[str, str],
        dict[str, str],
        dict[str, str],
        dict[str, Any],
    ]
]:
    client, srv, admin_auth = env
    alice_auth, bob_auth, ctx = await bootstrap_boundary_env(client, srv, admin_auth)
    yield client, srv, admin_auth, alice_auth, bob_auth, ctx


@pytest.fixture
async def env_acp_agent(
    env: tuple[httpx.AsyncClient, OctopServer, dict[str, str]],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], str]]:
    client, srv, auth = env
    agent_id = await create_agent(client, auth, name="acp-bot", config={})
    yield client, srv, auth, agent_id


@pytest.fixture
async def env_with_channel(
    env_with_agent: tuple[httpx.AsyncClient, OctopServer, dict[str, str], str],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], str, int]]:
    client, srv, auth, agent_id = env_with_agent
    r = await client.post(
        f"/api/agents/{agent_id}/channels",
        headers=auth,
        json={"kind": "feishu", "name": "main", "config": {"app_id": "x"}},
    )
    r.raise_for_status()
    yield client, srv, auth, agent_id, r.json()["id"]


@pytest.fixture
async def env_skills_offline(
    env_with_main_agent: tuple[httpx.AsyncClient, OctopServer, dict[str, str], str],
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, dict[str, str], str]]:
    """Main agent with registry patched to simulate agent-not-running."""
    client, srv, auth, agent_id = env_with_main_agent

    def _agent_not_running(_agent_id: str) -> None:
        raise OctopError(ErrorCode.AGENT_NOT_RUNNING, f"agent {_agent_id!r} not running")

    with patch.object(
        srv.app_runtime.agent_registry,
        "get_agent",
        side_effect=_agent_not_running,
    ):
        yield client, srv, auth, agent_id


@pytest.fixture
async def env_terminal(
    env_with_main_agent: tuple[httpx.AsyncClient, OctopServer, dict[str, str], str],
) -> AsyncIterator[tuple[OctopServer, Any, str, str]]:
    """``(server, app, token, agent_id)`` for terminal route tests."""
    client, srv, auth, agent_id = env_with_main_agent
    tok = auth["Authorization"].split(" ", 1)[1]
    yield srv, build_app(srv), tok, agent_id


@pytest.fixture
async def env_fake_harness(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer, FakeHarnessAgent, Path]]:
    """Patched harness with default greeting tokens — golden-path tests."""
    fake = FakeHarnessAgent(
        chunks=[
            {"type": "token", "node": "agent", "content": "Hi "},
            {"type": "token", "node": "agent", "content": "Alice."},
        ]
    )
    async with octop_client(tmp_octop_home, fake_agent=fake) as (client, srv):
        yield client, srv, fake, tmp_octop_home
