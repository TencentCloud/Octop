"""Feishu (Lark) channel implementation via lark-oapi SDK.

Connects to Feishu using WebSocket for receiving messages and REST API for
sending. Supports text, images, and file messages in both DM and group chats.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

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
from octop_gateway.push_routing import alias_subject_fields

logger = logging.getLogger(__name__)

# Feishu API base URL
_API_BASE = "https://open.feishu.cn/open-apis"

# Maximum number of message IDs to track for deduplication
_DEDUP_MAX_SIZE = 2000

# Token refresh interval (1.5 hours, token valid for 2 hours)
_TOKEN_REFRESH_INTERVAL = 5400

# WebSocket health: detect dead threads / stuck reconnects and hard-restart.
_WS_WATCHDOG_INTERVAL = 30.0
_WS_RECONNECT_STALE_SECONDS = 180.0
# No message/reconnect activity for this long while the thread looks "fine"
# usually means the SDK receive loop died without firing reconnect hooks.
_WS_ACTIVITY_STALE_SECONDS = 3600.0
_WS_RESTART_BACKOFF_SECONDS = 5.0
_WS_THREAD_JOIN_TIMEOUT = 10.0


@dataclass
class FeishuConfig(ChannelConfig):
    """Configuration for the Feishu channel.

    Attributes:
        app_id: Feishu application ID.
        app_secret: Feishu application secret.
        verification_token: Webhook verification token (for HTTP event callbacks).
        encrypt_key: Event encryption key (for HTTP event callbacks).
        channel_id: Optional explicit channel ID; auto-generated UUID if omitted.
        tenant_id: Optional tenant identifier for multi-tenant deployments.
    """

    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""

    required_credentials = ("app_id", "app_secret")


class FeishuChannel(BaseChannel):
    """Feishu/Lark messaging channel.

    Receives messages via lark-oapi WebSocket client and sends responses
    through the Feishu REST API. Handles token lifecycle, message dedup,
    and media upload/download.
    """

    channel_type = "feishu"

    def __init__(
        self,
        processor: MessageProcessor,
        config: FeishuConfig,
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
        self._tenant_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._ws_client: Any = None
        self._ws_thread: Any = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_watchdog_task: asyncio.Task[None] | None = None
        self._ws_restart_lock = asyncio.Lock()
        self._ws_reconnecting_since: float | None = None
        self._last_ws_activity_at: float = 0.0
        self._ws_orphan_threads: list[Any] = []
        self._running = False
        self._main_loop: asyncio.AbstractEventLoop | None = None
        # WebSocket connection session ID (generated on each connect/reconnect)
        self._ws_session_id: str | None = None
        # Bot open_id used for group @mention activation (group_context)
        self._bot_open_id: str | None = None
        # Deduplication: ordered dict acting as bounded LRU set
        self._seen_message_ids: OrderedDict[str, float] = OrderedDict()

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the Feishu channel: refresh token and connect WebSocket."""
        self._running = True
        self._main_loop = asyncio.get_running_loop()
        await self._refresh_token()
        await self._ensure_bot_open_id()
        await self._start_ws_client()
        self._ws_watchdog_task = asyncio.create_task(
            self._ws_watchdog_loop(),
            name=f"feishu-ws-watchdog-{self.channel_id}",
        )
        logger.info("FeishuChannel started (app_id=%s)", self._config.app_id)

    async def stop(self) -> None:
        """Stop the Feishu channel: disconnect and cleanup."""
        self._running = False
        await self._cancel_watchdog()
        await self._stop_ws_client(force=True)
        await self._close_http()
        logger.info("FeishuChannel stopped")

    async def _ensure_bot_open_id(self) -> str | None:
        """Resolve and cache this bot's open_id via ``/bot/v3/info``."""
        if self._bot_open_id:
            return self._bot_open_id
        try:
            http = await self._ensure_http()
            headers = await self._get_auth_headers()
            async with http.get(f"{_API_BASE}/bot/v3/info", headers=headers) as resp:
                data = await resp.json()
            if data.get("code") != 0:
                logger.warning("Feishu bot info failed: %s", data.get("msg", "unknown"))
                return None
            open_id = str((data.get("bot") or {}).get("open_id") or "").strip()
            if open_id:
                self._bot_open_id = open_id
                logger.info("Feishu bot open_id resolved: %s", open_id[:12])
            return self._bot_open_id
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Failed to resolve Feishu bot open_id", exc_info=True)
            return None

    # =========================================================================
    # Token Management
    # =========================================================================

    async def _refresh_token(self) -> str:
        """Obtain or refresh the tenant_access_token.

        Returns the current valid token. Thread-safe via asyncio lock.
        """
        async with self._token_lock:
            now = time.time()
            if self._tenant_token and now < self._token_expires_at:
                return self._tenant_token

            http = await self._ensure_http()
            url = f"{_API_BASE}/auth/v3/tenant_access_token/internal"
            payload = {
                "app_id": self._config.app_id,
                "app_secret": self._config.app_secret,
            }

            try:
                async with http.post(url, json=payload) as resp:
                    data = await resp.json()
                    if data.get("code") != 0:
                        raise RuntimeError(f"Feishu token refresh failed: {data.get('msg', 'unknown error')}")
                    self._tenant_token = data["tenant_access_token"]
                    expire = data.get("expire", 7200)
                    # Refresh slightly before actual expiry
                    self._token_expires_at = now + min(expire - 300, _TOKEN_REFRESH_INTERVAL)
                    logger.debug("Feishu tenant token refreshed, expires in %ds", expire)
                    return self._tenant_token
            except (
                aiohttp.ClientError,
                TimeoutError,
                json.JSONDecodeError,
                UnicodeDecodeError,
                KeyError,
                RuntimeError,
            ):
                logger.exception("Failed to refresh Feishu tenant token")
                raise

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with a valid token."""
        token = await self._refresh_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # =========================================================================
    # WebSocket Client (lark-oapi)
    # =========================================================================

    async def _start_ws_client(self) -> None:
        """Start the lark-oapi WebSocket event client in a background thread."""
        import threading

        try:
            import lark_oapi as lark
        except ImportError as e:
            raise ImportError("lark-oapi is required for FeishuChannel. Install with: pip install lark-oapi") from e

        # Generate a new session ID for this WebSocket connection
        self._ws_session_id = str(uuid.uuid4())
        self._ws_reconnecting_since = None
        self._mark_ws_activity()

        # Build event handler
        event_handler = (
            lark.EventDispatcherHandler.builder(
                self._config.encrypt_key or "",
                self._config.verification_token or "",
            )
            .register_p2_im_message_receive_v1(self._on_message_event)
            .build()
        )

        # Create WebSocket client (lark_oapi.ws.Client)
        self._ws_client = lark.ws.Client(
            self._config.app_id,
            self._config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        # SDK reconnect hooks (fire on the WS thread's loop).
        self._ws_client.on_reconnecting = self._on_ws_reconnecting
        self._ws_client.on_reconnected = self._on_ws_reconnected

        # lark-oapi WS client is blocking; run in a daemon thread
        self._ws_thread = threading.Thread(
            target=self._run_ws_thread,
            daemon=True,
            name=f"feishu-ws-{self.channel_id[:8]}",
        )
        self._ws_thread.start()
        logger.info("Feishu WebSocket client connecting (daemon thread, session=%s)", self._ws_session_id)

    def _run_ws_thread(self) -> None:
        """WebSocket client thread entry point."""
        import asyncio as _asyncio

        # Create a new event loop for this thread (lark-oapi needs it)
        loop = _asyncio.new_event_loop()
        self._ws_loop = loop
        _asyncio.set_event_loop(loop)
        try:
            import lark_oapi.ws.client as ws_client_module

            ws_client_module.loop = loop
        except (ImportError, AttributeError):
            pass
        try:
            if self._ws_client:
                self._ws_client.start()
        except Exception:  # pylint: disable=broad-except
            # The SDK owns this thread boundary and does not publish an exception contract.
            logger.exception("Feishu WebSocket thread failed")
        finally:
            self._ws_loop = None
            with contextlib.suppress(Exception):
                loop.close()

    def _mark_ws_activity(self) -> None:
        """Record that the WS transport recently did something observable."""
        self._last_ws_activity_at = time.time()

    def _on_ws_reconnecting(self) -> None:
        """Called by lark-oapi when the socket drops and reconnect starts."""
        self._ws_reconnecting_since = time.time()
        self._mark_ws_activity()
        logger.warning("Feishu WebSocket reconnecting...")

    def _on_ws_reconnected(self) -> None:
        """Called by lark-oapi after a successful reconnect; refresh session id."""
        self._ws_reconnecting_since = None
        self._ws_session_id = str(uuid.uuid4())
        self._mark_ws_activity()
        logger.info("Feishu WebSocket reconnected (session=%s)", self._ws_session_id)

    async def _cancel_watchdog(self) -> None:
        """Cancel the WS health watchdog task if it is running."""
        task = self._ws_watchdog_task
        self._ws_watchdog_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _prune_ws_orphans(self) -> None:
        """Drop references to orphaned WS threads that have finally exited."""
        if not self._ws_orphan_threads:
            return
        alive = [thread for thread in self._ws_orphan_threads if thread.is_alive()]
        exited = len(self._ws_orphan_threads) - len(alive)
        if exited:
            logger.info("Feishu WebSocket pruned %d exited orphan thread(s)", exited)
        self._ws_orphan_threads = alive

    async def _ws_watchdog_loop(self) -> None:
        """Restart the WS client when the daemon thread dies or reconnect stalls.

        Processing exceptions never reach here — they are handled in
        ``BaseChannel`` / workers. This only watches transport health so a
        silent SDK receive-loop death does not permanently mute the channel.
        """
        while self._running:
            await asyncio.sleep(_WS_WATCHDOG_INTERVAL)
            if not self._running:
                break
            self._prune_ws_orphans()
            if self._ws_orphan_threads:
                # Do not open another connection while an old one may still
                # hold a Feishu endpoint slot (EXCEED_CONN_LIMIT risk).
                logger.warning(
                    "Feishu WebSocket deferring health restart: %d orphan thread(s) still alive",
                    len(self._ws_orphan_threads),
                )
                continue
            if not self._ws_is_unhealthy():
                continue
            reason = self._ws_unhealthy_reason()
            logger.warning(
                "Feishu WebSocket unhealthy (%s); restarting",
                reason,
            )
            try:
                await self._restart_ws_client()
            except Exception:  # pylint: disable=broad-except
                # Keep the watchdog alive across arbitrary SDK restart failures.
                logger.exception("Feishu WebSocket restart failed")
            await asyncio.sleep(_WS_RESTART_BACKOFF_SECONDS)

    def _ws_unhealthy_reason(self) -> str:
        """Human-readable reason for the current unhealthy state."""
        thread = self._ws_thread
        if thread is None or not thread.is_alive():
            return "thread_dead"
        if self._ws_reconnecting_since is not None:
            age = time.time() - self._ws_reconnecting_since
            if age >= _WS_RECONNECT_STALE_SECONDS:
                return f"reconnect_stale={age:.0f}s"
        if self._last_ws_activity_at > 0:
            idle = time.time() - self._last_ws_activity_at
            if self._ws_reconnecting_since is None and idle >= _WS_ACTIVITY_STALE_SECONDS:
                return f"activity_stale={idle:.0f}s"
        return "unknown"

    def _ws_is_unhealthy(self) -> bool:
        """Return True when the WS transport needs a hard restart."""
        thread = self._ws_thread
        if thread is None or not thread.is_alive():
            return True
        if self._ws_reconnecting_since is not None:
            return (time.time() - self._ws_reconnecting_since) >= _WS_RECONNECT_STALE_SECONDS
        if self._last_ws_activity_at <= 0:
            return False
        return (time.time() - self._last_ws_activity_at) >= _WS_ACTIVITY_STALE_SECONDS

    async def _restart_ws_client(self) -> None:
        """Tear down and recreate the WS client while the channel stays running."""
        async with self._ws_restart_lock:
            if not self._running:
                return
            stopped = await self._stop_ws_client(force=False)
            if not stopped:
                logger.error(
                    "Skipping Feishu WS restart: previous thread still alive "
                    "(will retry after orphan exits or next watchdog tick)"
                )
                # Keep / set reconnecting marker so the next tick still sees unhealthy.
                if self._ws_reconnecting_since is None:
                    self._ws_reconnecting_since = time.time()
                return
            if self._running:
                await self._start_ws_client()

    def _request_ws_thread_shutdown(self) -> None:
        """Ask the WS thread event loop to disconnect and cancel its tasks.

        Current lark-oapi ``ws.Client`` has no public ``stop()``; cancelling
        tasks unblocks ``start()`` so the daemon thread can exit cleanly.
        """
        loop = self._ws_loop
        client = self._ws_client
        if loop is None or not loop.is_running():
            return

        def _shutdown() -> None:
            if client is not None:
                disconnect = getattr(client, "_disconnect", None)
                if callable(disconnect):
                    loop.create_task(disconnect())
            for task in asyncio.all_tasks(loop):
                task.cancel()

        loop.call_soon_threadsafe(_shutdown)

    async def _stop_ws_client(self, *, force: bool = True) -> bool:
        """Stop the WebSocket client gracefully.

        Args:
            force: When True (channel ``stop``), clear references even if the
                thread is still alive and track it as an orphan. When False
                (watchdog restart), refuse to clear a live thread so we do not
                open a second Feishu connection.

        Returns:
            True if there is no live WS thread left owned by this channel.
        """
        self._request_ws_thread_shutdown()
        thread = self._ws_thread
        if thread is not None:
            await asyncio.to_thread(thread.join, _WS_THREAD_JOIN_TIMEOUT)
            if thread.is_alive():
                logger.warning(
                    "Feishu WebSocket thread did not exit within %.0fs (force=%s)",
                    _WS_THREAD_JOIN_TIMEOUT,
                    force,
                )
                if not force:
                    return False
                self._ws_orphan_threads.append(thread)
                logger.error("Feishu WebSocket thread orphaned; connection slot may remain until it exits")

        self._ws_thread = None
        self._ws_client = None
        self._ws_loop = None
        self._ws_session_id = None
        if force:
            self._ws_reconnecting_since = None
        return True

    def _on_message_event(self, data: Any) -> None:
        """Handle incoming message event from lark-oapi dispatcher.

        This runs in the lark-oapi thread; enqueues via callback for async processing.
        Signature: (data: P2ImMessageReceiveV1) -> None
        """
        if not self._running:
            return

        try:
            event = data.event
            message = event.message
            sender = event.sender

            if not message or not sender:
                return

            # Skip bot messages
            sender_type = getattr(sender, "sender_type", "") or ""
            if sender_type == "bot":
                return

            message_id = message.message_id
            if self._is_duplicate(message_id):
                logger.debug("Duplicate Feishu message ignored: %s", message_id)
                return

            sender_id_obj = getattr(sender, "sender_id", None)
            sender_id = ""
            if sender_id_obj and getattr(sender_id_obj, "open_id", None):
                sender_id = str(sender_id_obj.open_id).strip()

            mentions = self._normalize_mentions(getattr(message, "mentions", None))

            # Build raw payload dict for parse_inbound
            raw_payload = {
                "message_id": message_id,
                "message_type": message.message_type,
                "content": message.content,
                "chat_id": message.chat_id,
                "chat_type": message.chat_type,
                "thread_id": getattr(message, "thread_id", "") or "",
                "mentions": mentions,
                "sender": {
                    "sender_id": sender_id,
                    "sender_type": sender_type,
                },
                "create_time": data.header.create_time if data.header else "",
            }

            logger.info(
                "Feishu received message: id=%s type=%s sender=%s",
                message_id,
                message.message_type,
                sender_id[:10],
            )
            self._mark_ws_activity()

            # Add "Typing" reaction to acknowledge receipt (non-blocking)
            self._add_reaction_async(message_id, "Typing")

            # Enqueue for processing
            if self._enqueue_callback:
                self._enqueue_callback(raw_payload)
                logger.info("Feishu message enqueued: %s", message_id)
            else:
                # Fallback: direct async handling (needs running loop)
                try:
                    loop = self._main_loop or asyncio.get_running_loop()
                    asyncio.run_coroutine_threadsafe(self.handle_inbound(raw_payload), loop)
                    logger.info("Feishu message dispatched (fallback): %s", message_id)
                except RuntimeError:
                    logger.error("Feishu: no running event loop, message DROPPED: %s", message_id)

        except Exception:  # pylint: disable=broad-except
            # SDK callbacks must not leak exceptions into the WebSocket dispatch thread.
            logger.exception("Error handling Feishu message event")

    @staticmethod
    def _normalize_mentions(raw_mentions: Any) -> list[dict[str, str]]:
        """Convert Feishu SDK mention objects into plain dicts for parse_inbound."""
        if not isinstance(raw_mentions, list | tuple) or not raw_mentions:
            return []
        mentions: list[dict[str, str]] = []
        for item in raw_mentions:
            if isinstance(item, dict):
                open_id = str(item.get("open_id") or "")
                id_obj = item.get("id")
                if not open_id and isinstance(id_obj, dict):
                    open_id = str(id_obj.get("open_id") or "")
                mentions.append(
                    {
                        "key": str(item.get("key") or ""),
                        "open_id": open_id,
                        "name": str(item.get("name") or ""),
                    }
                )
                continue
            id_obj = getattr(item, "id", None)
            open_id = ""
            if id_obj is not None and not isinstance(id_obj, dict):
                open_id = str(getattr(id_obj, "open_id", "") or "")
            elif isinstance(id_obj, dict):
                open_id = str(id_obj.get("open_id") or "")
            mentions.append(
                {
                    "key": str(getattr(item, "key", "") or ""),
                    "open_id": open_id,
                    "name": str(getattr(item, "name", "") or ""),
                }
            )
        return mentions

    # =========================================================================
    # Deduplication
    # =========================================================================

    def _is_duplicate(self, message_id: str) -> bool:
        """Check if a message_id has been seen recently.

        Uses an OrderedDict as a bounded LRU cache to track IDs.
        """
        if message_id in self._seen_message_ids:
            return True
        self._seen_message_ids[message_id] = time.time()
        # Evict oldest entries when exceeding max size
        while len(self._seen_message_ids) > _DEDUP_MAX_SIZE:
            self._seen_message_ids.popitem(last=False)
        return False

    # =========================================================================
    # Sending
    # =========================================================================

    def _enrich_push_metadata(self, subject: ChannelSubject, meta: dict[str, Any]) -> dict[str, Any]:
        out = dict(meta)
        if subject.chat_type:
            out.setdefault("chat_type", subject.chat_type)
        # subject_id may be a thread_id (omt_…), which is not a send target;
        # prefer the chat/open id when backfilling the routing handle.
        alias_subject_fields(out, str(out.get("chat_id") or "") or subject.subject_id, "to_handle")
        return out

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Send a message to Feishu as a 'post' with markdown support.

        Uses msg_type="post" with tag="md" for markdown rendering.
        This allows code blocks, bold, links, etc. to display correctly in Feishu.

        Routing (thread reply vs. plain send) is resolved by :meth:`_deliver`.

        Args:
            subject: Target subject; metadata carries the routing handle.
            text: Message text (supports markdown).
        """
        content = json.dumps(self._build_post_content(text), ensure_ascii=False)
        await self._deliver(subject, msg_type="post", content=content)

    @staticmethod
    def _build_post_content(text: str) -> dict[str, Any]:
        """Build Feishu post content structure with markdown tag.

        Feishu 'post' message format uses nested content rows,
        each row containing elements with tags (md, img, etc.).
        """
        # Normalize: ensure newline before code fences for proper rendering
        normalized = re.sub(r"([^\n])(```)", r"\1\n\2", text) if text else ""

        content_rows: list[list[dict[str, Any]]] = []
        if normalized:
            content_rows.append([{"tag": "md", "text": normalized}])
        else:
            content_rows.append([{"tag": "md", "text": "[empty]"}])

        return {"zh_cn": {"content": content_rows}}

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Send rich content parts (text, images, files) to Feishu.

        Text parts are concatenated into a single text message.
        Media parts are sent individually after uploading to Feishu.
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
        """Upload and send a media file to Feishu.

        For images: reads bytes via MediaBackend, uploads to Feishu image API,
        sends image message with the resulting image_key.
        For files/audio: same flow with the file API.
        """
        try:
            if isinstance(media, ImageContent):
                image_key = await self._upload_image_to_feishu(media)
                content = json.dumps({"image_key": image_key})
                await self._deliver(subject, msg_type="image", content=content)
            elif isinstance(media, FileContent | AudioContent):
                file_key = await self._upload_file_to_feishu(media)
                filename = media.filename if isinstance(media, FileContent) else "audio"
                content = json.dumps({"file_key": file_key, "file_name": filename})
                await self._deliver(subject, msg_type="file", content=content)
            else:
                # Fallback: send URL as text
                url = self._get_media_url(media)
                if url:
                    label = self._get_media_label(media)
                    await self._send_text(subject, f"[{label}: {url}]")
        except Exception:  # pylint: disable=broad-except
            # MediaBackend and platform upload implementations may raise adapter-specific errors.
            logger.exception("Failed to send media to Feishu: %s", type(media).__name__)
            # Fallback: prefer URL link, otherwise mark as local-only attachment
            url = self._get_media_url(media)
            label = self._get_media_label(media)
            if url:
                await self._send_text(subject, f"[Attachment: {url}]")
            elif getattr(media, "local_path", None):
                await self._send_text(subject, f"[{label} (local upload failed)]")

    async def _deliver(self, subject: ChannelSubject, *, msg_type: str, content: str) -> None:
        """Route one outbound message, staying inside the originating thread.

        Messages that arrived in a Feishu thread are answered with the reply
        API so the response lands in that same topic; the plain send API would
        open a new topic instead. Falls back to a normal send when the source
        message can no longer be replied to.
        """
        meta = subject.metadata or {}
        thread_id = str(meta.get("thread_id") or "")
        reply_to = str(meta.get("message_id") or "")

        if thread_id and reply_to:
            data = await self._reply_message(reply_to, msg_type=msg_type, content=content)
            if data.get("code") == 0:
                return
            logger.warning(
                "Feishu thread reply failed (code=%s), falling back to chat send: thread=%s",
                data.get("code"),
                thread_id[:16],
            )

        receive_id = str(meta.get("to_handle") or "") or subject.subject_id
        await self._send_message(
            receive_id=receive_id,
            receive_id_type=self._resolve_receive_id_type(receive_id, meta),
            msg_type=msg_type,
            content=content,
        )

    async def _reply_message(self, message_id: str, *, msg_type: str, content: str) -> dict[str, Any]:
        """Reply to a message inside its thread via the Feishu reply API."""
        http = await self._ensure_http()
        headers = await self._get_auth_headers()
        url = f"{_API_BASE}/im/v1/messages/{quote(message_id, safe='')}/reply"
        payload = {
            "msg_type": msg_type,
            "content": content,
            "reply_in_thread": True,
        }

        try:
            async with http.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    logger.info("Feishu thread reply sent: parent=%s msg_type=%s", message_id[:16], msg_type)
                else:
                    logger.error(
                        "Feishu reply_message failed: code=%s msg=%s parent=%s",
                        data.get("code"),
                        data.get("msg", "unknown"),
                        message_id[:16],
                    )
                return data  # type: ignore[no-any-return]
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("HTTP error replying to Feishu message %s", message_id[:16])
            return {"code": -1, "msg": "http_error"}

    async def _send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: str,
    ) -> dict[str, Any]:
        """Send a message through the Feishu Messages API.

        Args:
            receive_id: Target identifier (open_id, chat_id, etc.).
            receive_id_type: One of 'open_id', 'chat_id', 'user_id', 'union_id'.
            msg_type: Message type (text, image, file, interactive, etc.).
            content: JSON-encoded message content.

        Returns:
            API response data dict.
        """
        http = await self._ensure_http()
        headers = await self._get_auth_headers()
        url = f"{_API_BASE}/im/v1/messages?receive_id_type={receive_id_type}"
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }

        try:
            async with http.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                code = data.get("code", -1)
                if code != 0:
                    logger.error(
                        "Feishu send_message failed: code=%s msg=%s receive_id=%s",
                        code,
                        data.get("msg", "unknown"),
                        receive_id[:16],
                    )
                else:
                    logger.info("Feishu message sent: receive_id=%s msg_type=%s", receive_id[:16], msg_type)
                return data  # type: ignore[no-any-return]
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("HTTP error sending Feishu message to %s", receive_id[:16])
            return {"code": -1, "msg": "http_error"}

    # =========================================================================
    # Media — fetch (with Bearer auth) + upload
    # =========================================================================

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Download a URL, attaching tenant_access_token for Feishu API URLs."""
        http = await self._ensure_http()
        headers: dict[str, str] = {}
        if "open.feishu.cn" in url or "open-apis" in url:
            token = await self._refresh_token()
            headers["Authorization"] = f"Bearer {token}"
        async with http.get(url, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.content_type or "application/octet-stream"
            return await resp.read(), content_type

    async def _upload_image_to_feishu(self, media: ImageContent) -> str:
        """Upload an image to Feishu and return the image_key.

        Reads bytes through :meth:`load_media_bytes` so the source can be a
        MediaBackend key or an external URL.
        """
        data, mime = await self.load_media_bytes(media)
        http = await self._ensure_http()
        token = await self._refresh_token()
        url = f"{_API_BASE}/im/v1/images"
        headers = {"Authorization": f"Bearer {token}"}

        form = _build_multipart_form(
            fields={"image_type": "message"},
            file_field="image",
            file_data=data,
            filename="image.png",
            content_type=mime or "image/png",
        )

        try:
            async with http.post(url, headers=headers, data=form) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    raise RuntimeError(f"Feishu image upload failed: {result.get('msg')}")
                return result["data"]["image_key"]  # type: ignore[no-any-return]
        except RuntimeError:
            raise
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"Feishu image upload HTTP error: {e}") from e

    async def _upload_file_to_feishu(self, media: FileContent | AudioContent) -> str:
        """Upload a file (or audio) to Feishu and return the file_key.

        Reads bytes through :meth:`load_media_bytes` so the source can be a
        MediaBackend key or an external URL.
        """
        data, mime = await self.load_media_bytes(media)

        if isinstance(media, FileContent):
            filename = media.filename or "file"
            content_type = media.mime_type or mime or "application/octet-stream"
            file_type = self._guess_feishu_file_type(filename, content_type)
        else:
            filename = "audio.opus"
            file_type = "opus"
            content_type = media.mime_type or mime or "audio/ogg"

        http = await self._ensure_http()
        token = await self._refresh_token()
        api_url = f"{_API_BASE}/im/v1/files"
        headers = {"Authorization": f"Bearer {token}"}

        form = _build_multipart_form(
            fields={"file_type": file_type, "file_name": filename},
            file_field="file",
            file_data=data,
            filename=filename,
            content_type=content_type,
        )

        try:
            async with http.post(api_url, headers=headers, data=form) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    raise RuntimeError(f"Feishu file upload failed: {result.get('msg')}")
                return result["data"]["file_key"]  # type: ignore[no-any-return]
        except RuntimeError:
            raise
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RuntimeError(f"Feishu file upload HTTP error: {e}") from e

    @staticmethod
    def _guess_feishu_file_type(filename: str, mime: str) -> str:
        """Map filename/mime to Feishu file_type enum value."""
        lower = filename.lower()
        if lower.endswith((".opus", ".ogg")):
            return "opus"
        if lower.endswith((".mp4", ".avi", ".mov", ".mkv")):
            return "mp4"
        if lower.endswith((".pdf",)):
            return "pdf"
        if lower.endswith((".doc", ".docx")):
            return "doc"
        if lower.endswith((".xls", ".xlsx")):
            return "xls"
        if lower.endswith((".ppt", ".pptx")):
            return "ppt"
        return "stream"

    # =========================================================================
    # Reactions (typing acknowledgement)
    # =========================================================================

    def _add_reaction_async(self, message_id: str, emoji_type: str = "Typing") -> None:
        """Add emoji reaction to a message (fire-and-forget from lark-oapi thread).

        Dispatches the async reaction call to the main event loop via
        run_coroutine_threadsafe, ensuring the shared aiohttp session and
        asyncio primitives are used in the correct loop context.
        """
        loop = self._main_loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._add_reaction(message_id, emoji_type), loop)
        else:
            logger.debug("Feishu: main loop not available, skipping reaction")

    async def _add_reaction(self, message_id: str, emoji_type: str = "Typing") -> None:
        """Add an emoji reaction to a Feishu message via API.

        Runs in the main event loop (dispatched by _add_reaction_async).
        Uses a fresh aiohttp session for the actual POST to avoid holding
        the shared session during a fire-and-forget operation.

        Args:
            message_id: The message to react to.
            emoji_type: Feishu emoji type string (e.g. "Typing", "THUMBSUP", "OK").
        """
        try:
            token = await self._refresh_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            url = f"{_API_BASE}/im/v1/messages/{message_id}/reactions"
            payload = {"reaction_type": {"emoji_type": emoji_type}}

            async with aiohttp.ClientSession() as session, session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    logger.debug("Feishu reaction added: %s on %s", emoji_type, message_id[:16])
                else:
                    body = await resp.text()
                    logger.debug("Feishu reaction failed: %d %s", resp.status, body[:100])
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Feishu _add_reaction error for %s", message_id[:16], exc_info=True)

    # =========================================================================
    # Inbound Parsing
    # =========================================================================

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse a Feishu native message payload into InboundMessage.

        Expected payload structure (from _on_message_event):
            {
                "message_id": str,
                "message_type": str,  # "text", "image", "file", "sticker", etc.
                "content": str,       # JSON-encoded content
                "chat_id": str,
                "chat_type": str,     # "p2p" or "group"
                "mentions": [{"key", "open_id", "name"}, ...],
                "sender": {"sender_id": str, "sender_type": str},
                "create_time": str,   # milliseconds timestamp
            }
        """
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        if not isinstance(raw_payload, dict):
            raise ValueError(f"FeishuChannel.parse_inbound expects dict, got {type(raw_payload)}")

        sender_id = raw_payload.get("sender", {}).get("sender_id", "unknown")
        chat_id = raw_payload.get("chat_id", "")
        chat_type = raw_payload.get("chat_type", "p2p")
        thread_id = str(raw_payload.get("thread_id", "") or "")
        message_type = raw_payload.get("message_type", "text")
        raw_content = raw_payload.get("content", "{}")
        create_time = raw_payload.get("create_time", "")
        mentions = raw_payload.get("mentions") or []
        if not isinstance(mentions, list):
            mentions = []

        # Parse session key: DM vs group
        session_id = self._ws_session_id or "feishu-unconnected"

        # Parse timestamp
        timestamp = time.time()
        if create_time:
            with contextlib.suppress(ValueError, TypeError):
                timestamp = int(create_time) / 1000.0

        # Parse content JSON
        try:
            content_data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
        except (json.JSONDecodeError, TypeError):
            content_data = {}

        # Feishu message resources can only be downloaded with the message ID
        # that the resource key belongs to.
        message_id = str(raw_payload.get("message_id", ""))
        parts = self._parse_content_parts(message_type, content_data, message_id=message_id)

        # Strip @bot placeholders from text so the agent sees clean content.
        if mentions:
            parts = self._strip_bot_mentions_from_parts(parts, mentions)

        # Build metadata for reply routing
        to_handle = chat_id if chat_type == "group" else sender_id
        # A Feishu thread is its own conversation: keying the subject by
        # thread_id gives one agent session per topic instead of one per chat.
        subject_id = thread_id or to_handle
        # Subject chat_type uses the shared gateway vocabulary ("direct"/"group")
        # while metadata keeps the Feishu-native value for send routing.
        subject_chat_type = "group" if chat_type == "group" else "direct"
        bot_mentioned = self._is_bot_mentioned(chat_type, mentions)
        metadata: dict[str, Any] = {
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "to_handle": to_handle,
            "sender_id": sender_id,
            "bot_mentioned": bot_mentioned,
            "mentions": mentions,
        }
        if thread_id:
            metadata["thread_id"] = thread_id

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=subject_id,
                chat_type=subject_chat_type,
                metadata=metadata,
            ),
            channel_session_id=session_id,
            content=parts,
            metadata=metadata,
            timestamp=timestamp,
        )

    def _is_bot_mentioned(self, chat_type: str, mentions: list[Any]) -> bool:
        """Return whether this message @mentions the bot (group activation hint).

        DMs always count as addressed to the bot. Group activation for
        ``group_context`` relies on ``metadata.bot_mentioned``.
        """
        if chat_type != "group":
            return True
        if not mentions:
            return False
        bot_id = self._bot_open_id
        if not bot_id:
            # Identity unknown: any structured mention may be the bot. Prefer
            # activating over silently dropping @bot turns when group_context
            # is enabled.
            return True
        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            if str(mention.get("open_id") or "") == bot_id:
                return True
        return False

    def _strip_bot_mentions_from_parts(
        self,
        parts: list[ContentPart],
        mentions: list[Any],
    ) -> list[ContentPart]:
        """Remove Feishu ``@_user_N`` placeholders that refer to this bot.

        Preserves intentional newlines; only tidies spaces left by the removed
        mention tokens.
        """
        bot_keys = self._bot_mention_keys(mentions)
        if not bot_keys:
            return parts
        updated: list[ContentPart] = []
        for part in parts:
            if isinstance(part, TextContent) and part.text:
                text = part.text
                for key in bot_keys:
                    text = text.replace(key, "")
                # Collapse runs of spaces/tabs created by the removal, keep \\n.
                text = re.sub(r"[^\S\n]{2,}", " ", text)
                text = re.sub(r"[^\S\n]+\n", "\n", text)
                text = re.sub(r"\n[^\S\n]+", "\n", text)
                text = text.strip(" \t")
                updated.append(TextContent(text=text) if text != part.text else part)
            else:
                updated.append(part)
        return updated

    def _bot_mention_keys(self, mentions: list[Any]) -> list[str]:
        """Return mention placeholder keys that refer to this bot."""
        bot_id = self._bot_open_id
        if not bot_id:
            return []
        keys: list[str] = []
        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            if str(mention.get("open_id") or "") != bot_id:
                continue
            key = str(mention.get("key") or "").strip()
            if key:
                keys.append(key)
        return keys

    def _parse_content_parts(
        self,
        message_type: str,
        content_data: dict[str, Any],
        *,
        message_id: str,
    ) -> list[ContentPart]:
        """Convert Feishu message content into a list of ContentPart objects."""
        parts: list[ContentPart] = []

        if message_type == "text":
            text = content_data.get("text", "")
            if text:
                parts.append(TextContent(text=text))

        elif message_type == "image":
            image_key = content_data.get("image_key", "")
            if image_key and message_id:
                download_url = self._build_resource_url(message_id, image_key, resource_type="image")
                parts.append(ImageContent(url=download_url, alt_text=image_key))

        elif message_type == "file":
            file_key = content_data.get("file_key", "")
            filename = content_data.get("file_name", "")
            if file_key and message_id:
                download_url = self._build_resource_url(message_id, file_key, resource_type="file")
                parts.append(FileContent(url=download_url, filename=filename))

        elif message_type == "audio":
            file_key = content_data.get("file_key", "")
            if file_key and message_id:
                download_url = self._build_resource_url(message_id, file_key, resource_type="file")
                parts.append(AudioContent(url=download_url))

        elif message_type == "sticker":
            # Feishu does not allow downloading sticker bytes via the resource
            # API. Keep a visible marker (and the file_key) so the turn is not
            # silently empty after the Typing reaction.
            file_key = str(content_data.get("file_key", "") or "")
            label = f"[Sticker: {file_key}]" if file_key else "[Sticker]"
            parts.append(TextContent(text=label))

        elif message_type == "post":
            # Rich text post — extract text, emotions, and embedded images.
            text, media_parts = self._extract_post_parts(content_data, message_id=message_id)
            if text:
                parts.append(TextContent(text=text))
            parts.extend(media_parts)

        elif message_type == "interactive":
            # Card message — extract text representation
            text = content_data.get("text", "") or "[Interactive Card]"
            parts.append(TextContent(text=text))

        else:
            # Unknown type — store raw as text
            logger.debug("Unknown Feishu message_type: %s", message_type)
            parts.append(TextContent(text=f"[Unsupported message type: {message_type}]"))

        # Ensure we always have at least one content part
        if not parts:
            parts.append(TextContent(text=""))

        return parts

    @staticmethod
    def _build_resource_url(message_id: str, resource_key: str, *, resource_type: str) -> str:
        """Build the authenticated download URL for a resource in a message."""
        encoded_message_id = quote(message_id, safe="")
        encoded_resource_key = quote(resource_key, safe="")
        return f"{_API_BASE}/im/v1/messages/{encoded_message_id}/resources/{encoded_resource_key}?type={resource_type}"

    @staticmethod
    def _extract_post_parts(
        content_data: dict[str, Any],
        *,
        message_id: str,
    ) -> tuple[str, list[ContentPart]]:
        """Extract text and media from a Feishu post (rich text) message.

        Post content structure: ``{"title": str, "content": [[{tag, ...}]]}``.
        Text-like tags become plain text; ``img`` becomes :class:`ImageContent`
        (downloadable); ``emotion`` becomes a textual emoji marker.
        """
        lines: list[str] = []
        media: list[ContentPart] = []
        title = content_data.get("title", "")
        if title:
            lines.append(str(title))

        # Some Feishu post payloads nest under a language key (zh_cn / en_us).
        paragraphs = content_data.get("content", [])
        if not paragraphs:
            for value in content_data.values():
                if isinstance(value, dict) and isinstance(value.get("content"), list):
                    paragraphs = value["content"]
                    if not title and value.get("title"):
                        lines.append(str(value["title"]))
                    break

        for paragraph in paragraphs:
            if not isinstance(paragraph, list):
                continue
            line_parts: list[str] = []
            for element in paragraph:
                if not isinstance(element, dict):
                    continue
                tag = element.get("tag", "")
                if tag in {"text", "md"}:
                    line_parts.append(str(element.get("text", "") or ""))
                elif tag == "a":
                    href = element.get("href", "")
                    text = element.get("text", href)
                    line_parts.append(f"{text}({href})" if href else str(text))
                elif tag == "at":
                    line_parts.append(f"@{element.get('user_name', element.get('user_id', ''))}")
                elif tag == "emotion":
                    emoji = element.get("emoji_type") or element.get("emoji") or "emoji"
                    line_parts.append(f"[{emoji}]")
                elif tag == "img":
                    image_key = str(element.get("image_key", "") or "")
                    if image_key and message_id:
                        download_url = FeishuChannel._build_resource_url(message_id, image_key, resource_type="image")
                        media.append(ImageContent(url=download_url, alt_text=image_key))
                    elif image_key:
                        line_parts.append(f"[Image: {image_key}]")
                elif tag == "media":
                    file_key = str(element.get("file_key", "") or "")
                    if file_key and message_id:
                        download_url = FeishuChannel._build_resource_url(message_id, file_key, resource_type="file")
                        media.append(FileContent(url=download_url, filename=str(element.get("file_name") or "")))
                    elif file_key:
                        line_parts.append(f"[File: {file_key}]")
                elif tag == "code_block":
                    language = element.get("language", "")
                    code = element.get("text", "") or ""
                    fence = f"```{language}\n{code}\n```" if language else f"```\n{code}\n```"
                    line_parts.append(fence)
            if line_parts:
                lines.append("".join(line_parts))

        return "\n".join(lines), media

    @staticmethod
    def _extract_post_text(content_data: dict[str, Any]) -> str:
        """Extract plain text from a Feishu post (rich text) message.

        Kept for backwards compatibility with callers/tests that only need text.
        """
        text, _media = FeishuChannel._extract_post_parts(content_data, message_id="")
        return text

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _resolve_receive_id_type(to_handle: str, meta: dict[str, Any]) -> str:
        """Determine the receive_id_type based on target handle and metadata.

        Returns 'chat_id' for group chats, 'open_id' for DMs.
        """
        chat_type = meta.get("chat_type", "")
        if chat_type == "group":
            return "chat_id"
        # Heuristic: Feishu chat_ids start with "oc_", open_ids start with "ou_"
        if to_handle.startswith("oc_"):
            return "chat_id"
        return "open_id"


# =============================================================================
# Module-level helpers
# =============================================================================


def _build_multipart_form(
    fields: dict[str, str],
    file_field: str,
    file_data: bytes,
    filename: str,
    content_type: str,
) -> Any:
    """Build an aiohttp FormData for multipart/form-data upload."""
    form = aiohttp.FormData()
    for key, value in fields.items():
        form.add_field(key, value)
    form.add_field(
        file_field,
        file_data,
        filename=filename,
        content_type=content_type,
    )
    return form
