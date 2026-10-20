"""Discord Bot gateway, using discord.py for WebSocket and REST transport."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import mimetypes
import re
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

import aiohttp

from octop_gateway.channel import BaseChannel, ChannelConfig, ChannelCredentialsError, MessageProcessor
from octop_gateway.constraints import ChannelConstraints
from octop_gateway.group_context import GroupContextConfig
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)

logger = logging.getLogger(__name__)
_CONNECT_TIMEOUT = 30.0
_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


@dataclass
class DiscordConfig(ChannelConfig):
    """Configure guild channel access and the independent DM user allowlist.

    Guild channels are allowed by default, subject to Discord permissions.
    Restricted mode allows listed channels and their threads; DMs always require
    an allowed user ID. Empty lists deny access in their respective restricted scope.
    """

    bot_token: str = ""
    http_proxy: str = ""
    http_proxy_auth: str = ""
    allow_all_channels: bool = True
    allowed_user_ids: list[str] = field(default_factory=list)
    allowed_channel_ids: list[str] = field(default_factory=list)
    group_context: GroupContextConfig = field(
        default_factory=lambda: GroupContextConfig(enabled=True, visibility="all", activation="mention")
    )

    required_credentials = ("bot_token",)
    field_aliases: ClassVar[dict[str, str]] = {"token": "bot_token"}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        cleaned = dict(data)
        for key in ("allowed_user_ids", "allowed_channel_ids"):
            value = cleaned.get(key, [])
            if isinstance(value, str):
                value = re.split(r"[,\s]+", value.strip()) if value.strip() else []
            if not isinstance(value, list) or any(not str(item).isascii() or not str(item).isdigit() for item in value):
                raise ValueError(f"{key}: expected Discord IDs separated by commas or whitespace")
            cleaned[key] = list(dict.fromkeys(str(item) for item in value))
        return super().from_dict(cleaned)


class DiscordChannel(BaseChannel):
    channel_type = "discord"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: DiscordConfig,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints: ChannelConstraints | None = None,
    ) -> None:
        self._config = config
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            debounce_seconds=debounce_seconds,
            constraints=constraints,
            config=config,
        )
        self._client: Any = None
        self._client_task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._connection_session: str | None = None
        self._runtime_error: str | None = None
        self._seen: OrderedDict[str, None] = OrderedDict()

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(typing_keepalive_interval=8.0, show_thinking=False, show_tool_hints=True)

    @property
    def is_connected(self) -> bool:
        return bool(
            self._ready.is_set()
            and self._client
            and self._client.is_ready()
            and self._client_task
            and not self._client_task.done()
        )

    @property
    def runtime_error(self) -> str | None:
        return None if self.is_connected else self._runtime_error or "discord_disconnected"

    def _proxy_auth(self) -> aiohttp.BasicAuth | None:
        if not self._config.http_proxy_auth:
            return None
        user, separator, password = self._config.http_proxy_auth.partition(":")
        if not separator:
            raise ValueError("discord_proxy_auth_invalid")
        return aiohttp.BasicAuth(user, password)

    async def start(self) -> None:
        import discord

        if self.is_connected:
            return
        await self.stop()
        if self._config.missing_credentials():
            raise ChannelCredentialsError("discord", ["bot_token"])
        self._runtime_error = None
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.dm_messages = True
        intents.message_content = True
        self._client = discord.Client(
            intents=intents,
            proxy=self._config.http_proxy or None,
            proxy_auth=self._proxy_auth(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self._client.event(self.on_ready)
        self._client.event(self.on_resumed)
        self._client.event(self.on_disconnect)
        self._client.event(self.on_message)
        self._client_task = asyncio.create_task(self._run_client(), name=f"discord-{self.channel_id}")
        ready_task = asyncio.create_task(self._ready.wait())
        try:
            done, _ = await asyncio.wait(
                {ready_task, self._client_task},
                timeout=_CONNECT_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._client_task in done:
                await self._client_task
                raise RuntimeError(self._runtime_error or "discord_connection_failed")
            if ready_task not in done or not self.is_connected:
                raise RuntimeError("discord_connect_timeout")
        except BaseException:
            await self.stop()
            raise
        finally:
            ready_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ready_task

    async def _run_client(self) -> None:
        import discord

        try:
            await self._client.start(self._config.bot_token, reconnect=True)
        except discord.LoginFailure:
            self._runtime_error = "discord_invalid_token"
        except discord.PrivilegedIntentsRequired:
            self._runtime_error = "discord_intents_required"
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            # Do not surface SDK exception text: proxy URLs may include secrets.
            self._runtime_error = "discord_connection_failed"
        finally:
            self._ready.clear()
            self._connection_session = None

    async def stop(self) -> None:
        task, client = self._client_task, self._client
        self._client_task = None
        self._client = None
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        try:
            if client:
                await client.close()
        finally:
            self._ready.clear()
            self._connection_session = None
            await self._close_http()

    async def on_ready(self) -> None:
        self._connection_session = f"discord-{uuid.uuid4().hex}"
        self._runtime_error = None
        self._ready.set()

    async def on_resumed(self) -> None:
        await self.on_ready()

    async def on_disconnect(self) -> None:
        self._ready.clear()
        self._connection_session = None

    def _is_duplicate(self, message_id: str) -> bool:
        if message_id in self._seen:
            self._seen.move_to_end(message_id)
            return True
        self._seen[message_id] = None
        if len(self._seen) > 1000:
            self._seen.popitem(last=False)
        return False

    async def on_message(self, message: Any) -> None:
        import discord

        if (
            message.author.bot
            or message.webhook_id
            or message.type not in (discord.MessageType.default, discord.MessageType.reply)
        ):
            return
        if message.guild is None:
            allowed = str(message.author.id) in self._config.allowed_user_ids
        else:
            allowed = (
                self._config.allow_all_channels
                or str(message.channel.id) in self._config.allowed_channel_ids
                or str(getattr(message.channel, "parent_id", None)) in self._config.allowed_channel_ids
            )
        if not allowed or self._is_duplicate(str(message.id)):
            return
        if not message.content and not message.attachments:
            return
        msg = self.parse_inbound(message)
        # When shared group context is disabled, keep the default mention gate.
        if (
            message.guild is not None
            and not self._config.group_context.resolve(str(message.channel.id)).enabled
            and not msg.metadata["bot_mentioned"]
        ):
            return
        self.enqueue(msg)

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload
        message = raw_payload
        is_group = message.guild is not None
        chat_id = str(message.channel.id)
        sender_id = str(message.author.id)
        bot = self._client.user if self._client else None
        text = message.content or ""
        mentioned = bool(bot and re.search(rf"<@!?{bot.id}>", text))
        if bot:
            text = re.sub(rf"<@!?{bot.id}>", "", text).strip()
        parts: list[ContentPart] = [TextContent(text=text)] if text else []
        for attachment in message.attachments:
            mime = attachment.content_type or mimetypes.guess_type(attachment.filename)[0] or "application/octet-stream"
            values = {"url": attachment.url, "mime_type": mime, "size": attachment.size}
            if mime.startswith("image/"):
                parts.append(ImageContent(**values, alt_text=attachment.filename))
            elif mime.startswith("audio/"):
                parts.append(AudioContent(**values))
            elif mime.startswith("video/"):
                parts.append(VideoContent(**values))
            else:
                parts.append(FileContent(**values, filename=attachment.filename))
        chat_type = "group" if is_group else "dm"
        metadata: dict[str, Any] = {
            "chat_id": chat_id,
            "channel_id_native": chat_id,
            "chat_type": chat_type,
            "sender_id": sender_id,
            "sender_name": message.author.display_name,
            "message_id": str(message.id),
            "bot_mentioned": mentioned,
        }
        if is_group:
            metadata["guild_id"] = str(message.guild.id)
        if getattr(message.channel, "parent_id", None):
            metadata["parent_channel_id"] = str(message.channel.parent_id)
        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self.tenant_id,
            channel_subject=ChannelSubject(
                subject_id=chat_id if is_group else sender_id,
                chat_type=chat_type,
                display_name=getattr(message.channel, "name", "") if is_group else message.author.display_name,
                metadata=dict(metadata),
            ),
            channel_session_id=self._connection_session or f"{self.channel_id}-unconnected",
            content=parts,
            metadata=metadata,
            timestamp=message.created_at.timestamp(),
        )

    async def _target(self, subject: ChannelSubject) -> Any:
        if not self.is_connected:
            raise RuntimeError(self.runtime_error)
        chat_id = subject.metadata.get("chat_id") or subject.metadata.get("channel_id_native")
        if not chat_id and subject.chat_type == "dm":
            user = self._client.get_user(int(subject.subject_id)) or await self._client.fetch_user(
                int(subject.subject_id)
            )
            return await user.create_dm()
        target_id = int(chat_id or subject.subject_id)
        return self._client.get_channel(target_id) or await self._client.fetch_channel(target_id)

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        import discord

        if not text.strip():
            return
        target = await self._target(subject)
        for chunk in split_discord_text(text):
            await target.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        for part in parts:
            if isinstance(part, TextContent):
                await self._send_text(subject, part.text)
            else:
                await self._send_media(subject, part)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        import discord

        try:
            data, mime = await self.load_media_bytes(media)
            filename = getattr(media, "filename", "") or getattr(media, "alt_text", "")
            filename = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
            filename = filename or "attachment" + (mimetypes.guess_extension(mime) or ".bin")
            target = await self._target(subject)
            upload = discord.File(io.BytesIO(data), filename=filename)
            try:
                await target.send(file=upload, allowed_mentions=discord.AllowedMentions.none())
            finally:
                upload.close()
        except Exception:  # pylint: disable=broad-except
            # Discord SDK and MediaBackend failures share this attachment boundary.
            logger.warning("Discord attachment delivery failed")
            url = self._get_media_url(media)
            await self._send_text(subject, f"[Attachment: {url}]" if url else "[Attachment upload failed]")

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        try:
            target = await self._target(subject)
            await target.typing()
        except Exception:  # pylint: disable=broad-except
            # Typing indicators are best-effort across arbitrary Discord targets.
            logger.debug("Discord typing indicator unavailable")

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        url = "https:" + url if url.startswith("//") else url
        http = await self._ensure_http()
        async with http.get(
            url,
            proxy=self._config.http_proxy or None,
            proxy_auth=self._proxy_auth(),
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            response.raise_for_status()
            if response.content_length and response.content_length > _MAX_DOWNLOAD_BYTES:
                raise ValueError("Discord attachment exceeds 25 MiB")
            data = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                data.extend(chunk)
                if len(data) > _MAX_DOWNLOAD_BYTES:
                    raise ValueError("Discord attachment exceeds 25 MiB")
            return bytes(data), response.content_type


def split_discord_text(text: str, limit: int = 2000) -> list[str]:
    """Split on lines, closing/reopening code fences; budget UTF-16 units for emoji."""

    def size(value: str) -> int:
        return len(value.encode("utf-16-le")) // 2

    if limit < 32:
        raise ValueError("Discord chunk limit must be at least 32")
    if size(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    current = ""
    opener = ""
    marker = ""

    def closing(value: str) -> str:
        return "\n" + value if value else ""

    for line in text.splitlines(keepends=True):
        next_opener, next_marker = opener, marker
        match = re.match(r"^(`{3,}|~{3,})([^\r\n]*)", line)
        if match:
            candidate, info = match.groups()
            if marker and candidate[0] == marker[0] and len(candidate) >= len(marker) and not info.strip():
                next_opener, next_marker = "", ""
            elif not marker and (candidate[0] != "`" or "`" not in info):
                # Bound only the *recognition* of a fence, never truncate user text.
                header = line.rstrip("\r\n") + "\n"
                if size(header) + size(closing(candidate)) < limit // 2:
                    next_opener, next_marker = header, candidate
        while line:
            room = limit - size(current) - size(closing(next_marker))
            if size(line) <= room:
                current += line
                break
            if current and current != opener:
                chunks.append(current + closing(marker))
                current = opener
                continue
            # A long ordinary line is split without losing whitespace or emoji.
            room = limit - size(current) - size(closing(marker))
            used = 0
            cut = 0
            for char in line:
                units = size(char)
                if used + units > room:
                    break
                used += units
                cut += 1
            current += line[:cut]
            line = line[cut:]
            chunks.append(current + closing(marker))
            current = opener
        opener, marker = next_opener, next_marker
    if current:
        chunks.append(current + closing(marker))
    return chunks
