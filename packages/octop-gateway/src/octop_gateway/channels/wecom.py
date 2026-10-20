"""WeCom (Enterprise WeChat) channel: WebSocket long connection via aibot SDK.

Uses wecom-aibot-sdk (pip install wecom-aibot-sdk) for:
- WebSocket bidirectional messaging (no public URL needed)
- Stream reply support (thinking bubble + progressive output)
- Media send/receive

Connection is initiated by the client to WeChat Work servers.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import mimetypes
import time
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.constraints import ChannelConstraints, tool_hint_message
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEventType,
    TextContent,
    VideoContent,
)
from octop_gateway.push_routing import alias_subject_fields
from octop_gateway.utils import close_event_stream

logger = logging.getLogger(__name__)

# Stream reply timeout
_STREAM_REPLY_TIMEOUT = 10


@dataclass
class WeComConfig(ChannelConfig):
    """Configuration for WeCom AI Bot channel.

    Uses wecom-aibot-sdk WebSocket connection (not HTTP callback).

    Attributes:
        bot_id: AI Bot ID from WeCom admin console.
        secret: Bot secret for authentication.
        ws_url: Optional custom WebSocket URL (leave empty for default).
        channel_id: Optional explicit channel ID; auto-generated UUID if omitted.
        tenant_id: Optional tenant identifier for multi-tenant deployments.
    """

    bot_id: str = ""
    secret: str = ""
    ws_url: str = ""

    required_credentials = ("bot_id", "secret")


class WeComChannel(BaseChannel):
    """WeCom channel using wecom-aibot-sdk WebSocket.

    No public URL needed — connects to WeCom servers via WebSocket.
    Supports stream reply (progressive output with thinking bubble).
    """

    channel_type = "wecom"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: WeComConfig,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints: ChannelConstraints | None = None,
    ) -> None:
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            debounce_seconds=debounce_seconds,
            constraints=constraints,
            config=config,
        )
        self._config = config
        self._ws_client: Any = None
        self._connected = False
        self._running = False
        # WebSocket connection session ID (generated on each connect/reconnect)
        self._ws_session_id: str | None = None

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            reply_timeout=10.0,
            timeout_strategy="placeholder",
            send_rate_limit=(2, 5.0),
            show_thinking=False,
            show_tool_hints=True,
            placeholder_texts=["⏳ 思考中...", "🤔 处理中...", "💭 让我想想..."],
        )

    async def start(self) -> None:
        """Start WebSocket connection via wecom-aibot-sdk."""
        self._running = True

        if not self._config.bot_id or not self._config.secret:
            raise RuntimeError("WeComChannel: bot_id and secret are required")

        try:
            from wecom_aibot_sdk import WSClient
        except ImportError as e:
            raise ImportError(
                "wecom-aibot-sdk is required for WeComChannel. Install with: pip install wecom-aibot-sdk"
            ) from e

        self._ws_client = WSClient(
            bot_id=self._config.bot_id,
            secret=self._config.secret,
            ws_url=self._config.ws_url or "",
            max_reconnect_attempts=-1,  # infinite reconnect
            heartbeat_interval=30000,
        )

        # Register event handlers
        self._ws_client.on("authenticated", self._on_authenticated)
        self._ws_client.on("disconnected", self._on_disconnected)
        self._ws_client.on("error", self._on_error)
        self._ws_client.on("message", self._on_message)

        await self._ws_client.connect()
        logger.info("WeComChannel started (bot_id=%s)", self._config.bot_id[:12])

    async def stop(self) -> None:
        """Disconnect WebSocket."""
        self._running = False
        if self._ws_client:
            with contextlib.suppress(Exception):
                await self._ws_client.disconnect()
            self._ws_client = None
        self._connected = False
        await self._close_http()
        logger.info("WeComChannel stopped")

    def _enrich_push_metadata(self, subject: ChannelSubject, meta: dict[str, Any]) -> dict[str, Any]:
        out = dict(meta)
        alias_subject_fields(out, subject.subject_id, "chat_id")
        return out

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Send text via reply_stream, response_url, or proactive send_message.

        Priority: reply_stream (if frame available) > response_url (webhook)
        > send_message (proactive, e.g. cron).
        """
        meta = subject.metadata
        ws_client = meta.get("_ws_client", self._ws_client)
        frame = meta.get("_frame")
        response_url = meta.get("response_url", "")

        # Method 1: reply via SDK stream reply (async)
        if ws_client and frame:
            try:
                from wecom_aibot_sdk import generate_req_id

                stream_id = generate_req_id("him")
                await ws_client.reply_stream(
                    frame=frame,
                    stream_id=stream_id,
                    content=text,
                    finish=True,
                )
                logger.info("WeComChannel sent via reply_stream: %s", text[:50])
                return
            except Exception:  # pylint: disable=broad-except
                # The SDK does not expose a stable exception hierarchy for stream replies.
                logger.exception("WeComChannel reply_stream failed, trying response_url")

        # Method 2: reply via response_url (HTTP webhook)
        if response_url:
            try:
                http = await self._ensure_http()
                payload = {"msgtype": "text", "text": {"content": text}}
                async with http.post(response_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.debug("WeComChannel sent via response_url: %s", text[:50])
                    else:
                        body = await resp.text()
                        logger.error("WeComChannel response_url failed: %d %s", resp.status, body[:200])
                        msg = f"WeCom response_url failed: HTTP {resp.status}"
                        raise RuntimeError(msg)
                return
            except RuntimeError:
                raise
            except (aiohttp.ClientError, TimeoutError) as exc:
                logger.exception("WeComChannel response_url send failed")
                raise RuntimeError("WeCom response_url send failed") from exc

        # Method 3: proactive send (no frame context, e.g. cron)
        client = self._ws_client
        if client is None:
            msg = "WeComChannel: no ws_client available for proactive send"
            logger.warning(msg)
            raise RuntimeError(msg)

        chat_id = meta.get("chat_id") or subject.subject_id
        if not chat_id:
            msg = "WeComChannel: no chat_id or subject_id for proactive send"
            logger.warning(msg)
            raise RuntimeError(msg)

        try:
            await client.send_message(
                chat_id,
                {"msgtype": "markdown", "markdown": {"content": text}},
            )
            logger.info("WeComChannel sent via send_message: chat_id=%s", str(chat_id)[:16])
        except Exception as exc:  # pylint: disable=broad-except
            # The SDK does not expose a stable exception hierarchy for proactive sends.
            logger.exception("WeComChannel send_message failed")
            raise RuntimeError("WeCom send_message failed") from exc

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Send text via stream reply and media via native WeCom messages."""
        from octop_gateway.utils import extract_media, extract_text

        text_content = extract_text(parts)
        if text_content:
            await self._send_text(subject, text_content)
        for media in extract_media(parts):
            await self._send_media(subject, media)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Upload a media item and reply in the current chat natively."""
        meta = subject.metadata
        ws_client = meta.get("_ws_client", self._ws_client)
        if ws_client is None:
            raise RuntimeError("WeComChannel: no ws_client available for media send")

        media_type, filename = self._wecom_media_type_and_filename(media)
        try:
            data, _mime = await self.load_media_bytes(media)
            result = await ws_client.upload_media(data, type=media_type, filename=filename)
            media_id = result.get("media_id")
            if not media_id:
                raise RuntimeError("WeCom media upload returned no media_id")

            frame = meta.get("_frame")
            if frame:
                await ws_client.reply_media(frame, media_type, media_id)
                return

            chat_id = meta.get("chat_id") or subject.subject_id
            if not chat_id:
                raise RuntimeError("WeComChannel: no chat_id or subject_id for media send")
            await ws_client.send_media_message(chat_id, media_type, media_id)
        except Exception:  # pylint: disable=broad-except
            # SDK upload methods and MediaBackend implementations have adapter-specific errors.
            logger.exception("WeComChannel native media send failed")
            url = self._get_media_url(media)
            label = self._get_media_label(media)
            if url:
                await self._send_text(subject, f"[{label}: {url}]")
            else:
                await self._send_text(subject, f"[{label} (native upload failed)]")

    @staticmethod
    def _wecom_media_type_and_filename(media: ContentPart) -> tuple[str, str]:
        if isinstance(media, ImageContent):
            media_type = "image"
            default_name = "image.png"
        elif isinstance(media, AudioContent):
            media_type = "voice"
            default_name = "voice.amr"
        elif isinstance(media, VideoContent):
            media_type = "video"
            default_name = "video.mp4"
        elif isinstance(media, FileContent):
            media_type = "file"
            default_name = "file.bin"
        else:
            raise ValueError(f"Unsupported WeCom media type: {type(media).__name__}")

        filename = media.filename if isinstance(media, FileContent) else ""
        if not filename:
            mime = getattr(media, "mime_type", None)
            extension = mimetypes.guess_extension(mime) if mime else None
            if extension:
                filename = f"{media_type}{extension}"
        return media_type, filename or default_name

    async def _persist_media(self, message: InboundMessage) -> None:
        """Download WeCom media through the SDK so ``aeskey`` is applied."""
        if not self._media_backend:
            return

        aes_keys = message.metadata.get("_media_aes_keys", {})
        ws_client = message.metadata.get("_ws_client", self._ws_client)
        timestamp = int(time.time())

        for index, part in enumerate(message.content):
            if isinstance(part, TextContent) or part.local_path:
                continue
            url = getattr(part, "url", "")
            if not url:
                continue

            try:
                aes_key = aes_keys.get(url)
                if ws_client is not None and aes_key:
                    result = await ws_client.download_file(url, aes_key)
                    data = result["buffer"]
                    downloaded_name = result.get("filename")
                    if isinstance(part, FileContent) and downloaded_name and not part.filename:
                        part.filename = downloaded_name
                    original_name = part.filename if isinstance(part, FileContent) else ""
                    mime = mimetypes.guess_type(downloaded_name or original_name or url)[0]
                    part.mime_type = part.mime_type or mime or "application/octet-stream"
                else:
                    data, mime = await self.fetch_remote_media(url)
                    part.mime_type = part.mime_type or mime

                filename = self._resolve_media_filename(part, index, timestamp)
                key = f"{self.channel_type}/{self._channel_id}/{filename}"
                await self._media_backend.save(data, key)
                part.local_path = key
                part.size = len(data)
                logger.info(
                    "WeCom media decrypted and persisted: %s (%d bytes) -> key=%s",
                    type(part).__name__,
                    len(data),
                    key,
                )
            except Exception:  # pylint: disable=broad-except
                # Decryption and host-provided storage are a fail-soft media boundary.
                logger.warning(
                    "Failed to decrypt/persist WeCom media: url=%s",
                    url[:100],
                    exc_info=True,
                )

    async def handle_inbound(self, raw_payload: Any) -> None:
        """Override: stream deltas progressively via WeCom reply_stream.

        Instead of accumulating all deltas and sending once (BaseChannel default),
        sends progressive updates via reply_stream(finish=False) as tokens arrive.
        WeCom displays the content incrementally with a thinking bubble effect.

        Constraint integration:
          - One :meth:`_acquire_rate_slot` is taken at the top: each
            ``reply_stream(finish=False)`` is a partial update of the same
            logical user-visible message, not a separate send.
          - When ``reply_timeout > 0`` and ``timeout_strategy == "placeholder"``,
            the wait for the *first* processor event is bounded; if the
            first token does not arrive in time, a placeholder is streamed
            so WeCom does not drop the connection. Streaming continues
            normally afterwards.
          - The error path uses :attr:`ChannelConstraints.placeholder_text`
            so manager-level overrides take effect.
        """
        message = self.parse_inbound(raw_payload)

        # Auto-persist media if backend configured
        if self._media_backend:
            await self._persist_media(message)

        self._track_subject(message)
        meta = message.metadata

        ws_client = meta.get("_ws_client", self._ws_client)
        frame = meta.get("_frame")

        # If no frame/ws_client available, fall back to BaseChannel behavior
        if not ws_client or not frame:
            await super().handle_inbound(raw_payload)
            return

        # One rate-limit slot for the whole stream reply.
        await self._acquire_rate_slot()

        from wecom_aibot_sdk import generate_req_id

        stream_id = generate_req_id("him")
        content_buffer: list[str] = []
        thinking_buffer: list[str] = []
        media_buffer: list[ContentPart] = []
        stream_open = False

        # First-token timeout handling: if reply_timeout is configured and
        # the first event does not arrive in (timeout * 0.8) seconds, emit
        # a placeholder via reply_stream and continue streaming.
        #
        # We use ``asyncio.wait`` (not ``wait_for``) so the underlying
        # ``__anext__`` task is *not* cancelled on timeout — the placeholder
        # is streamed, then we await the in-flight first event normally.
        iterator = self._processor(message)
        first_event = None
        if self._constraints.reply_timeout > 0 and self._constraints.timeout_strategy == "placeholder":
            first_task: asyncio.Task[Any] = asyncio.create_task(iterator.__anext__())  # type: ignore[arg-type]
            done, _pending = await asyncio.wait(
                [first_task],
                timeout=self._constraints.reply_timeout * 0.8,
            )
            if not done:
                # Timeout fired — stream a placeholder, then keep waiting.
                placeholder = self._constraints.placeholder_text
                if placeholder:
                    try:
                        await ws_client.reply_stream(
                            frame=frame,
                            stream_id=stream_id,
                            content=placeholder,
                            finish=False,
                        )
                        stream_open = True
                    except Exception:  # pylint: disable=broad-except
                        # A placeholder failure must not cancel the underlying processor.
                        logger.debug("WeCom placeholder reply_stream failed", exc_info=True)
            try:
                first_event = await first_task
            except StopAsyncIteration:
                # Processor produced no events at all — nothing to stream.
                return

        async def _events() -> Any:
            if first_event is not None:
                yield first_event
            async for ev in iterator:
                yield ev

        events = _events()
        try:
            async for event in events:
                if event.type == MessageEventType.TYPING:
                    pass  # WeCom shows thinking bubble on first stream chunk

                elif event.type == MessageEventType.THINKING_DELTA:
                    if self._constraints.show_thinking:
                        for part in event.content:
                            if isinstance(part, TextContent) and part.text:
                                thinking_buffer.append(part.text)
                        thinking_text = self._constraints.thinking_template.format(
                            content="".join(thinking_buffer).strip()
                        )
                        await ws_client.reply_stream(
                            frame=frame,
                            stream_id=stream_id,
                            content=thinking_text,
                            finish=False,
                        )
                        stream_open = True

                elif event.type == MessageEventType.FLUSH:
                    thinking_buffer.clear()

                elif event.type == MessageEventType.DELTA:
                    for part in event.content:
                        if isinstance(part, TextContent) and part.text:
                            content_buffer.append(part.text)
                    full_text = "".join(content_buffer)
                    if full_text:
                        await ws_client.reply_stream(
                            frame=frame,
                            stream_id=stream_id,
                            content=full_text,
                            finish=False,
                        )
                        stream_open = True

                elif event.type == MessageEventType.TOOL_START:
                    if self._constraints.show_tool_hints:
                        hint = tool_hint_message(
                            event.metadata,
                            self._constraints,
                            phase="start",
                        )
                        await ws_client.reply_stream(
                            frame=frame,
                            stream_id=stream_id,
                            content=hint,
                            finish=False,
                        )
                        stream_open = True

                elif event.type == MessageEventType.TOOL_END:
                    pass

                elif event.type == MessageEventType.ERROR:
                    error_text = event.error or "An unexpected error occurred."
                    await ws_client.reply_stream(
                        frame=frame,
                        stream_id=stream_id,
                        content=error_text,
                        finish=True,
                    )
                    return

                elif event.type == MessageEventType.MESSAGE:
                    from octop_gateway.utils import extract_media, extract_text

                    text = extract_text(event.content)
                    if text:
                        content_buffer.append(text)
                    media_buffer.extend(extract_media(event.content))

                elif event.type == MessageEventType.COMPLETED:
                    break

        except Exception:  # pylint: disable=broad-except
            # The processor and SDK stream are independent extension boundaries.
            logger.exception("WeComChannel streaming error")
            error_text = self._constraints.placeholder_text or "An unexpected error occurred."
            await ws_client.reply_stream(
                frame=frame,
                stream_id=stream_id,
                content=error_text,
                finish=True,
            )
            return

        finally:
            await close_event_stream(events)
            await close_event_stream(iterator)

        # Close a text stream before replying with native media messages.
        final_text = "".join(content_buffer)
        if final_text or stream_open or not media_buffer:
            await ws_client.reply_stream(
                frame=frame,
                stream_id=stream_id,
                content=final_text or "✅",
                finish=True,
            )

        if media_buffer:
            subject_id = message.channel_subject.subject_id if message.channel_subject else ""
            media_meta = dict(meta)
            if final_text or stream_open:
                # The callback frame has already completed its stream reply;
                # send subsequent media proactively to the same chat.
                media_meta.pop("_frame", None)
            reply_subject = ChannelSubject(subject_id=subject_id, metadata=media_meta)
            for media in media_buffer:
                await self._send_media(reply_subject, media)

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse WebSocket message frame into InboundMessage.

        Actual SDK message format:
        {
            "msgid": "...",
            "aibotid": "...",
            "chattype": "single" | "group",
            "from": {"userid": "T48500024A"},
            "msgtype": "text" | "image" | "file" | ...,
            "content": {"text": "hello"} | ...,
            "response_url": "https://...",
            "_frame": <original frame ref>
        }
        """
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        data = raw_payload if isinstance(raw_payload, dict) else {}

        # Extract sender info
        sender_info = data.get("from", {})
        sender_id = sender_info.get("userid", "") or sender_info.get("user_id", "unknown")
        chat_type = data.get("chattype", "single")
        chat_id = data.get("chatid", "")
        session_id = self._ws_session_id or "wecom-unconnected"

        # Parse message content based on msgtype
        content_parts: list[ContentPart] = []
        media_aes_keys: dict[str, str] = {}
        msg_type = data.get("msgtype", "text")

        def _remember_aes_key(media_obj: dict[str, Any], url: str) -> None:
            aes_key = media_obj.get("aeskey") or media_obj.get("aes_key")
            if url and aes_key:
                media_aes_keys[url] = aes_key

        if msg_type == "text":
            # Text content is in data["text"]["content"]
            text_obj = data.get("text", {})
            text = text_obj.get("content", "") if isinstance(text_obj, dict) else str(text_obj)
            if text:
                content_parts.append(TextContent(text=text))
        elif msg_type == "image":
            img_obj = data.get("image", {})
            url = img_obj.get("url", "") if isinstance(img_obj, dict) else ""
            if url:
                content_parts.append(ImageContent(url=url))
                _remember_aes_key(img_obj, url)
        elif msg_type == "file":
            file_obj = data.get("file", {})
            url = file_obj.get("url", "") if isinstance(file_obj, dict) else ""
            filename = file_obj.get("file_name", "") if isinstance(file_obj, dict) else ""
            if url:
                content_parts.append(FileContent(url=url, filename=filename))
                _remember_aes_key(file_obj, url)
        elif msg_type == "voice":
            voice_obj = data.get("voice", {})
            url = voice_obj.get("url", "") if isinstance(voice_obj, dict) else ""
            if url:
                content_parts.append(AudioContent(url=url))
                _remember_aes_key(voice_obj, url)
        elif msg_type == "video":
            video_obj = data.get("video", {})
            url = video_obj.get("url", "") if isinstance(video_obj, dict) else ""
            if url:
                content_parts.append(VideoContent(url=url))
                _remember_aes_key(video_obj, url)
        elif msg_type == "mixed":
            mixed_obj = data.get("mixed", {})
            items = mixed_obj.get("msg_item", []) if isinstance(mixed_obj, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("msgtype", "")
                if item_type == "text":
                    text_obj = item.get("text", {})
                    text = text_obj.get("content", "") if isinstance(text_obj, dict) else ""
                    if text:
                        content_parts.append(TextContent(text=text))
                elif item_type == "image":
                    image_obj = item.get("image", {})
                    url = image_obj.get("url", "") if isinstance(image_obj, dict) else ""
                    if url:
                        content_parts.append(ImageContent(url=url))
                        _remember_aes_key(image_obj, url)
        else:
            # Fallback: try text field
            text_obj = data.get("text", {})
            text = text_obj.get("content", "") if isinstance(text_obj, dict) else str(data.get("content", ""))
            if text:
                content_parts.append(TextContent(text=text))

        if not content_parts:
            content_parts.append(TextContent(text=""))

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(subject_id=sender_id, metadata={}),
            channel_session_id=session_id,
            content=content_parts,
            metadata={
                "to_handle": sender_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "msgid": data.get("msgid", ""),
                "response_url": data.get("response_url", ""),
                "_media_aes_keys": media_aes_keys,
                "_ws_client": self._ws_client,
                "_frame": data.get("_frame", data),
            },
        )

    # --- Event handlers ---

    def _on_authenticated(self) -> None:
        self._connected = True
        self._ws_session_id = str(uuid.uuid4())
        logger.info("WeComChannel WebSocket authenticated (session=%s)", self._ws_session_id)

    def _on_disconnected(self, reason: str = "") -> None:
        self._connected = False
        self._ws_session_id = None
        logger.warning("WeComChannel disconnected: %s", reason)

    def _on_error(self, error: Exception) -> None:
        logger.error("WeComChannel WebSocket error: %s", error)

    async def _on_message(self, frame: dict[str, Any]) -> None:
        """WebSocket message event → enqueue for processing.

        SDK frame structure:
        {
            "cmd": "aibot_msg_callback",
            "headers": {"req_id": "..."},
            "body": {
                "msgid": "...",
                "msgtype": "text",
                "from": {"userid": "..."},
                "text": {"content": "hello"},
                "response_url": "https://...",
            }
        }
        """
        body = frame.get("body") or {}
        msg_type = body.get("msgtype", "")

        # Skip non-message events
        if msg_type not in ("text", "image", "file", "voice", "video", "mixed"):
            logger.debug("WeComChannel ignoring msgtype=%s", msg_type)
            return

        # Enqueue body with frame reference for reply routing
        payload = dict(body)
        payload["_frame"] = frame
        self.enqueue(payload)
