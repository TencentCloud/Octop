"""Discord routing and diagnostics through Octop's real gateway contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from harness_gateway.channels.discord import DiscordChannel, DiscordConfig
from harness_gateway.models import ChannelSubject, InboundMessage, MessageEvent
from tests.unit.gateway.test_gateway_runtime_status import _make_gateway

from octop.infra.gateway.gateway import ChannelCreateSpec, ChannelKind, Gateway
from octop.infra.gateway.process.message_keys import (
    resolve_user_id_for_message,
    sanitize_im_metadata,
    session_key_from_message,
)


def test_discord_session_and_push_routing():
    def inbound(subject: str, sender: str, chat_type: str = "group") -> InboundMessage:
        return InboundMessage(
            channel_id="bot-registration",
            channel_type="discord",
            tenant_id="agent1",
            channel_subject=ChannelSubject(subject_id=subject, chat_type=chat_type),
            content=[],
            metadata={
                "chat_type": chat_type,
                "chat_id": subject,
                "sender_id": sender,
                "message_id": "ephemeral",
            },
        )

    a, b = inbound("200", "10"), inbound("200", "11")
    thread = inbound("300", "10")
    dm = inbound("10", "10", "dm")
    assert session_key_from_message(a, agent_id="agent1") == session_key_from_message(
        b, agent_id="agent1"
    )
    assert len({session_key_from_message(m, agent_id="agent1") for m in [a, thread, dm]}) == 3
    assert resolve_user_id_for_message(dm, agent_owner_id=7) == 7
    metadata = sanitize_im_metadata(thread)
    assert metadata["chat_id"] == "300"
    assert "message_id" not in metadata


def test_live_discord_status_and_localized_diagnostics(tmp_path):
    gateway = _make_gateway(tmp_path)
    channel = SimpleNamespace(is_connected=True, runtime_error=None)
    gateway._channel_manager = SimpleNamespace(get_channel=lambda _: channel)
    gateway._set_runtime_status("discord1", connected=True)
    channel.is_connected = False
    channel.runtime_error = "discord_disconnected"
    state = gateway.runtime_status_to_dict("discord1", locale="zh")
    assert state["connected"] is False
    assert "重连" in state["error"]
    channel.is_connected = True
    channel.runtime_error = None
    state = gateway.runtime_status_to_dict("discord1", locale="zh")
    assert state["connected"] is True
    assert state["error"] is None
    assert "Message Content Intent" in Gateway._format_probe_error(
        RuntimeError("discord_intents_required"), "zh"
    )
    assert "Bot Token" in Gateway._format_probe_error(RuntimeError("discord_invalid_token"), "en")


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_all", [None, True, False])
async def test_discord_registration_forwards_config_and_routing(tmp_path, monkeypatch, allow_all):
    import json
    from unittest.mock import AsyncMock, MagicMock

    from harness_gateway.manager import ChannelManager
    from harness_gateway.media import FileSystemMediaBackend

    async def processor(msg):
        yield MessageEvent.completed()

    monkeypatch.setattr(DiscordChannel, "start", AsyncMock())
    monkeypatch.setattr(DiscordChannel, "stop", AsyncMock())
    gateway = _make_gateway(tmp_path)
    manager = ChannelManager(
        processor=processor, media_backend=FileSystemMediaBackend(str(tmp_path))
    )
    gateway._channel_manager = manager
    gateway._processor = MagicMock()
    # Use the same real row contract as registration, without invoking an LLM.
    row = SimpleNamespace(
        channel_id="discord1",
        agent_id="agent1",
        kind="discord",
        config_json=json.dumps(
            {
                "bot_token": "fake",
                "allowed_channel_ids": ["200"],
                **({} if allow_all is None else {"allow_all_channels": allow_all}),
            }
        ),
    )
    await manager.start()
    try:
        await gateway._register_channel(row)
        registered = manager.get_channel("discord1")
        assert isinstance(registered, DiscordChannel)
        assert registered.tenant_id == "agent1"
        assert registered._config.allowed_channel_ids == ["200"]
        assert registered._config.allow_all_channels is (allow_all is not False)
        assert isinstance(registered._config, DiscordConfig)
        assert (
            ChannelCreateSpec("discord1", "agent1", 1, ChannelKind.DISCORD, "Discord").kind
            == "discord"
        )
    finally:
        await manager.stop()
