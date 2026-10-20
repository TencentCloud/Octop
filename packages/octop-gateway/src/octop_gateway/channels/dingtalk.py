"""DingTalk channel implementation via dingtalk-stream SDK.

Connects to DingTalk using the Stream protocol for receiving robot messages
and the OpenAPI for sending text, images, and file messages.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
)

logger = logging.getLogger(__name__)

# DingTalk OpenAPI base URL
_API_BASE = "https://api.dingtalk.com"
_OAPI_BASE = "https://oapi.dingtalk.com"

# Token refresh interval (1.5 hours, token valid for 2 hours)
_TOKEN_REFRESH_INTERVAL = 5400


@dataclass
class DingTalkConfig(ChannelConfig):
    """Configuration for the DingTalk channel.

    Attributes:
        app_key: DingTalk application key (Client ID).
        app_secret: DingTalk application secret (Client Secret).
        robot_code: Robot code for proactive messaging. If empty, uses app_key.
        channel_id: Optional explicit channel ID; auto-generated UUID if omitted.
        tenant_id: Optional tenant identifier for multi-tenant deployments.
    """

    app_key: str = ""
    app_secret: str = ""
    robot_code: str = ""

    @property
    def effective_robot_code(self) -> str:
        """Return robot_code if set, otherwise fall back to app_key."""
        return self.robot_code or self.app_key


DingTalkConfig.field_aliases = {"client_id": "app_key", "client_secret": "app_secret"}  # type: ignore[attr-defined]
DingTalkConfig.required_credentials = ("app_key", "app_secret")  # type: ignore[attr-defined]


class DingTalkChannel(BaseChannel):
    """DingTalk messaging channel via Stream protocol.

    Receives messages through dingtalk-stream callback and sends responses
    via the DingTalk OpenAPI. Supports text, markdown, images, and file messages.
    """

    channel_type = "dingtalk"

    def __init__(
        self,
        processor: MessageProcessor,
        config: DingTalkConfig,
        *,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints: Any = None,
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
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._stream_client: Any = None
        self._running = False
        self._stream_task: asyncio.Task[None] | None = None
        # Stream connection session ID (generated on each connect)
        self._stream_session_id: str | None = None

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the DingTalk channel: refresh token and connect stream client."""
        self._running = True
        await self._refresh_token()
        await self._start_stream_client()
        logger.info("DingTalkChannel started (app_key=%s)", self._config.app_key)

    async def stop(self) -> None:
        """Stop the DingTalk channel: disconnect stream and cleanup."""
        self._running = False
        await self._stop_stream_client()
        await self._close_http()
        logger.info("DingTalkChannel stopped")

    # =========================================================================
    # Token Management
    # =========================================================================

    async def _refresh_token(self) -> str:
        """Obtain or refresh the DingTalk access_token.

        Uses the new v2 credential-based API.
        Returns the current valid token. Thread-safe via asyncio lock.
        """
        async with self._token_lock:
            now = time.time()
            if self._access_token and now < self._token_expires_at:
                return self._access_token

            http = await self._ensure_http()
            url = f"{_API_BASE}/v1.0/oauth2/accessToken"
            payload = {
                "appKey": self._config.app_key,
                "appSecret": self._config.app_secret,
            }

            try:
                async with http.post(url, json=payload) as resp:
                    data = await resp.json()
                    token = data.get("accessToken")
                    if not token:
                        raise RuntimeError(
                            f"DingTalk token refresh failed: {data.get('message', data.get('errmsg', 'unknown'))}"
                        )
                    self._access_token = token
                    expire_in = data.get("expireIn", 7200)
                    self._token_expires_at = now + min(expire_in - 300, _TOKEN_REFRESH_INTERVAL)
                    logger.debug("DingTalk access token refreshed, expires in %ds", expire_in)
                    return self._access_token
            except (
                aiohttp.ClientError,
                TimeoutError,
                json.JSONDecodeError,
                UnicodeDecodeError,
                RuntimeError,
            ):
                logger.exception("Failed to refresh DingTalk access token")
                raise

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with a valid token."""
        token = await self._refresh_token()
        return {
            "x-acs-dingtalk-access-token": token,
            "Content-Type": "application/json",
        }

    # =========================================================================
    # Stream Client (dingtalk-stream)
    # =========================================================================

    async def _start_stream_client(self) -> None:
        """Start the dingtalk-stream client for receiving robot messages."""
        try:
            import dingtalk_stream
        except ImportError as e:
            raise ImportError(
                "dingtalk-stream is required for DingTalkChannel. Install with: pip install dingtalk-stream"
            ) from e

        # Generate a new session ID for this stream connection
        self._stream_session_id = str(uuid.uuid4())

        credential = dingtalk_stream.Credential(self._config.app_key, self._config.app_secret)
        self._stream_client = dingtalk_stream.DingTalkStreamClient(credential)

        # Register callback handler for robot messages
        handler = _DingTalkMessageHandler(self)
        self._stream_client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            handler,
        )

        # The gateway already owns an asyncio event loop, so run the SDK's
        # async entry point directly.  ``start_forever()`` creates an
        # uninterruptible executor thread in dingtalk-stream 0.24.3 and leaks
        # probe connections after the channel is stopped.
        self._stream_task = asyncio.create_task(
            self._stream_client.start(),
            name=f"dingtalk-stream-{self.channel_id}",
        )
        logger.debug("DingTalk stream client connecting (session=%s)", self._stream_session_id)

    async def _stop_stream_client(self) -> None:
        """Stop the stream client gracefully."""
        client = self._stream_client
        task = self._stream_task

        if task is not None and not task.done():
            task.cancel()
            await asyncio.sleep(0)

        websocket = getattr(client, "websocket", None) if client is not None else None
        if websocket is not None:
            try:
                await asyncio.wait_for(websocket.close(), timeout=1.0)
            except Exception:  # pylint: disable=broad-except
                # The SDK websocket implementation is outside our exception contract.
                logger.debug("Error closing DingTalk websocket", exc_info=True)

        if task is not None and not task.done():
            # dingtalk-stream 0.24.3 catches the first CancelledError inside
            # ``start()`` and enters a reconnect sleep.  Re-issue cancellation
            # after yielding so that sleep is interrupted and the task exits.
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
                if task.done():
                    break
            if not task.done():
                logger.warning("DingTalk stream task did not stop promptly")

        if task is not None and task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                task.result()

        self._stream_client = None
        self._stream_task = None

        self._stream_session_id = None

    def _handle_stream_message(self, raw_payload: dict[str, Any]) -> None:
        """Process a message received from the stream callback.

        Called from the stream handler thread; schedules processing on the event loop.
        """
        if not self._running:
            return

        if self._enqueue_callback:
            self._enqueue_callback(raw_payload)
        else:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(self.handle_inbound(raw_payload), loop)
            except RuntimeError:
                logger.warning("No running event loop for DingTalk message dispatch")

    # =========================================================================
    # Sending
    # =========================================================================

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Send a text message to a DingTalk subject or group.

        Uses the webhook URL if available in metadata, otherwise falls back to
        the OpenAPI robot/oToMessages endpoint for DM.
        """
        meta = subject.metadata
        webhook_url = meta.get("webhook_url")

        if webhook_url:
            await self._send_via_webhook(webhook_url, text)
        else:
            await self._send_via_openapi(subject.subject_id, text, meta)

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Send rich content parts to DingTalk.

        Text parts are concatenated into a single message.
        Media parts are sent individually.
        """
        text_segments: list[str] = []
        media_parts: list[ContentPart] = []

        for part in parts:
            if isinstance(part, TextContent):
                if part.text:
                    text_segments.append(part.text)
            else:
                media_parts.append(part)

        # Send combined text
        if text_segments:
            await self._send_text(subject, "\n".join(text_segments))

        # Send each media part
        for media in media_parts:
            await self._send_media(subject, media)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Send a media file to DingTalk.

        For images: reads bytes via MediaBackend, uploads to media API, sends image message.
        For files: same flow with type="file".
        For voice: same flow with type="voice".
        For unsupported types: falls back to sending the URL as text.
        """
        meta = subject.metadata

        try:
            if isinstance(media, ImageContent):
                media_id = await self._upload_to_dingtalk(media, "image")
                await self._send_media_message(subject.subject_id, "image", media_id, meta)
            elif isinstance(media, FileContent):
                media_id = await self._upload_to_dingtalk(media, "file")
                await self._send_media_message(subject.subject_id, "file", media_id, meta, filename=media.filename)
            elif isinstance(media, AudioContent):
                media_id = await self._upload_to_dingtalk(media, "voice")
                await self._send_media_message(subject.subject_id, "voice", media_id, meta)
            else:
                # Fallback: send URL as text
                url = self._get_media_url(media)
                if url:
                    label = self._get_media_label(media)
                    await self._send_text(subject, f"[{label}: {url}]")
        except Exception:  # pylint: disable=broad-except
            # MediaBackend and platform upload implementations may raise adapter-specific errors.
            logger.exception("Failed to send DingTalk media: %s", type(media).__name__)
            url = self._get_media_url(media)
            label = self._get_media_label(media)
            if url:
                await self._send_text(subject, f"[Attachment: {url}]")
            elif getattr(media, "data", None) or getattr(media, "local_path", None):
                await self._send_text(subject, f"[{label} (local upload failed)]")

    async def _send_via_webhook(self, webhook_url: str, text: str) -> None:
        """Send a Markdown message via DingTalk robot webhook (reply mode).

        This is the simplest sending method: POST to the session webhook URL
        provided in the incoming message.
        """
        http = await self._ensure_http()
        if len(text) > 3500:
            payload = {
                "msgtype": "text",
                "text": {"content": text},
            }
        else:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "Octop",
                    "text": text,
                },
            }

        try:
            async with http.post(webhook_url, json=payload) as resp:
                data = await resp.json()
                errcode = data.get("errcode", 0)
                if errcode != 0:
                    logger.error(
                        "DingTalk webhook send failed: errcode=%s errmsg=%s",
                        errcode,
                        data.get("errmsg", "unknown"),
                    )
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("HTTP error sending DingTalk webhook message")

    async def _send_via_openapi(self, subject_id: str, text: str, meta: dict[str, Any]) -> None:
        """Send a single-chat (DM) message via DingTalk OpenAPI.

        Uses the robot/oToMessages/batchSend endpoint for proactive DM.
        """
        http = await self._ensure_http()
        headers = await self._get_auth_headers()
        url = f"{_API_BASE}/v1.0/robot/oToMessages/batchSend"

        if len(text) > 3500:
            msg_key = "sampleText"
            msg_param = {"content": text}
        else:
            msg_key = "sampleMarkdown"
            msg_param = {"title": "Octop", "text": text}

        payload = {
            "robotCode": self._config.effective_robot_code,
            "userIds": [subject_id],
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param),
        }

        try:
            async with http.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if "processQueryKey" not in data and "requestId" not in data:
                    logger.error("DingTalk OpenAPI send failed: %s", data)
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("HTTP error sending DingTalk OpenAPI message")

    async def _send_media_message(
        self,
        subject_id: str,
        media_type: str,
        media_id: str,
        meta: dict[str, Any],
        *,
        filename: str = "",
    ) -> None:
        """Send a media message (image/file/voice) via DingTalk OpenAPI.

        Constructs the appropriate msgKey and msgParam for the media type.
        """
        http = await self._ensure_http()
        headers = await self._get_auth_headers()
        url = f"{_API_BASE}/v1.0/robot/oToMessages/batchSend"

        # Map media type to DingTalk msgKey
        msg_key_map = {
            "image": "sampleImageMsg",
            "file": "sampleFile",
            "voice": "sampleAudio",
        }
        msg_key = msg_key_map.get(media_type, "sampleFile")

        # Build msg_param based on type
        if media_type == "image":
            msg_param = json.dumps({"photoURL": media_id})
        elif media_type == "file":
            resolved_filename = filename or "file"
            msg_param = json.dumps(
                {
                    "mediaId": media_id,
                    "fileName": resolved_filename,
                    "fileType": _file_type_for_name(resolved_filename),
                }
            )
        else:
            msg_param = json.dumps({"mediaId": media_id})

        # Session webhooks support text/Markdown replies but not uploaded media.
        # Direct chats still include a sessionWebhook, so media must use the
        # robot OpenAPI instead of following the text-message routing path.
        if str(meta.get("conversation_type", "1")) != "1":
            raise RuntimeError("DingTalk group session webhooks do not support uploaded media")

        # DM via OpenAPI
        payload_dm = {
            "robotCode": self._config.effective_robot_code,
            "userIds": [subject_id],
            "msgKey": msg_key,
            "msgParam": msg_param,
        }

        try:
            async with http.post(url, headers=headers, json=payload_dm) as resp:
                resp.raise_for_status()
                data = await resp.json()
                if "processQueryKey" not in data and "requestId" not in data:
                    raise RuntimeError(f"DingTalk media send failed: {data}")
        except RuntimeError:
            raise
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"DingTalk OpenAPI media send error: {e}") from e

    # =========================================================================
    # Media — fetch (with downloadCode auth) + upload
    # =========================================================================

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Download from DingTalk: handles both URLs and downloadCodes.

        Non-http identifiers are DingTalk ``downloadCode`` values.  Resolve
        them to a short-lived URL through ``messageFiles/download`` before
        fetching the actual bytes.
        """
        http = await self._ensure_http()
        download_url = url
        if not url.startswith(("http://", "https://")):
            headers = await self._get_auth_headers()
            resolve_url = f"{_API_BASE}/v1.0/robot/messageFiles/download"
            payload = {
                "downloadCode": url,
                "robotCode": self._config.effective_robot_code,
            }
            async with http.post(resolve_url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                result = await resp.json()
            download_url = str(result.get("downloadUrl") or "")
            if not download_url.startswith(("http://", "https://")):
                raise RuntimeError("DingTalk message file response missing a valid downloadUrl")

        async with http.get(download_url) as resp:
            resp.raise_for_status()
            content_type = resp.content_type or "application/octet-stream"
            return await resp.read(), content_type

    async def _upload_to_dingtalk(self, part: ContentPart, media_type: str) -> str:
        """Upload media bytes to DingTalk and return the media_id.

        Reads bytes via :meth:`load_media_bytes` so the source can be a
        MediaBackend key, an external URL, or a downloadCode.
        """
        data, content_type = await self.load_media_bytes(part)
        http = await self._ensure_http()
        token = await self._refresh_token()

        # Use legacy OAPI for media upload (more reliable)
        url = f"{_OAPI_BASE}/media/upload?access_token={token}&type={media_type}"

        form = aiohttp.FormData()
        form.add_field("type", media_type)
        form.add_field(
            "media",
            data,
            filename=_upload_filename(part, media_type),
            content_type=content_type or _mime_for_type(media_type),
        )

        try:
            async with http.post(url, data=form) as resp:
                result = await resp.json()
                media_id = result.get("media_id")
                if not media_id:
                    raise RuntimeError(f"DingTalk media upload failed: {result.get('errmsg', result)}")
                return media_id  # type: ignore[no-any-return]
        except RuntimeError:
            raise
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"DingTalk media upload HTTP error: {e}") from e

    # =========================================================================
    # Inbound Parsing
    # =========================================================================

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse a DingTalk stream callback payload into InboundMessage.

        Expected payload structure (from _DingTalkMessageHandler):
            {
                "sender_id": str,          # staffId / openId of sender
                "sender_nick": str,        # display name
                "sender_corp_id": str,     # corp ID
                "conversation_id": str,    # conversation identifier
                "conversation_type": str,  # "1" = DM, "2" = group
                "msg_id": str,             # message ID
                "msgtype": str,            # "text", "richText", "picture", etc.
                "text": {"content": str},  # for text messages
                "content": Any,            # raw content for other types
                "webhook_url": str,        # reply webhook
                "create_at": int,          # timestamp in ms
            }
        """
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        if not isinstance(raw_payload, dict):
            raise ValueError(f"DingTalkChannel.parse_inbound expects dict, got {type(raw_payload)}")

        sender_id = raw_payload.get("sender_id", "unknown")
        sender_nick = raw_payload.get("sender_nick", "")
        conversation_id = raw_payload.get("conversation_id", "")
        conversation_type = str(raw_payload.get("conversation_type", "1"))
        msgtype = raw_payload.get("msgtype", "text")
        msg_id = raw_payload.get("msg_id", "")

        # Build session key
        session_id = self._stream_session_id or "dingtalk-unconnected"

        # Parse timestamp
        timestamp = time.time()
        create_at = raw_payload.get("create_at")
        if create_at:
            with contextlib.suppress(ValueError, TypeError):
                timestamp = int(create_at) / 1000.0

        # Parse content parts
        parts = self._parse_content_parts(msgtype, raw_payload)

        # Build metadata for routing
        metadata: dict[str, Any] = {
            "msg_id": msg_id,
            "conversation_id": conversation_id,
            "conversation_type": conversation_type,
            "sender_nick": sender_nick,
            "to_handle": sender_id,
        }

        # Include webhook URL for reply-mode sending
        webhook_url = raw_payload.get("webhook_url", "")
        if webhook_url:
            metadata["webhook_url"] = webhook_url

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(subject_id=sender_id, metadata=metadata),
            channel_session_id=session_id,
            content=parts,
            metadata=metadata,
            timestamp=timestamp,
        )

    def _parse_content_parts(self, msgtype: str, payload: dict[str, Any]) -> list[ContentPart]:
        """Convert DingTalk message content into ContentPart list."""
        parts: list[ContentPart] = []

        if msgtype == "text":
            text_data = payload.get("text", {})
            content = text_data.get("content", "") if isinstance(text_data, dict) else str(text_data)
            if content:
                # Strip @bot mention prefix
                content = self._strip_at_mention(content)
                parts.append(TextContent(text=content))

        elif msgtype == "richText":
            # Rich text with multiple sections
            rich_text = payload.get("content", {})
            text = self._extract_rich_text(rich_text)
            if text:
                parts.append(TextContent(text=text))

        elif msgtype == "picture":
            # Image message
            picture_url = payload.get("content", {}).get("downloadCode", "")
            if not picture_url:
                picture_url = payload.get("content", {}).get("pictureDownloadCode", "")
            if picture_url:
                parts.append(ImageContent(url=picture_url))
            else:
                parts.append(TextContent(text="[Image]"))

        elif msgtype == "file":
            # File message
            file_info = payload.get("content", {})
            download_code = file_info.get("downloadCode", "")
            filename = file_info.get("fileName", "file")
            if download_code:
                parts.append(FileContent(url=download_code, filename=filename))
            else:
                parts.append(TextContent(text=f"[File: {filename}]"))

        elif msgtype == "audio":
            # Voice message
            audio_info = payload.get("content", {})
            download_code = audio_info.get("downloadCode", "")
            duration = audio_info.get("duration")
            if download_code:
                parts.append(AudioContent(url=download_code, duration=duration))
            else:
                parts.append(TextContent(text="[Audio]"))

        else:
            # Unknown type
            logger.debug("Unknown DingTalk msgtype: %s", msgtype)
            parts.append(TextContent(text=f"[Unsupported message type: {msgtype}]"))

        if not parts:
            parts.append(TextContent(text=""))

        return parts

    @staticmethod
    def _strip_at_mention(text: str) -> str:
        """Remove leading @bot mention from message text.

        DingTalk prepends mentions like '@BotName ' to group messages.
        """
        # Common pattern: text starts with an @mention followed by space
        stripped = text.strip()
        if stripped.startswith("@"):
            # Find the end of the mention (first space or newline)
            idx = stripped.find(" ")
            if idx > 0 and idx < 30:
                stripped = stripped[idx + 1 :].strip()
        return stripped or text

    @staticmethod
    def _extract_rich_text(content: Any) -> str:
        """Extract plain text from DingTalk richText content structure.

        Rich text format: {"richText": [{"text": str, "type": str, ...}]}
        """
        if not isinstance(content, dict):
            return str(content) if content else ""

        rich_text_items = content.get("richText", [])
        if not isinstance(rich_text_items, list):
            return ""

        text_parts: list[str] = []
        for item in rich_text_items:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            if text:
                text_parts.append(text)

        return "".join(text_parts)


