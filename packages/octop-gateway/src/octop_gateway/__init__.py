"""octop-gateway: Multi-platform IM channel bridge for AI agents and bots.

Provides a unified abstraction for building bots across multiple IM platforms
(Feishu, QQ, WeChat, DingTalk, Discord, etc.) with a single processor function.

Quick start:
    from octop_gateway import BaseChannel, ChannelManager, InboundMessage, MessageEvent

    async def my_bot(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
        yield MessageEvent.text(f"Echo: {msg.text}")
        yield MessageEvent.completed()
"""

from __future__ import annotations

from octop_gateway.channel import BaseChannel, ChannelConfig, ChannelCredentialsError, MessageProcessor
from octop_gateway.channels import SUPPORTED_CHANNEL_KINDS, ChannelKind
from octop_gateway.channels.discord import DiscordChannel, DiscordConfig
from octop_gateway.constraints import ChannelConstraints, RateLimiter, ReplyTimeoutGuard, TypingKeepalive
from octop_gateway.group_context import (
    GroupActivation,
    GroupContextConfig,
    GroupContextManager,
    GroupHistoryMode,
    GroupVisibility,
)
from octop_gateway.manager import ChannelManager
from octop_gateway.media import FileSystemMediaBackend, MediaBackend
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    ContentType,
    FileContent,
    GroupContext,
    GroupContextMessage,
    ImageContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
    VideoContent,
)
from octop_gateway.utils import Debouncer, extract_media, extract_text, has_media, has_text, merge_messages

__all__ = [
    "DASHBOARD_CHANNEL_ID",
    "SUPPORTED_CHANNEL_KINDS",
    "AudioContent",
    "BaseChannel",
    "ChannelConfig",
    "ChannelConstraints",
    "ChannelCredentialsError",
    "ChannelKind",
    "ChannelManager",
    "ChannelSubject",
    "ContentPart",
    "ContentType",
    "DashboardChannel",
    "Debouncer",
    "DiscordChannel",
    "DiscordConfig",
    "FileContent",
    "FileSystemMediaBackend",
    "GroupActivation",
    "GroupContext",
    "GroupContextConfig",
    "GroupContextManager",
    "GroupContextMessage",
    "GroupHistoryMode",
    "GroupVisibility",
    "ImageContent",
    "InboundMessage",
    "MediaBackend",
    "MessageEvent",
    "MessageEventType",
    "MessageProcessor",
    "RateLimiter",
    "ReplyTimeoutGuard",
    "TextContent",
    "TypingKeepalive",
    "VideoContent",
    "extract_media",
    "extract_text",
    "has_media",
    "has_text",
    "merge_messages",
]
