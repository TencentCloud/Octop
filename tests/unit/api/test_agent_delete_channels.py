"""Deleting an agent must tear down its live IM channels (issue #801).

The ``channels`` rows cascade away with the agent row, but the live channel
instances stay registered with the channel manager and keep polling their
platform. Inbound messages were then routed to a removed agent and every turn
failed with an opaque "An error occurred while processing your message." until
the operator disabled and re-enabled the channel.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.api.routers.agents import delete_agent


def _server(*, order: list[str]) -> MagicMock:
    registry = MagicMock()
    registry.get_row = MagicMock(return_value=MagicMock(user_id=1))
    registry.delete = AsyncMock(side_effect=lambda _agent_id: order.append("delete"))
    gateway = MagicMock()
    gateway.unregister_agent_channels = AsyncMock(
        side_effect=lambda _agent_id: order.append("unregister"),
    )
    server = MagicMock()
    server.app_runtime.agent_registry = registry
    server.app_runtime.gateway = gateway
    return server


@pytest.mark.asyncio
async def test_delete_agent_unregisters_live_channels_before_removing_agent() -> None:
    """Channel ids must be read before the cascade wipes the rows."""
    order: list[str] = []
    server = _server(order=order)

    await delete_agent("agent1", user=MagicMock(is_admin=True), server=server)

    server.app_runtime.gateway.unregister_agent_channels.assert_awaited_once_with("agent1")
    server.app_runtime.agent_registry.delete.assert_awaited_once_with("agent1")
    assert order == ["unregister", "delete"]


@pytest.mark.asyncio
async def test_delete_agent_teardown_happens_for_plain_owner() -> None:
    """Non-admin owners get the same teardown."""
    order: list[str] = []
    server = _server(order=order)

    await delete_agent("agent1", user=MagicMock(is_admin=False, id=1), server=server)

    server.app_runtime.gateway.unregister_agent_channels.assert_awaited_once_with("agent1")
    assert order == ["unregister", "delete"]


@pytest.mark.asyncio
async def test_delete_agent_missing_row_does_not_touch_channels() -> None:
    """A 404 must not tear down anything."""
    order: list[str] = []
    server = _server(order=order)
    server.app_runtime.agent_registry.get_row = MagicMock(return_value=None)

    with pytest.raises(Exception):  # noqa: B017 - OctopError(AGENT_NOT_FOUND)
        await delete_agent("agent1", user=MagicMock(is_admin=True), server=server)

    server.app_runtime.gateway.unregister_agent_channels.assert_not_awaited()
    server.app_runtime.agent_registry.delete.assert_not_awaited()