# =============================================================================
# Stream callback handler
# =============================================================================


try:
    from dingtalk_stream import AckMessage as _AckMessage
    from dingtalk_stream import ChatbotHandler as _ChatbotHandlerBase
except ImportError:  # pragma: no cover - dependency declared, kept for import safety
    _AckMessage = None
    _ChatbotHandlerBase = object


# dingtalk-stream has no type stubs for its dynamically imported handler base.
class _DingTalkMessageHandler(_ChatbotHandlerBase):  # type: ignore[misc]
    """Callback handler for dingtalk-stream ChatbotMessage events.

    Must subclass ``ChatbotHandler`` so ``DingTalkStreamClient.pre_start()`` and
    ``raw_process()`` find the SDK-required interface (see Octop #73).
    """

    def __init__(self, channel: DingTalkChannel) -> None:
        super().__init__()
        self._channel = channel

    async def process(self, callback: Any) -> tuple[int, str]:
        """Handle incoming chatbot message from stream.

        Extracts relevant fields and forwards to channel for async processing.
        """
        try:
            data = getattr(callback, "data", None) or {}
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, dict):
                data = {}

            # Extract standard fields from the chatbot message
            raw_payload: dict[str, Any] = {
                "sender_id": data.get("senderStaffId", data.get("senderId", "")),
                "sender_nick": data.get("senderNick", ""),
                "sender_corp_id": data.get("senderCorpId", ""),
                "conversation_id": data.get("conversationId", ""),
                "conversation_type": data.get("conversationType", "1"),
                "msg_id": data.get("msgId", ""),
                "msgtype": data.get("msgtype", "text"),
                "text": data.get("text", {}),
                "content": data.get("content", {}),
                "create_at": data.get("createAt"),
            }

            # Extract webhook URL for reply (if present)
            session_webhook = data.get("sessionWebhook", "")
            if session_webhook:
                raw_payload["webhook_url"] = session_webhook

            # Dispatch to channel
            self._channel._handle_stream_message(raw_payload)

            if _AckMessage is None:
                return 200, "OK"
            return _AckMessage.STATUS_OK, "OK"

        except Exception:  # pylint: disable=broad-except
            # This is the SDK callback boundary; malformed events must be acknowledged safely.
            logger.exception("Error in DingTalk stream message handler")
            if _AckMessage is None:
                return 500, "handler error"
            return _AckMessage.STATUS_SYSTEM_EXCEPTION, "handler error"


# =============================================================================
# Module-level helpers
# =============================================================================


def _extension_for_type(media_type: str) -> str:
    """Get default file extension for a DingTalk media type."""
    return {
        "image": "png",
        "voice": "amr",
        "file": "bin",
    }.get(media_type, "bin")


def _file_type_for_name(filename: str) -> str:
    """Return the extension expected by DingTalk's ``sampleFile`` template."""
    basename = filename.rsplit("/", 1)[-1]
    if "." not in basename:
        return "file"
    return basename.rsplit(".", 1)[-1].lower() or "file"


def _upload_filename(part: ContentPart, media_type: str) -> str:
    """Preserve file names so DingTalk can infer the uploaded media type."""
    if isinstance(part, FileContent) and part.filename:
        return part.filename
    return f"upload.{_extension_for_type(media_type)}"


def _mime_for_type(media_type: str) -> str:
    """Get default MIME type for a DingTalk media type."""
    return {
        "image": "image/png",
        "voice": "audio/amr",
        "file": "application/octet-stream",
    }.get(media_type, "application/octet-stream")
