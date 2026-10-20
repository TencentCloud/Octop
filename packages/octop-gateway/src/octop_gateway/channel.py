"""Base channel abstract class and channel configuration.

Defines the contract that all IM platform channel implementations must follow.
Provides shared logic for message processing, debouncing, and lifecycle management.
Also exports :class:`ChannelConfig` — the base dataclass for all platform-specific
Config classes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import mimetypes
import re
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, fields
from typing import Any, Self
from urllib.parse import urlparse

import aiohttp

from octop_gateway.constraints import (
    ChannelConstraints,
    RateLimiter,
    ReplyTimeoutGuard,
    TypingKeepalive,
    tool_hint_message,
)
from octop_gateway.group_context import GroupContextConfig, GroupContextManager
from octop_gateway.media import MediaBackend
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
from octop_gateway.push_routing import strip_ephemeral_push_meta
from octop_gateway.utils import Debouncer, close_event_stream, extract_media, extract_text, merge_messages

logger = logging.getLogger(__name__)

# Type alias for the message processor: takes InboundMessage, yields MessageEvents
MessageProcessor = Callable[[InboundMessage], AsyncIterator[MessageEvent]]


# ---------------------------------------------------------------------------
# ChannelConfig — base class for all platform-specific Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChannelConfig:
    """Base class for all channel configuration dataclasses.

    Every platform-specific Config (e.g. ``FeishuConfig``, ``WeComConfig``)
    inherits from this class, so callers can always set ``channel_id`` and
    ``tenant_id`` directly on the config object instead of passing them as
    separate kwargs to :meth:`~octop_gateway.manager.ChannelManager.add_channel`.

    Example::

        feishu_id = await manager.add_feishu_channel(
            FeishuConfig(
                app_id="cli_xxx",
                app_secret="yyy",
                tenant_id="acme",       # inherited from ChannelConfig
            )
        )

    Attributes:
        channel_id: Opaque UUID used as the registration key inside
            :class:`~octop_gateway.manager.ChannelManager`.  When ``None``
            (the default), the manager auto-generates a ``uuid4().hex`` value.
            Set this explicitly only when you need a stable, predictable ID
            across restarts (e.g. for integration tests or deterministic push
            targets).
        tenant_id: Optional tenant identifier for multi-tenant deployments.
    """

    channel_id: str | None = field(default=None)
    tenant_id: str | None = field(default=None)
    show_thinking: bool = False
    show_tool_hints: bool = True
    group_context: GroupContextConfig = field(default_factory=GroupContextConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Instantiate this config class from a plain dictionary.

        Behaviour:

        - String values are stripped of surrounding whitespace.
        - Keys listed in :attr:`field_aliases` are mapped to their canonical
          field name (only when the canonical field was not given directly).
        - Keys that do not match a declared dataclass field are ignored, so
          callers can pass a wider config dict (e.g. loaded from JSON) without
          a ``TypeError``.

        Example::

            cfg = FeishuConfig.from_dict({
                "app_id": "cli_xxx",
                "app_secret": "yyy",
                "tenant_id": "acme",
                "some_other_key": "ignored",
            })

        Args:
            data: Mapping of field names (or aliases) to values.

        Returns:
            A new instance of the calling config class.
        """

        def _clean(value: Any) -> Any:
            return value.strip() if isinstance(value, str) else value

        known = {f.name for f in fields(cls)}
        out = {k: _clean(v) for k, v in data.items() if k in known}
        group_context = out.get("group_context")
        if isinstance(group_context, dict):
            out["group_context"] = GroupContextConfig.from_dict(group_context)
        for alias, canonical in cls.field_aliases.items():  # type: ignore[attr-defined]
            if canonical in known and not out.get(canonical) and data.get(alias):
                out[canonical] = _clean(data[alias])
        return cls(**out)

    def missing_credentials(self) -> list[str]:
        """Return the :attr:`required_credentials` fields that are empty.

        An empty list means the config is complete enough to attempt a
        connection. Platform configs with non-field requirements (e.g. WeChat
        needs at least one account) override this method.
        """
        return [
            name
            for name in self.required_credentials  # type: ignore[attr-defined]
            if not getattr(self, name, None)
        ]


# Class attributes (not dataclass fields): ``from __future__ import annotations``
# can prevent ClassVar from being recognised, so mutable defaults must not
# live on the @dataclass body.
ChannelConfig.field_aliases = {}  # type: ignore[attr-defined]
ChannelConfig.required_credentials = ()  # type: ignore[attr-defined]


class ChannelCredentialsError(ValueError):
    """Raised when a channel config is missing required credentials.

    Locale-neutral on purpose: carries the structured ``kind`` / ``missing``
    so the embedding application can render a localized message.
    """

    def __init__(self, kind: str, missing: list[str]) -> None:
        self.kind = kind
        self.missing = missing
        super().__init__(f"channel {kind!r} missing required credentials: {', '.join(missing)}")


