"""Tests for platform constraints and rate limiting utilities."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

from octop_gateway.constraints import (
    ChannelConstraints,
    RateLimiter,
    ReplyTimeoutGuard,
    TypingKeepalive,
)

# ---------------------------------------------------------------------------
# ChannelConstraints
# ---------------------------------------------------------------------------


class TestChannelConstraintsDefaults:
    """Verify default field values match the docstring/spec."""

    def test_reply_timeout_default(self):
        c = ChannelConstraints()
        assert c.reply_timeout == 0.0

    def test_send_rate_limit_default_none(self):
        c = ChannelConstraints()
        assert c.send_rate_limit is None

    def test_typing_keepalive_interval_default(self):
        c = ChannelConstraints()
        assert c.typing_keepalive_interval == 0.0

    def test_timeout_strategy_default(self):
        c = ChannelConstraints()
        assert c.timeout_strategy == "none"

    def test_placeholder_texts_default_is_list_of_three(self):
        c = ChannelConstraints()
        assert len(c.placeholder_texts) == 3
        assert all(isinstance(t, str) for t in c.placeholder_texts)

    def test_tool_hint_throttle_default(self):
        c = ChannelConstraints()
        assert c.tool_hint_throttle == 6.0

    def test_show_tool_hints_default_true(self):
        c = ChannelConstraints()
        assert c.show_tool_hints is True

    def test_tool_hint_template_default(self):
        c = ChannelConstraints()
        assert c.tool_hint_template == "🔧 Calling tool: {tool_name}"

    def test_show_thinking_default_false(self):
        c = ChannelConstraints()
        assert c.show_thinking is False


class TestChannelConstraintsCustom:
    """Verify fields accept custom values."""

    def test_custom_reply_timeout(self):
        c = ChannelConstraints(reply_timeout=10.0)
        assert c.reply_timeout == 10.0

    def test_custom_send_rate_limit(self):
        c = ChannelConstraints(send_rate_limit=(5, 60.0))
        assert c.send_rate_limit == (5, 60.0)

    def test_custom_typing_keepalive_interval(self):
        c = ChannelConstraints(typing_keepalive_interval=3.0)
        assert c.typing_keepalive_interval == 3.0

    def test_custom_timeout_strategy(self):
        c = ChannelConstraints(timeout_strategy="placeholder")
        assert c.timeout_strategy == "placeholder"

    def test_custom_placeholder_texts(self):
        texts = ["Working...", "Hold on..."]
        c = ChannelConstraints(placeholder_texts=texts)
        assert c.placeholder_texts == texts

    def test_custom_tool_hint_throttle(self):
        c = ChannelConstraints(tool_hint_throttle=10.0)
        assert c.tool_hint_throttle == 10.0

    def test_custom_show_tool_hints_false(self):
        c = ChannelConstraints(show_tool_hints=False)
        assert c.show_tool_hints is False

    def test_custom_tool_hint_template(self):
        tpl = "Using {tool_name} now..."
        c = ChannelConstraints(tool_hint_template=tpl)
        assert c.tool_hint_template == tpl

    def test_custom_show_thinking_true(self):
        c = ChannelConstraints(show_thinking=True)
        assert c.show_thinking is True

    def test_placeholder_texts_independent_across_instances(self):
        """Each instance gets its own default list (no mutable default sharing)."""
        c1 = ChannelConstraints()
        c2 = ChannelConstraints()
        c1.placeholder_texts.append("extra")
        assert "extra" not in c2.placeholder_texts


class TestPlaceholderTextProperty:
    """Tests for the placeholder_text random selection property."""

    def test_returns_string_from_list(self):
        texts = ["A", "B", "C"]
        c = ChannelConstraints(placeholder_texts=texts)
        for _ in range(50):
            assert c.placeholder_text in texts

    def test_single_item_always_returned(self):
        c = ChannelConstraints(placeholder_texts=["Only one"])
        assert c.placeholder_text == "Only one"

    def test_empty_list_returns_fallback(self):
        c = ChannelConstraints(placeholder_texts=[])
        assert c.placeholder_text == "⏳ ..."

    def test_randomness_covers_multiple_entries(self):
        """Over many samples, we expect to see more than one unique value."""
        texts = ["X", "Y", "Z"]
        c = ChannelConstraints(placeholder_texts=texts)
        seen = {c.placeholder_text for _ in range(200)}
        # With 200 samples and 3 options, extremely unlikely to miss one
        assert len(seen) >= 2


class TestToolHintTemplate:
    """Tests for tool_hint_template formatting."""

    def test_format_with_tool_name(self):
        c = ChannelConstraints()
        result = c.tool_hint_template.format(tool_name="web_search")
        assert result == "🔧 Calling tool: web_search"

    def test_format_custom_template(self):
        c = ChannelConstraints(tool_hint_template="[{tool_name}] running...")
        result = c.tool_hint_template.format(tool_name="calculator")
        assert result == "[calculator] running..."

    def test_format_with_empty_tool_name(self):
        c = ChannelConstraints()
        result = c.tool_hint_template.format(tool_name="")
        assert result == "🔧 Calling tool: "

    def test_format_with_special_characters(self):
        c = ChannelConstraints()
        result = c.tool_hint_template.format(tool_name="file_io/read")
        assert result == "🔧 Calling tool: file_io/read"


class TestToolHintMessage:
    def test_prefers_metadata_tool_hint_text(self):
        from octop_gateway.constraints import tool_hint_message

        c = ChannelConstraints()
        text = tool_hint_message(
            {"tool_name": "read_file", "tool_hint_text": "🔧 正在调用工具：读取文件"},
            c,
            phase="start",
        )
        assert text == "🔧 正在调用工具：读取文件"

    def test_falls_back_to_constraints_template(self):
        from octop_gateway.constraints import tool_hint_message

        c = ChannelConstraints()
        text = tool_hint_message({"tool_name": "grep"}, c, phase="start")
        assert text == "🔧 Calling tool: grep"

    def test_end_phase_uses_end_template(self):
        from octop_gateway.constraints import tool_hint_message

        c = ChannelConstraints()
        text = tool_hint_message({"tool_name": "grep"}, c, phase="end")
        assert text == "✅ grep done"


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Tests for sliding window rate limiter."""

    async def test_allows_within_limit(self):
        """Acquiring up to max_calls should not block."""
        limiter = RateLimiter(max_calls=3, window_seconds=10.0)
        start = time.monotonic()
        for _ in range(3):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should complete almost instantly
        assert elapsed < 0.1

    async def test_blocks_when_limit_exceeded(self):
        """Exceeding max_calls causes acquire() to wait."""
        limiter = RateLimiter(max_calls=2, window_seconds=0.2)
        # Fill the window
        await limiter.acquire()
        await limiter.acquire()

        start = time.monotonic()
        await limiter.acquire()  # should block ~0.2s
        elapsed = time.monotonic() - start
        # Should have waited roughly the window duration
        assert elapsed >= 0.15

    async def test_window_expiry_frees_slots(self):
        """After the window expires, new calls go through immediately."""
        limiter = RateLimiter(max_calls=1, window_seconds=0.1)
        await limiter.acquire()
        # Wait for window to expire
        await asyncio.sleep(0.15)

        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    async def test_available_property(self):
        """The available property reflects remaining slots."""
        limiter = RateLimiter(max_calls=3, window_seconds=10.0)
        assert limiter.available == 3

        await limiter.acquire()
        assert limiter.available == 2

        await limiter.acquire()
        assert limiter.available == 1

        await limiter.acquire()
        assert limiter.available == 0

    async def test_available_recovers_after_window(self):
        limiter = RateLimiter(max_calls=2, window_seconds=0.1)
        await limiter.acquire()
        await limiter.acquire()
        assert limiter.available == 0

        await asyncio.sleep(0.15)
        assert limiter.available == 2

    async def test_reset_clears_all_timestamps(self):
        """reset() should make all slots available again."""
        limiter = RateLimiter(max_calls=2, window_seconds=10.0)
        await limiter.acquire()
        await limiter.acquire()
        assert limiter.available == 0

        limiter.reset()
        assert limiter.available == 2

    async def test_concurrent_acquires_respect_limit(self):
        """Multiple concurrent acquire() calls still respect the limit."""
        limiter = RateLimiter(max_calls=2, window_seconds=0.3)
        call_times: list[float] = []

        async def acquire_and_record():
            await limiter.acquire()
            call_times.append(time.monotonic())

        # Fire 4 concurrent acquires with limit of 2
        tasks = [asyncio.create_task(acquire_and_record()) for _ in range(4)]
        await asyncio.gather(*tasks)

        # First 2 should be near-instant, last 2 should be delayed
        assert len(call_times) == 4
        # Sort and check gap between 2nd and 3rd
        call_times.sort()
        gap = call_times[2] - call_times[1]
        assert gap >= 0.2  # waited for window


