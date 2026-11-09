"""Regression tests for media backends after a late agent start / reload.

Gateway boots before agents, so ``refresh_media_backends()`` has to run again
once an agent is loaded. The server boot and backup-restore paths already do
this; the ``start`` and ``reload`` endpoints did not, leaving channels bound to
that agent with ``_media_backend is None`` (inbound IM images are downloaded
and then silently discarded).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers import agents as agents_router
from octop.infra.errors import OctopError
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend

_AGENT_ID = "agent-1"
_CHANNEL_ID = "channel-1"
_OWNER = SimpleNamespace(id=1, is_admin=False)
_ROW = SimpleNamespace(user_id=1)


def _server(*, gateway: Any, fail: bool = False, missing: bool = False) -> MagicMock:
    registry = MagicMock()
    registry.get_row.return_value = None if missing else _ROW
    registry.start = AsyncMock(side_effect=RuntimeError("boot failed") if fail else None)
    registry.reload = AsyncMock()
    server = MagicMock()
    server.app_runtime.agent_registry = registry
    server.app_runtime.gateway = gateway
    return server


def _missing_agent(_agent_id: str) -> Any:
    raise KeyError(_agent_id)


def _real_gateway(*, loaded: bool) -> tuple[Gateway, list[Any], object]:
    """A Gateway with real ``refresh_media_backends`` and fake collaborators."""
    workspace = object()
    agent_manager = SimpleNamespace(
        get_agent=(lambda _id: SimpleNamespace(workspace=workspace)) if loaded else _missing_agent,
        octop_config=SimpleNamespace(max_upload_bytes=1024),
    )
    attached: list[Any] = []
    channel = SimpleNamespace(set_media_backend=attached.append)
    channel_manager = SimpleNamespace(get_channel=lambda _cid: channel)
    channel_repo = SimpleNamespace(
        list_all=lambda *, include_disabled: [
            SimpleNamespace(channel_id=_CHANNEL_ID, agent_id=_AGENT_ID)
        ]
    )
    gateway = Gateway.__new__(Gateway)
    gateway._agent_manager = agent_manager
    gateway._repos = SimpleNamespace(channel_repo=channel_repo)
    gateway._channel_manager = channel_manager
    return gateway, attached, workspace


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["start_agent", "reload_agent"])
async def test_agent_endpoint_refreshes_media_backends(endpoint: str) -> None:
    refresh = AsyncMock()
    server = _server(gateway=SimpleNamespace(refresh_media_backends=refresh))

    await getattr(agents_router, endpoint)(_AGENT_ID, user=_OWNER, server=server)

    refresh.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["start_agent", "reload_agent"])
async def test_agent_endpoint_attaches_a_real_media_backend(endpoint: str) -> None:
    """The refresh must actually resolve the freshly loaded agent's workspace."""
    gateway, attached, workspace = _real_gateway(loaded=True)
    server = _server(gateway=gateway)

    await getattr(agents_router, endpoint)(_AGENT_ID, user=_OWNER, server=server)

    assert len(attached) == 1, "the channel must receive a media backend after reload"
    backend = attached[0]
    assert isinstance(backend, AgentBackedMediaBackend)
    assert backend._workspace is workspace


@pytest.mark.asyncio
async def test_unloaded_agent_leaves_the_existing_fallback_intact() -> None:
    """Refresh stays a no-op while the agent is still unavailable."""
    gateway, attached, _workspace = _real_gateway(loaded=False)

    await gateway.refresh_media_backends()

    assert attached == []


@pytest.mark.asyncio
async def test_failed_start_does_not_refresh() -> None:
    refresh = AsyncMock()
    server = _server(gateway=SimpleNamespace(refresh_media_backends=refresh), fail=True)

    with pytest.raises(RuntimeError, match="boot failed"):
        await agents_router.start_agent(_AGENT_ID, user=_OWNER, server=server)

    refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_agent_does_not_refresh() -> None:
    refresh = AsyncMock()
    server = _server(gateway=SimpleNamespace(refresh_media_backends=refresh), missing=True)

    with pytest.raises(OctopError):
        await agents_router.start_agent(_AGENT_ID, user=_OWNER, server=server)

    refresh.assert_not_awaited()
