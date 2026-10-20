"""Platform constraints and rate limiting utilities.

Handles platform-specific limitations:
- Reply timeout: must respond within N seconds
- Send rate limit: max N messages per time window
- Typing keepalive: refresh typing indicator during long processing
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform Constraints Configuration
# ---------------------------------------------------------------------------


@dataclass
class ChannelConstraints:
    """Platform-specific constraints that affect message delivery behavior.

    Channels declare their constraints, and BaseChannel uses them to:
    - Enforce reply timeouts (placeholder + streaming to keep alive)
    - Rate-limit outbound messages (sliding window)
    - Maintain typing indicators during long processing

    Examples:
        WeChat Work: reply_timeout=10, send_rate_limit=(2, 5)
        WeChat Public: reply_timeout=5, send_rate_limit=(5, 60)
        QQ: no hard timeout, send_rate_limit=(20, 60)
        Feishu: no hard timeout, generous rate limits
    """

    # Max seconds allowed before first reply. 0 = no constraint.
    reply_timeout: float = 0.0

    # (max_messages, window_seconds): max N messages in M seconds. None = no limit.
    send_rate_limit: tuple[int, float] | None = None

    # How often (seconds) to refresh typing indicator during processing. 0 = disabled.
    typing_keepalive_interval: float = 0.0

    # Strategy when reply_timeout is about to expire:
    # "placeholder" — send a placeholder message, then follow up with real content
    # "none"        — do nothing (for platforms without hard timeout)
    #
    # Channels that stream their reply (e.g. WeCom) implement first-token
    # timeout handling in their own ``handle_inbound`` override; they too
    # honour this field by emitting a placeholder when "placeholder" is set.
    timeout_strategy: str = "none"

    # Placeholder texts: one is randomly selected when timeout fires.
    # Supports multiple entries for variety. Users can fully customize.
    placeholder_texts: list[str] = field(
        default_factory=lambda: [
            "⏳ 思考中...",
            "🤔 让我想想...",
            "💭 正在处理你的问题...",
        ]
    )

    # Max seconds to wait for tool execution before sending intermediate status
    tool_hint_throttle: float = 6.0

    # Display control: whether to show tool call status to user
    show_tool_hints: bool = True

    # Tool hint prefix template. {tool_name} will be replaced with actual tool name.
    tool_hint_template: str = "🔧 Calling tool: {tool_name}"

    # Tool completion template. {tool_name} will be replaced. Sent on TOOL_END.
    tool_end_template: str = "✅ {tool_name} done"

    # Display control: whether to forward thinking/reasoning content to user
    show_thinking: bool = False

    # Thinking content template. {content} will be replaced with the thinking text.
    # Only used when show_thinking=True.
    thinking_template: str = "💭 Thinking: {content}"

    @property
    def placeholder_text(self) -> str:
        """Randomly select one placeholder text."""
        if not self.placeholder_texts:
            return "⏳ ..."
        return random.choice(self.placeholder_texts)


def tool_hint_message(
    metadata: dict[str, Any],
    constraints: ChannelConstraints,
    *,
    phase: Literal["start", "end"] = "start",
) -> str:
    """Format a tool status line, preferring pre-localized ``tool_hint_text`` in *metadata*."""
    raw = metadata.get("tool_hint_text")
    if isinstance(raw, str) and raw.strip():
        return raw
    tool_name = metadata.get("tool_name", "tool")
    template = constraints.tool_end_template if phase == "end" else constraints.tool_hint_template
    return template.format(tool_name=tool_name)


def apply_config_display_flags(
    constraints: ChannelConstraints,
    config: Any,
) -> ChannelConstraints:
    """Apply ``show_thinking`` / ``show_tool_hints`` from a ChannelConfig."""
    constraints.show_thinking = getattr(config, "show_thinking", constraints.show_thinking)
    constraints.show_tool_hints = getattr(config, "show_tool_hints", constraints.show_tool_hints)
    return constraints


# ---------------------------------------------------------------------------
# Rate Limiter (Sliding Window)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Sliding window rate limiter for outbound messages.

    Ensures we don't exceed `max_calls` within `window_seconds`.
    If the limit is reached, `acquire()` will wait until a slot opens.

    Usage:
        limiter = RateLimiter(max_calls=2, window_seconds=5.0)
        await limiter.acquire()  # waits if needed
        send_message(...)
    """

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a send slot. Blocks if rate limit would be exceeded."""
        async with self._lock:
            now = time.monotonic()
            # Evict expired timestamps
            while self._timestamps and now - self._timestamps[0] >= self._window:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_calls:
                # Must wait until oldest timestamp expires
                wait_time = self._window - (now - self._timestamps[0])
                if wait_time > 0:
                    logger.debug("RateLimiter: throttling %.2fs", wait_time)
                    await asyncio.sleep(wait_time)
                    # Re-evict after sleep
                    now = time.monotonic()
                    while self._timestamps and now - self._timestamps[0] >= self._window:
                        self._timestamps.popleft()

            self._timestamps.append(time.monotonic())

    @property
    def available(self) -> int:
        """Number of available slots right now (without waiting)."""
        now = time.monotonic()
        # Count non-expired
        active = sum(1 for t in self._timestamps if now - t < self._window)
        return max(0, self._max_calls - active)

    def reset(self) -> None:
        """Clear all tracked timestamps."""
        self._timestamps.clear()


# ---------------------------------------------------------------------------
# Reply Timeout Guard
# ---------------------------------------------------------------------------


class ReplyTimeoutGuard:
    """Manages reply timeout for platforms that require response within N seconds.

    Usage:
        guard = ReplyTimeoutGuard(timeout=5.0, on_timeout=send_placeholder)
        guard.start()
        # ... process message ...
        guard.cancel()  # cancel if replied in time

    If the timeout fires before cancel(), it calls `on_timeout()` to send
    a placeholder or start streaming to keep the connection alive.
    """

    def __init__(
        self,
        timeout: float,
        on_timeout: Any,  # Callable[[], Awaitable[None]]
    ) -> None:
        self._timeout = timeout
        self._on_timeout = on_timeout
        self._task: asyncio.Task[None] | None = None
        self._fired = False

    def start(self) -> None:
        """Start the timeout countdown."""
        if self._timeout <= 0:
            return
        self._task = asyncio.create_task(self._countdown())

    def cancel(self) -> None:
        """Cancel the timeout (reply was sent in time)."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    @property
    def fired(self) -> bool:
        """True if the timeout fired (placeholder was sent)."""
        return self._fired

    async def _countdown(self) -> None:
        """Wait for timeout then fire the callback."""
        try:
            # Fire slightly before actual deadline to ensure delivery
            await asyncio.sleep(self._timeout * 0.8)
            self._fired = True
            await self._on_timeout()
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Typing Keepalive
# ---------------------------------------------------------------------------


class TypingKeepalive:
    """Periodically sends typing indicator during long processing.

    Usage:
        keepalive = TypingKeepalive(interval=5.0, send_typing=channel.send_typing)
        keepalive.start()
        # ... long processing ...
        keepalive.stop()
    """

    def __init__(
        self,
        interval: float,
        send_typing: Any,  # Callable[[], Awaitable[None]]
    ) -> None:
        self._interval = interval
        self._send_typing = send_typing
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start sending periodic typing indicators."""
        if self._interval <= 0:
            return
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Stop the typing keepalive loop."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        """Typing indicator loop."""
        try:
            while True:
                await self._send_typing()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass
        except Exception:  # pylint: disable=broad-except
            # Typing callbacks are channel-provided and must not kill the keepalive task.
            logger.exception("TypingKeepalive error")