# ---------------------------------------------------------------------------
# ReplyTimeoutGuard
# ---------------------------------------------------------------------------


class TestReplyTimeoutGuard:
    """Tests for reply timeout guard."""

    async def test_fires_callback_at_80_percent(self):
        """Callback fires at 80% of the configured timeout."""
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=0.1, on_timeout=callback)
        guard.start()

        # Wait for it to fire (0.1 * 0.8 = 0.08s)
        await asyncio.sleep(0.15)

        callback.assert_called_once()
        assert guard.fired is True

    async def test_cancel_prevents_firing(self):
        """Cancelling before timeout prevents callback."""
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=0.5, on_timeout=callback)
        guard.start()

        # Cancel quickly before 80% (0.5 * 0.8 = 0.4s)
        await asyncio.sleep(0.01)
        guard.cancel()

        # Wait past when it would have fired
        await asyncio.sleep(0.5)

        callback.assert_not_called()
        assert guard.fired is False

    async def test_fired_property_false_initially(self):
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=1.0, on_timeout=callback)
        assert guard.fired is False

    async def test_zero_timeout_does_not_start(self):
        """A timeout of 0 should not schedule any task."""
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=0.0, on_timeout=callback)
        guard.start()

        await asyncio.sleep(0.05)
        callback.assert_not_called()
        assert guard.fired is False

    async def test_negative_timeout_does_not_start(self):
        """A negative timeout should not schedule any task."""
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=-1.0, on_timeout=callback)
        guard.start()

        await asyncio.sleep(0.05)
        callback.assert_not_called()

    async def test_cancel_is_idempotent(self):
        """Calling cancel multiple times should not raise."""
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=1.0, on_timeout=callback)
        guard.start()
        guard.cancel()
        guard.cancel()  # should not raise
        guard.cancel()

    async def test_cancel_without_start(self):
        """Calling cancel without start should not raise."""
        callback = AsyncMock()
        guard = ReplyTimeoutGuard(timeout=1.0, on_timeout=callback)
        guard.cancel()  # no-op, no error


