"""C2C replace-mode stream session for QQ official ``stream_messages``.

Mirrors the dsh-qqbot-community OutboundPipeline drain: one in-flight frame,
throttled full-text replace, then a DONE frame. Token fragments from Octop
are accumulated by the caller; this module only reconciles prefixes and
serializes HTTP frames.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

StreamState = Literal[1, 10]
STREAM_GENERATING: StreamState = 1
STREAM_DONE: StreamState = 10

_stream_seq = 0
_stream_seq_lock = threading.Lock()


def next_stream_msg_seq() -> int:
    """Process-wide ``msg_seq`` in ``0..65535`` (one value per C2C stream)."""
    global _stream_seq
    with _stream_seq_lock:
        _stream_seq = (_stream_seq + 1) % 65_536
        return _stream_seq


def reset_stream_msg_seq_for_tests() -> None:
    """Reset the process-wide stream seq. Tests only."""
    global _stream_seq
    with _stream_seq_lock:
        _stream_seq = 0


def _collapse_ws(text: str) -> str:
    return " ".join(text.split())


def prefix_matches(accepted: str, incoming: str) -> bool:
    """True when *incoming* continues or equals *accepted* (whitespace-tolerant)."""
    if incoming.startswith(accepted):
        return True
    if not accepted:
        return True
    # A newline-only hold must stay; collapsing it to "" would drop the prefix.
    if not accepted.strip():
        return False
    # Incoming that dropped a leading newline is not a legal replace prefix.
    if accepted[0] in "\r\n" and (not incoming or incoming[0] not in "\r\n"):
        return False
    return _collapse_ws(incoming).startswith(_collapse_ws(accepted))


def _longest_common_prefix(left: str, right: str) -> int:
    index = 0
    limit = min(len(left), len(right))
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def reconcile_stream_text(accepted: str, incoming: str) -> str:
    """Build the next replace-mode full text from the last accepted frame."""
    if not accepted:
        return incoming
    if prefix_matches(accepted, incoming):
        return incoming
    if prefix_matches(incoming, accepted):
        return accepted
    lcp = _longest_common_prefix(accepted, incoming)
    return accepted + incoming[lcp:]


@dataclass(frozen=True)
class StreamFrame:
    """One QQ ``stream_messages`` replace frame."""

    user_id: str
    msg_id: str
    msg_seq: int
    index: int
    text: str
    state: StreamState
    stream_msg_id: str | None = None


SendFrame = Callable[[StreamFrame], Awaitable[str | None]]


class StreamSession:
    """Single-slot drain for one C2C inbound turn."""

    def __init__(
        self,
        *,
        user_id: str,
        msg_id: str,
        msg_seq: int | None = None,
        throttle_ms: int = 150,
        done_retries: int = 3,
        send_frame: SendFrame,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.user_id = user_id
        self.msg_id = msg_id
        self.msg_seq = next_stream_msg_seq() if msg_seq is None else msg_seq
        self.throttle_ms = max(0, throttle_ms)
        self.done_retries = max(1, done_retries)
        self._send_frame = send_frame
        self._sleep = sleep or asyncio.sleep
        self._monotonic = monotonic or time.monotonic
        self.index = 0
        self.last_accepted = ""
        self.pending: str | None = None
        self.in_flight = False
        self.closing = False
        self.stream_msg_id: str | None = None
        self.sent_frames = 0
        self.failed = False
        # A visible frame came back without a stream id, so later frames
        # would be new QQ messages. Stop the replace chain.
        self.unlinked = False
        self.last_sent_at = 0.0
        self._drain_task: asyncio.Task[None] | None = None
        self._inflight_text: str | None = None

    def _prefix_base(self) -> str:
        locked = self.last_accepted
        if self._inflight_text is not None:
            locked = self._inflight_text
        if self.pending is not None:
            return reconcile_stream_text(locked, self.pending)
        return locked

    def offer(self, text: str) -> None:
        """Record the latest candidate full text and kick the drain loop.

        Visible text that is already accepted, in flight, or queued is not
        submitted again. A whitespace hold may still be re-offered so the
        generating indicator stays alive before the first readable frame.
        """
        if self.failed or self.closing:
            return
        merged = reconcile_stream_text(self._prefix_base(), text)
        if self._same_visible(merged):
            return
        self.pending = merged
        self._kick_drain()

    def _same_visible(self, merged: str) -> bool:
        if not merged.strip():
            return False
        if merged == self.pending or merged == self._inflight_text:
            return True
        return merged == self.last_accepted and self.pending is None and self._inflight_text is None

    def discard_unsent(self) -> None:
        """Drop queued text that has not been accepted yet.

        An empty session must not invent a newline frame. Mobile QQ shows
        that frame as a blank bubble.
        """
        if self.failed or self.closing:
            return
        locked = self._inflight_text if self._inflight_text is not None else self.last_accepted
        if not locked.strip():
            self.pending = locked or None
            return
        self.pending = None

    @property
    def dirty(self) -> bool:
        """True when this session has sent or queued text."""
        return self.sent_frames > 0 or self.pending is not None

    def _kick_drain(self) -> None:
        if self.in_flight or self.failed or self.closing:
            return
        if self.pending is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._drain_task = loop.create_task(self.drain(), name="qq-c2c-stream-drain")

    async def drain(self) -> None:
        """Send queued content one replace frame at a time."""
        if self.in_flight or self.failed or self.closing:
            return
        self.in_flight = True
        try:
            while not self.failed and not self.closing and self.pending is not None:
                wait = (self.throttle_ms / 1000.0) - (self._monotonic() - self.last_sent_at)
                if wait > 0:
                    await self._sleep(wait)
                    continue
                text = self.pending
                self._inflight_text = text
                self.pending = None
                await self._emit(text, STREAM_GENERATING)
        finally:
            self.in_flight = False
            if not self.failed and not self.closing and self.pending is not None:
                self._kick_drain()

    async def finish(self, text: str, *, discard_pending: bool = False) -> None:
        """Close the stream. Successful turns flush pending first; abort drops it."""
        if discard_pending:
            self.closing = True
            self.pending = None
        else:
            await self._wait_idle()
            if self.pending is not None and not self.failed:
                self._kick_drain()
                await self._wait_idle()
            self.closing = True
            self.pending = None
        await self._wait_idle()
        if self.sent_frames <= 0 or self.unlinked:
            return
        payload = text if text else self.last_accepted
        for attempt in range(1, self.done_retries + 1):
            if await self._emit(payload, STREAM_DONE):
                return
            if attempt == self.done_retries:
                return
            logger.warning("QQ DONE frame attempt %d failed; retrying", attempt)
            await self._sleep(0.4 * attempt)

    async def _wait_idle(self) -> None:
        task = self._drain_task
        if task is not None and not task.done():
            await task
        while self.in_flight:
            await self._sleep(0.05)

    async def _emit(self, text: str, state: StreamState) -> bool:
        # The hold frame may leave without an id. Do not post visible text
        # after that: QQ would show each frame as a new message.
        if state == STREAM_GENERATING and text.strip() and self.sent_frames > 0 and not self.stream_msg_id:
            self.unlinked = True
            self.failed = True
            return False
        frame = StreamFrame(
            user_id=self.user_id,
            msg_id=self.msg_id,
            msg_seq=self.msg_seq,
            index=self.index,
            text=text,
            state=state,
            stream_msg_id=self.stream_msg_id,
        )
        self._inflight_text = text
        try:
            stream_msg_id = await self._send_frame(frame)
        except Exception:  # pylint: disable=broad-except
            # The frame sender is injected by the channel and owns transport errors.
            self.failed = True
            logger.warning("QQ stream frame failed; falling back to static delivery", exc_info=True)
            return False
        else:
            self.index += 1
            self.last_accepted = text
            self.last_sent_at = self._monotonic()
            self.sent_frames += 1
            if stream_msg_id and not self.stream_msg_id:
                self.stream_msg_id = stream_msg_id
            if state == STREAM_GENERATING and text.strip() and not self.stream_msg_id:
                self.unlinked = True
                self.failed = True
            return True
        finally:
            if self._inflight_text == text:
                self._inflight_text = None
