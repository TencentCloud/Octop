"""QQ Bot channel: integration via QQ official bot WebSocket + REST API.

Connects to the QQ bot gateway using WebSocket for event reception and
communicates via REST API for message sending. Supports C2C (direct message),
guild channel, and group message types.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Self

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.channels.qq.login_qr import QQBotQRCredentials
from octop_gateway.channels.qq.stream import (
    STREAM_DONE,
    StreamFrame,
    StreamSession,
    reconcile_stream_text,
)
from octop_gateway.channels.qq.stream_blocks import stable_markdown_prefix
from octop_gateway.constraints import ChannelConstraints, tool_hint_message
from octop_gateway.group_context import GroupContextConfig
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    GroupContext,
    GroupContextMessage,
    ImageContent,
    InboundMessage,
    MessageEventType,
    TextContent,
    VideoContent,
)
from octop_gateway.utils import close_event_stream, extract_media, extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# QQ Gateway OP codes
# ---------------------------------------------------------------------------

_OP_DISPATCH = 0  # Server → Client: event dispatch
_OP_HEARTBEAT = 1  # Client → Server: heartbeat
_OP_IDENTIFY = 2  # Client → Server: authentication
_OP_RESUME = 6  # Client → Server: resume session
_OP_RECONNECT = 7  # Server → Client: reconnect request
_OP_INVALID_SESSION = 9  # Server → Client: invalid session
_OP_HELLO = 10  # Server → Client: hello (contains heartbeat_interval)
_OP_HEARTBEAT_ACK = 11  # Server → Client: heartbeat acknowledged


class _GatewayReconnectError(Exception):
    """Server-initiated reconnect (op=7).

    Not an error — the gateway routinely cycles connections for load
    balancing. The session_id and last_sequence are preserved so the
    next connection can RESUME without losing buffered events.
    """


# ---------------------------------------------------------------------------
# Intent bitmasks (QQ Bot API)
# ---------------------------------------------------------------------------

INTENT_GUILDS = 1 << 0
INTENT_GUILD_MEMBERS = 1 << 1
INTENT_GUILD_MESSAGES = 1 << 9  # Private guild messages (requires whitelist)
INTENT_GUILD_MESSAGE_REACTIONS = 1 << 10
INTENT_DIRECT_MESSAGE = 1 << 12
INTENT_GROUP_AND_C2C = 1 << 25  # Group + C2C messages (requires whitelist)
INTENT_INTERACTION = 1 << 26
INTENT_MESSAGE_AUDIT = 1 << 27
INTENT_FORUM_EVENT = 1 << 28
INTENT_AUDIO_ACTION = 1 << 29
INTENT_AT_MESSAGES = 1 << 30  # Public guild @bot messages

_DEFAULT_INTENTS = INTENT_AT_MESSAGES | INTENT_GUILD_MEMBERS | INTENT_DIRECT_MESSAGE | INTENT_GROUP_AND_C2C

# ---------------------------------------------------------------------------
# Media tag regex for QQ rich messages
# ---------------------------------------------------------------------------

_MEDIA_TAG_RE = re.compile(
    r"<qq(?:img|video|audio|file)\s+[^>]*?(?:src|url)\s*=\s*[\"']([^\"']+)[\"'][^>]*?>",
    re.IGNORECASE,
)
_IMG_TAG_RE = re.compile(r"<qqimg\s+[^>]*?src\s*=\s*[\"']([^\"']+)[\"'][^>]*?>", re.IGNORECASE)
_VIDEO_TAG_RE = re.compile(r"<qqvideo\s+[^>]*?src\s*=\s*[\"']([^\"']+)[\"'][^>]*?>", re.IGNORECASE)
_AUDIO_TAG_RE = re.compile(r"<qqaudio\s+[^>]*?src\s*=\s*[\"']([^\"']+)[\"'][^>]*?>", re.IGNORECASE)
_FILE_TAG_RE = re.compile(r"<qqfile\s+[^>]*?src\s*=\s*[\"']([^\"']+)[\"'][^>]*?>", re.IGNORECASE)
# Strip @bot mentions
_AT_MENTION_RE = re.compile(r"<@!?[A-Za-z0-9_-]+>\s*", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(
    r"<(?:think|thinking)>(.*?)</(?:think|thinking)>",
    re.IGNORECASE | re.DOTALL,
)
_THINK_OPEN_RE = re.compile(r"<(?:think|thinking)>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</(?:think|thinking)>", re.IGNORECASE)


def extract_think_blocks(text: str) -> str:
    """Return inner text of complete ``<think>`` / ``<thinking>`` blocks."""
    if not text:
        return ""
    parts = [match.group(1).strip() for match in _THINK_BLOCK_RE.finditer(text) if match.group(1).strip()]
    return "\n".join(parts)


def strip_think_tags(text: str) -> str:
    """Remove think markup so only the user-visible remainder remains.

    Some models emit reasoning as ordinary tokens with ``<think>`` tags, or
    only a closing ``</think>`` before the answer. Those must never enter the
    QQ replace bubble — accepted stream text cannot shrink.
    """
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    while True:
        close_match = _THINK_CLOSE_RE.search(cleaned)
        if close_match is None:
            break
        open_match = _THINK_OPEN_RE.search(cleaned)
        if open_match is not None and open_match.start() < close_match.start():
            break
        cleaned = cleaned[close_match.end() :]
    open_match = _THINK_OPEN_RE.search(cleaned)
    if open_match is not None:
        cleaned = cleaned[: open_match.start()]
    # Keep surrounding whitespace. Per-token strip() deleted trailing ``\n``
    # and dropped newline-only deltas, which collapses Markdown in the
    # replace stream.
    return cleaned


# A previous generating frame may already have locked this prefix. Mobile QQ
# paints a newline-only frame as an empty bubble, so new turns do not send it.
_C2C_STREAM_HOLD = "\n"


# ---------------------------------------------------------------------------
# REST API base URLs
# ---------------------------------------------------------------------------

_API_BASE = "https://api.sgroup.qq.com"
_SANDBOX_API_BASE = "https://sandbox.api.sgroup.qq.com"
_GATEWAY_PATH = "/gateway/bot"

# Deduplication window size
_DEDUP_MAX_SIZE = 1000

# ---------------------------------------------------------------------------
# Module-level msg_seq counter (per msg_id)
# QQ API requires incrementing msg_seq to avoid deduplication (error 40054005).
# ---------------------------------------------------------------------------

_msg_seq: dict[str, int] = {}
_msg_seq_lock = threading.Lock()


def _get_next_msg_seq(msg_id: str) -> int:
    """Get next msg_seq for a given msg_id key, starting from time-based value."""
    with _msg_seq_lock:
        if msg_id not in _msg_seq:
            _msg_seq[msg_id] = int(time.time()) % 1_000_000
        n = _msg_seq[msg_id] + 1
        _msg_seq[msg_id] = n
        # Evict old entries to prevent memory leak
        if len(_msg_seq) > 1000:
            for k in list(_msg_seq.keys())[:500]:
                if k in ("c2c-rich", "group-rich", "input-notify"):
                    continue
                del _msg_seq[k]
        return n


@dataclass
class QQConfig(ChannelConfig):
    """Configuration for QQ Bot channel.

    Attributes:
        app_id: QQ Bot application ID.
        token: Bot token for authentication.
        secret: App secret for signature verification.
        sandbox: Use sandbox API endpoint if True.
        intents: Event subscription bitmask. None for defaults.
        channel_id: Optional explicit channel ID; auto-generated UUID if omitted.
        tenant_id: Optional tenant identifier for multi-tenant deployments.
    """

    app_id: str = ""
    token: str = ""
    secret: str = ""
    sandbox: bool = False
    intents: int | None = None
    c2c_streaming: bool = True
    show_tool_hints: bool = False
    stream_throttle_ms: int = 150
    stream_hold_keepalive_s: float = 3.0
    stream_done_retries: int = 3
    group_context: GroupContextConfig = field(
        default_factory=lambda: GroupContextConfig(
            enabled=True,
            visibility="auto",
            activation="mention",
            history="recent",
            history_limit=10,
        )
    )

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        config = super().from_dict(data)
        raw_streaming = data.get("c2c_streaming")
        if isinstance(raw_streaming, str):
            config.c2c_streaming = raw_streaming.strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
        elif raw_streaming is not None:
            config.c2c_streaming = bool(raw_streaming)
        else:
            # Missing key (and legacy ``streaming``) defaults on. Explicit
            # ``c2c_streaming: false`` remains the only opt-out.
            config.c2c_streaming = True
        raw_group_context = data.get("group_context")
        if isinstance(raw_group_context, dict) and "enabled" not in raw_group_context:
            config.group_context.enabled = True
        return config

    @classmethod
    def from_qr_credentials(cls, credentials: QQBotQRCredentials, **overrides: object) -> Self:
        """Build a channel config from a successful QQ Bot QR binding."""
        data = dict(overrides)
        data.update({"app_id": credentials.app_id, "secret": credentials.app_secret})
        return cls.from_dict(data)


QQConfig.field_aliases = {"client_secret": "secret"}  # type: ignore[attr-defined]
QQConfig.required_credentials = ("app_id", "secret")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Channel Implementation
# ---------------------------------------------------------------------------


class QQChannel(BaseChannel):
    """QQ Bot channel via official WebSocket gateway and REST API.

    Supports:
      - Guild channel messages (public @bot mentions)
      - Direct messages (C2C)
      - Group messages
      - Rich content: text, images, files
      - Automatic heartbeat keepalive
      - Message deduplication
      - Reconnection on disconnect
    """

    channel_type = "qq"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: QQConfig,
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
        self._intents = config.intents if config.intents is not None else _DEFAULT_INTENTS
        self._api_base = _SANDBOX_API_BASE if config.sandbox else _API_BASE

        # WebSocket state
        self._ws: Any = None  # websockets connection
        self._ws_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_interval: float = 41.25  # seconds, updated from HELLO
        self._last_sequence: int | None = None
        self._session_id_ws: str | None = None
        self._gateway_url: str | None = None

        # Lifecycle control
        self._running = False
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0

        # Deduplication: ordered dict acting as LRU cache
        self._seen_message_ids: OrderedDict[str, float] = OrderedDict()

        # OAuth access token state
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_refresh_at: float = 0.0
        self._token_lock: asyncio.Lock = asyncio.Lock()
        # Set when the gateway rejects our token (op=9, can_resume=False) or
        # IDENTIFY otherwise fails — next reconnect must drop the cached
        # token and obtain a fresh one before re-IDENTIFY.
        self._force_token_refresh: bool = False

        # Markdown support tracking: per-user/group.
        # If markdown send fails (400), we cache that and skip for subsequent sends.
        self._markdown_unsupported: set[str] = set()
        self._active_c2c_stream: StreamSession | None = None

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            send_rate_limit=(20, 60.0),
            typing_keepalive_interval=5.0,
            show_thinking=False,
            show_tool_hints=False,
        )

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        """Show C2C「正在输入」without writing into the replace bubble."""
        msg_type, meta = self._resolve_send_routing(subject)
        if msg_type != "c2c":
            return
        user_id = str(meta.get("user_openid") or subject.subject_id)
        msg_id = str(meta.get("msg_id") or "")
        if not user_id or not msg_id:
            return
        payload: dict[str, Any] = {
            "msg_type": 6,
            "input_notify": {"input_type": 1, "input_second": 60},
            "msg_id": msg_id,
        }
        try:
            await self._send_message(user_id, payload, "c2c", meta)
        except Exception:  # pylint: disable=broad-except
            # Typing hints are best-effort across QQ API and transport failures.
            logger.debug("QQ C2C input notify failed", exc_info=True)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the QQ bot: obtain access token, fetch gateway URL and connect WebSocket."""
        self._running = True
        logger.info("QQChannel starting: app_id=%s sandbox=%s", self._config.app_id, self._config.sandbox)

        try:
            # Obtain OAuth access token first
            await self._ensure_access_token()
            self._gateway_url = await self._fetch_gateway_url()
        except Exception:  # pylint: disable=broad-except
            # OAuth and gateway clients can surface SDK-specific transport errors.
            logger.exception("Failed to fetch QQ gateway URL")
            raise

        self._ws_task = asyncio.create_task(self._ws_loop(), name="qq-ws-loop")
        logger.info("QQChannel started successfully")

    async def stop(self) -> None:
        """Stop the QQ bot: close WebSocket and cleanup tasks."""
        stream = self._active_c2c_stream
        self._active_c2c_stream = None
        if stream is not None:
            with contextlib.suppress(Exception):
                await stream.finish(stream.last_accepted, discard_pending=True)
        self._running = False
        logger.info("QQChannel stopping")

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None

        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

        await self._close_http()
        logger.info("QQChannel stopped")

    # =========================================================================
    # Sending
    # =========================================================================

    def _resolve_send_routing(self, subject: ChannelSubject) -> tuple[str, dict[str, Any]]:
        """Resolve msg_type + metadata for send; infer proactive C2C/group when needed."""
        meta = dict(subject.metadata or {})
        msg_type = str(meta.get("msg_type") or "channel")

        if meta.get("msg_id"):
            return msg_type, meta

        if msg_type in ("c2c", "group", "direct"):
            return msg_type, meta

        if msg_type == "channel":
            if meta.get("channel_id_native"):
                return msg_type, meta
            if meta.get("group_openid"):
                return "group", meta
            if meta.get("user_openid"):
                return "c2c", meta
            if subject.chat_type == "group":
                meta.setdefault("group_openid", subject.subject_id)
                return "group", meta
            meta.setdefault("user_openid", subject.subject_id)
            return "c2c", meta

        return msg_type, meta

    def _enrich_push_metadata(self, subject: ChannelSubject, meta: dict[str, Any]) -> dict[str, Any]:
        out = dict(meta)
        routed_type, routed_meta = self._resolve_send_routing(
            ChannelSubject(
                subject_id=subject.subject_id,
                chat_type=subject.chat_type,
                metadata=out,
            )
        )
        out.update(routed_meta)
        out.setdefault("msg_type", routed_type)
        return out

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Send a plain text message to the specified destination.

        For C2C/group messages, tries markdown format first (msg_type=2) for
        better rendering. If markdown is rejected (400), falls back to plain
        text (msg_type=0) and caches the failure to skip markdown next time.
        """
        msg_type, meta = self._resolve_send_routing(subject)
        msg_id = meta.get("msg_id")

        # Guild channel messages: use plain content (markdown not applicable)
        if msg_type in ("channel", "direct"):
            channel_payload: dict[str, Any] = {"content": text}
            if msg_id:
                channel_payload["msg_id"] = msg_id
            await self._send_message(subject.subject_id, channel_payload, msg_type, meta)
            return

        # C2C / group: try markdown first, fall back to plain text
        target_key = meta.get("user_openid") or meta.get("group_openid") or subject.subject_id

        if target_key in self._markdown_unsupported:
            # Known: markdown not supported, send plain text directly
            plain_payload: dict[str, Any] = {"content": text, "msg_type": 0}
            if msg_id:
                plain_payload["msg_id"] = msg_id
            await self._send_message(subject.subject_id, plain_payload, msg_type, meta)
            return

        # Try markdown (msg_type=2)
        md_payload: dict[str, Any] = {
            "content": "",
            "msg_type": 2,
            "markdown": {"content": text},
        }
        if msg_id:
            md_payload["msg_id"] = msg_id
            md_payload["msg_seq"] = _get_next_msg_seq(msg_id)

        ok, _, _ = await self._try_send_message(subject.subject_id, md_payload, msg_type, meta)
        if ok:
            return

        # Markdown failed — mark unsupported and retry as plain text
        logger.info("QQChannel markdown not supported for %s, falling back to plain text", target_key)
        self._markdown_unsupported.add(target_key)
        payload = {"content": text, "msg_type": 0}
        if msg_id:
            payload["msg_id"] = msg_id
        await self._send_message(subject.subject_id, payload, msg_type, meta)

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Send rich content (text + media) to the destination."""
        msg_type, meta = self._resolve_send_routing(subject)
        msg_id = meta.get("msg_id")

        # Separate text and media parts
        text_parts: list[str] = []
        media_parts: list[ContentPart] = []

        for part in parts:
            if isinstance(part, TextContent):
                text_parts.append(part.text)
            else:
                media_parts.append(part)

        # Send text content
        if text_parts:
            payload: dict[str, Any] = {"content": "\n".join(text_parts)}
            if msg_id:
                payload["msg_id"] = msg_id
            await self._send_message(subject.subject_id, payload, msg_type, meta)

        # Send media items individually
        for media in media_parts:
            await self._send_media(subject, media)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Send a single media item via QQ rich media API.

        Resolves the source in this order: ``data`` / ``local_path`` (inline
        bytes via ``load_media_bytes``) → ``url`` (remote). At least one
        must be present.

        Routing:
          - **guild / DM channels** (``msg_type='channel'`` or ``'direct'``):
            QQ ``/channels/.../messages`` only accepts a public ``image`` URL —
            base64 is not supported by this endpoint. Inline-only parts fall
            back to a text marker.
          - **C2C / group** (``msg_type='c2c'`` or ``'group'``): two-step
            process — upload via ``/v2/users/{openid}/files`` (or
            ``/v2/groups/...``) then send rich-media message (``msg_type=7``).
            Upload supports both URL pull-through and base64 ``file_data``,
            with three-tier fallback: URL direct → base64 direct →
            URL-download-then-base64 retry.
        """
        meta = subject.metadata
        msg_type = meta.get("msg_type", "channel")
        msg_id = meta.get("msg_id")

        # Resolve source. Need at least one of: inline bytes (data/local_path) or url.
        url = self._get_media_url(media)
        has_inline = bool(getattr(media, "data", None) or getattr(media, "local_path", None))
        if not url and not has_inline:
            return

        # ── Guild / DM channel: protocol only accepts public URL ──
        if msg_type in ("channel", "direct"):
            if not url:
                # Inline-only: fall back to a text marker.
                label = self._get_media_label(media)
                await self._send_text(subject, f"[{label} (local file, not deliverable on guild)]")
                return
            payload: dict[str, Any] = {"content": "", "image": url}
            if msg_id:
                payload["msg_id"] = msg_id
            await self._send_message(subject.subject_id, payload, msg_type, meta)
            return

        if msg_type not in ("c2c", "group"):
            return

        # ── C2C / group: rich media upload (msg_type=7) ──
        file_type, filename = self._classify_qq_file(media)

        # Pre-load bytes when inline source is available so we can attempt
        # base64 upload (covers both data and local_path uniformly).
        local_bytes: bytes | None = None
        if has_inline:
            try:
                local_bytes, _ = await self.load_media_bytes(media)
            except Exception:  # pylint: disable=broad-except
                # MediaBackend implementations may raise backend-specific errors.
                logger.warning("QQChannel send_media: failed to read inline bytes", exc_info=True)

        try:
            file_info = await self._upload_with_fallback(
                subject.subject_id, msg_type, meta, file_type, url=url, data=local_bytes, filename=filename
            )
        except Exception:  # pylint: disable=broad-except
            # Upload fallback spans QQ APIs and host-provided media storage.
            logger.exception("QQChannel send_media upload error")
            file_info = None

        if not file_info:
            # Last-resort: post a text marker (URL if available, otherwise label).
            label = self._get_media_label(media)
            text = f"[{label}: {url}]" if url else f"[{label}]"
            await self._send_text(subject, text)
            return

        # Step 2: send rich media message (msg_type=7 with msg_seq)
        seq_key = msg_id or f"{msg_type}-rich"
        send_payload: dict[str, Any] = {
            "msg_type": 7,
            "msg_seq": _get_next_msg_seq(seq_key),
            "media": file_info,
            "content": "",
        }
        if msg_id:
            send_payload["msg_id"] = msg_id
        await self._send_message(subject.subject_id, send_payload, msg_type, meta)

    def _should_stream_c2c(self, subject: ChannelSubject) -> bool:
        """True when this inbound can use QQ C2C ``stream_messages``."""
        if not self._config.c2c_streaming:
            return False
        msg_type, meta = self._resolve_send_routing(subject)
        return msg_type == "c2c" and bool(meta.get("msg_id"))

    async def _process_inbound(self, message: InboundMessage, subject: ChannelSubject) -> bool:
        """Stream raw answer tokens when the C2C switch is on.

        Off uses origin/main: one static ``msg_type=2`` with the model text
        unchanged. On: show C2C「正在输入」until a complete Markdown block is
        ready, then open the replace bubble with that text. A newline-only
        frame is a blank bubble on mobile QQ, so it is not sent. ``finish``
        still flushes the tail.
        """
        if not self._should_stream_c2c(subject):
            return await super()._process_inbound(message, subject)

        await self._acquire_rate_slot()
        _, meta = self._resolve_send_routing(subject)
        user_id = str(meta.get("user_openid") or subject.subject_id)
        inbound_msg_id = str(meta.get("msg_id") or "")

        async def _send_frame(frame: StreamFrame) -> str | None:
            return await self._send_stream_frame(frame)

        session = StreamSession(
            user_id=user_id,
            msg_id=inbound_msg_id,
            throttle_ms=self._config.stream_throttle_ms,
            done_retries=self._config.stream_done_retries,
            send_frame=_send_frame,
        )
        self._active_c2c_stream = session
        text_parts: list[str] = []
        answer_prefix = ""
        thinking_parts: list[str] = []
        media_buffer: list[ContentPart] = []
        processing_succeeded = False
        show_thinking = self._constraints.show_thinking
        show_tool_hints = self._constraints.show_tool_hints

        def _full_text() -> str:
            return "".join(text_parts)

        def _answer_text() -> str:
            return strip_think_tags(_full_text())

        def _format_thinking(content: str) -> str:
            template = self._constraints.thinking_template
            if "{content}" in template:
                return template.replace("{content}", content)
            return template.format(content=content)

        def _thinking_text() -> str:
            raw = "".join(thinking_parts).strip()
            if not raw:
                return ""
            return _format_thinking(raw)

        def _ingest_body_text(raw: str) -> None:
            if not raw:
                return
            extracted = extract_think_blocks(raw)
            if extracted and show_thinking:
                thinking_parts.append(extracted)
            visible = strip_think_tags(raw)
            if visible:
                text_parts.append(visible)

        def _locked_stream_text(text: str) -> str:
            text = answer_prefix + text
            accepted = session._prefix_base()
            if accepted.startswith(_C2C_STREAM_HOLD) and not text.startswith(_C2C_STREAM_HOLD):
                text = _C2C_STREAM_HOLD + text
            return reconcile_stream_text(accepted, text)

        def _offer_answer(*, final: bool = False) -> None:
            text = _answer_text()
            if session.failed or session.closing:
                return
            payload = text if final else stable_markdown_prefix(text)
            if not payload:
                return
            session.offer(_locked_stream_text(payload))

        async def _typing_until_visible() -> None:
            """Refresh「正在输入」until the first readable stream frame."""
            interval = float(self._config.stream_hold_keepalive_s)
            if interval <= 0:
                return
            while not session.closing and not session.failed:
                if session.last_accepted.strip() or (session.pending or "").strip():
                    return
                await self._send_typing_indicator(subject)
                await asyncio.sleep(interval)

        typing_until_visible = asyncio.create_task(
            _typing_until_visible(),
            name="qq-c2c-stream-typing",
        )

        async def _deliver_static(text: str) -> None:
            cleaned = (text or "").strip()
            if not cleaned:
                return
            try:
                await self._send_text(subject, cleaned)
            except Exception:  # pylint: disable=broad-except
                # Preserve the stream fallback when a static platform send fails.
                logger.warning(
                    "QQ static markdown send failed: channel=%s",
                    self.channel_id,
                    exc_info=True,
                )

        async def _flush_thinking() -> None:
            if not show_thinking:
                thinking_parts.clear()
                return
            text = _thinking_text()
            thinking_parts.clear()
            if text:
                await _deliver_static(text)

        events = None
        try:
            events = self._processor(message)
            async for event in events:
                if event.type == MessageEventType.DELTA:
                    await _flush_thinking()
                    for part in event.content:
                        if isinstance(part, TextContent) and part.text:
                            _ingest_body_text(part.text)
                    _offer_answer()
                elif event.type == MessageEventType.MESSAGE:
                    await _flush_thinking()
                    extra = extract_text(event.content)
                    extracted = extract_think_blocks(extra)
                    if extracted and show_thinking:
                        thinking_parts.append(extracted)
                        await _flush_thinking()
                    extra = strip_think_tags(extra)
                    if extra:
                        current = _full_text()
                        if not current:
                            text_parts.append(extra)
                        elif extra.startswith(current) or current.startswith(extra):
                            if len(extra) > len(current):
                                text_parts.clear()
                                text_parts.append(extra)
                        else:
                            text_parts.append(extra)
                    _offer_answer()
                    media_buffer.extend(extract_media(event.content))
                elif event.type == MessageEventType.THINKING_DELTA:
                    if show_thinking:
                        for part in event.content:
                            if isinstance(part, TextContent) and part.text:
                                thinking_parts.append(part.text)
                elif event.type == MessageEventType.THINKING:
                    if show_thinking:
                        block = extract_text(event.content).strip()
                        if block:
                            thinking_parts.clear()
                            thinking_parts.append(block)
                        await _flush_thinking()
                elif event.type == MessageEventType.TOOL_START:
                    await _flush_thinking()
                    text_parts.clear()
                    session.discard_unsent()
                    # QQ cannot remove accepted or in-flight narration. Freeze
                    # that prefix once so each new answer snapshot extends it.
                    answer_prefix = session._prefix_base()
                    if show_tool_hints:
                        hint = tool_hint_message(event.metadata, self._constraints, phase="start")
                        if hint:
                            await _deliver_static(hint)
                elif event.type == MessageEventType.TOOL_END:
                    if show_tool_hints:
                        hint = tool_hint_message(event.metadata, self._constraints, phase="end")
                        if hint:
                            await _deliver_static(hint)
                elif event.type == MessageEventType.ERROR:
                    await session.finish(session.last_accepted, discard_pending=True)
                    await _deliver_static(event.error or "An unexpected error occurred.")
                    return False
                elif event.type == MessageEventType.COMPLETED:
                    processing_succeeded = True
                    break
                elif event.type in (MessageEventType.TYPING, MessageEventType.FLUSH):
                    continue
            answer = _answer_text()
            _offer_answer(final=True)
            locked = _locked_stream_text(answer) if answer else session.last_accepted
            await session.finish(locked)
            await _flush_thinking()
            # Hold-only frames are not visible. Fall back when nothing
            # readable was accepted, even if sent_frames > 0. An unlinked
            # visible frame cannot be replaced, so the finished answer is
            # delivered once as a normal message instead of more stream frames.
            if session.unlinked or session.sent_frames <= 0 or not session.last_accepted.strip():
                await _deliver_static(answer)
            for media in media_buffer:
                await self.reply_media(subject, media)
            return processing_succeeded
        except Exception:  # pylint: disable=broad-except
            # The processor, media backend, and QQ stream form one failure boundary.
            logger.exception(
                "QQ C2C reply error: channel=%s session=%s",
                self.channel_id,
                message.channel_session_id,
            )
            with contextlib.suppress(Exception):
                await session.finish(session.last_accepted, discard_pending=True)
            await self._send_text(
                subject,
                "An error occurred while processing your message.",
            )
            return False
        finally:
            typing_until_visible.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await typing_until_visible
            if self._active_c2c_stream is session:
                self._active_c2c_stream = None
            if not session.closing:
                with contextlib.suppress(Exception):
                    await session.finish(session.last_accepted, discard_pending=True)
            if events is not None:
                await close_event_stream(events)

    @staticmethod
    def _extract_stream_id(payload: dict[str, Any]) -> str | None:
        """Return the replace-chain id from a QQ stream response.

        QQ has returned this as a top-level string, a nested ``data.id``, and
        an integer. A missing id means the next frame would be a new message.
        """
        sources: list[dict[str, Any]] = [payload]
        nested = payload.get("data")
        if isinstance(nested, dict):
            sources.append(nested)
        for source in sources:
            for key in ("stream_msg_id", "id"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, int) and not isinstance(value, bool):
                    return str(value)
        return None

    async def _send_stream_frame(self, frame: StreamFrame) -> str | None:
        """POST one replace-mode C2C stream frame. Returns QQ stream msg id."""
        content_raw = frame.text
        if frame.state == STREAM_DONE and content_raw and not content_raw.endswith("\n"):
            content_raw += "\n"
        body: dict[str, Any] = {
            "input_mode": "replace",
            "input_state": frame.state,
            "content_type": "markdown",
            "content_raw": content_raw,
            "event_id": frame.msg_id,
            "msg_id": frame.msg_id,
            "msg_seq": frame.msg_seq,
            "index": frame.index,
        }
        if frame.stream_msg_id:
            body["stream_msg_id"] = frame.stream_msg_id
        url = f"{self._api_base}/v2/users/{frame.user_id}/stream_messages"
        status, raw = await self._qq_post(url, body)
        if status not in (200, 201, 202, 204):
            raise RuntimeError(f"QQ stream frame failed: status={status} body={raw[:500]}")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        err = payload.get("code")
        if err not in (None, 0, "0"):
            raise RuntimeError(f"QQ stream frame failed: status={status} body={raw[:500]}")
        return self._extract_stream_id(payload)

    @staticmethod
    def _classify_qq_file(media: ContentPart) -> tuple[int, str | None]:
        """Map a content part to ``(qq_file_type, filename_or_none)``.

        ``filename`` is required by QQ when ``file_type=4`` (generic file).
        """
        if isinstance(media, ImageContent):
            return 1, None
        if isinstance(media, VideoContent):
            return 2, None
        if isinstance(media, AudioContent):
            return 3, None
        if isinstance(media, FileContent):
            name = media.filename or "attachment"
            return 4, name
        return 1, None

    async def _upload_with_fallback(
        self,
        to_handle: str,
        msg_type: str,
        meta: dict[str, Any],
        file_type: int,
        *,
        url: str | None,
        data: bytes | None,
        filename: str | None,
    ) -> dict[str, Any] | None:
        """Three-tier upload: URL pull → base64 → fetch+base64 retry.

        Mirrors the strategy used by finnie's QQ channel: every variant the
        QQ API accepts is tried in turn so the call only fails when both
        protocols and the network are exhausted.
        """
        # Priority 1: URL direct upload (QQ servers fetch the file themselves).
        if url:
            try:
                file_info = await self._upload_media(to_handle, msg_type, meta, file_type, url=url, filename=filename)
                if file_info:
                    return file_info
            except Exception:  # pylint: disable=broad-except
                # URL upload failures fall through to the byte-upload path.
                logger.warning("QQChannel upload via URL failed, will try base64", exc_info=True)

        # Priority 2: base64 direct upload from already-loaded bytes.
        if data:
            file_info = await self._upload_media(to_handle, msg_type, meta, file_type, data=data, filename=filename)
            if file_info:
                return file_info

        # Priority 3: URL was given but pull-through failed and we have no bytes
        # yet — download via fetch_remote_media (with auth) and retry as base64.
        if url and not data:
            try:
                fetched, _ = await self.fetch_remote_media(url)
            except Exception:  # pylint: disable=broad-except
                # Authenticated fetch implementations may raise adapter-specific errors.
                logger.warning("QQChannel fallback download failed: %s", url[:80], exc_info=True)
                return None
            file_info = await self._upload_media(to_handle, msg_type, meta, file_type, data=fetched, filename=filename)
            if file_info:
                logger.info("QQChannel upload succeeded via fetch+base64 fallback")
                return file_info

        return None

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Download with QQ OAuth ('QQBot {access_token}') header."""
        token = await self._ensure_access_token()
        http = await self._ensure_http()
        headers = {"Authorization": f"QQBot {token}"}
        async with http.get(url, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.content_type or "application/octet-stream"
            data = await resp.read()
            return data, content_type

    async def _upload_media(
        self,
        to_handle: str,
        msg_type: str,
        meta: dict[str, Any],
        file_type: int,
        *,
        url: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> dict[str, Any] | None:
        """Upload media to QQ and return file_info dict for rich media send.

        Args:
            to_handle: Target user/group openid.
            msg_type: "c2c" or "group".
            meta: Message metadata.
            file_type: 1=image, 2=video, 3=audio, 4=file.
            url: Public URL — QQ servers fetch the bytes themselves.
            data: Raw bytes — uploaded as base64 ``file_data`` (preferred for
                local files or when the URL is not publicly reachable).
            filename: Required by QQ API when ``file_type=4`` (generic file);
                otherwise filenames may be rejected or rendered incorrectly.

        Either ``url`` or ``data`` must be provided. Returns the ``file_info``
        dict from QQ API, or None on failure.
        """
        if url is None and data is None:
            return None

        http = await self._ensure_http()
        headers = await self._fresh_auth_headers()
        headers["Content-Type"] = "application/json"

        body: dict[str, Any] = {
            "file_type": file_type,
            "srv_send_msg": False,
        }
        if url:
            body["url"] = url
        else:
            body["file_data"] = base64.b64encode(data).decode()  # type: ignore[arg-type]
        if file_type == 4 and filename:
            body["file_name"] = filename

        # Determine upload endpoint based on message type
        if msg_type == "c2c":
            openid = meta.get("user_openid") or to_handle
            endpoint = f"/v2/users/{openid}/files"
        elif msg_type == "group":
            group_openid = meta.get("group_openid") or to_handle
            endpoint = f"/v2/groups/{group_openid}/files"
        else:
            return None

        api_url = f"{self._api_base}{endpoint}"

        try:
            async with http.post(api_url, headers=headers, json=body) as resp:
                if resp.status in (200, 201):
                    payload = await resp.json()
                    # QQ send API expects media={"file_info": "<string>"},
                    # not the raw string or the whole upload response dict.
                    if "file_info" in payload:
                        return {"file_info": payload["file_info"]}
                    return payload  # type: ignore[no-any-return]
                resp_body = await resp.text()
                logger.error("QQ media upload failed: status=%d body=%s", resp.status, resp_body[:200])
                return None
        except Exception:  # pylint: disable=broad-except
            # Normalize all QQ upload transport failures into a failed upload result.
            logger.exception("QQ media upload error")
            return None

    # =========================================================================
    # Inbound parsing
    # =========================================================================

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse a QQ gateway dispatch event into InboundMessage.

        Handles:
          - AT_MESSAGE_CREATE (guild @bot mentions)
          - DIRECT_MESSAGE_CREATE (direct messages)
          - C2C_MESSAGE_CREATE (C2C messages)
          - GROUP_AT_MESSAGE_CREATE (group @bot messages)
          - GROUP_MESSAGE_CREATE (ordinary group messages when granted)
        """
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        if not isinstance(raw_payload, dict):
            raise ValueError(f"QQChannel.parse_inbound expects dict, got {type(raw_payload)}")

        event_type = raw_payload.get("t", "")
        data = raw_payload.get("d", {})

        sender_id = self._extract_sender_id(data, event_type)
        session_id = self._resolve_session_from_event(data, event_type)
        content_parts = self._parse_content(data, event_type=event_type)
        msg_type = self._classify_msg_type(event_type)
        is_group = msg_type == "group"
        conversation_id = self._extract_to_handle(data, event_type) if is_group else ""
        sender = data.get("author", {})
        sender_name = str(sender.get("username") or "") if isinstance(sender, dict) else ""

        metadata: dict[str, Any] = {
            "event_type": event_type,
            "msg_type": msg_type,
            "msg_id": data.get("id", ""),
            "to_handle": self._extract_to_handle(data, event_type),
            "chat_type": "group" if is_group else "dm",
            "sender_id": sender_id,
            "sender_name": sender_name,
        }
        if is_group:
            metadata["conversation_id"] = conversation_id
            metadata["bot_mentioned"] = self._is_bot_mentioned(data, event_type)

        # Carry guild/group/user context for replies
        if "guild_id" in data:
            metadata["guild_id"] = data["guild_id"]
        if "channel_id" in data:
            metadata["channel_id_native"] = data["channel_id"]
        if "group_id" in data:
            metadata["group_id"] = data["group_id"]
        if "group_openid" in data:
            metadata["group_openid"] = data["group_openid"]
        # C2C: carry user_openid for media upload endpoint
        if event_type == "C2C_MESSAGE_CREATE":
            author = data.get("author", {})
            user_openid = (author.get("user_openid") if isinstance(author, dict) else None) or data.get("user_openid")
            if user_openid:
                metadata["user_openid"] = user_openid

        message = InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_session_id=session_id,
            content=content_parts,
            metadata=metadata,
            channel_subject=ChannelSubject(
                subject_id=conversation_id if is_group else sender_id,
                display_name=sender_name if not is_group else "",
                chat_type="group" if is_group else "direct",
                metadata=metadata,
            ),
            timestamp=self._parse_event_timestamp(data.get("timestamp")),
        )
        if is_group:
            message.group_context = self._parse_platform_group_context(data, conversation_id)
        return message

    # =========================================================================
    # Internal: WebSocket management
    # =========================================================================

    async def _ws_loop(self) -> None:
        """Main WebSocket connection loop with automatic reconnection.

        Backoff is reset only after a successful READY (or RESUMED) — merely
        completing the TCP handshake does not count as success because
        IDENTIFY can still be rejected with INVALID_SESSION, which would
        otherwise cause the loop to spin at the minimum delay.
        """
        import websockets

        while self._running:
            try:
                # If the previous session was rejected we drop the cached
                # access_token and refetch the gateway URL with a new one.
                if self._force_token_refresh:
                    logger.info("QQChannel forcing access_token refresh before reconnect")
                    self._access_token = None
                    self._token_expires_at = 0.0
                    self._force_token_refresh = False
                    try:
                        await self._ensure_access_token()
                        self._gateway_url = await self._fetch_gateway_url()
                    except Exception:  # pylint: disable=broad-except
                        # Token providers and gateway transports share the reconnect boundary.
                        logger.exception("QQChannel token refresh failed; will retry")
                        await asyncio.sleep(self._reconnect_delay)
                        self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                        continue

                logger.info("QQChannel connecting to gateway: %s", self._gateway_url)
                async with websockets.connect(self._gateway_url) as ws:  # type: ignore[arg-type]
                    self._ws = ws
                    await self._handle_ws_lifecycle(ws)
            except asyncio.CancelledError:
                break
            except _GatewayReconnectError:
                # Server-initiated cycling — not an error. Reconnect
                # immediately at the minimum delay; do NOT inflate backoff.
                if not self._running:
                    break
                logger.info("QQChannel reconnecting per server request in %.1fs", self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
            except Exception:  # pylint: disable=broad-except
                # The reconnect loop must survive arbitrary WebSocket implementation errors.
                if not self._running:
                    break
                logger.exception("QQChannel WebSocket error, reconnecting in %.1fs", self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _handle_ws_lifecycle(self, ws: Any) -> None:
        """Handle the full lifecycle of a single WebSocket connection."""
        async for raw_msg in ws:
            if not self._running:
                break

            try:
                payload = json.loads(raw_msg)
            except json.JSONDecodeError:
                logger.warning("QQChannel received non-JSON message: %s", raw_msg[:100])
                continue

            op = payload.get("op")
            await self._handle_op(ws, op, payload)

    async def _handle_op(self, ws: Any, op: int, payload: dict[str, Any]) -> None:
        """Route a gateway opcode to its handler."""
        if op == _OP_HELLO:
            # Extract heartbeat interval and start heartbeat + identify
            heartbeat_data = payload.get("d", {})
            self._heartbeat_interval = heartbeat_data.get("heartbeat_interval", 41250) / 1000.0
            logger.debug("QQChannel HELLO: heartbeat_interval=%.1fs", self._heartbeat_interval)

            # Start heartbeat task
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws), name="qq-heartbeat")

            # Send IDENTIFY or RESUME
            if self._session_id_ws and self._last_sequence is not None:
                await self._send_resume(ws)
            else:
                await self._send_identify(ws)

        elif op == _OP_DISPATCH:
            # Update sequence number
            seq = payload.get("s")
            if seq is not None:
                self._last_sequence = seq

            # Store session_id from READY event
            event_type = payload.get("t", "")
            data = payload.get("d", {})

            if event_type == "READY":
                self._session_id_ws = data.get("session_id")
                # Reconnect succeeded all the way through IDENTIFY → reset
                # the geometric backoff so a healthy session doesn't carry
                # an inflated delay from prior failures.
                self._reconnect_delay = 1.0
                logger.info("QQChannel READY: session_id=%s", self._session_id_ws)
            elif event_type == "RESUMED":
                # Same reset on a clean RESUME — proves the cached token
                # and session_id were both still valid.
                self._reconnect_delay = 1.0
                logger.info("QQChannel session resumed")
            else:
                await self._handle_dispatch(event_type, data, payload)

        elif op == _OP_HEARTBEAT_ACK:
            logger.debug("QQChannel heartbeat ACK received")

        elif op == _OP_RECONNECT:
            # Routine cycling — preserve session_id + last_sequence so the
            # next connection RESUMEs and we don't drop events that may
            # have been dispatched between op=7 and the new socket coming up.
            logger.info("QQChannel received RECONNECT request — will RESUME on next connect")
            raise _GatewayReconnectError

        elif op == _OP_INVALID_SESSION:
            # QQ Gateway op=9 carries a boolean ``d``:
            #   True  → the session is recoverable, RESUME on next reconnect.
            #   False → not recoverable, must IDENTIFY fresh; the token is
            #           almost certainly the cause, so refresh it.
            can_resume = bool(payload.get("d"))
            logger.warning("QQChannel INVALID_SESSION (can_resume=%s)", can_resume)
            if not can_resume:
                self._session_id_ws = None
                self._last_sequence = None
                self._force_token_refresh = True
            raise ConnectionError("Invalid session")

    async def _send_identify(self, ws: Any) -> None:
        """Send IDENTIFY payload to authenticate.

        Always pulls a current access_token through ``_ensure_access_token``
        — this is correctly cached, but pulling here means a stale cached
        value gets refreshed by ``_ws_loop`` setting ``_force_token_refresh``
        before us.
        """
        token = await self._ensure_access_token()
        token_str = f"QQBot {token}"

        intents = self._intents

        identify_payload = {
            "op": _OP_IDENTIFY,
            "d": {
                "token": token_str,
                "intents": intents,
                "shard": [0, 1],
            },
        }
        await ws.send(json.dumps(identify_payload))
        logger.debug("QQChannel sent IDENTIFY (intents=%d)", intents)

    async def _send_resume(self, ws: Any) -> None:
        """Send RESUME payload to resume a previous session.

        Uses the same ``QQBot {access_token}`` OAuth header as IDENTIFY —
        mixing the legacy ``Bot {app_id}.{token}`` form here causes the
        gateway to reject the RESUME, which then falls back to IDENTIFY.
        If the access token has expired in the meantime the second hop
        also fails with INVALID_SESSION and the loop spins.
        """
        token = await self._ensure_access_token()
        resume_payload = {
            "op": _OP_RESUME,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self._session_id_ws,
                "seq": self._last_sequence,
            },
        }
        await ws.send(json.dumps(resume_payload))
        logger.debug("QQChannel sent RESUME: session=%s seq=%s", self._session_id_ws, self._last_sequence)

    async def _heartbeat_loop(self, ws: Any) -> None:
        """Send periodic heartbeats to keep the connection alive."""
        try:
            while self._running:
                heartbeat = {"op": _OP_HEARTBEAT, "d": self._last_sequence}
                try:
                    await ws.send(json.dumps(heartbeat))
                    logger.debug("QQChannel sent heartbeat: seq=%s", self._last_sequence)
                except Exception:  # pylint: disable=broad-except
                    # Any WebSocket send failure terminates this heartbeat loop.
                    logger.warning("QQChannel failed to send heartbeat")
                    break
                await asyncio.sleep(self._heartbeat_interval)
        except asyncio.CancelledError:
            pass

    # =========================================================================
    # Internal: Event dispatch
    # =========================================================================

    async def _handle_dispatch(self, event_type: str, data: dict[str, Any], full_payload: dict[str, Any]) -> None:
        """Handle a DISPATCH event from the gateway."""
        # Only process message events
        message_events = {
            "AT_MESSAGE_CREATE",
            "DIRECT_MESSAGE_CREATE",
            "C2C_MESSAGE_CREATE",
            "GROUP_AT_MESSAGE_CREATE",
            "GROUP_MESSAGE_CREATE",
            "MESSAGE_CREATE",
        }

        if event_type not in message_events:
            logger.debug("QQChannel ignoring event: %s", event_type)
            return

        # Log raw payload for debugging C2C messages
        logger.info(
            "QQChannel received %s: id=%s content=%r attachments=%s msg_elements=%d",
            event_type,
            data.get("id") or "",
            (data.get("content") or "")[:100],
            json.dumps(data.get("attachments", []), ensure_ascii=False)[:300] if data.get("attachments") else "none",
            len(data.get("msg_elements") or []) if isinstance(data.get("msg_elements"), list) else 0,
        )

        if event_type not in message_events:
            logger.debug("QQChannel ignoring event: %s", event_type)
            return

        # Deduplication check
        msg_id = data.get("id", "")
        if msg_id and self._is_duplicate(msg_id):
            logger.debug("QQChannel skipping duplicate message: %s", msg_id)
            return

        # Enqueue for processing
        self.enqueue(full_payload)

    def _is_duplicate(self, msg_id: str) -> bool:
        """Check and record message ID for deduplication."""
        if msg_id in self._seen_message_ids:
            return True

        self._seen_message_ids[msg_id] = time.time()

        # Evict oldest entries when exceeding max size
        while len(self._seen_message_ids) > _DEDUP_MAX_SIZE:
            self._seen_message_ids.popitem(last=False)

        return False

    # =========================================================================
    # Internal: REST API
    # =========================================================================

    async def _fetch_gateway_url(self) -> str:
        """Fetch the WebSocket gateway URL from QQ API."""
        http = await self._ensure_http()
        headers = await self._fresh_auth_headers()

        async with http.get(f"{self._api_base}{_GATEWAY_PATH}", headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Failed to fetch gateway URL: {resp.status} {body}")
            data = await resp.json()
            url = data.get("url")
            if not url:
                raise RuntimeError(f"No gateway URL in response: {data}")
            return url  # type: ignore[no-any-return]

    async def _send_message(
        self,
        to_handle: str,
        payload: dict[str, Any],
        msg_type: str,
        meta: dict[str, Any],
    ) -> None:
        """Send a message via the appropriate REST API endpoint.

        Automatically injects msg_type and msg_seq for C2C/group messages
        as required by QQ Bot v2 API.
        """
        endpoint = self._resolve_send_endpoint(to_handle, msg_type, meta)
        if not endpoint:
            logger.warning("QQChannel cannot resolve send endpoint: to=%s type=%s", to_handle, msg_type)
            return

        # For C2C and group messages, inject msg_type and msg_seq if not already set
        if msg_type in ("c2c", "group"):
            if "msg_type" not in payload:
                payload["msg_type"] = 0  # Plain text
            msg_id = payload.get("msg_id") or meta.get("msg_id")
            if msg_id:
                # Passive reply: include msg_id and msg_seq
                payload.setdefault("msg_id", msg_id)
                payload["msg_seq"] = _get_next_msg_seq(msg_id)
            else:
                # Proactive message: omit msg_id/msg_seq per QQ docs
                payload.pop("msg_seq", None)

        url = f"{self._api_base}{endpoint}"

        try:
            status, body = await self._qq_post(url, payload)
            if status not in (200, 201, 202, 204):
                logger.error(
                    "QQChannel send failed: status=%d url=%s payload_keys=%s body=%s",
                    status,
                    url,
                    list(payload.keys()),
                    body[:500],
                )
                raise RuntimeError(f"QQChannel send failed: status={status} body={body[:500]}")
            logger.debug("QQChannel message sent: endpoint=%s resp=%s", endpoint, body[:200])
        except Exception:  # pylint: disable=broad-except
            # Preserve transport-specific diagnostics before propagating to the caller.
            logger.exception("QQChannel send request failed: url=%s", url)
            raise

    async def _try_send_message(
        self,
        to_handle: str,
        payload: dict[str, Any],
        msg_type: str,
        meta: dict[str, Any],
    ) -> tuple[bool, int, str]:
        """Try to send a message. Returns ``(ok, status, body)``.

        Used for markdown-first-then-fallback strategy.
        Does NOT inject msg_type/msg_seq (caller must set them).
        """
        endpoint = self._resolve_send_endpoint(to_handle, msg_type, meta)
        if not endpoint:
            return False, 0, ""

        url = f"{self._api_base}{endpoint}"

        try:
            status, body = await self._qq_post(url, payload)
            if status in (200, 201, 202, 204):
                logger.debug("QQChannel message sent (try): endpoint=%s resp=%s", endpoint, body[:200])
                return True, status, body
            logger.warning("QQChannel try_send failed: status=%d body=%s", status, body[:200])
            return False, status, body
        except Exception:  # pylint: disable=broad-except
            # This best-effort send API converts all transport failures into False.
            logger.exception("QQChannel try_send error: url=%s", url)
            return False, 0, ""

    def _resolve_send_endpoint(self, to_handle: str, msg_type: str, meta: dict[str, Any]) -> str | None:
        """Determine the REST API endpoint for sending a message."""
        if msg_type == "c2c":
            # C2C message: /v2/users/{openid}/messages
            openid = meta.get("user_openid") or to_handle
            return f"/v2/users/{openid}/messages"

        if msg_type == "group":
            # Group message: /v2/groups/{group_openid}/messages
            group_openid = meta.get("group_openid") or to_handle
            return f"/v2/groups/{group_openid}/messages"

        if msg_type == "direct":
            # Direct message (guild DM): /dms/{guild_id}/messages
            guild_id = meta.get("guild_id") or to_handle
            return f"/dms/{guild_id}/messages"

        if msg_type == "channel":
            # Guild channel message: /channels/{channel_id}/messages
            channel_id = meta.get("channel_id_native") or to_handle
            return f"/channels/{channel_id}/messages"

        return None

    def _auth_headers(self) -> dict[str, str]:
        """Build authorization headers for QQ API requests.

        Uses 'QQBot {access_token}' format (v2 OAuth API).
        """
        if self._access_token:
            return {"Authorization": f"QQBot {self._access_token}"}
        # Legacy format (requires separate token field)
        return {"Authorization": f"Bot {self._config.app_id}.{self._config.token}"}

    async def _fresh_auth_headers(self) -> dict[str, str]:
        """Authorization headers after refreshing an expired OAuth token."""
        token = await self._ensure_access_token()
        return {"Authorization": f"QQBot {token}"}

    def _invalidate_access_token(self) -> None:
        self._access_token = None
        self._token_expires_at = 0.0
        self._token_refresh_at = 0.0

    @staticmethod
    def _is_access_token_error(status: int, body: str) -> bool:
        if status != 401:
            return False
        lowered = body.lower()
        return "40011027" in body or "11244" in body or "accesstoken" in lowered or "access token" in lowered

    def _token_still_fresh(self) -> bool:
        if not self._access_token:
            return False
        refresh_at = self._token_refresh_at
        if refresh_at <= 0 and self._token_expires_at > 0:
            refresh_at = self._token_expires_at - 60
        return time.time() < refresh_at

    async def _qq_post(self, url: str, payload: dict[str, Any]) -> tuple[int, str]:
        """POST to QQ REST and retry once after an expired-token 401."""
        http = await self._ensure_http()

        async def _do(headers: dict[str, str]) -> tuple[int, str]:
            async with http.post(url, headers=headers, json=payload) as resp:
                return resp.status, await resp.text()

        headers = await self._fresh_auth_headers()
        headers["Content-Type"] = "application/json"
        status, body = await _do(headers)
        if self._is_access_token_error(status, body):
            logger.warning("QQ access token rejected; refreshing and retrying: url=%s", url)
            self._invalidate_access_token()
            headers = await self._fresh_auth_headers()
            headers["Content-Type"] = "application/json"
            status, body = await _do(headers)
        return status, body

    async def _ensure_access_token(self) -> str:
        """Ensure a valid OAuth2 access token is available.

        QQ Bot v2 API uses app_id + secret to obtain an access_token via:
        POST https://bots.qq.com/app/getAppAccessToken
        Body: {"appId": "...", "clientSecret": "..."}

        Returns the access token string.
        """
        async with self._token_lock:
            # Return cached token if still valid (with 60s buffer)
            if self._token_still_fresh():
                return self._access_token or ""

            http = await self._ensure_http()
            url = "https://bots.qq.com/app/getAppAccessToken"
            payload = {
                "appId": self._config.app_id,
                "clientSecret": self._config.secret,
            }

            async with http.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Failed to get QQ access token: {resp.status} {body}")
                data = await resp.json()

            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 7200))

            if not token:
                raise RuntimeError(f"No access_token in response: {data}")

            ttl = max(1, expires_in)
            now = time.time()
            self._access_token = token
            self._token_expires_at = now + ttl
            # Refresh 60s early on long-lived tokens; for short leftover TTLs
            # (common after a restart reuses the same token) refresh at half-life.
            skew = min(60, max(1, ttl // 2))
            self._token_refresh_at = now + max(1, ttl - skew)
            logger.info("QQChannel access token refreshed, expires_in=%ds", expires_in)
            return token  # type: ignore[no-any-return]

    # =========================================================================
    # Internal: Content parsing helpers
    # =========================================================================

    def _parse_content(self, data: dict[str, object], *, event_type: str = "") -> list[ContentPart]:
        """Parse message content from QQ event data into ContentPart list."""
        parts: list[ContentPart] = []
        raw_content = str(data.get("content") or "")
        text_parts: list[str] = []

        # Extract inline media tags
        for match in _IMG_TAG_RE.finditer(raw_content):
            parts.append(ImageContent(url=match.group(1)))

        for match in _VIDEO_TAG_RE.finditer(raw_content):
            parts.append(VideoContent(url=match.group(1)))

        for match in _AUDIO_TAG_RE.finditer(raw_content):
            parts.append(AudioContent(url=match.group(1)))

        for match in _FILE_TAG_RE.finditer(raw_content):
            parts.append(FileContent(url=match.group(1)))

        # Strip media tags and @bot mentions to get clean text
        clean_text = _MEDIA_TAG_RE.sub("", raw_content)
        clean_text = self._strip_bot_mention(clean_text, data, event_type=event_type)

        quoted = self._find_quoted_element(data)
        if quoted is not None:
            quoted_text = str(quoted.get("content") or "").strip()
            quoted_attachments = quoted.get("attachments") or []
            quoted_voice_transcripts: list[str] = []
            if quoted_text:
                text_parts.append(f"[quoted message: {quoted_text}]")
            if isinstance(quoted_attachments, list):
                quoted_voice_transcripts = self._append_attachments(parts, quoted_attachments)
            if not quoted_text and quoted_voice_transcripts:
                text_parts.append(f"[quoted message: {' '.join(quoted_voice_transcripts)}]")
            elif not quoted_text and not quoted_attachments:
                text_parts.append("[quoted message]")

        if clean_text:
            text_parts.append(clean_text)
        if text_parts:
            parts.insert(0, TextContent(text="\n".join(text_parts)))

        # Handle attachments array (alternative media format for C2C/group)
        attachments = data.get("attachments", [])
        if isinstance(attachments, list):
            voice_transcripts = self._append_attachments(parts, attachments)
            existing_texts = {part.text.strip() for part in parts if isinstance(part, TextContent)}
            new_transcripts = [text for text in voice_transcripts if text not in existing_texts]
            if new_transcripts:
                parts.insert(0, TextContent(text="\n".join(new_transcripts)))

        # Ensure at least empty text content if nothing parsed
        if not parts:
            parts.append(TextContent(text=""))

        return parts

    def _append_attachments(self, parts: list[ContentPart], attachments: list[object]) -> list[str]:
        """Append normalized QQ attachments and return platform voice transcripts."""
        existing_urls = {part.url for part in parts if not isinstance(part, TextContent) and part.url}
        voice_transcripts: list[str] = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            content_type = str(att.get("content_type") or "").lower()
            wav_url = str(att.get("voice_wav_url") or "").strip()
            is_voice = content_type == "voice" or content_type.startswith("audio/") or bool(wav_url)
            transcript = str(att.get("asr_refer_text") or "").strip()
            if is_voice and transcript and transcript not in voice_transcripts:
                voice_transcripts.append(transcript)
            if is_voice and transcript:
                continue
            att_url = wav_url if is_voice and wav_url else str(att.get("url") or "").strip()
            if not att_url:
                continue
            # Ensure URL has protocol scheme
            if att_url.startswith("//"):
                att_url = f"https:{att_url}"
            elif not att_url.startswith("http"):
                att_url = f"https://{att_url}"
            if att_url in existing_urls:
                continue
            mime_type = "audio/wav" if is_voice and wav_url else content_type if "/" in content_type else None
            filename = str(att.get("filename") or att.get("file_name") or att.get("name") or "")
            if content_type.startswith("image/") or self._is_image_url(att_url, filename):
                parts.append(ImageContent(url=att_url, mime_type=mime_type))
            elif content_type.startswith("video/"):
                parts.append(VideoContent(url=att_url, mime_type=mime_type))
            elif is_voice:
                parts.append(AudioContent(url=att_url, mime_type=mime_type))
            else:
                parts.append(FileContent(url=att_url, filename=filename, mime_type=mime_type))
            existing_urls.add(att_url)
        return voice_transcripts

    @staticmethod
    def _strip_bot_mention(text: str, data: dict[str, object], *, event_type: str) -> str:
        """Remove only the bot's QQ mention token from agent-facing text."""
        bot_ids: set[str] = set()
        mentions = data.get("mentions")
        if isinstance(mentions, list):
            for mention in mentions:
                if not isinstance(mention, dict) or mention.get("is_you") is not True:
                    continue
                for key in ("id", "user_openid", "member_openid"):
                    value = mention.get(key)
                    if value:
                        bot_ids.add(str(value))

        clean = text
        for bot_id in bot_ids:
            token = re.compile(rf"<@!?{re.escape(bot_id)}>\s*", re.IGNORECASE)
            clean = token.sub("", clean)

        if event_type in ("GROUP_AT_MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
            clean = _AT_MENTION_RE.sub("", clean, count=1)
        return clean.strip()

    @staticmethod
    def _find_quoted_element(data: dict[str, object]) -> dict[str, object] | None:
        """Find the referenced QQ ``msg_elements`` entry by message index."""
        elements = data.get("msg_elements")
        if not isinstance(elements, list) or not elements:
            return None
        scene = data.get("message_scene")
        ext = scene.get("ext") if isinstance(scene, dict) else []
        ref_idx = ""
        own_idx = ""
        if isinstance(ext, list):
            for entry in ext:
                if not isinstance(entry, str):
                    continue
                if entry.startswith("ref_msg_idx="):
                    ref_idx = entry.removeprefix("ref_msg_idx=")
                elif entry.startswith("msg_idx="):
                    own_idx = entry.removeprefix("msg_idx=")
        if not ref_idx:
            return None
        for element in elements:
            if isinstance(element, dict) and str(element.get("msg_idx") or "") == ref_idx:
                return {str(key): value for key, value in element.items()}
        for element in elements:
            if not isinstance(element, dict):
                continue
            element_idx = str(element.get("msg_idx") or "")
            if element_idx and element_idx != own_idx:
                return {str(key): value for key, value in element.items()}
        return None

    def _parse_platform_group_context(
        self,
        data: dict[str, object],
        conversation_id: str,
    ) -> GroupContext | None:
        """Normalize QQ's mention-time recent messages into shared context."""
        elements = data.get("msg_elements")
        if not isinstance(elements, list) or not elements:
            return None
        # A reference payload is already rendered into the current message.
        # Treat only non-reference msg_elements as platform-provided history.
        if self._find_quoted_element(data) is not None:
            return None

        scene = data.get("message_scene")
        ext = scene.get("ext") if isinstance(scene, dict) else []
        own_idx = ""
        if isinstance(ext, list):
            for entry in ext:
                if isinstance(entry, str) and entry.startswith("msg_idx="):
                    own_idx = entry.removeprefix("msg_idx=")
                    break

        messages: list[GroupContextMessage] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            element_idx = str(element.get("msg_idx") or "")
            if own_idx and element_idx == own_idx:
                continue
            text = str(element.get("content") or "").strip()
            media: list[ContentPart] = []
            attachments = element.get("attachments")
            if isinstance(attachments, list):
                voice_transcripts = self._append_attachments(media, attachments)
                if voice_transcripts:
                    text = (
                        "\n".join(dict.fromkeys([text, *voice_transcripts])) if text else "\n".join(voice_transcripts)
                    )
            if not text and not media:
                continue
            author = element.get("author")
            author = author if isinstance(author, dict) else {}
            sender_id = str(author.get("member_openid") or author.get("user_openid") or author.get("id") or "unknown")
            messages.append(
                GroupContextMessage(
                    message_id=str(element.get("id") or element_idx),
                    sender_id=sender_id,
                    sender_name=str(author.get("username") or ""),
                    text=text,
                    content=media,
                    timestamp=self._parse_event_timestamp(element.get("timestamp")),
                )
            )
        if not messages:
            return None
        return GroupContext(
            conversation_id=conversation_id,
            visibility="mention_recent",
            activation="mention",
            messages=messages,
        )

    def _extract_sender_id(self, data: dict[str, Any], event_type: str) -> str:
        """Extract the sender user ID from event data."""
        # C2C events have user_openid at top level of d
        if event_type == "C2C_MESSAGE_CREATE":
            author = data.get("author", {})
            if isinstance(author, dict):
                openid = author.get("user_openid") or author.get("id")
                if openid:
                    return openid  # type: ignore[no-any-return]
            # Fallback to top-level
            return data.get("user_openid") or "unknown"

        # Group events use author.member_openid
        if event_type in ("GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE"):
            author = data.get("author", {})
            if isinstance(author, dict):
                return author.get("member_openid") or author.get("id") or "unknown"
            return data.get("member_openid") or "unknown"

        # Guild events use author.id
        author = data.get("author", {})
        if isinstance(author, dict):
            return author.get("id") or author.get("user_openid") or "unknown"
        return "unknown"

    def _resolve_session_from_event(self, data: dict[str, Any], event_type: str) -> str:
        """Return the platform connection session ID.

        Uses the WebSocket session_id assigned by the QQ gateway on READY.
        This represents the current connection lifecycle, not the user identity.
        """
        return self._session_id_ws or "qq-unconnected"

    def _extract_to_handle(self, data: dict[str, Any], event_type: str) -> str:
        """Extract the reply destination handle from event data."""
        if event_type == "C2C_MESSAGE_CREATE":
            # For C2C, reply target is the user's openid
            author = data.get("author", {})
            if isinstance(author, dict):
                openid = author.get("user_openid") or author.get("id")
                if openid:
                    return openid  # type: ignore[no-any-return]
            return data.get("user_openid") or self._extract_sender_id(data, event_type)
        if event_type in ("GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE"):
            return data.get("group_openid") or data.get("group_id", "")  # type: ignore[no-any-return]
        if event_type == "DIRECT_MESSAGE_CREATE":
            return data.get("guild_id", "")  # type: ignore[no-any-return]
        # Guild channel — reply to same channel
        return data.get("channel_id", "")  # type: ignore[no-any-return]

    def _classify_msg_type(self, event_type: str) -> str:
        """Classify the message type for routing send calls."""
        if event_type == "C2C_MESSAGE_CREATE":
            return "c2c"
        if event_type in ("GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE"):
            return "group"
        if event_type == "DIRECT_MESSAGE_CREATE":
            return "direct"
        return "channel"

    def _is_bot_mentioned(self, data: dict[str, object], event_type: str) -> bool:
        """Use QQ's event/structured mention markers as the source of truth."""
        if event_type == "GROUP_AT_MESSAGE_CREATE":
            return True
        mentions = data.get("mentions")
        if isinstance(mentions, list):
            for mention in mentions:
                if not isinstance(mention, dict):
                    continue
                if mention.get("is_you") is True:
                    return True
                mention_id = mention.get("id") or mention.get("user_openid") or mention.get("member_openid")
                if mention_id is not None and str(mention_id) == self._config.app_id:
                    return True
        content = str(data.get("content") or "")
        return f"<@!{self._config.app_id}>" in content or f"<@{self._config.app_id}>" in content

    @staticmethod
    def _parse_event_timestamp(value: object) -> float:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str) and value:
            with contextlib.suppress(ValueError):
                from datetime import datetime

                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        return time.time()

    @staticmethod
    def _is_image_url(url: str, filename: str = "") -> bool:
        """Check if a URL or filename looks like an image."""
        suffixes = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff")
        path = url.split("?")[0].lower()
        return any(path.endswith(s) for s in suffixes) or (
            bool(filename) and any(filename.lower().endswith(s) for s in suffixes)
        )