# ---------------------------------------------------------------------------
# TypingKeepalive
# ---------------------------------------------------------------------------


class TestTypingKeepalive:
    """Tests for periodic typing indicator."""

    async def test_calls_send_typing_periodically(self):
        """send_typing is called multiple times within the interval."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=0.05, send_typing=send_typing)
        keepalive.start()

        # Let it run for enough time to get multiple calls
        await asyncio.sleep(0.18)
        keepalive.stop()

        # First call is immediate (before first sleep), then every 0.05s
        # In 0.18s: call at 0, sleep 0.05, call at 0.05, sleep 0.05,
        #           call at 0.10, sleep 0.05, call at 0.15
        # Expect at least 3 calls
        assert send_typing.call_count >= 3

    async def test_stop_prevents_further_calls(self):
        """After stop(), no further calls to send_typing."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=0.05, send_typing=send_typing)
        keepalive.start()

        # Let one call happen
        await asyncio.sleep(0.02)
        keepalive.stop()

        count_at_stop = send_typing.call_count
        # Wait and verify no more calls
        await asyncio.sleep(0.15)
        assert send_typing.call_count == count_at_stop

    async def test_zero_interval_does_not_start(self):
        """An interval of 0 should not start the loop."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=0.0, send_typing=send_typing)
        keepalive.start()

        await asyncio.sleep(0.05)
        send_typing.assert_not_called()

    async def test_negative_interval_does_not_start(self):
        """A negative interval should not start the loop."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=-1.0, send_typing=send_typing)
        keepalive.start()

        await asyncio.sleep(0.05)
        send_typing.assert_not_called()

    async def test_stop_is_idempotent(self):
        """Calling stop multiple times should not raise."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=0.1, send_typing=send_typing)
        keepalive.start()
        keepalive.stop()
        keepalive.stop()  # should not raise

    async def test_stop_without_start(self):
        """Calling stop without start should not raise."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=0.1, send_typing=send_typing)
        keepalive.stop()  # no-op, no error

    async def test_first_call_is_immediate(self):
        """send_typing is called before the first sleep."""
        send_typing = AsyncMock()
        keepalive = TypingKeepalive(interval=10.0, send_typing=send_typing)
        keepalive.start()

        # Even with 10s interval, first call should be nearly immediate
        await asyncio.sleep(0.05)
        keepalive.stop()

        assert send_typing.call_count == 1

    async def test_exception_in_send_typing_stops_loop(self):
        """If send_typing raises a non-CancelledError, the loop stops."""
        call_count = 0

        async def failing_typing():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("network error")

        keepalive = TypingKeepalive(interval=0.03, send_typing=failing_typing)
        keepalive.start()

        await asyncio.sleep(0.15)
        keepalive.stop()

        # Should have called twice: first succeeds, second raises and stops
        assert call_count == 2
