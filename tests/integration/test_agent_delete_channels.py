"""Deleting agents must keep live IM channels consistent with their DB rows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_gateway.channel import BaseChannel
from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.i18n import tr
from octop.infra.gateway.cli import CLI_CHANNEL_ID
from octop.infra.gateway.ws import WS_CHANNEL_ID
from tests.support.auth import create_user


async def _attach_channel(server, agent_id, channel_id):
    gateway = server.app_runtime.gateway
    row = server.services.agent_repo.get(agent_id)
    server.services.channel_repo.create(
        channel_id=channel_id,
        agent_id=agent_id,
        user_id=row.user_id,
        kind="weixin",
        name=channel_id,
        config_json="{}",
    )
    channel = MagicMock(
        spec=BaseChannel, channel_id=channel_id, tenant_id=agent_id, channel_type="weixin"
    )
    channel.stopped_with_rows = []

    async def stop():
        # The agent delete cascades channel rows: collect/stop channels first.
        channel.stopped_with_rows.append(
            (
                server.services.agent_repo.get(agent_id) is not None,
                server.services.channel_repo.get(channel_id) is not None,
            )
        )

    channel.stop = AsyncMock(side_effect=stop)
    await gateway.channel_manager.add_channel(channel)
    gateway._set_runtime_status(channel_id, connected=True)
    return channel


@pytest.mark.parametrize("entry", ["agent", "team", "user"])
async def test_delete_stops_only_owned_channels_before_db_cascade(env, entry):
    client, server, auth = env
    survivor = server.services.agent_repo.list_all()[0]
    await create_user(client, auth, username="channel-owner")
    owner = server.services.user_repo.get_by_username("channel-owner")
    server.services.agent_repo.create(
        agent_id="delete-me",
        user_id=owner.id,
        name="Delete me",
        kind="team" if entry == "team" else "expert",
    )
    gateway = server.app_runtime.gateway
    first = await _attach_channel(server, "delete-me", "first")
    second = await _attach_channel(server, "delete-me", "second")
    kept = await _attach_channel(server, survivor.agent_id, "kept")
    server.services.channel_repo.create(
        channel_id="disabled",
        agent_id="delete-me",
        user_id=owner.id,
        kind="weixin",
        name="disabled",
        config_json="{}",
    )
    server.services.channel_repo.update("disabled", enabled=False)
    gateway._set_runtime_status("disabled", connected=False, reason="disabled")
    thread_id = await gateway.thread_registry.get_or_create(
        agent_id="delete-me",
        user_id=owner.id,
        channel_type="weixin",
        channel_subject_id="wx-user",
        channel_id="first",
    )

    url = {
        "agent": "/api/agents/delete-me",
        "team": "/api/teams/delete-me",
        "user": f"/api/users/{owner.id}",
    }[entry]
    response = await client.delete(url, headers=auth)

    assert response.status_code == 204, response.text
    assert server.services.agent_repo.get("delete-me") is None
    assert server.services.thread_repo.get(thread_id) is None
    assert server.services.session_repo.list_by_thread(thread_id) == []
    for channel in (first, second):
        channel.stop.assert_awaited_once()
        assert channel.stopped_with_rows == [(True, True)]
    for channel_id in ("first", "second", "disabled"):
        assert server.services.channel_repo.get(channel_id) is None
        assert gateway.channel_manager.get_channel(channel_id) is None
        assert gateway.get_runtime_status(channel_id) is None
    kept.stop.assert_not_awaited()
    assert gateway.channel_manager.get_channel("kept") is kept
    assert gateway.get_runtime_status("kept").connected
    assert gateway.channel_manager.get_channel(WS_CHANNEL_ID) is not None
    assert gateway.channel_manager.get_channel(CLI_CHANNEL_ID) is not None


@pytest.mark.parametrize("reason", ["forbidden", "busy"])
async def test_rejected_delete_keeps_live_channels(env, reason):
    client, server, auth = env
    owner_auth = await create_user(client, auth, username="channel-owner")
    owner = server.services.user_repo.get_by_username("channel-owner")
    server.services.agent_repo.create(agent_id="keep-me", user_id=owner.id, name="Keep me")
    channel = await _attach_channel(server, "keep-me", "kept")
    registry = server.app_runtime.agent_registry
    if reason == "forbidden":
        auth = await create_user(client, auth, username="other-user")
    else:
        auth = owner_auth
        registry.teams.jobs.begin("host", "keep-me")
    try:
        response = await client.delete("/api/agents/keep-me", headers=auth)
        assert response.status_code == (403 if reason == "forbidden" else 409), response.text
        assert server.services.agent_repo.get("keep-me") is not None
        assert server.services.channel_repo.get("kept") is not None
        assert server.app_runtime.gateway.channel_manager.get_channel("kept") is channel
        channel.stop.assert_not_awaited()
    finally:
        if reason == "busy":
            registry.teams.jobs.end("host", "keep-me")


@pytest.mark.parametrize("text", ["continue", "/help", "/approve"])
@pytest.mark.parametrize(
    ("channel_type", "metadata", "locale"),
    [("weixin", {}, "zh"), ("telegram", {}, "en"), ("weixin", {"locale": "en"}, "en")],
)
async def test_missing_agent_returns_localized_error_before_session_creation(
    env, monkeypatch, text, channel_type, metadata, locale
):
    _, server, _ = env
    gateway = server.app_runtime.gateway
    create_thread = AsyncMock(wraps=gateway.thread_registry.get_or_create_by_key)
    monkeypatch.setattr(gateway.thread_registry, "get_or_create_by_key", create_thread)
    msg = InboundMessage(
        channel_id="stale-channel",
        channel_type=channel_type,
        tenant_id="deleted-agent",
        channel_subject=ChannelSubject(subject_id="wx-user"),
        content=[TextContent(text=text)],
        metadata=metadata,
    )

    events = [event async for event in gateway.processor(msg)]

    assert [event.type for event in events] == ["error", "completed"]
    assert events[0].error == f"[AGENT_NOT_FOUND] {tr('errors.AGENT_NOT_FOUND', locale)}"
    create_thread.assert_not_awaited()
