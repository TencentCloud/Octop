"""Global inbox queue for asynchronous agent-to-agent collaboration.

One :class:`HarnessAgentInboxManager` serves all agents in a shared
:class:`~octop_harness.registry.AgentRegistry`. A dispatcher hands each
message to a task, up to ``max_concurrency`` jobs at once. Calls to the
same callee stay serial; different callees run in parallel. Host
follow-up ``call``s are serialized per source thread:

    registry.get(target).agent.call(message) -> compose_followup ->
    registry.get(source).agent.call(prompt) -> on_reply
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from octop_harness.backends.utils import ASYNC_DEFENSIVE_OP_ERRORS
from octop_harness.messages import extract_call_response, is_model_retry_failure_text
from octop_harness.request import ChatRequest
from octop_harness.teams.processor import ReplyEvent, TeamProcessor
from octop_harness.teams.util import build_one_shot_request, derive_peer_thread_id

logger = logging.getLogger(__name__)

InboxStatus = Literal["queued", "running", "replying", "done", "failed", "cancelled"]
_TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})
DEFAULT_INBOX_MAX_CONCURRENCY = 8


@dataclass
class InboxMessage:
    """A queued cross-agent request and its routing/status info."""

    id: str
    target_agent_id: str
    source_agent_id: str
    source_thread_id: str | None
    message: str
    user_id: str | int
    status: InboxStatus = "queued"
    original_user_prompt: str | None = None
    error_text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PeerResult:
    """Return value of a peer interaction (sync call or async submit)."""

    mode: Literal["sync", "background"]
    agent_id: str
    name: str
    job_id: str | None = None
    thread_id: str | None = None
    status: str | None = None
    response: str | None = None
    message: str | None = None


class HarnessAgentInboxManager:
    """Process-wide inbox: enqueue messages; per-callee tasks fulfil them."""

    def __init__(
        self,
        *,
        call_agent: Callable[[str, ChatRequest], Awaitable[dict[str, Any]]],
        processor: TeamProcessor,
        invoke_target: Callable[[InboxMessage], Awaitable[dict[str, Any]]] | None = None,
        max_concurrency: int = DEFAULT_INBOX_MAX_CONCURRENCY,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be at least 1, got {max_concurrency!r}")
        self._call_agent = call_agent
        self._processor = processor
        self._invoke_target = invoke_target
        self._max_concurrency = max_concurrency
        self._messages: dict[str, InboxMessage] = {}
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._target_locks: dict[str, asyncio.Lock] = {}
        self._source_locks: dict[str, asyncio.Lock] = {}
        self._target_refs: dict[str, int] = {}
        self._source_refs: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public queue API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        *,
        target_agent_id: str,
        source_agent_id: str,
        source_thread_id: str | None,
        message: str,
        user_id: str | int,
        original_user_prompt: str | None = None,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a message to the inbox and return its id (returns immediately)."""
        self.start()
        mid = job_id or uuid.uuid4().hex
        self._messages[mid] = InboxMessage(
            id=mid,
            target_agent_id=target_agent_id,
            source_agent_id=source_agent_id,
            source_thread_id=source_thread_id,
            message=message,
            user_id=user_id,
            original_user_prompt=original_user_prompt,
            metadata=dict(metadata or {}),
        )
        self._queue.put_nowait(mid)
        return mid

    def get(self, inbox_id: str) -> InboxMessage | None:
        return self._messages.get(inbox_id)

    def list(
        self,
        *,
        target: str | None = None,
        source: str | None = None,
        status: InboxStatus | None = None,
    ) -> list[InboxMessage]:
        return [
            m
            for m in self._messages.values()
            if (target is None or m.target_agent_id == target)
            and (source is None or m.source_agent_id == source)
            and (status is None or m.status == status)
        ]

    def cancel(self, inbox_id: str) -> bool:
        msg = self._messages.get(inbox_id)
        if msg is None or msg.status in _TERMINAL_STATUSES:
            return False
        self._set_status(msg, "cancelled")
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._worker_loop(), name="harness-inbox")

    async def shutdown(self) -> None:
        if self._worker is None and not self._tasks:
            return
        if self._worker is not None:
            await self._queue.put(None)
            try:
                await asyncio.wait_for(self._worker, timeout=30.0)
            except TimeoutError:
                self._worker.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._worker = None

    def cancel_worker(self) -> None:
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
        self._worker = None
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _sema(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
        return self._semaphore

    def _lock_for(
        self,
        bucket: dict[str, asyncio.Lock],
        refs: dict[str, int],
        key: str,
    ) -> asyncio.Lock:
        lock = bucket.get(key)
        if lock is None:
            lock = asyncio.Lock()
            bucket[key] = lock
        refs[key] = refs.get(key, 0) + 1
        return lock

    def _release_lock(
        self,
        bucket: dict[str, asyncio.Lock],
        refs: dict[str, int],
        key: str,
        lock: asyncio.Lock,
    ) -> None:
        left = refs.get(key, 1) - 1
        if left <= 0:
            refs.pop(key, None)
            if bucket.get(key) is lock and not lock.locked():
                bucket.pop(key, None)
        else:
            refs[key] = left

    def _source_lock_key(self, msg: InboxMessage) -> str:
        return msg.source_thread_id or msg.source_agent_id

    async def _worker_loop(self) -> None:
        while True:
            mid = await self._queue.get()
            try:
                if mid is None:
                    break
                msg = self._messages.get(mid)
                if msg is None:
                    continue
                task = asyncio.create_task(self._run_job(msg), name=f"harness-inbox-{mid}")
                self._tasks[mid] = task
            except ASYNC_DEFENSIVE_OP_ERRORS:
                logger.exception("inbox dispatch failed id=%s", mid)
            finally:
                self._queue.task_done()

    async def _run_job(self, msg: InboxMessage) -> None:
        async with self._sema():
            try:
                await self._process(msg)
            except ASYNC_DEFENSIVE_OP_ERRORS:
                logger.exception("inbox message failed id=%s", msg.id)
                if msg.status not in _TERMINAL_STATUSES:
                    await self._finish(
                        msg,
                        status="failed",
                        reply_text=None,
                        error_text=msg.error_text or "inbox job failed",
                    )
            finally:
                self._tasks.pop(msg.id, None)

    def _is_cancelled(self, msg: InboxMessage) -> bool:
        return msg.status == "cancelled"

    async def _process(self, msg: InboxMessage) -> None:
        if self._is_cancelled(msg):
            await self._finish(msg, status="cancelled", reply_text=None, error_text=None)
            return
        result_text: str | None = None
        error_text: str | None = None
        status: Literal["done", "failed", "cancelled"] = "done"
        target_lock = self._lock_for(self._target_locks, self._target_refs, msg.target_agent_id)
        try:
            async with target_lock:
                if self._is_cancelled(msg):
                    await self._finish(msg, status="cancelled", reply_text=None, error_text=None)
                    return
                self._set_status(msg, "running")
                try:
                    if self._invoke_target is not None:
                        result = await self._invoke_target(msg)
                    else:
                        sk_raw = msg.metadata.get("session_key")
                        session_key = sk_raw if isinstance(sk_raw, str) and sk_raw.strip() else None
                        target_req = build_one_shot_request(
                            user_id=msg.user_id,
                            agent_id=msg.target_agent_id,
                            text=msg.message,
                            source="inbox",
                            thread_id=(
                                derive_peer_thread_id(msg.source_thread_id, msg.target_agent_id)
                                if msg.source_thread_id
                                else None
                            ),
                            session_key=session_key,
                        )
                        result = await self._call_agent(msg.target_agent_id, target_req)
                    result_text = extract_call_response(result) if isinstance(result, dict) else ""
                    if is_model_retry_failure_text(result_text):
                        status = "failed"
                        error_text = result_text
                        result_text = None
                except (Exception, asyncio.CancelledError) as exc:
                    # Provider SDK errors do not share the backend I/O error base.
                    error_text = f"{type(exc).__name__}: {exc}"
                    status = "failed"
        finally:
            self._release_lock(self._target_locks, self._target_refs, msg.target_agent_id, target_lock)

        if self._is_cancelled(msg):
            await self._finish(msg, status="cancelled", reply_text=None, error_text=error_text)
            return

        source_key = self._source_lock_key(msg)
        source_lock = self._lock_for(self._source_locks, self._source_refs, source_key)
        try:
            async with source_lock:
                if self._is_cancelled(msg):
                    await self._finish(msg, status="cancelled", reply_text=None, error_text=error_text)
                    return
                self._set_status(msg, "replying")
                reply_text = await self._synthesize_reply(msg, result_text, error_text)
                if self._is_cancelled(msg):
                    await self._finish(msg, status="cancelled", reply_text=reply_text, error_text=error_text)
                    return
                if reply_text is None and status == "done":
                    status = "failed"
                    error_text = error_text or msg.error_text or "source agent reply failed"
                await self._finish(msg, status=status, reply_text=reply_text, error_text=error_text)
        finally:
            self._release_lock(self._source_locks, self._source_refs, source_key, source_lock)

    async def _finish(
        self,
        msg: InboxMessage,
        *,
        status: Literal["done", "failed", "cancelled"],
        reply_text: str | None,
        error_text: str | None,
    ) -> None:
        if msg.status in _TERMINAL_STATUSES and msg.id not in self._messages:
            return
        msg.error_text = error_text
        self._set_status(msg, status)
        try:
            await self._processor.on_reply(
                ReplyEvent(
                    inbox_id=msg.id,
                    status=status,
                    source_agent_id=msg.source_agent_id,
                    source_thread_id=msg.source_thread_id,
                    target_agent_id=msg.target_agent_id,
                    user_id=msg.user_id,
                    reply_text=reply_text,
                    error_text=error_text,
                    metadata=msg.metadata,
                )
            )
        except ASYNC_DEFENSIVE_OP_ERRORS:
            logger.exception("inbox on_reply failed id=%s", msg.id)
        self._prune_terminal(msg.id)

    async def _synthesize_reply(
        self,
        msg: InboxMessage,
        result_text: str | None,
        error_text: str | None,
    ) -> str | None:
        if self._is_cancelled(msg):
            return None
        prompt = self._processor.compose_followup(msg, result_text=result_text, error_text=error_text)
        try:
            sk_raw = msg.metadata.get("session_key") if msg.metadata else None
            session_key = sk_raw if isinstance(sk_raw, str) and sk_raw.strip() else None
            source_req = build_one_shot_request(
                user_id=msg.user_id,
                agent_id=msg.source_agent_id,
                text=prompt,
                source="inbox",
                thread_id=msg.source_thread_id,
                session_key=session_key,
                configurable={"octop_memory_capture_exclude": True} if error_text else None,
            )
            reply = await self._call_agent(msg.source_agent_id, source_req)
            return extract_call_response(reply) if isinstance(reply, dict) else ""
        except (Exception, asyncio.CancelledError) as exc:
            msg.error_text = f"{type(exc).__name__}: {exc}"
            logger.exception("inbox source reply failed id=%s", msg.id)
            return None

    def _set_status(self, msg: InboxMessage, status: InboxStatus) -> None:
        msg.status = status
        msg.updated_at = datetime.now(tz=UTC)

    def _prune_terminal(self, inbox_id: str) -> None:
        msg = self._messages.get(inbox_id)
        if msg is not None and msg.status in _TERMINAL_STATUSES:
            self._messages.pop(inbox_id, None)


__all__ = [
    "DEFAULT_INBOX_MAX_CONCURRENCY",
    "HarnessAgentInboxManager",
    "InboxMessage",
    "InboxStatus",
    "PeerResult",
]
