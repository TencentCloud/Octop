"""Data models for octop-gateway.

Defines the unified content type system, message models, and routing types
used across all channel implementations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Content Types
# ---------------------------------------------------------------------------


class ContentType(StrEnum):
    """Supported content types for message parts."""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"


class TextContent(BaseModel):
    """Plain text content part."""

    type: Literal[ContentType.TEXT] = ContentType.TEXT
    text: str


class ImageContent(BaseModel):
    """Image content part.

    A media part carries one of three byte sources, in priority order:
      - ``data`` — base64-encoded raw bytes (highest priority; agents that
        already hold the bytes in memory should bind this directly).
      - ``local_path`` — a key into the active ``MediaBackend``; reading
        ``ContentPart.data`` through the backend without it is undefined.
      - ``url`` — remote source; fetched via
        :meth:`BaseChannel.fetch_remote_media` (may need platform auth).

    Always read bytes via :meth:`BaseChannel.load_media_bytes(part)`. Never
    decode ``data`` or open ``local_path`` directly: the bridge owns the
    contract that lets non-filesystem backends and inline payloads work
    transparently across all channels.
    """

    type: Literal[ContentType.IMAGE] = ContentType.IMAGE
    url: str = ""
    alt_text: str = ""
    width: int | None = None
    height: int | None = None
    size: int | None = None  # bytes
    mime_type: str | None = None
    local_path: str | None = None  # MediaBackend key (read via backend.read)
    data: str | None = None  # Base64-encoded raw bytes (highest-priority source)


class VideoContent(BaseModel):
    """Video content part.

    See :class:`ImageContent` for the ``data`` / ``local_path`` / ``url``
    priority contract.
    """

    type: Literal[ContentType.VIDEO] = ContentType.VIDEO
    url: str = ""
    duration: int | None = None  # milliseconds
    thumbnail_url: str | None = None
    size: int | None = None  # bytes
    mime_type: str | None = None
    local_path: str | None = None  # MediaBackend key (read via backend.read)
    data: str | None = None  # Base64-encoded raw bytes (highest-priority source)


class AudioContent(BaseModel):
    """Audio content part.

    See :class:`ImageContent` for the ``data`` / ``local_path`` / ``url``
    priority contract.
    """

    type: Literal[ContentType.AUDIO] = ContentType.AUDIO
    url: str = ""
    duration: int | None = None  # milliseconds
    size: int | None = None  # bytes
    mime_type: str | None = None
    local_path: str | None = None  # MediaBackend key (read via backend.read)
    data: str | None = None  # Base64-encoded raw bytes (highest-priority source)


class FileContent(BaseModel):
    """File attachment content part.

    See :class:`ImageContent` for the ``data`` / ``local_path`` / ``url``
    priority contract.
    """

    type: Literal[ContentType.FILE] = ContentType.FILE
    url: str = ""
    filename: str = ""
    size: int | None = None  # bytes
    mime_type: str | None = None
    local_path: str | None = None  # MediaBackend key (read via backend.read)
    data: str | None = None  # Base64-encoded raw bytes (highest-priority source)


# Discriminated union for content parts
ContentPart = Annotated[
    TextContent | ImageContent | VideoContent | AudioContent | FileContent,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Message Event Types
# ---------------------------------------------------------------------------


class MessageEventType(StrEnum):
    """Types of events emitted by the message processor."""

    MESSAGE = "message"  # Complete message (send immediately)
    DELTA = "delta"  # Streaming text delta (accumulated, sent on COMPLETED)
    THINKING = "thinking"  # Complete thinking/reasoning block
    THINKING_DELTA = "thinking_delta"  # Streaming thinking fragment
    FLUSH = "flush"  # Flush accumulated content as one message, start new one
    TYPING = "typing"  # Typing indicator
    TOOL_START = "tool_start"  # Tool/function call started
    TOOL_END = "tool_end"  # Tool/function call finished
    ERROR = "error"  # Error occurred
    COMPLETED = "completed"  # End of response stream


# ---------------------------------------------------------------------------
# Message Models
# ---------------------------------------------------------------------------


class GroupContextMessage(BaseModel):
    """One passive group message supplied as background for a later turn."""

    message_id: str = ""
    sender_id: str
    sender_name: str = ""
    text: str
    content: list[ContentPart] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class GroupContext(BaseModel):
    """Structured, short-lived group context attached to the current message."""

    conversation_id: str
    visibility: str
    activation: str
    messages: list[GroupContextMessage] = Field(default_factory=list)
    capability_degraded: bool = False


class InboundMessage(BaseModel):
    """Inbound message from user to bot (normalized from platform-native format).

    ``channel_subject`` is the reply/conversation target: a user for direct
    messages and the conversation ID for group messages. Group adapters retain
    the individual author in ``metadata.sender_id`` / ``metadata.sender_name``
    so all members share one thread without losing attribution.
    """

    channel_id: str
    channel_type: str = ""
    tenant_id: str | None = None
    channel_subject: ChannelSubject | None = None
    channel_session_id: str | None = None
    content: list[ContentPart]
    group_context: GroupContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

    @property
    def text(self) -> str:
        """Extract concatenated text from all TextContent parts."""
        parts: list[str] = []
        for c in self.content:
            if isinstance(c, TextContent) and c.text:
                parts.append(c.text)
        return "\n".join(parts)

    @property
    def has_media(self) -> bool:
        """True if message contains any media (image/video/audio/file)."""
        return any(not isinstance(c, TextContent) for c in self.content)


class MessageEvent(BaseModel):
    """Event emitted by message processor back to channel for delivery."""

    type: MessageEventType = MessageEventType.MESSAGE
    content: list[ContentPart] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @classmethod
    def text(cls, text: str, **kwargs: Any) -> MessageEvent:
        """Create a MESSAGE event with a single text content part."""
        return cls(
            type=MessageEventType.MESSAGE,
            content=[TextContent(text=text)],
            **kwargs,
        )

    @classmethod
    def delta(cls, text: str, **kwargs: Any) -> MessageEvent:
        """Create a DELTA event (streaming text fragment).

        Deltas are accumulated by the channel and merged into a single
        message when COMPLETED is received. Use this for token-by-token
        LLM output.
        """
        return cls(
            type=MessageEventType.DELTA,
            content=[TextContent(text=text)],
            **kwargs,
        )

    @classmethod
    def typing(cls) -> MessageEvent:
        """Create a TYPING indicator event."""
        return cls(type=MessageEventType.TYPING)

    @classmethod
    def flush(cls) -> MessageEvent:
        """Create a FLUSH event — sends accumulated content as one message immediately.

        Use between thinking and response, or anywhere you want to split
        the output into separate messages for the user.

        Example:
            yield MessageEvent.thinking_delta("reasoning...")
            yield MessageEvent.flush()  # → sends thinking as message #1
            yield MessageEvent.delta("answer...")
            yield MessageEvent.completed()  # → sends answer as message #2
        """
        return cls(type=MessageEventType.FLUSH)

    @classmethod
    def thinking(cls, text: str, **kwargs: Any) -> MessageEvent:
        """Create a THINKING event (complete reasoning block).

        Channel will format with thinking_template if show_thinking=True,
        or discard if show_thinking=False.
        """
        return cls(
            type=MessageEventType.THINKING,
            content=[TextContent(text=text)],
            **kwargs,
        )

    @classmethod
    def thinking_delta(cls, text: str, **kwargs: Any) -> MessageEvent:
        """Create a THINKING_DELTA event (streaming reasoning fragment).

        Thinking deltas are accumulated separately from content deltas.
        Channel will format/discard based on show_thinking constraint.
        """
        return cls(
            type=MessageEventType.THINKING_DELTA,
            content=[TextContent(text=text)],
            **kwargs,
        )

    @classmethod
    def tool_start(cls, tool_name: str, **kwargs: Any) -> MessageEvent:
        """Create a TOOL_START event (tool/function call began)."""
        return cls(
            type=MessageEventType.TOOL_START,
            metadata={"tool_name": tool_name, **kwargs},
        )

    @classmethod
    def tool_end(cls, tool_name: str, **kwargs: Any) -> MessageEvent:
        """Create a TOOL_END event (tool/function call finished)."""
        return cls(
            type=MessageEventType.TOOL_END,
            metadata={"tool_name": tool_name, **kwargs},
        )

    @classmethod
    def completed(cls) -> MessageEvent:
        """Create a COMPLETED event signaling end of response."""
        return cls(type=MessageEventType.COMPLETED)

    @classmethod
    def error_event(cls, message: str) -> MessageEvent:
        """Create an ERROR event."""
        return cls(type=MessageEventType.ERROR, error=message)


# ---------------------------------------------------------------------------
# Subject Registry Model
# ---------------------------------------------------------------------------


@dataclass
class ChannelSubject:
    """Known outbound routing subject (a direct user or group conversation).

    Automatically collected on first message. Used for proactive push and
    as the unified routing handle for all outbound send operations.

    The ``to_handle`` field carries the platform-native reply destination
    (openid, group_id, webhook URL, etc.) extracted from the last inbound
    message. ``metadata`` carries any platform-specific routing extras
    (msg_id, webhook_url, chat_type, …) needed by ``_send_*`` implementations.

    Both fields are updated on every inbound message so the channel always
    holds the most recent routing context for the subject.
    """

    subject_id: str  # Unique identifier (openid, user_id, etc.)
    first_seen: float | None = None
    last_seen: float | None = None
    display_name: str = ""
    chat_type: str = ""  # "direct", "group", etc.
    metadata: dict[str, Any] = field(default_factory=dict)
