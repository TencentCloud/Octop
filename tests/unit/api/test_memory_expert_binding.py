"""Expert bindings grant scoped access through a private Memory credential."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.tools import StructuredTool

from octop.api.routers import memory_sharing as router
from octop.infra.agents import memory_shared_access, memory_sharing
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OCTOP_MEMORY_SERVICE_URL", "https://memory.example.test")
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    repo = SecretRepo(db)
    row = SimpleNamespace(
        agent_id="alpha",
        user_id=7,
        kind="expert",
        is_shared=0,
        config_json='{"memory_sharing": {"space_id": "legacy-space"}}',
    )
    registry = SimpleNamespace(get_row=lambda _: row, reload=AsyncMock())
    server = SimpleNamespace(
        app_runtime=SimpleNamespace(agent_registry=registry),
        services=SimpleNamespace(repos=SimpleNamespace(secret_repo=repo)),
    )
    owner = SimpleNamespace(id=7, is_admin=False)
    issue = Mock(return_value={"token_id": "shared-1", "token": "omcp_test_secret"})
    monkeypatch.setattr(
        memory_sharing, "list_spaces", lambda _: {"spaces": [{"space_id": "project"}]}
    )
    monkeypatch.setattr(
        memory_sharing,
        "list_tokens_in",
        lambda *_: {"tokens": [{"token_id": "shared-1", "token_hint": "cret"}]},
    )
    monkeypatch.setattr(memory_sharing, "create_token_in", issue)
    yield SimpleNamespace(server=server, row=row, owner=owner, repo=repo, issue=issue)
    db.close()


@pytest.mark.asyncio
async def test_binding_is_reusable_and_keeps_token_out_of_agent_config(setup) -> None:
    assert router.binding("alpha", setup.owner, setup.server) == {
        "agent_id": "alpha",
        "space_id": "legacy-space",
        "has_credential": False,
        "can_manage": True,
    }
    body = router.BindBody(agent_id="alpha", space_id="project")
    first, repeated = await asyncio.gather(
        router.bind(body, setup.owner, setup.server),
        router.bind(body, setup.owner, setup.server),
    )

    assert first == repeated == router.binding("alpha", setup.owner, setup.server)
    assert first == {
        "agent_id": "alpha",
        "space_id": "project",
        "has_credential": True,
        "can_manage": True,
    }
    setup.issue.assert_called_once_with(7, "project", "Octop expert alpha", ["read", "write"])
    stored = setup.repo.get("memory_sharing.expert.alpha")
    assert stored is not None and b"omcp_test_secret" not in stored
    assert "omcp_test_secret" not in setup.row.config_json


@pytest.mark.asyncio
async def test_binding_replaces_token_rotated_outside_octop(
    setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = router.BindBody(agent_id="alpha", space_id="project")
    await router.bind(body, setup.owner, setup.server)
    monkeypatch.setattr(
        memory_sharing,
        "list_tokens_in",
        lambda *_: {"tokens": [{"token_id": "shared-1", "token_hint": "new1"}]},
    )
    setup.issue.return_value = {"token_id": "shared-2", "token": "omcp_replacement"}
    revoke = Mock(return_value={"revoked": True})
    monkeypatch.setattr(memory_sharing, "revoke_token", revoke)

    result = await router.bind(body, setup.owner, setup.server)

    assert result["has_credential"] is True
    assert setup.issue.call_count == 2
    revoke.assert_called_once_with(7, "shared-1")
    saved = memory_shared_access.get_expert_binding(setup.repo, "alpha")
    assert saved is not None and saved.token_id == "shared-2"


@pytest.mark.asyncio
async def test_retry_after_failed_reload_does_not_reissue_or_revoke_twice(
    setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = setup.server.app_runtime.agent_registry
    registry.reload.side_effect = [RuntimeError("failed"), None, RuntimeError("failed"), None]
    body = router.BindBody(agent_id="alpha", space_id="project")
    with pytest.raises(RuntimeError, match="failed"):
        await router.bind(body, setup.owner, setup.server)
    await router.bind(body, setup.owner, setup.server)
    setup.issue.assert_called_once()

    revoke = Mock(return_value={"revoked": True})
    monkeypatch.setattr(memory_sharing, "revoke_token", revoke)
    unbind = router.BindBody(agent_id="alpha", space_id=None)
    with pytest.raises(RuntimeError, match="failed"):
        await router.bind(unbind, setup.owner, setup.server)
    assert (await router.bind(unbind, setup.owner, setup.server))["space_id"] is None
    revoke.assert_called_once_with(7, "shared-1")


@pytest.mark.asyncio
async def test_binding_requires_local_owner_allowed_space_and_private_expert(setup) -> None:
    body = router.BindBody(agent_id="alpha", space_id="project")
    for unauthorized, actor in (
        (body, SimpleNamespace(id=8, is_admin=False)),
        (router.BindBody(agent_id="alpha", space_id="not-authorized"), setup.owner),
    ):
        with pytest.raises(OctopError) as caught:
            await router.bind(unauthorized, actor, setup.server)
        assert caught.value.code == ErrorCode.FORBIDDEN
    setup.row.is_shared = 1
    with pytest.raises(OctopError) as caught:
        await router.bind(body, setup.owner, setup.server)
    assert caught.value.code == ErrorCode.FORBIDDEN
    setup.issue.assert_not_called()


@pytest.mark.asyncio
async def test_unbinding_blocks_stale_mcp_tool_even_if_remote_revocation_fails(
    setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    await router.bind(
        router.BindBody(agent_id="alpha", space_id="project"), setup.owner, setup.server
    )

    async def search(query: str) -> tuple[str, dict[str, str]]:
        return query, {"query": query}

    load = Mock(
        return_value=[
            StructuredTool.from_function(
                coroutine=search,
                name="octop_shared_memory_search",
                description="Search memory",
                response_format="content_and_artifact",
            )
        ]
    )
    monkeypatch.setattr(memory_shared_access, "load_mcp_tools", load)
    tools = memory_shared_access.shared_memory_tools(setup.row, setup.repo, lambda _: setup.row)
    assert len(tools) == 1
    result = await tools[0].ainvoke(
        {
            "type": "tool_call",
            "id": "call-1",
            "name": "octop_shared_memory_search",
            "args": {"query": "old memory"},
        }
    )
    assert result.content == "old memory"
    assert result.artifact == {"query": "old memory"}
    spec = load.call_args.args[0]["octop_shared"]
    assert spec["headers"] == {
        "Authorization": "Bearer omcp_test_secret",
        "X-Octop-Space": "project",
    }
    assert spec["allowed_tools"] == ("memory_search", "memory_get", "memory_save", "memory_capture")
    revoke = Mock(side_effect=OctopError(ErrorCode.FORBIDDEN, "different space"))
    monkeypatch.setattr(memory_sharing, "revoke_token", revoke)

    result = await router.bind(
        router.BindBody(agent_id="alpha", space_id=None), setup.owner, setup.server
    )

    assert result["previous_token_revoked"] is False
    assert router.binding("alpha", setup.owner, setup.server)["space_id"] is None
    assert "Shared memory access changed" in await tools[0].ainvoke({"query": "old memory"})
    assert (
        memory_shared_access.shared_memory_tools(setup.row, setup.repo, lambda _: setup.row) == []
    )
    revoke.assert_called_once_with(7, "shared-1")
