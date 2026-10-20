"""Telegram channel: Bot API with HTTP long polling."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Self

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, ReplyParameters
from telegram.error import BadRequest, NetworkError, TelegramError

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.channels.telegram.delivery import RequestScheduler, formatting_error, request, sanitized_errors
from octop_gateway.channels.telegram.format_html import markdown_to_telegram_html, split_telegram_html
from octop_gateway.channels.telegram.interaction import Interactions
from octop_gateway.channels.telegram.policy import parse_id_list, should_accept_message
from octop_gateway.constraints import ChannelConstraints
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
    VideoContent,
)
from octop_gateway.utils import close_event_stream

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_MESSAGE_LENGTH = 4096
_TELEGRAM_SEND_CHUNK_SIZE = 4000
_TELEGRAM_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


@dataclass
class TelegramConfig(ChannelConfig):
    """Configuration for Telegram Bot channel.

    Attributes:
        bot_token: Telegram Bot API token from @BotFather.
        http_proxy: Optional HTTP proxy URL.
        show_typing: Send ``typing`` chat action while processing.
        show_thinking: Forward thinking/reasoning content to the chat.
        show_tool_hints: Show tool-call status messages in the chat.
        allowed_user_ids: Telegram user IDs allowed to talk to the bot, in
            private chats and groups. Empty (default) keeps the bot open to
            everyone, as before. Messages from other users are dropped before
            any media is fetched or the agent runs.
    """

    bot_token: str = ""
    http_proxy: str = ""
    show_typing: bool = True
    allowed_user_ids: list[str] = field(default_factory=list)

    group_activation: str = "always"
    allowed_chat_ids: list[str] = field(default_factory=list)
    allow_unaddressed_commands: bool = True
    topic_isolation: bool = False
    reply_to_message: bool = True
    edited_messages: bool = False
    streaming_mode: str = "off"
    status_reactions: bool = False
    disable_notification: bool = False
    protect_content: bool = False
    link_preview: bool = True
    command_menu: bool = False
    albums: bool = False
    audio_as_voice: bool = False

    def __post_init__(self) -> None:
        self.allowed_user_ids = parse_id_list(self.allowed_user_ids)
        self.allowed_chat_ids = parse_id_list(self.allowed_chat_ids, allow_negative=True)
        if self.group_activation not in ("always", "mention", "mention_or_reply"):
            raise ValueError("Invalid Telegram group_activation")
        if self.streaming_mode not in ("off", "auto", "edit", "draft"):
            raise ValueError("Invalid Telegram streaming_mode")

    required_credentials = ("bot_token",)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        cleaned = dict(data)
        value = cleaned.get("allowed_user_ids", [])
        if isinstance(value, str):
            value = re.split(r"[,\s]+", value.strip()) if value.strip() else []
        if not isinstance(value, list) or any(not str(item).isascii() or not str(item).isdigit() for item in value):
            raise ValueError("allowed_user_ids: expected Telegram user IDs separated by commas or whitespace")
        cleaned["allowed_user_ids"] = list(dict.fromkeys(str(item) for item in value))
        return super().from_dict(cleaned)


class TelegramChannel(BaseChannel):
    """Telegram Bot channel using python-telegram-bot long polling."""

    channel_type = "telegram"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: TelegramConfig,
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
        self._bot_id: int | None = None
        self._bot_username: str | None = None
        self._seen_updates: OrderedDict[str, None] = OrderedDict()
        self._seen_messages: OrderedDict[str, None] = OrderedDict()
        self._passive_albums: OrderedDict[tuple[str, str, str, str], tuple[float, list[Any]]] = OrderedDict()
        self._files: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._albums: dict[tuple[str, str, str, str], list[Any]] = {}
        self._album_tasks: set[asyncio.Task[None]] = set()
        self.interactions = Interactions()
        self._requests = RequestScheduler()
        self._active: dict[tuple[str, str, int | None], asyncio.Task[bool]] = {}
        self._stream: ContextVar[dict[str, Any] | None] = ContextVar("telegram_stream", default=None)
        self._original_processor = self._processor
        self._processor = self._stream_events
        self._app: Any = None
        self._polling_task: asyncio.Task[None] | None = None
        self._connection_session: str | None = None

    async def _request(self, method: Any, **kwargs: Any) -> Any:
        return await request(method, scheduler=self._requests, **kwargs)

    def _default_constraints(self) -> ChannelConstraints:
        interval = 4.0 if self._config.show_typing else 0.0
        return ChannelConstraints(
            send_rate_limit=(20, 60.0),
            typing_keepalive_interval=interval,
            show_thinking=False,
            show_tool_hints=True,
        )

    async def start(self) -> None:
        async with sanitized_errors():
            await self._start()

    async def _start(self) -> None:
        if not self._config.bot_token:
            raise RuntimeError("TelegramChannel: bot_token is required")

        try:
            from telegram.ext import Application, ContextTypes, MessageHandler, filters
        except ImportError as exc:
            raise ImportError(
                "python-telegram-bot is required for TelegramChannel. Install with: pip install python-telegram-bot"
            ) from exc

        builder = Application.builder().token(self._config.bot_token)
        if self._config.http_proxy:
            builder = builder.proxy(self._config.http_proxy).get_updates_proxy(self._config.http_proxy)

        self._app = builder.build()
        self._connection_session = f"telegram-{uuid.uuid4().hex[:12]}"

        async def handle_message(update: Any, _context: ContextTypes.DEFAULT_TYPE) -> None:
            await self._handle_update(update)

        from telegram.ext import CallbackQueryHandler

        self._app.add_handler(MessageHandler(filters.ALL, handle_message))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        await self._app.initialize()
        identity = self._app.bot
        self._bot_id = identity.id
        self._bot_username = identity.username
        if self._config.command_menu:
            await self._request(
                self._app.bot.set_my_commands,
                commands=[
                    BotCommand("help", "Show available commands"),
                    BotCommand("stop", "Stop your current response"),
                ],
            )
        await self._app.start()
        if self._app.updater:
            await self._app.updater.start_polling(
                allowed_updates=["message", "callback_query"]
                + (["edited_message"] if self._config.edited_messages else [])
            )
        logger.info("TelegramChannel started")

    async def stop(self) -> None:
        async with sanitized_errors():
            await self._stop()

    async def _stop(self) -> None:
        for task in [*self._album_tasks, *self._active.values()]:
            task.cancel()
        await asyncio.gather(*self._album_tasks, *self._active.values(), return_exceptions=True)
        self._albums.clear()
        self._files.clear()
        self._seen_updates.clear()
        self._seen_messages.clear()
        self._passive_albums.clear()
        self.interactions.pending.clear()
        if self._app:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
        self._connection_session = None
        logger.info("TelegramChannel stopped")

    def _is_duplicate(self, key: str) -> bool:
        # Independent FIFO windows: update churn cannot evict source IDs.
        seen = self._seen_messages if key.startswith("message:") else self._seen_updates
        if key in seen:
            return True
        seen[key] = None
        while len(seen) > 1000:
            seen.popitem(last=False)
        return False

    def _is_allowed_sender(self, message: Any) -> bool:
        allowed = self._config.allowed_user_ids
        if not allowed:
            return True
        user = getattr(message, "from_user", None)
        user_id = str(getattr(user, "id", "")) if user else ""
        if user_id in allowed:
            return True
        logger.info("Telegram message from user %s ignored: not in allowed_user_ids", user_id or "unknown")
        return False

    def _accept(self, message: Any) -> bool:
        return self._is_allowed_sender(message) and should_accept_message(
            message,
            bot_id=self._bot_id,
            bot_username=self._bot_username,
            activation=self._config.group_activation,
            allowed_user_ids=self._config.allowed_user_ids,
            allowed_chat_ids=self._config.allowed_chat_ids,
            allow_unaddressed_commands=self._config.allow_unaddressed_commands,
        )

    async def _handle_update(self, update: Any) -> None:
        update_id = getattr(update, "update_id", None)
        if update_id is not None and self._is_duplicate(f"update:{update_id}"):
            return
        message = getattr(update, "message", None) or getattr(update, "edited_message", None)
        if not message:
            return
        if getattr(update, "edited_message", None):
            # Suppress edits while the source ID remains in its bounded cache.
            # Commands on previously unseen edited messages are rejected too.
            if not self._config.edited_messages or (message.text or message.caption or "").lstrip().startswith("/"):
                return
            if f"message:{message.chat.id}:{message.message_id}" in self._seen_messages:
                return
        group = getattr(message, "media_group_id", None)
        if group and self._config.albums:
            # Check identity, allowlists, and command ownership before buffering.
            # Activation remains album-wide so an uncaptioned first member survives.
            if not should_accept_message(
                message,
                bot_id=self._bot_id,
                bot_username=self._bot_username,
                activation="always",
                allowed_user_ids=self._config.allowed_user_ids,
                allowed_chat_ids=self._config.allowed_chat_ids,
            ):
                return
            key = (
                str(message.chat.id),
                str(message.message_thread_id),
                str(group),
                str(
                    message.sender_chat.id if message.sender_chat else message.from_user.id if message.from_user else ""
                ),
            )
            now = time.monotonic()
            while self._passive_albums and next(iter(self._passive_albums.values()))[0] <= now:
                self._passive_albums.popitem(last=False)
            if key not in self._albums:
                if not self._accept(message):
                    if key not in self._passive_albums:
                        self._passive_albums[key] = (now + 0.35, [])
                        while len(self._passive_albums) > 100:
                            self._passive_albums.popitem(last=False)
                    buffered = self._passive_albums[key][1]
                    if len(buffered) < 10:
                        buffered.append(message)
                    return
                if len(self._album_tasks) >= 100:
                    logger.warning("Telegram pending album limit reached; dropping member")
                    return
                expires, buffered = self._passive_albums.pop(key, (now + 0.35, []))
                # Keep room for the activating caption even at the member cap.
                self._albums[key] = buffered[:9]
                task = asyncio.create_task(self._flush_album(key, delay=max(0, expires - now)))
                self._album_tasks.add(task)
                task.add_done_callback(self._album_tasks.discard)
            if len(self._albums[key]) < 10:
                self._albums[key].append(message)
            else:
                logger.warning("Telegram album member limit reached; dropping member")
            return
        if not self._accept(message):
            return
        native = await self._build_message(message, edited=bool(getattr(update, "edited_message", None)))
        if native:
            command = (message.text or "").split()[0].split("@")[0].lower() if message.text else ""
            if command in ("/stop", "/help"):
                if command == "/stop":
                    active_task = self._active.get((native["chat_id"], native["user_id"], native["message_thread_id"]))
                    if active_task:
                        active_task.cancel()
                else:
                    await self._send_text(
                        ChannelSubject(subject_id=native["chat_id"], metadata=native),
                        "/help — available commands\n/stop — stop your current response",
                    )
                return
            self.enqueue(native)

    async def _flush_album(self, key: tuple[str, str, str, str], *, delay: float = 0.35) -> None:
        await asyncio.sleep(delay)
        messages = sorted(self._albums.pop(key, []), key=lambda item: item.message_id)
        if not any(self._accept(item) for item in messages):
            return
        # Apply admission independently to every member; activation can come from
        # any caption, but may never authorize a different sender.
        result = None
        for item in messages:
            admitted = should_accept_message(
                item,
                bot_id=self._bot_id,
                bot_username=self._bot_username,
                activation="always",
                allowed_user_ids=self._config.allowed_user_ids,
                allowed_chat_ids=self._config.allowed_chat_ids,
            )
            if not admitted:
                continue
            native = await self._build_message(item)
            if native:
                if result is None:
                    result = native
                else:
                    result["content"].extend(native["content"])
                    result["media"].extend(native["media"])
        if result:
            self.enqueue(result)

    async def _build_native_from_update(self, update: Any) -> dict[str, Any] | None:
        message = getattr(update, "message", None) or getattr(update, "edited_message", None)
        if not message or not self._accept(message):
            return None
        if getattr(update, "edited_message", None) and (
            not self._config.edited_messages or (message.text or message.caption or "").lstrip().startswith("/")
        ):
            return None
        return await self._build_message(message, edited=bool(getattr(update, "edited_message", None)))

    async def _build_message(self, message: Any, *, edited: bool = False) -> dict[str, Any] | None:
        if self._is_duplicate(f"message:{message.chat.id}:{message.message_id}"):
            return None
        return await self._extract_message(message, edited=edited)

    async def _extract_message(self, message: Any, *, edited: bool = False) -> dict[str, Any] | None:
        content_parts: list[ContentPart] = []
        text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
        if text:
            content_parts.append(TextContent(text=text))

        media_metadata: list[dict[str, Any]] = []
        for attr in ("photo", "document", "video", "voice", "audio"):
            media = getattr(message, attr, None)
            if not media:
                continue
            file_obj = media[-1] if attr == "photo" else media
            file_id = getattr(file_obj, "file_id", "")
            filename = getattr(file_obj, "file_name", "") or attr
            url = ""
            if file_id:
                reference = uuid.uuid4().hex
                # Telegram PhotoSize has no mime_type; Bot API photos are JPEG.
                mime = (
                    "image/jpeg"
                    if attr == "photo"
                    else (getattr(file_obj, "mime_type", None) or "application/octet-stream")
                )
                self._files[reference] = (file_id, mime)
                while len(self._files) > 2000:
                    self._files.popitem(last=False)
                url = f"telegram-file://{self.channel_id}/{reference}"
                media_metadata.append(
                    {
                        "kind": attr,
                        "file_id": file_id,
                        "file_unique_id": getattr(file_obj, "file_unique_id", ""),
                        "filename": filename,
                        "mime_type": mime,
                        "size": getattr(file_obj, "file_size", None),
                    }
                )
            if attr == "photo":
                content_parts.append(ImageContent(url=url, alt_text=filename))
            elif attr == "video":
                content_parts.append(VideoContent(url=url))
            elif attr in ("voice", "audio"):
                content_parts.append(AudioContent(url=url))
            else:
                content_parts.append(FileContent(url=url, filename=filename))

        if not content_parts:
            return None

        chat = message.chat
        user = message.from_user
        chat_id = str(getattr(chat, "id", ""))
        user_id = str(user.id) if user and not message.sender_chat else ""
        is_group = getattr(chat, "type", "") in ("group", "supergroup")

        return {
            "chat_id": chat_id,
            "user_id": user_id,
            "message_id": str(getattr(message, "message_id", "")),
            "is_group": is_group,
            "message_thread_id": getattr(message, "message_thread_id", None),
            "content": content_parts,
            "media": media_metadata,
            "edited": edited,
            "reply_to_message_id": getattr(getattr(message, "reply_to_message", None), "message_id", None),
        }

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        if not url.startswith("telegram-file://"):
            return await super().fetch_remote_media(url)
        prefix = f"telegram-file://{self.channel_id}/"
        if not url.startswith(prefix) or url[len(prefix) :] not in self._files or not self._app:
            raise ValueError("Unknown or expired Telegram media reference")
        file_id, mime = self._files[url[len(prefix) :]]
        try:
            remote = await self._app.bot.get_file(file_id)
            if getattr(remote, "file_size", 0) and remote.file_size > 20 * 1024 * 1024:
                raise ValueError("Telegram cloud download exceeds 20 MB")
            data = bytes(await remote.download_as_bytearray())
            # Content signatures override missing or incorrect Telegram metadata.
            if data.startswith(b"\xff\xd8\xff"):
                mime = "image/jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                mime = "image/png"
            elif data.startswith((b"GIF87a", b"GIF89a")):
                mime = "image/gif"
            elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                mime = "image/webp"
            return data, mime
        except TelegramError:
            # SDK exceptions can contain credential-bearing URLs.
            raise RuntimeError("Telegram media download failed") from None

    def _send_options(self, subject: ChannelSubject, *, text: bool = False) -> dict[str, Any]:
        options: dict[str, Any] = {
            "disable_notification": self._config.disable_notification,
            "protect_content": self._config.protect_content,
        }
        if subject.metadata.get("message_thread_id"):
            options["message_thread_id"] = subject.metadata["message_thread_id"]
        source = subject.metadata.get("source_message_id") or subject.metadata.get("message_id")
        if self._config.reply_to_message and source:
            options["reply_parameters"] = ReplyParameters(message_id=int(source), allow_sending_without_reply=True)
        if text:
            options["link_preview_options"] = LinkPreviewOptions(is_disabled=not self._config.link_preview)
        return options

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        if not self._config.show_typing or not self._app:
            return
        chat_id = subject.metadata.get("chat_id") or subject.subject_id
        try:
            await self._request(
                self._app.bot.send_chat_action,
                chat_id=int(chat_id),
                action="typing",
                **(
                    {"message_thread_id": subject.metadata["message_thread_id"]}
                    if subject.metadata.get("message_thread_id")
                    else {}
                ),
            )
        except TelegramError:
            logger.debug("Telegram typing indicator failed")

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        if not self._app or not text.strip():
            return
        chat_id = int(subject.metadata.get("chat_id") or subject.subject_id)
        state = self._stream.get()
        if state and state.get("delivery_failed"):
            return
        if state and state.get("finalizing") and text == self._clean_output(state.get("text", "")):
            try:
                await self._finish_preview(subject, text, state)
            except TelegramError:
                state["delivery_failed"] = True
                raise
            return
        for html, plain in split_telegram_html(markdown_to_telegram_html(text), limit=4000):
            try:
                await self._request(
                    self._app.bot.send_message,
                    chat_id=chat_id,
                    text=html,
                    parse_mode="HTML",
                    **self._send_options(subject, text=True),
                )
            except BadRequest as exc:
                if not formatting_error(exc):
                    raise
                try:
                    await self._request(
                        self._app.bot.send_message,
                        chat_id=chat_id,
                        text=plain,
                        **self._send_options(subject, text=True),
                    )
                except NetworkError:
                    if state is not None:
                        state["delivery_failed"] = True
                    raise
            except NetworkError:
                if state is not None:
                    state["delivery_failed"] = True
                raise

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        from telegram import InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo

        if not self._app:
            return
        pending: list[ContentPart] = []
        kind = ""

        async def flush() -> None:
            while pending:
                batch = pending[:10]
                del pending[:10]
                if len(batch) == 1:
                    await self._send_media(subject, batch[0])
                    continue
                inputs: list[Any] = []
                for part in batch:
                    try:
                        source = await self._media_source(part)
                    except (ValueError, RuntimeError, OSError):
                        # Preflight failed before a group request: individual sends
                        # preserve each attachment or emit its unavailable marker.
                        for item in batch:
                            await self._send_media(subject, item)
                        inputs.clear()
                        break
                    cls = (
                        InputMediaPhoto
                        if isinstance(part, ImageContent)
                        else InputMediaVideo
                        if isinstance(part, VideoContent)
                        else InputMediaAudio
                        if isinstance(part, AudioContent)
                        else InputMediaDocument
                    )
                    inputs.append(cls(media=source))
                if not inputs:
                    continue
                # No fallback after an attempted group send: its result may be ambiguous.
                await self._request(
                    self._app.bot.send_media_group,
                    chat_id=int(subject.metadata.get("chat_id") or subject.subject_id),
                    media=inputs,
                    **self._send_options(subject),
                )

        for part in parts:
            next_kind = (
                "visual"
                if isinstance(part, ImageContent | VideoContent)
                else "audio"
                if isinstance(part, AudioContent) and not self._config.audio_as_voice
                else "document"
                if isinstance(part, FileContent)
                else ""
            )
            if not self._config.albums or not next_kind:
                await flush()
                if isinstance(part, TextContent):
                    await self._send_text(subject, part.text)
                else:
                    await self._send_media(subject, part)
            else:
                if kind != next_kind:
                    await flush()
                kind = next_kind
                pending.append(part)
        await flush()

    async def _media_source(self, media: ContentPart) -> Any:
        url = self._get_media_url(media)
        if (
            getattr(media, "data", None)
            or getattr(media, "local_path", None)
            or (url and url.startswith("telegram-file://"))
        ):
            data, mime = await self.load_media_bytes(media)
            if len(data) > _TELEGRAM_MAX_FILE_SIZE_BYTES:
                raise ValueError("Telegram upload exceeds 50 MB")
            stream = BytesIO(data)
            stream.name = getattr(media, "filename", None) or f"file.{mime.split('/')[-1]}"
            return stream
        if url:
            return "https:" + url if url.startswith("//") else url
        raise ValueError("Telegram attachment has no source")

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        if not self._app:
            return
        chat_id = int(subject.metadata.get("chat_id") or subject.subject_id)
        kwargs = self._send_options(subject)

        try:
            source = await self._media_source(media)
        except (ValueError, RuntimeError, OSError):
            await self._send_text(subject, f"[{self._get_media_label(media)} (upload unavailable)]")
            return
        if isinstance(media, ImageContent):
            await self._request(self._app.bot.send_photo, chat_id=chat_id, photo=source, **kwargs)
        elif isinstance(media, VideoContent):
            await self._request(self._app.bot.send_video, chat_id=chat_id, video=source, **kwargs)
        elif isinstance(media, AudioContent):
            await self._send_audio(chat_id, source, kwargs)
        else:
            await self._request(self._app.bot.send_document, chat_id=chat_id, document=source, **kwargs)

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        data = raw_payload if isinstance(raw_payload, dict) else {}
        chat_id = str(data.get("chat_id") or "unknown")
        user_id = str(data.get("user_id") or chat_id)
        content = data.get("content") or []
        is_group = bool(data.get("is_group"))

        metadata = {
            "chat_id": chat_id,
            "user_id": user_id,
            "message_id": data.get("message_id", ""),
            "message_thread_id": data.get("message_thread_id"),
            "is_group": is_group,
            "source_message_id": data.get("message_id", ""),
            "sender_id": user_id,
            "reply_to_message_id": data.get("reply_to_message_id"),
            "media": data.get("media", []),
            "edited": data.get("edited", False),
            "topic_isolation": self._config.topic_isolation,
        }

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=(
                    f"{chat_id}:topic:{metadata['message_thread_id']}"
                    if self._config.topic_isolation and metadata["message_thread_id"] is not None
                    else chat_id
                ),
                display_name=user_id,
                chat_type="group" if is_group else "direct",
                metadata=metadata,
            ),
            channel_session_id=self._connection_session or f"{self.channel_id}-unconnected",
            content=content,
            metadata=metadata,
        )

    async def _send_audio(self, chat_id: int, audio: Any, kwargs: dict[str, Any]) -> None:
        if self._config.audio_as_voice:
            await self._request(self._app.bot.send_voice, chat_id=chat_id, voice=audio, **kwargs)
        else:
            await self._request(self._app.bot.send_audio, chat_id=chat_id, audio=audio, **kwargs)

    def register_callback(
        self, subject: ChannelSubject, action: Callable[[], Awaitable[None]], *, ttl: float = 300
    ) -> str:
        """Host hook for authorized model/agent options or private approvals.

        The host must enforce its own application permissions before registering
        an action. Telegram identity or administrator status grants no privilege.
        Actions run inline in the serial SDK update handler: apply short state
        changes or enqueue work and return. Never await a whole agent turn here;
        use enqueue() so later updates, including Stop, remain responsive.
        """
        return self.interactions.register(
            str(subject.metadata.get("user_id", "")),
            str(subject.metadata.get("chat_id") or subject.subject_id),
            subject.metadata.get("message_thread_id"),
            action,
            ttl=ttl,
        )

    async def send_buttons(
        self,
        subject: ChannelSubject,
        text: str,
        actions: list[tuple[str, Callable[[], Awaitable[None]]]],
        *,
        ttl: float = 300,
    ) -> None:
        """Render host-authorized model, agent, or approval choices as native buttons."""
        if not self._app:
            return
        tokens = [self.register_callback(subject, action, ttl=ttl) for _, action in actions]
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(label, callback_data=token)]
                for (label, _), token in zip(actions, tokens, strict=True)
            ]
        )
        try:
            await self._request(
                self._app.bot.send_message,
                chat_id=int(subject.metadata.get("chat_id") or subject.subject_id),
                text=text,
                reply_markup=markup,
                **self._send_options(subject, text=True),
            )
        except TelegramError:
            for token in tokens:
                self.interactions.pending.pop(token, None)
            raise

    async def _handle_callback(self, update: Any, _context: Any = None) -> None:
        query = update.callback_query
        if not query:
            return
        await self._request(query.answer)
        if not query.message or not query.from_user:
            return
        async with sanitized_errors():
            await self.interactions.invoke(
                query.data or "",
                str(query.from_user.id),
                str(query.message.chat.id),
                getattr(query.message, "message_thread_id", None),
            )

    async def _reaction(self, subject: ChannelSubject, emoji: str) -> None:
        if not self._config.status_reactions or not self._app:
            return
        source = subject.metadata.get("source_message_id")
        if not source:
            return
        try:
            await self._request(
                self._app.bot.set_message_reaction,
                chat_id=int(subject.metadata.get("chat_id") or subject.subject_id),
                message_id=int(source),
                reaction=emoji,
            )
        except TelegramError:
            logger.debug("Telegram reaction unavailable")

    async def _process_inbound(self, message: InboundMessage, subject: ChannelSubject) -> bool:
        subject = ChannelSubject(
            subject_id=subject.subject_id,
            display_name=subject.display_name,
            chat_type=subject.chat_type,
            metadata={**subject.metadata, **message.metadata},
        )
        key = (
            str(subject.metadata.get("chat_id") or subject.subject_id),
            str(message.metadata.get("user_id", "")),
            subject.metadata.get("message_thread_id"),
        )

        async def run() -> bool:
            state: dict[str, Any] = {
                "text": "",
                "last": 0.0,
                "subject": subject,
                "draft_id": int(uuid.uuid4().hex[:7], 16),
            }
            context = self._stream.set(state)
            try:
                await self._reaction(subject, "👀")
                success = await super(TelegramChannel, self)._process_inbound(message, subject)
                success = success and not state.get("delivery_failed", False)
                await self._reaction(subject, "👍" if success else "👎")
                return success
            finally:
                await self._clear_draft(subject, state)
                if state.get("stop_token"):
                    self.interactions.pending.pop(state["stop_token"], None)
                if state.get("message_id"):
                    try:
                        await self._request(
                            self._app.bot.edit_message_reply_markup,
                            chat_id=int(key[0]),
                            message_id=state["message_id"],
                            reply_markup=None,
                        )
                    except TelegramError:
                        logger.debug("Telegram stop button cleanup unavailable")
                self._stream.reset(context)

        task = asyncio.create_task(run())
        self._active[key] = task
        try:
            return await task
        except asyncio.CancelledError:
            # A button cancels this child only; external worker cancellation still propagates.
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            return False
        finally:
            if self._active.get(key) is task:
                self._active.pop(key, None)

    async def _stream_events(self, message: InboundMessage) -> AsyncIterator[MessageEvent]:
        state = self._stream.get()
        # Closing this wrapper must close the host processor. Aclosing an async
        # generator paused at ``yield`` does not run a nested ``async for``
        # finalizer, so ERROR (a terminal event) would skip host cleanup.
        source = self._original_processor(message)
        try:
            async for event in source:
                if state is not None:
                    if event.type == MessageEventType.DELTA:
                        state["text"] += "".join(part.text for part in event.content if isinstance(part, TextContent))
                        if self._config.streaming_mode != "off" and time.monotonic() - state["last"] >= 1:
                            await self._preview(state["subject"], state)
                        continue
                    elif event.type in (MessageEventType.FLUSH, MessageEventType.COMPLETED, MessageEventType.MESSAGE):
                        state["finalizing"] = True
                        if event.type == MessageEventType.MESSAGE:
                            final_text = "".join(part.text for part in event.content if isinstance(part, TextContent))
                            # A textual final is authoritative, including revisions. A
                            # media-only final still flushes the pending delta text.
                            if final_text:
                                state["text"] = final_text
                                event = event.model_copy(
                                    update={
                                        "content": [part for part in event.content if not isinstance(part, TextContent)]
                                    }
                                )
                        if state["text"]:
                            yield MessageEvent.delta(state["text"])
                yield event
                if state is not None and event.type in (MessageEventType.FLUSH, MessageEventType.MESSAGE):
                    state.update(text="", finalizing=False, last=0.0)
            if state is not None and state["text"]:
                yield MessageEvent.delta(state["text"])
            # BaseChannel defines successful completion via COMPLETED, not iterator exhaustion.
        finally:
            await close_event_stream(source)

    async def _preview(self, subject: ChannelSubject, state: dict[str, Any]) -> None:
        if not self._app or state.get("disabled"):
            return
        text = self._clean_output(state["text"]).encode("utf-16-le")[:8000].decode("utf-16-le", errors="ignore")
        if not text:
            return
        chat = int(subject.metadata.get("chat_id") or subject.subject_id)
        mode = self._config.streaming_mode
        draft = (
            not state.get("use_edit")
            and mode in ("auto", "draft")
            and subject.chat_type == "direct"
            and callable(getattr(self._app.bot, "send_message_draft", None))
        )
        state["last"] = time.monotonic()
        try:
            if draft:
                await self._request(
                    self._app.bot.send_message_draft,
                    chat_id=chat,
                    draft_id=state["draft_id"],
                    text=text,
                    **(
                        {"message_thread_id": subject.metadata["message_thread_id"]}
                        if subject.metadata.get("message_thread_id")
                        else {}
                    ),
                )
                state["draft_sent"] = True
            elif state.get("message_id"):
                await self._request(
                    self._app.bot.edit_message_text, chat_id=chat, message_id=state["message_id"], text=text
                )
            else:
                task = asyncio.current_task()

                async def cancel() -> None:
                    if task is not None and not task.done():
                        task.cancel()

                token = self.register_callback(subject, cancel)
                state["stop_token"] = token
                sent = await self._request(
                    self._app.bot.send_message,
                    chat_id=chat,
                    text=text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Stop", callback_data=token)]]),
                    **self._send_options(subject, text=True),
                )
                state["message_id"] = sent.message_id
        except BadRequest:
            # A rejected draft is safe to replace with an edit preview next time.
            if draft:
                state["use_edit"] = True
            else:
                state["disabled"] = True
        except TelegramError:
            # A timeout may have delivered the preview. Do not resend it.
            state["disabled"] = True
            state["delivery_failed"] = True

    async def _clear_draft(self, subject: ChannelSubject, state: dict[str, Any]) -> None:
        if not state.pop("draft_sent", False) or not self._app:
            return
        try:
            await self._request(
                self._app.bot.send_message_draft,
                chat_id=int(subject.metadata.get("chat_id") or subject.subject_id),
                draft_id=state["draft_id"],
                text="",
                **(
                    {"message_thread_id": subject.metadata["message_thread_id"]}
                    if subject.metadata.get("message_thread_id")
                    else {}
                ),
            )
        except TelegramError:
            logger.debug("Telegram draft cleanup unavailable")

    async def _finish_preview(self, subject: ChannelSubject, text: str, state: dict[str, Any]) -> None:
        chunks = split_telegram_html(markdown_to_telegram_html(text), limit=4000)
        message_id = state.pop("message_id", None)
        state["finalizing"] = False
        if state.get("draft_sent"):
            await self._clear_draft(subject, state)
        if state.get("stop_token"):
            self.interactions.pending.pop(state.pop("stop_token"), None)
        if message_id and chunks:
            html, plain = chunks.pop(0)
            chat = int(subject.metadata.get("chat_id") or subject.subject_id)
            try:
                await self._request(
                    self._app.bot.edit_message_text,
                    chat_id=chat,
                    message_id=message_id,
                    text=html,
                    parse_mode="HTML",
                    reply_markup=None,
                    link_preview_options=LinkPreviewOptions(is_disabled=not self._config.link_preview),
                )
            except BadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    if not formatting_error(exc):
                        raise
                    await self._request(
                        self._app.bot.edit_message_text,
                        chat_id=chat,
                        message_id=message_id,
                        text=plain,
                        reply_markup=None,
                    )
        for html, plain in chunks:
            try:
                await self._request(
                    self._app.bot.send_message,
                    chat_id=int(subject.metadata.get("chat_id") or subject.subject_id),
                    text=html,
                    parse_mode="HTML",
                    **self._send_options(subject, text=True),
                )
            except BadRequest as exc:
                if not formatting_error(exc):
                    raise
                await self._request(
                    self._app.bot.send_message,
                    chat_id=int(subject.metadata.get("chat_id") or subject.subject_id),
                    text=plain,
                    **self._send_options(subject, text=True),
                )
