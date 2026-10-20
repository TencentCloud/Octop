"""Discord transport tests; real SDK types, mocked network and Gateway events."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from octop_gateway.channel import ChannelCredentialsError
from octop_gateway.channels import ChannelKind
from octop_gateway.channels.discord import DiscordChannel, DiscordConfig, split_discord_text
from octop_gateway.group_context import GroupContextConfig
from octop_gateway.manager import ChannelManager
from octop_gateway.media import FileSystemMediaBackend
from octop_gateway.models import ChannelSubject, FileContent, ImageContent, MessageEvent


async def processor(msg):
    yield MessageEvent.text(f"reply: {msg.text}")
    yield MessageEvent.completed()


class FakeClient:
    def __init__(self, mode="ready"):
        self.mode = mode
        self.user = SimpleNamespace(id=99)
        self.ready = False
        self.events = {}
        self.close = AsyncMock(side_effect=self.disconnect)
        self.target = SimpleNamespace(send=AsyncMock(), typing=AsyncMock())
        self.get_channel = Mock(return_value=self.target)
        self.fetch_channel = AsyncMock(return_value=self.target)

    def event(self, callback):
        self.events[callback.__name__] = callback

    def is_ready(self):
        return self.ready

    async def disconnect(self):
        self.ready = False

    async def start(self, token, reconnect=True):
        if self.mode == "login_failure":
            raise discord.LoginFailure(f"secret: {token}")
        if self.mode == "intents":
            raise discord.PrivilegedIntentsRequired(None)
        if self.mode == "network":
            raise OSError("proxy credential should not leak")
        if self.mode == "ready":
            self.ready = True
            await self.events["on_ready"]()
        await asyncio.Future()


def message(*, channel=200, author=10, guild=100, parent=None, content="<@99> hello", msg_id=1, bot=False):
    return SimpleNamespace(
        id=msg_id,
        author=SimpleNamespace(id=author, bot=bot, display_name=f"User {author}"),
        guild=SimpleNamespace(id=guild) if guild else None,
        channel=SimpleNamespace(id=channel, parent_id=parent, name="test-room"),
        content=content,
        attachments=[],
        webhook_id=None,
        type=discord.MessageType.default,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def channel():
    return DiscordChannel(
        processor,
        config=DiscordConfig(
            bot_token="fake-token", allow_all_channels=False, allowed_channel_ids=["200"], allowed_user_ids=["10"]
        ),
        channel_id="registration",
        tenant_id="agent-one",
    )


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(discord, "Client", Mock(return_value=fake))
    return fake


def test_config_and_registration():
    cfg = DiscordConfig.from_dict(
        {"token": " t ", "allowed_channel_ids": "200, 201\n202", "allowed_user_ids": [10, "11"]}
    )
    assert cfg.bot_token == "t"
    assert cfg.allow_all_channels is True
    assert DiscordConfig.from_dict({"allow_all_channels": False}).allow_all_channels is False
    assert cfg.allowed_channel_ids == ["200", "201", "202"]
    assert cfg.allowed_user_ids == ["10", "11"]
    assert cfg.group_context.enabled
    assert cfg.group_context.activation == "mention"
    assert ChannelKind("discord") is ChannelKind.DISCORD
    assert DiscordConfig().missing_credentials() == ["bot_token"]
    with pytest.raises(ValueError):
        DiscordConfig.from_dict({"allowed_channel_ids": "#general"})


async def test_start_waits_ready_and_stop_is_repeatable(channel, client):
    await channel.start()
    assert channel.is_connected
    assert channel.runtime_error is None
    task = channel._client_task
    await channel.start()
    assert channel._client_task is task
    first_session = channel._connection_session
    await channel.on_disconnect()
    assert not channel.is_connected
    client.ready = True
    await channel.on_resumed()
    assert channel.is_connected
    assert channel._connection_session != first_session
    await channel.stop()
    await channel.stop()
    assert task.done()
    assert not channel.is_connected
    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    "mode, error",
    [
        ("login_failure", "discord_invalid_token"),
        ("intents", "discord_intents_required"),
        ("network", "discord_connection_failed"),
    ],
)
async def test_connection_errors_fail_probe_without_leaking_secrets(channel, client, mode, error):
    client.mode = mode
    with pytest.raises(RuntimeError, match=f"^{error}$"):
        await channel.start()
    assert channel._client_task is None
    client.close.assert_awaited_once()


async def test_timeout_cleans_up_and_does_not_report_success(channel, client, monkeypatch):
    client.mode = "timeout"
    monkeypatch.setattr("octop_gateway.channels.discord._CONNECT_TIMEOUT", 0.01)
    with pytest.raises(RuntimeError, match="discord_connect_timeout"):
        await channel.start()
    assert not channel.is_connected
    assert channel._client_task is None
    client.close.assert_awaited_once()


async def test_cancellation_cleans_up(channel, client):
    client.mode = "timeout"
    task = asyncio.create_task(channel.start())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert channel._client_task is None
    client.close.assert_awaited_once()


async def test_manager_probe_validates_then_connects(client):
    manager = ChannelManager(processor=processor)
    with pytest.raises(ChannelCredentialsError):
        await manager.probe_channel("discord", {})
    await manager.probe_channel("discord", {"bot_token": "fake"})
    assert not manager.channel_ids
    client.close.assert_awaited_once()


async def test_failed_registration_can_be_retried(client, tmp_path):
    manager = ChannelManager(processor=processor, media_backend=FileSystemMediaBackend(str(tmp_path)))
    await manager.start()
    client.mode = "login_failure"
    try:
        with pytest.raises(RuntimeError, match="discord_invalid_token"):
            await manager.add_discord_channel(DiscordConfig(bot_token="fake"), channel_id="same-id")
        assert manager.get_channel("same-id") is None
        assert "same-id" not in manager._queues
        client.mode = "ready"
        await manager.add_discord_channel(DiscordConfig(bot_token="fixed"), channel_id="same-id")
        assert manager.get_channel("same-id").is_connected
    finally:
        await manager.stop()


async def test_proxy_and_minimal_intents(channel, client):
    channel._config.http_proxy = "http://localhost:8080"
    channel._config.http_proxy_auth = "alice:pass:word"
    await channel.start()
    options = discord.Client.call_args.kwargs
    assert options["proxy"] == "http://localhost:8080"
    assert options["proxy_auth"].password == "pass:word"
    assert options["intents"].message_content
    assert not options["intents"].members
    assert not options["intents"].presences
    assert options["allowed_mentions"].everyone is False
    await channel.stop()


def test_conversation_routing_separates_channels_threads_and_dms(channel):
    messages = [
        channel.parse_inbound(message(channel=200, author=10)),
        channel.parse_inbound(message(channel=200, author=11)),
        channel.parse_inbound(message(channel=201)),
        channel.parse_inbound(message(channel=300, parent=200)),
        channel.parse_inbound(message(channel=400, guild=None)),
    ]
    assert [m.channel_subject.subject_id for m in messages] == ["200", "200", "201", "300", "10"]
    assert [m.metadata["chat_type"] for m in messages] == ["group", "group", "group", "group", "dm"]
    assert messages[1].metadata["sender_id"] == "11"
    assert messages[3].metadata["chat_id"] == "300"
    assert messages[4].metadata["chat_id"] == "400"
    assert all(m.tenant_id == "agent-one" and m.channel_id == "registration" for m in messages)


async def test_access_filter_threads_bots_webhooks_and_dedup(channel, client):
    await channel.start()
    enqueue = Mock()
    channel.set_enqueue_callback(enqueue)
    await channel.on_message(message())
    await channel.on_message(message())
    await channel.on_message(message(channel=201, msg_id=2))
    await channel.on_message(message(bot=True, msg_id=3))
    webhook = message(msg_id=4)
    webhook.webhook_id = 123
    await channel.on_message(webhook)
    await channel.on_message(message(channel=300, parent=200, msg_id=5))
    await channel.on_message(message(guild=None, author=11, msg_id=6))
    await channel.on_message(message(guild=None, msg_id=7))
    assert enqueue.call_count == 3
    assert [c.args[0].channel_subject.subject_id for c in enqueue.call_args_list] == ["200", "300", "10"]
    assert enqueue.call_args_list[0].args[0].text == "hello"
    await channel.stop()


async def test_default_all_channels_accepts_unlisted_rooms_and_threads_but_not_dms(client):
    channel = DiscordChannel(processor, config=DiscordConfig(bot_token="fake-token"))
    await channel.start()
    enqueue = Mock()
    channel.set_enqueue_callback(enqueue)
    try:
        await channel.on_message(message(channel=201))
        await channel.on_message(message(channel=301, parent=201, msg_id=2))
        await channel.on_message(message(channel=401, guild=101, msg_id=3))
        await channel.on_message(message(guild=None, msg_id=4))
        await channel.on_message(message(bot=True, msg_id=5))
        assert [c.args[0].channel_subject.subject_id for c in enqueue.call_args_list] == ["201", "301", "401"]
    finally:
        await channel.stop()


async def test_restricted_empty_channels_deny_guild_messages_but_keep_dm_access(channel, client):
    channel._config.allowed_channel_ids = []
    await channel.start()
    enqueue = Mock()
    channel.set_enqueue_callback(enqueue)
    try:
        await channel.on_message(message())
        await channel.on_message(message(channel=300, parent=200, msg_id=2))
        await channel.on_message(message(guild=None, msg_id=3))
        enqueue.assert_called_once()
        assert enqueue.call_args.args[0].channel_subject.subject_id == "10"
    finally:
        await channel.stop()


async def test_group_context_only_invokes_on_direct_mention(channel, client):
    channel._config.allow_all_channels = True
    await channel.start()
    enqueue = Mock()
    channel.set_enqueue_callback(enqueue)
    channel._send_text = AsyncMock()
    for index, text in enumerate(["background", "@everyone hello", "<@99> question"]):
        await channel.on_message(message(content=text, msg_id=index))
    for call in enqueue.call_args_list:
        await channel.handle_inbound(call.args[0])
    channel._send_text.assert_awaited_once()
    assert "question" in channel._send_text.await_args.args[1]
    await channel.stop()


async def test_disabled_group_context_does_not_open_all_messages(channel, client):
    channel._config.group_context = GroupContextConfig(enabled=False)
    await channel.start()
    enqueue = Mock()
    channel.set_enqueue_callback(enqueue)
    await channel.on_message(message(content="no mention"))
    enqueue.assert_not_called()
    await channel.stop()


def test_parse_attachments(channel):
    incoming = message()
    incoming.attachments = [
        SimpleNamespace(content_type="image/png", filename="a.png", url="https://cdn.discordapp.com/a.png", size=15),
        SimpleNamespace(content_type=None, filename="note.txt", url="https://cdn.discordapp.com/note.txt", size=10),
    ]
    result = channel.parse_inbound(incoming)
    assert isinstance(result.content[1], ImageContent)
    assert isinstance(result.content[2], FileContent)


@pytest.mark.parametrize(
    "text",
    [
        "x" * 5100,
        "😀" * 2300,
        "```python\n" + "print('hello')\n" * 500 + "```",
        "Before\n~~~js\n" + "a" * 4800 + "\n~~~\nAfter",
    ],
)
def test_long_output_preserves_text_and_balances_fences(text):
    chunks = split_discord_text(text)
    assert len(chunks) > 1
    assert all(0 < len(chunk.encode("utf-16-le")) // 2 <= 2000 for chunk in chunks)
    if "```" in text or "~~~" in text:
        marker = "```" if "```" in text else "~~~"
        assert all(chunk.count(marker) % 2 == 0 for chunk in chunks)

        def body(value):
            return "".join(line for line in value.splitlines() if not line.startswith(marker))

        assert body("\n".join(chunks)) == body(text)
    else:
        assert "".join(chunks) == text


async def test_send_uses_native_thread_after_restart_and_blocks_mentions(channel, client):
    await channel.start()
    client.get_channel.return_value = None
    await channel._send_text(
        ChannelSubject(subject_id="300", chat_type="group", metadata={"chat_id": "300"}), "@everyone " + "x" * 2200
    )
    client.fetch_channel.assert_awaited_once_with(300)
    assert client.target.send.await_count == 2
    assert client.target.send.await_args.kwargs["allowed_mentions"].everyone is False
    await channel.stop()


def test_split_does_not_truncate_inline_code_or_long_headers():
    for text in ["```inline code```\n" + "x" * 4000, "```" + "language" * 500 + "\ncontent"]:
        assert "".join(split_discord_text(text)) == text
    text = "````python\n" + "print('```')\n" * 500 + "````"
    chunks = split_discord_text(text)
    assert all(len(chunk.encode("utf-16-le")) // 2 <= 2000 for chunk in chunks)
    assert all(chunk.count("````") == 2 for chunk in chunks)
    assert sum(chunk.count("print('```')") for chunk in chunks) == 500


async def test_media_inline_and_backend_upload_failure_is_visible(channel, client, tmp_path):
    await channel.start()
    subject = ChannelSubject(subject_id="200")
    uploaded = []

    async def capture(*args, **kwargs):
        uploaded.append(kwargs["file"].fp.read())

    client.target.send.side_effect = capture
    await channel._send_media(subject, ImageContent(data=base64.b64encode(b"image").decode(), mime_type="image/png"))
    channel.set_media_backend(FileSystemMediaBackend(str(tmp_path)))
    (tmp_path / "test.txt").write_bytes(b"document")
    await channel._send_media(subject, FileContent(local_path="test.txt", filename="test.txt"))
    assert uploaded == [b"image", b"document"]
    client.target.send.side_effect = [OSError("upload failed"), None]
    await channel._send_media(subject, FileContent(data=base64.b64encode(b"file").decode()))
    assert client.target.send.await_args.args == ("[Attachment upload failed]",)
    await channel.stop()


async def test_attachment_download_uses_proxy_and_size_limit(channel):
    channel._config.http_proxy = "http://localhost:8080"
    channel._config.http_proxy_auth = "u:p"
    response = Mock(content_length=3, content_type="image/png")

    async def chunks(size):
        yield b"png"

    response.content.iter_chunked = chunks
    session = Mock()
    session.get.return_value = AsyncMock(__aenter__=AsyncMock(return_value=response))
    channel._ensure_http = AsyncMock(return_value=session)
    assert await channel.fetch_remote_media("//cdn.discordapp.com/image") == (b"png", "image/png")
    assert session.get.call_args.args == ("https://cdn.discordapp.com/image",)
    assert session.get.call_args.kwargs["proxy"] == "http://localhost:8080"
    response.content_length = 26 * 1024 * 1024
    with pytest.raises(ValueError, match="25 MiB"):
        await channel.fetch_remote_media("https://cdn.discordapp.com/image")