# Mime type to file extension mapping
_MIME_EXT_MAP: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/silk": ".silk",
    "application/pdf": ".pdf",
}


def _mime_to_ext(mime_type: str | None, default: str = ".bin") -> str:
    """Convert mime type to file extension."""
    if not mime_type:
        return default
    return _MIME_EXT_MAP.get(mime_type.lower().split(";")[0].strip(), default)


def _guess_content_type(url_or_path: str) -> str:
    """Guess MIME type from a URL or filesystem path."""
    path = urlparse(url_or_path).path or url_or_path
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


class BaseChannel(ABC):
    """Abstract base class for all IM channel implementations.

    Subclasses must implement:
      - start() / stop() — lifecycle
      - send_text() / send_content() / send_media() — outbound messaging
      - parse_inbound() — convert platform-native payload to InboundMessage

    Optional overrides:
      - fetch_remote_media() — add platform-specific auth headers for downloads
      - get_debounce_key() / merge_messages() — batching customization
      - push_message() — proactive bot-initiated messages
    """

    channel_type: str = "base"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints: ChannelConstraints | None = None,
        config: ChannelConfig | None = None,
    ) -> None:
        import uuid as _uuid

        self._processor = processor
        self._channel_id = channel_id or _uuid.uuid4().hex
        self._tenant_id = tenant_id
        self._media_backend: MediaBackend | None = None
        self._debounce_seconds = debounce_seconds
        self._debouncer: Debouncer | None = None
        self._http: aiohttp.ClientSession | None = None
        # Set by ChannelManager
        self._enqueue_callback: Callable[[Any], None] | None = None
        self._group_context = GroupContextManager(config.group_context if config is not None else None)

        # Platform constraints
        self._constraints = constraints or self._default_constraints()
        if config is not None:
            self._constraints.show_thinking = config.show_thinking
            self._constraints.show_tool_hints = config.show_tool_hints
        self._rate_limiter: RateLimiter | None = None
        if self._constraints.send_rate_limit:
            max_calls, window = self._constraints.send_rate_limit
            self._rate_limiter = RateLimiter(max_calls=max_calls, window_seconds=window)

        # Subject registry: auto-populated on first interaction
        self._known_subjects: dict[str, ChannelSubject] = {}
        self._on_new_subject: Callable[[ChannelSubject], None] | None = None

    @property
    def channel_id(self) -> str:
        """Unique instance ID for this channel (UUID, set at instantiation)."""
        return self._channel_id

    @property
    def tenant_id(self) -> str | None:
        """Tenant identifier for multi-tenant deployments."""
        return self._tenant_id

    def _default_constraints(self) -> ChannelConstraints:
        """Return default constraints for this channel. Override in subclasses."""
        return ChannelConstraints()

    @property
    def constraints(self) -> ChannelConstraints:
        """Access channel constraints for dynamic runtime modification.

        Allows external code to adjust behavior at runtime:
            channel.constraints.show_thinking = True
            channel.constraints.show_tool_hints = False
        """
        return self._constraints

    @property
    def group_context_manager(self) -> GroupContextManager:
        """Expose group policy state for adapter capability-change hooks."""
        return self._group_context

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def set_media_backend(self, backend: MediaBackend) -> None:
        """Set the media persistence backend. Called by ChannelManager before start()."""
        self._media_backend = backend

    @property
    def media_backend(self) -> MediaBackend | None:
        """The active media backend, if configured."""
        return self._media_backend

    @abstractmethod
    async def start(self) -> None:
        """Start the channel (open connections, register webhooks, etc.)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel (close connections, cleanup resources)."""

    async def _ensure_http(self) -> aiohttp.ClientSession:
        """Get or create a shared aiohttp session."""
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def _close_http(self) -> None:
        """Close the shared HTTP session if open."""
        if self._http and not self._http.closed:
            await self._http.close()
            self._http = None

    # =========================================================================
    # Outbound API
    #
    # Three layers:
    #   - Public reply_* (in inbound context) — applies rate-limit, then
    #     delegates to the platform primitive. Routing is fully determined by
    #     the ChannelSubject object, which carries subject_id + metadata.
    #   - Public push_* (bot-initiated, no inbound context) — same throttle,
    #     calls into _send_content directly to keep "one call, one acquire".
    #   - Abstract _send_* (platform primitives) — channels implement these.
    #     Channels MUST call sibling _send_* helpers from inside their own
    #     code, never the public reply_* names, otherwise a single user-
    #     visible message would acquire the rate slot multiple times.
    # =========================================================================

    async def _acquire_rate_slot(self) -> None:
        """Acquire one rate-limit token if a limiter is configured.

        Called once per "logical user-visible message" by the public
        ``reply_*`` / ``push_*`` entry points. Internal helpers in subclasses
        must NOT call this; they call ``_send_*`` directly.
        """
        if self._rate_limiter:
            await self._rate_limiter.acquire()

    # ------- Reply (in inbound context) -------------------------------------

    async def reply_text(self, subject: ChannelSubject, text: str) -> None:
        """Reply with a plain text message in the context of an inbound message.

        Routing and platform metadata are fully carried by ``subject``
        (``subject.subject_id`` + ``subject.metadata``).
        """
        await self._acquire_rate_slot()
        await self._send_text(subject, text)

    async def reply_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Reply with rich content (text + media)."""
        await self._acquire_rate_slot()
        await self._send_content(subject, parts)

    async def reply_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Reply with a single media item."""
        await self._acquire_rate_slot()
        await self._send_media(subject, media)

    # ------- Push (bot-initiated) -------------------------------------------

    def resolve_push_subject(self, subject: ChannelSubject) -> ChannelSubject:
        """Prepare *subject* for proactive push (cron, webhooks, admin, …).

        Merges in-memory inbound routing state, applies platform backfill, and
        strips ephemeral passive-reply fields so sends use proactive paths.
        """
        meta = dict(subject.metadata or {})
        known = self._known_subjects.get(subject.subject_id)
        if known is not None and known.metadata:
            meta = {**meta, **known.metadata}
        meta = self._enrich_push_metadata(subject, meta)
        strip_ephemeral_push_meta(meta)
        chat_type = subject.chat_type or (known.chat_type if known is not None else None)
        return ChannelSubject(
            subject_id=subject.subject_id,
            chat_type=chat_type,  # type: ignore[arg-type]
            metadata=meta,
            first_seen=subject.first_seen or (known.first_seen if known is not None else 0),
            last_seen=subject.last_seen or (known.last_seen if known is not None else 0),
        )

    def _enrich_push_metadata(self, subject: ChannelSubject, meta: dict[str, Any]) -> dict[str, Any]:
        """Platform hook: backfill routing fields for sparse proactive subjects."""
        return meta

    async def push_message(
        self,
        subject: ChannelSubject,
        parts: list[ContentPart],
    ) -> None:
        """Send a bot-initiated message (no prior user request).

        Used for scheduled notifications, webhooks, admin pushes, etc.
        Routes through the same rate-limit slot as ``reply_content`` so
        proactive bursts cannot bypass per-channel throttling. Override for
        platform-specific proactive sending patterns; if you do, remember to
        call ``_acquire_rate_slot()`` exactly once before each subject-visible
        send.
        """
        await self._acquire_rate_slot()
        resolved = self.resolve_push_subject(subject)
        await self._send_content(resolved, parts)

    async def push_text(
        self,
        subject: ChannelSubject,
        text: str,
    ) -> None:
        """Convenience: push a text-only message proactively."""
        await self._acquire_rate_slot()
        resolved = self.resolve_push_subject(subject)
        await self._send_text(resolved, text)

    # ------- Platform primitives (subclasses implement) ---------------------

    @abstractmethod
    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Platform-native rich content send. See :meth:`_send_text` for the
        non-recursion rule.
        """

    @abstractmethod
    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Platform-native text send. Implementations must NOT call
        ``self.reply_text`` / ``self.push_text`` — call sibling ``_send_*``
        helpers instead so the public throttle stays at one acquire per
        subject-visible message.

        Routing destination is ``subject.subject_id``; platform extras (msg_id,
        webhook_url, …) are in ``subject.metadata``.
        """

    @abstractmethod
    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Platform-native media send.

        Implementations should:
          1. Read bytes via :meth:`load_media_bytes` (uniformly handles
             ``data`` / ``local_path`` / ``url``).
          2. Upload to the platform CDN with a channel-private helper.
          3. Deliver the platform reference (image_key / media_id / file_id).

        For platforms without native media support, falling back to
        ``self._send_text`` is acceptable. Do NOT call ``self.reply_text``
        from inside; see :meth:`_send_text`.
        """

    # =========================================================================
    # Receiving (abstract — must implement per platform)
    # =========================================================================

    @abstractmethod
    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse a platform-native message payload into InboundMessage.

        This is the main entry point for converting platform events
        (WebSocket messages, HTTP callbacks, etc.) into the unified format.

        Args:
            raw_payload: Platform-specific message data.

        Returns:
            Normalized InboundMessage ready for processing.
        """

    # =========================================================================
    # Media — fetch (inbound) / load (outbound)
    # =========================================================================

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Download a remote URL and return ``(bytes, content_type)``.

        Default implementation: plain HTTP GET via the shared session.
        Subclasses override to inject platform auth headers (Bearer token,
        OAuth signature, etc.) for URLs that point at the platform's own
        media API.
        """
        http = await self._ensure_http()
        async with http.get(url) as resp:
            resp.raise_for_status()
            content_type = resp.content_type or _guess_content_type(url)
            data = await resp.read()
            return data, content_type

    async def load_media_bytes(self, part: ContentPart) -> tuple[bytes, str]:
        """Resolve a content part to ``(bytes, content_type)``.

        Resolution order:
          1. ``part.data`` set → decode the base64 payload (zero I/O).
          2. ``part.local_path`` set → read from the configured
             ``MediaBackend``. A ``local_path`` without a backend is a
             configuration error and raises ``RuntimeError``.
          3. ``part.url`` set → fetch via :meth:`fetch_remote_media` and,
             when a backend is configured, cache the result back to the
             backend so subsequent reads are local.

        Raises ``ValueError`` if none of the three fields is set.
        """
        if isinstance(part, TextContent):
            raise ValueError("load_media_bytes called on TextContent")

        # Priority 1: inline base64 bytes — the source of truth, no I/O.
        data_field = getattr(part, "data", None)
        if data_field:
            mime = getattr(part, "mime_type", None) or "application/octet-stream"
            try:
                raw = base64.b64decode(data_field, validate=False)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(f"Invalid base64 in ContentPart.data: {exc}") from exc
            return raw, mime

        # Priority 2: MediaBackend key.
        local_path = getattr(part, "local_path", None)
        if local_path:
            if self._media_backend is None:
                raise RuntimeError(
                    f"ContentPart.local_path is set but no MediaBackend is configured "
                    f"for channel {self._channel_id} — call ChannelManager(media_backend=...) or "
                    f"channel.set_media_backend(...) before send."
                )
            raw = await self._media_backend.read(local_path)
            mime = getattr(part, "mime_type", None) or _guess_content_type(local_path)
            return raw, mime

        # Priority 3: remote URL.
        url = getattr(part, "url", "")
        if not url:
            raise ValueError(f"ContentPart has no data/local_path/url: {part}")

        raw, mime = await self.fetch_remote_media(url)

        # Cache to backend so future reads are local and downstream consumers
        # see a stable local_path even for URL-only parts.
        if self._media_backend is not None:
            key = self._derive_storage_key(part, mime)
            try:
                await self._media_backend.save(raw, key)
                part.local_path = key
            except Exception:  # pylint: disable=broad-except
                # MediaBackend is a host-provided extension; cache failures are non-fatal.
                logger.debug("Failed to cache fetched media to backend", exc_info=True)

        return raw, mime

    # =========================================================================
    # Media auto-persist on inbound
    # =========================================================================

    async def _persist_media(self, message: InboundMessage) -> None:
        """Download remote media and persist via the configured backend.

        For each non-text content part with a URL but no ``local_path``:
          1. Download via :meth:`fetch_remote_media` (platform auth applied)
          2. Save bytes to the backend under a deterministic key
          3. Stamp ``part.local_path`` with the backend key
        """
        if not self._media_backend:
            return

        ts = int(time.time())

        content_groups = [message.content]
        if message.group_context is not None:
            content_groups.extend(item.content for item in message.group_context.messages)

        index = 0
        for parts in content_groups:
            for part in parts:
                await self._persist_media_part(part, index, ts)
                index += 1

    async def _persist_media_part(self, part: ContentPart, index: int, timestamp: int) -> None:
        """Persist one inbound media part, including platform group context."""
        if not self._media_backend:
            return
        if isinstance(part, TextContent) or part.local_path:
            return
        url = getattr(part, "url", "")
        if not url:
            return

        try:
            data, mime = await self.fetch_remote_media(url)
            # Image downloaders may identify the actual format from file bytes.
            # Resolve the storage extension only after applying that information.
            if isinstance(part, ImageContent) and mime.startswith("image/"):
                part.mime_type = mime
            else:
                part.mime_type = part.mime_type or mime
            filename = self._resolve_media_filename(part, index, timestamp)
            key = f"{self.channel_type}/{self._channel_id}/{filename}"
            await self._media_backend.save(data, key)
            part.local_path = key
            part.size = len(data)
            logger.info(
                "Media persisted: %s (%d bytes) -> key=%s",
                type(part).__name__,
                len(data),
                key,
            )
        except Exception:  # pylint: disable=broad-except
            # Remote fetchers and MediaBackend implementations are host-provided.
            logger.warning("Failed to persist media: url=%s", url[:100], exc_info=True)

    @staticmethod
    def _safe_media_filename(filename: str, fallback: str = "attachment") -> str:
        """Return a storage-safe basename while retaining Unicode names."""
        basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        basename = re.sub(r"[\x00-\x1f\x7f]", "_", basename).strip(" .")
        return basename or fallback

    def _derive_storage_key(self, part: ContentPart, mime: str) -> str:
        """Build a deterministic backend key for an outbound-cached part."""
        ts = int(time.time())
        url = getattr(part, "url", "") or ""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        ext = _mime_to_ext(mime, ".bin")
        if isinstance(part, FileContent) and part.filename:
            filename = self._safe_media_filename(part.filename)
            return f"{self.channel_type}/_outbound/{ts}_{filename}"
        return f"{self.channel_type}/_outbound/{ts}_{url_hash}{ext}"

    @staticmethod
    def _resolve_media_filename(part: ContentPart, index: int, timestamp: int) -> str:
        """Generate a filename for a media part."""
        # Try to use original filename if available
        if isinstance(part, FileContent) and part.filename:
            name = BaseChannel._safe_media_filename(part.filename)
            return f"{timestamp}_{index}_{name}"
        if isinstance(part, ImageContent) and part.url:
            ext = _mime_to_ext(part.mime_type, ".png")
            url_hash = hashlib.md5(part.url.encode()).hexdigest()[:8]
            return f"{timestamp}_{url_hash}{ext}"
        if isinstance(part, VideoContent):
            ext = _mime_to_ext(part.mime_type, ".mp4")
            url_hash = hashlib.md5(part.url.encode()).hexdigest()[:8]
            return f"{timestamp}_{url_hash}{ext}"
        if isinstance(part, AudioContent):
            ext = _mime_to_ext(part.mime_type, ".mp3")
            url_hash = hashlib.md5(part.url.encode()).hexdigest()[:8]
            return f"{timestamp}_{url_hash}{ext}"
        # Fallback
        url_hash = hashlib.md5(getattr(part, "url", str(index)).encode()).hexdigest()[:8]
        return f"{timestamp}_{url_hash}.bin"

    @staticmethod
    def _get_media_url(part: ContentPart) -> str | None:
        """Extract URL from a media content part (legacy text-fallback helper)."""
        if isinstance(part, ImageContent | VideoContent | AudioContent | FileContent):
            return part.url or None
        return None

    @staticmethod
    def _get_media_label(part: ContentPart) -> str:
        """Get a human-readable label for a media type."""
        if isinstance(part, ImageContent):
            return "Image"
        if isinstance(part, VideoContent):
            return "Video"
        if isinstance(part, AudioContent):
            return "Audio"
        if isinstance(part, FileContent):
            return f"File: {part.filename}" if part.filename else "File"
        return "Attachment"

    # =========================================================================
    # Subject Registry (in-memory)
    # =========================================================================

    def list_subjects(self) -> list[ChannelSubject]:
        """List all known subjects who have interacted with this channel."""
        return list(self._known_subjects.values())

    def get_subject(self, subject_id: str) -> ChannelSubject | None:
        """Get a specific subject by their platform subject ID."""
        return self._known_subjects.get(subject_id)

    def set_on_new_subject(self, callback: Callable[[ChannelSubject], None]) -> None:
        """Set callback fired when a new subject is first seen."""
        self._on_new_subject = callback

    def _track_subject(self, message: InboundMessage) -> None:
        """Track subject from inbound message. Called automatically in handle_inbound.

        Uses ``channel_subject.subject_id`` as the routing handle (open_id for
        DMs, chat_id for group chats).
        """
        if not message.channel_subject:
            return
        subject_id = message.channel_subject.subject_id
        if not subject_id or subject_id == "unknown":
            return
        now = message.timestamp or time.time()
        meta = message.metadata.copy() if message.metadata else {}

        if subject_id in self._known_subjects:
            existing = self._known_subjects[subject_id]
            existing.last_seen = now
            existing.metadata = meta
            if message.channel_subject.display_name:
                existing.display_name = message.channel_subject.display_name
            if message.channel_subject.chat_type:
                existing.chat_type = message.channel_subject.chat_type
        else:
            subject = ChannelSubject(
                subject_id=subject_id,
                first_seen=now,
                last_seen=now,
                display_name=message.channel_subject.display_name,
                chat_type=message.channel_subject.chat_type,
                metadata=meta,
            )
            self._known_subjects[subject_id] = subject
            if self._on_new_subject:
                self._on_new_subject(subject)

    # =========================================================================
    # Message processing pipeline
    # =========================================================================

    async def handle_inbound(self, raw_payload: object) -> None:
        """Run the shared inbound template around platform-specific delivery.

        1. Parse raw payload → InboundMessage
        2. Let the adapter normalize/decrypt platform-specific content
        3. Apply media persistence and shared group-context policy
        4. Process and deliver events using the channel's output strategy
        5. Finalize the group-context lifecycle after a successful reply
        """
        prepared = await self._prepare_inbound(raw_payload)
        if prepared is None:
            return
        message, subject = prepared
        processing_succeeded = await self._process_inbound(message, subject)
        self._finalize_inbound(message, processing_succeeded=processing_succeeded)

    async def _preprocess_inbound(self, message: InboundMessage) -> None:
        """Normalize platform-specific content before shared policy runs.

        Adapters may override this hook for work such as decrypting inbound
        media or enriching platform capability facts. Output delivery belongs
        in :meth:`_process_inbound`; adapters should not replace the shared
        :meth:`handle_inbound` template.
        """

    async def _prepare_inbound(
        self,
        raw_payload: object,
    ) -> tuple[InboundMessage, ChannelSubject] | None:
        """Prepare one message for any channel-specific output strategy."""
        message = self.parse_inbound(raw_payload)
        await self._preprocess_inbound(message)

        # GroupContextManager owns short-lived passive chatter and activation
        # policy.  A non-triggering group message is intentionally observed but
        # never enters the agent's durable conversation thread.
        self._track_subject(message)
        # Persist media before a passive group message is reduced into the
        # short-lived context buffer. The manager avoids downloads for messages
        # that mention-only/history-none policies will discard.
        if self._media_backend and self._group_context.should_persist_media(message):
            await self._persist_media(message)

        prepared = self._group_context.prepare(message)
        if prepared is None:
            return None
        message = prepared

        # Look up or create subject
        subject_id = message.channel_subject.subject_id if message.channel_subject else ""
        subject = self._known_subjects.get(subject_id) or ChannelSubject(
            subject_id=subject_id,
            first_seen=message.timestamp or time.time(),
            last_seen=message.timestamp or time.time(),
        )
        message.channel_subject = subject
        return message, subject

    def _finalize_inbound(self, message: InboundMessage, *, processing_succeeded: bool) -> None:
        """Commit one-shot group-context state after successful completion."""
        if processing_succeeded:
            self._group_context.mark_replied(message)

    async def _process_inbound(self, message: InboundMessage, subject: ChannelSubject) -> bool:
        """Run the default buffered event-delivery strategy.

        Streaming or protocol-specialized adapters override this method while
        retaining the shared preparation and finalization lifecycle.
        """

        # Delta accumulation buffer for streaming
        delta_buffer: list[str] = []
        # Thinking accumulation buffer (separate from content)
        thinking_buffer: list[str] = []

        # --- Set up platform constraint helpers ---
        timeout_guard: ReplyTimeoutGuard | None = None
        typing_keepalive: TypingKeepalive | None = None

        # Reply timeout guard
        if self._constraints.reply_timeout > 0:

            async def _on_reply_timeout() -> None:
                """Called when reply timeout is about to expire.

                Streaming channels (e.g. WeCom) handle first-token timeout
                inside their own ``_process_inbound`` override — see
                :class:`octop_gateway.channels.wecom.WeComChannel`.
                """
                if self._constraints.timeout_strategy == "placeholder":
                    await self._rate_limited_send(subject, self._constraints.placeholder_text)

            timeout_guard = ReplyTimeoutGuard(
                timeout=self._constraints.reply_timeout,
                on_timeout=_on_reply_timeout,
            )
            timeout_guard.start()

        # Typing keepalive
        if self._constraints.typing_keepalive_interval > 0:
            typing_keepalive = TypingKeepalive(
                interval=self._constraints.typing_keepalive_interval,
                send_typing=lambda: self._send_typing_indicator(subject),
            )
            typing_keepalive.start()

        processing_succeeded = False
        events: AsyncIterator[MessageEvent] | None = None
        try:
            events = self._processor(message)
            async for event in events:
                if event.type == MessageEventType.DELTA:
                    # Accumulate delta text
                    for part in event.content:
                        if isinstance(part, TextContent) and part.text:
                            delta_buffer.append(part.text)
                elif event.type == MessageEventType.THINKING:
                    # Complete thinking block — format and send if show_thinking
                    await self._on_thinking(subject, event)
                elif event.type == MessageEventType.THINKING_DELTA:
                    # Streaming thinking fragment — accumulate separately
                    if self._constraints.show_thinking:
                        for part in event.content:
                            if isinstance(part, TextContent) and part.text:
                                thinking_buffer.append(part.text)
                elif event.type == MessageEventType.FLUSH:
                    # Flush all accumulated buffers as separate messages NOW
                    if thinking_buffer:
                        thinking_text = "".join(thinking_buffer)
                        thinking_buffer.clear()
                        formatted = self._constraints.thinking_template.format(content=thinking_text.strip())
                        await self._rate_limited_send(subject, formatted)
                    if delta_buffer:
                        full_text = "".join(delta_buffer)
                        delta_buffer.clear()
                        await self._rate_limited_send(subject, full_text)
                elif event.type == MessageEventType.COMPLETED:
                    # Cancel timeout guard (we're about to reply)
                    if timeout_guard:
                        timeout_guard.cancel()
                    # Flush accumulated thinking first (if show_thinking)
                    if thinking_buffer:
                        thinking_text = "".join(thinking_buffer)
                        thinking_buffer.clear()
                        formatted = self._constraints.thinking_template.format(content=thinking_text.strip())
                        await self._rate_limited_send(subject, formatted)
                    # Flush accumulated deltas as one message
                    if delta_buffer:
                        full_text = "".join(delta_buffer)
                        delta_buffer.clear()
                        await self._rate_limited_send(subject, full_text)
                    processing_succeeded = True
                    break
                elif event.type == MessageEventType.MESSAGE:
                    # Cancel timeout guard on first real message
                    if timeout_guard:
                        timeout_guard.cancel()
                    # Flush thinking buffer
                    if thinking_buffer:
                        thinking_text = "".join(thinking_buffer)
                        thinking_buffer.clear()
                        formatted = self._constraints.thinking_template.format(content=thinking_text.strip())
                        await self._rate_limited_send(subject, formatted)
                    # Flush any pending deltas before sending complete message
                    if delta_buffer:
                        full_text = "".join(delta_buffer)
                        delta_buffer.clear()
                        await self._rate_limited_send(subject, full_text)
                    # Send complete message immediately
                    await self._deliver_event(subject, event)
                elif event.type == MessageEventType.ERROR:
                    if delta_buffer:
                        await self._rate_limited_send(subject, "".join(delta_buffer))
                        delta_buffer.clear()
                    await self._deliver_event(subject, event)
                    break
                else:
                    # TYPING, TOOL_START, TOOL_END
                    await self._deliver_event(subject, event)
        except Exception:  # pylint: disable=broad-except
            # The processor is host-provided; one failed message must not stop the worker.
            logger.exception(
                "Error processing message: channel=%s session=%s",
                self.channel_id,
                message.channel_session_id,
            )
            if timeout_guard:
                timeout_guard.cancel()
            # Flush anything accumulated before error
            if delta_buffer:
                full_text = "".join(delta_buffer)
                await self._rate_limited_send(subject, full_text)
            await self._rate_limited_send(
                subject,
                "An error occurred while processing your message.",
            )
        finally:
            # Cleanup helpers
            if timeout_guard:
                timeout_guard.cancel()
            if typing_keepalive:
                typing_keepalive.stop()
            if events is not None:
                await close_event_stream(events)
        return processing_succeeded

    async def _rate_limited_send(self, subject: ChannelSubject, text: str) -> None:
        """Clean output and dispatch via :meth:`reply_text`.

        Acts as the internal helper used inside :meth:`handle_inbound` and
        the constraint hook points (thinking, tool hints, error). Cleaning
        is applied first so empty results short-circuit before consuming a
        rate-limit slot.
        """
        text = self._clean_output(text)
        if not text:
            return
        await self.reply_text(subject, text)

    def _clean_output(self, text: str) -> str:
        """Legacy fallback: strip/format <think> tags in raw model output.

        BACKGROUND:
            Modern message processors emit THINKING_DELTA events for streaming
            thinking fragments and THINKING events for complete thinking blocks.
            These are already constrained by show_thinking during emit.

            However, some LLM backends or custom processors may emit raw text
            containing <think>...</think> tags in DELTA events instead of using
            the structured THINKING_DELTA event type. This method is a fallback
            handler for that legacy pattern.

        BEHAVIOR:
            - show_thinking=True: Formats <think> blocks with thinking_template
            - show_thinking=False: Strips all <think> content entirely
            - Handles unclosed <think> tags (from response truncation)

        NOTE:
            With proper MessageEventType usage (THINKING_DELTA), this method
            becomes a no-op. It's retained for backwards compatibility.

        Args:
            text: Raw text that may contain <think> tags

        Returns:
            Cleaned text with thinking tags processed according to constraint
        """
        if not text:
            return ""

        if self._constraints.show_thinking:
            # Format thinking blocks with template prefix
            def _format_think(match: re.Match[str]) -> str:
                content = match.group(1).strip()
                if not content:
                    return ""
                formatted = self._constraints.thinking_template.format(content=content)
                return f"{formatted}\n\n"

            text = re.sub(r"<think>(.*?)</think>", _format_think, text, flags=re.DOTALL)
            # Handle unclosed <think> at the end
            unclosed = re.search(r"<think>(.*?)$", text, flags=re.DOTALL)
            if unclosed:
                content = unclosed.group(1).strip()
                if content:
                    formatted = self._constraints.thinking_template.format(content=content)
                    text = text[: unclosed.start()] + f"{formatted}\n\n"
                else:
                    text = text[: unclosed.start()]
        else:
            # Remove complete <think>...</think> blocks
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
            # Remove unclosed <think> at the end (truncated by max_tokens)
            text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)

        return text.strip()

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        """Send a typing indicator. Override for platform-specific implementation.

        Default: no-op. Platforms that support typing indicators (WeChat, Discord)
        should override this to call their platform API.
        """

    async def _deliver_event(
        self,
        subject: ChannelSubject,
        event: MessageEvent,
    ) -> None:
        """Deliver a single MessageEvent to the subject.

        Events handled in handle_inbound's main loop (DELTA, THINKING_DELTA,
        FLUSH, COMPLETED) should never reach here. This handles the remaining
        event types that need immediate delivery.
        """
        if event.type in (
            MessageEventType.COMPLETED,
            MessageEventType.DELTA,
            MessageEventType.THINKING_DELTA,
            MessageEventType.FLUSH,
        ):
            return  # These are handled by handle_inbound's buffer logic

        if event.type == MessageEventType.THINKING:
            # Handled by _on_thinking in the main loop
            return

        if event.type == MessageEventType.ERROR:
            error_text = event.error or "An unexpected error occurred."
            await self._rate_limited_send(subject, error_text)
            return

        if event.type == MessageEventType.TYPING:
            # Subclasses can override _send_typing_indicator
            return

        if event.type == MessageEventType.TOOL_START:
            await self._on_tool_start(subject, event)
            return

        if event.type == MessageEventType.TOOL_END:
            await self._on_tool_end(subject, event)
            return

        # MessageEventType.MESSAGE — deliver content
        if not event.content:
            return

        text_parts = extract_text(event.content)
        media_parts = extract_media(event.content)

        if text_parts:
            await self._rate_limited_send(subject, text_parts)

        for media in media_parts:
            await self.reply_media(subject, media)

    async def _on_thinking(self, subject: ChannelSubject, event: MessageEvent) -> None:
        """Handle THINKING event. Formats and sends thinking content.

        Only sends if show_thinking=True. Formats with thinking_template.
        """
        if not self._constraints.show_thinking:
            return
        for part in event.content:
            if isinstance(part, TextContent) and part.text:
                formatted = self._constraints.thinking_template.format(content=part.text.strip())
                await self._rate_limited_send(subject, formatted)

    async def _on_tool_start(self, subject: ChannelSubject, event: MessageEvent) -> None:
        """Handle TOOL_START event. Override for platform-specific status display.

        Default: sends a formatted status message using tool_hint_template
        (if show_tool_hints is True).
        """
        if not self._constraints.show_tool_hints:
            return
        text = tool_hint_message(event.metadata, self._constraints, phase="start")
        await self._rate_limited_send(subject, text)

    async def _on_tool_end(self, subject: ChannelSubject, event: MessageEvent) -> None:
        """Handle TOOL_END event. Sends a brief completion notice.

        Default: sends tool_end_template (if show_tool_hints is True).
        Does NOT send the tool's output/result to the subject.
        """
        if not self._constraints.show_tool_hints:
            return
        text = tool_hint_message(event.metadata, self._constraints, phase="end")
        await self._rate_limited_send(subject, text)

    # =========================================================================
    # Batching hooks (optional override)
    # =========================================================================

    def get_debounce_key(self, message: InboundMessage) -> str:
        """Return a key for message debouncing/batching and session locking.

        Messages with the same key within debounce_seconds are merged.
        Also used by ChannelManager for per-user sequential processing.
        Default: channel_subject.subject_id (ensures per-user serialization).
        """
        if message.channel_subject:
            return message.channel_subject.subject_id
        return ""

    def should_batch_inbound(self, message: InboundMessage) -> bool:
        """Return whether manager-level batching may merge this message.

        Group-context-enabled messages must retain individual sender labels and
        ordering, so they are processed one event at a time.
        """
        return not self._group_context.handles(message)

    def merge_inbound(self, messages: list[InboundMessage]) -> InboundMessage:
        """Merge multiple inbound messages into one (for batching).

        Default: concatenates content, keeps earliest timestamp.
        Override for platform-specific merge logic.
        """
        return merge_messages(messages)

    # =========================================================================
    # Internal: enqueue support (used by ChannelManager)
    # =========================================================================

    def set_enqueue_callback(self, callback: Callable[[Any], None]) -> None:
        """Set the enqueue callback (called by ChannelManager)."""
        self._enqueue_callback = callback

    def enqueue(self, payload: Any) -> None:
        """Enqueue a payload for processing (delegates to manager)."""
        if self._enqueue_callback:
            self._enqueue_callback(payload)
        else:
            logger.warning("No enqueue callback set for channel %s", self._channel_id)
