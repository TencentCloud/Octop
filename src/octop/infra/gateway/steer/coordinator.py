"""In-process mid-turn steer queues (Dashboard v1; sticky single process).

Authoritative admission lives here until octop-harness exposes a native
between-model drain seam. Drain currently happens at Octop turn boundaries
(after each harness ``stream`` invocation completes) via continuation loops.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from octop.infra.gateway.process.message_keys import COMPOSER_CTX_KEY
from octop.infra.gateway.steer.types import (
    GATEWAY_REJECT_REASONS,
    HITL_PARK_TTL_SECONDS,
    STEER_CONTINUATION_CAP,
    STEER_DEPTH_CAP,
    STEER_TEXT_CAP_BYTES,
    STEERABLE_PHASES,
    AdmitResult,
    Delivery,
    DiscardReason,
    PendingSteer,
    SteerAdmitOk,
    SteerAdmitReject,
    TurnPhase,
    TurnSteerState,
    coalesce_texts,
    preview_text,
    queue_sum_bytes,
    utf8_len,
)
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)

# Copied onto a steer continuation so a parked resume keeps the turn's composer.
_CONTINUATION_META_KEYS = frozenset(
    {
        "session_key",
        "thread_id",
        "user_is_admin",
        "mcp_servers",
        "knowledge_base_ids",
        "skills",
        "model",
        "reasoning_mode",
        "reasoning_effort",
        "conversation_mode",
        "hitl_policy",
        "target_agent_ids",
        COMPOSER_CTX_KEY,
    }
)


@dataclass(frozen=True)
class DrainBundle:
    turn_id: str
    text: str
    client_pending_ids: list[str]
    pending_ids: list[str]
    message_id: str
    content_blocks: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class DiscardBundle:
    turn_id: str
    client_pending_ids: list[str]
    pending_ids: list[str]
    reason: DiscardReason
    seq: int


@dataclass(frozen=True)
class RemoveResult:
    status: str  # removed | already_drained | already_gone
    turn_id: str
    client_pending_id: str
    pending_id: str
    seq: int | None = None
    emit_removed: bool = False
    already_drained: bool = False
    already_gone: bool = False


class SteerCoordinator:
    """Per-thread steer state under one lock."""

    def __init__(self, *, text_cap_bytes: int = STEER_TEXT_CAP_BYTES) -> None:
        self._lock = threading.RLock()
        self._by_thread: dict[str, TurnSteerState] = {}
        self._text_cap = text_cap_bytes
        self._staged_hitl: dict[str, tuple[DrainBundle, int]] = {}

    def begin_turn(
        self, thread_id: str, *, phase: TurnPhase = "streaming_text"
    ) -> tuple[str, int, DiscardBundle | None]:
        """Start a steerable turn.

        Returns ``(turn_id, seq, discarded)``. ``discarded`` is set when a
        previous queue was still parked (expired HITL, or a missed end).
        """
        tid = thread_id.strip()
        with self._lock:
            previous = self._by_thread.pop(tid, None)
            self._staged_hitl.pop(tid, None)
            discarded = None
            if previous is not None and previous.queue:
                reason: DiscardReason = (
                    "park_expired" if self._park_expired(previous) else "turn_cancelled"
                )
                logger.warning(
                    "steer begin_turn drops queued state thread=%s old_turn=%s queued=%d reason=%s",
                    tid,
                    previous.turn_id,
                    len(previous.queue),
                    reason,
                )
                discarded = self._discard_locked(previous, reason=reason)
            turn_id = new_ulid()
            state = TurnSteerState(turn_id=turn_id, phase=phase)
            state.last_allocated_seq = 1
            self._by_thread[tid] = state
            return turn_id, state.last_allocated_seq, discarded

    def set_phase(self, thread_id: str, phase: TurnPhase) -> None:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None:
                return
            state.phase = phase

    def get_state(self, thread_id: str) -> TurnSteerState | None:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None:
                return None
            # shallow copy for snapshot callers
            return TurnSteerState(
                turn_id=state.turn_id,
                phase=state.phase,
                queue=list(state.queue),
                continuation_count=state.continuation_count,
                last_allocated_seq=state.last_allocated_seq,
                parked_at=state.parked_at,
                drained_message_ids=dict(state.drained_message_ids),
                continuation_meta=dict(state.continuation_meta),
            )

    def is_active(self, thread_id: str) -> bool:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            return (
                state is not None
                and state.phase not in ("idle", "terminal")
                and not self._park_expired(state)
            )

    def has_pending(self, thread_id: str) -> bool:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            return state is not None and bool(state.queue)

    def is_hitl_paused(self, thread_id: str) -> bool:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            return (
                state is not None and state.phase == "hitl_paused" and not self._park_expired(state)
            )

    def remember_context(self, thread_id: str, metadata: dict[str, Any] | None) -> None:
        """Keep composer fields so a later continuation can rebuild the inbound."""
        if not metadata:
            return
        kept: dict[str, Any] = {}
        for key in _CONTINUATION_META_KEYS:
            if key not in metadata:
                continue
            value = metadata[key]
            if isinstance(value, list):
                kept[key] = list(value)
            elif isinstance(value, dict):
                kept[key] = dict(value)
            else:
                kept[key] = value
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is not None:
                state.continuation_meta = kept

    def continuation_metadata(self, thread_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None:
                return {}
            return dict(state.continuation_meta)

    def sweep_expired(self, thread_id: str) -> DiscardBundle | None:
        """Drop an HITL park that outlived the approval window."""
        tid = thread_id.strip()
        with self._lock:
            state = self._by_thread.get(tid)
            if state is None or not self._park_expired(state):
                return None
            self._staged_hitl.pop(tid, None)
            bundle = None
            if state.queue:
                bundle = self._discard_locked(state, reason="park_expired")
            self._by_thread.pop(tid, None)
            return bundle

    @staticmethod
    def _park_expired(state: TurnSteerState) -> bool:
        """True when an HITL park outlived the approval window (TTL)."""
        return (
            state.phase == "hitl_paused"
            and state.parked_at is not None
            and (time.time() - state.parked_at) > HITL_PARK_TTL_SECONDS
        )

    def allocate_seq(self, thread_id: str) -> int:
        with self._lock:
            state = self._require(thread_id)
            state.last_allocated_seq += 1
            return state.last_allocated_seq

    def snapshot_frames(self, thread_id: str) -> list[dict[str, Any]]:
        """Connection-local baseline frames (no seq allocation)."""
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None or state.phase in ("idle", "terminal"):
                return [
                    {
                        "type": "steer.queue_snapshot",
                        "seq": 0,
                        "turn_id": None,
                        "queue_length": 0,
                        "continuation_count": 0,
                        "items": [],
                    }
                ]
            seq = state.last_allocated_seq
            return [
                {
                    "type": "steer.queue_snapshot",
                    "seq": seq,
                    "turn_id": state.turn_id,
                    "queue_length": len(state.queue),
                    "continuation_count": state.continuation_count,
                    "items": [
                        {
                            "client_pending_id": item.client_pending_id,
                            "pending_id": item.pending_id,
                            "preview": item.preview,
                        }
                        for item in state.queue
                    ],
                },
                {
                    "type": "turn.resumed",
                    "turn_id": state.turn_id,
                    "seq": seq,
                    "phase": state.phase,
                },
            ]

    def admit(
        self,
        thread_id: str,
        *,
        text: str,
        client_pending_id: str | None,
        expected_turn_id: str | None,
        delivery: Delivery = "auto",
        hitl_paused: bool = False,
        content_blocks: list[dict[str, Any]] | None = None,
    ) -> AdmitResult | None:
        """Return None when the caller should start a normal new turn (idle)."""
        cleaned = (text or "").strip()
        blocks = _normalize_blocks(content_blocks)
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            active = (
                state is not None
                and state.phase not in ("idle", "terminal")
                and not self._park_expired(state)
            )

            if delivery == "follow_up" and active:
                return SteerAdmitReject(
                    reason="turn_active",
                    client_pending_id=client_pending_id,
                    turn_id=state.turn_id if state else None,
                    seq=self._alloc(state) if state else None,
                    gateway_class=False,
                )

            if not active:
                if delivery == "steer":
                    return SteerAdmitReject(
                        reason="no_active_turn",
                        client_pending_id=client_pending_id,
                        gateway_class=False,
                    )
                # idle auto / follow_up → caller starts a normal new turn
                return None

            assert state is not None

            # Busy auto / steer path. Mint a pending id when the client omitted
            # one so a busy user_turn still steers instead of hard-failing the
            # live stream (Dashboard race: intermediate harness ``done``).
            if not client_pending_id or not str(client_pending_id).strip():
                cpid = new_ulid()
            else:
                cpid = str(client_pending_id).strip()

            if not cleaned and not blocks:
                return SteerAdmitReject(
                    reason="empty_input",
                    client_pending_id=cpid,
                    gateway_class=True,
                )

            incoming_bytes = utf8_len(cleaned) + _blocks_bytes(blocks)
            queued_bytes = queue_sum_bytes(state.queue, extra=cleaned or None)
            queued_bytes += sum(_blocks_bytes(item.content_blocks) for item in state.queue)
            queued_bytes += _blocks_bytes(blocks)
            if incoming_bytes > self._text_cap or queued_bytes > self._text_cap:
                return SteerAdmitReject(
                    reason="input_too_large",
                    client_pending_id=cpid,
                    gateway_class=True,
                )

            if state.phase == "cancelling":
                return SteerAdmitReject(
                    reason="turn_already_cancelled",
                    client_pending_id=cpid,
                    turn_id=state.turn_id,
                    seq=self._alloc(state),
                )

            if hitl_paused or state.phase == "hitl_paused":
                return SteerAdmitReject(
                    reason="hitl_paused",
                    client_pending_id=cpid,
                    turn_id=state.turn_id,
                    seq=self._alloc(state),
                )

            if expected_turn_id is None or not str(expected_turn_id).strip():
                # ``delivery=auto`` busy path (e.g. local follow-up flush that
                # raced an intermediate harness done): bind to the live turn.
                if delivery != "auto":
                    return SteerAdmitReject(
                        reason="expected_turn_id_required",
                        client_pending_id=cpid,
                        turn_id=state.turn_id,
                        seq=self._alloc(state),
                    )
            elif str(expected_turn_id).strip() != state.turn_id:
                return SteerAdmitReject(
                    reason="expected_turn_id_mismatch",
                    client_pending_id=cpid,
                    turn_id=state.turn_id,
                    seq=self._alloc(state),
                )

            if state.phase not in STEERABLE_PHASES:
                return SteerAdmitReject(
                    reason="turn_not_steerable",
                    client_pending_id=cpid,
                    turn_id=state.turn_id,
                    seq=self._alloc(state),
                )

            # Idempotent while known
            if cpid in state.known:
                pending_id = state.known[cpid]
                msg_id = state.drained_message_ids.get(cpid)
                return SteerAdmitOk(
                    status="idempotent",
                    turn_id=state.turn_id,
                    pending_id=pending_id,
                    client_pending_id=cpid,
                    queue_length=len(state.queue),
                    message_id=msg_id,
                    emit_queued=False,
                )

            if len(state.queue) >= STEER_DEPTH_CAP:
                return SteerAdmitReject(
                    reason="queue_full",
                    client_pending_id=cpid,
                    turn_id=state.turn_id,
                    seq=self._alloc(state),
                )

            pending_id = new_ulid()
            item = PendingSteer(
                client_pending_id=cpid,
                pending_id=pending_id,
                text=cleaned,
                preview=preview_text(cleaned) or _block_preview(blocks),
                content_blocks=blocks,
            )
            state.queue.append(item)
            state.known[cpid] = pending_id
            seq = self._alloc(state)
            return SteerAdmitOk(
                status="queued",
                turn_id=state.turn_id,
                pending_id=pending_id,
                client_pending_id=cpid,
                queue_length=len(state.queue),
                seq=seq,
                emit_queued=True,
            )

    def remove(
        self,
        thread_id: str,
        *,
        turn_id: str,
        client_pending_id: str,
        pending_id: str,
    ) -> RemoveResult:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            cpid = (client_pending_id or "").strip()
            pid = (pending_id or "").strip()
            if not cpid or not pid:
                return RemoveResult(
                    status="already_gone",
                    turn_id=turn_id,
                    client_pending_id=cpid,
                    pending_id=pid,
                    already_gone=True,
                )
            if state is None or state.turn_id != turn_id.strip():
                return RemoveResult(
                    status="already_gone",
                    turn_id=turn_id,
                    client_pending_id=cpid,
                    pending_id=pid,
                    already_gone=True,
                )
            known_pid = state.known.get(cpid)
            if known_pid is not None and known_pid != pid:
                return RemoveResult(
                    status="already_gone",
                    turn_id=state.turn_id,
                    client_pending_id=cpid,
                    pending_id=pid,
                    already_gone=True,
                )
            if cpid in state.drained_message_ids:
                seq = self._alloc(state)
                return RemoveResult(
                    status="already_drained",
                    turn_id=state.turn_id,
                    client_pending_id=cpid,
                    pending_id=pid,
                    seq=seq,
                    emit_removed=True,
                    already_drained=True,
                )
            for i, item in enumerate(state.queue):
                if item.client_pending_id == cpid and item.pending_id == pid:
                    state.queue.pop(i)
                    state.known.pop(cpid, None)
                    seq = self._alloc(state)
                    return RemoveResult(
                        status="removed",
                        turn_id=state.turn_id,
                        client_pending_id=cpid,
                        pending_id=pid,
                        seq=seq,
                        emit_removed=True,
                    )
            return RemoveResult(
                status="already_gone",
                turn_id=state.turn_id,
                client_pending_id=cpid,
                pending_id=pid,
                already_gone=True,
            )

    def drain_for_continuation(self, thread_id: str) -> DrainBundle | DiscardBundle | None:
        """After a harness stream would stop: drain+continue, discard, or idle."""
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None or not state.queue:
                return None
            if state.continuation_count >= STEER_CONTINUATION_CAP:
                return self._discard_locked(state, reason="continuation_exhausted")
            items = list(state.queue)
            state.queue.clear()
            message_id = new_ulid()
            for item in items:
                state.drained_message_ids[item.client_pending_id] = message_id
                state.known[item.client_pending_id] = item.pending_id
            state.continuation_count += 1
            state.phase = "between_model_steps"
            text = coalesce_texts([item.text for item in items])
            blocks = tuple(block for item in items for block in item.content_blocks)
            return DrainBundle(
                turn_id=state.turn_id,
                text=text,
                client_pending_ids=[item.client_pending_id for item in items],
                pending_ids=[item.pending_id for item in items],
                message_id=message_id,
                content_blocks=blocks,
            )

    def drained_event_seq(self, thread_id: str) -> int:
        """Allocate the seq for the ``steer.drained`` frame of a fresh drain."""
        with self._lock:
            return self._alloc(self._require(thread_id))

    def discard(
        self,
        thread_id: str,
        *,
        reason: DiscardReason,
    ) -> DiscardBundle | None:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None or not state.queue:
                if state is not None:
                    state.phase = "terminal" if reason != "continuation_exhausted" else "idle"
                return None
            return self._discard_locked(state, reason=reason)

    def end_turn(self, thread_id: str, *, failed: bool = False) -> DiscardBundle | None:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is None:
                return None
            if state.phase == "hitl_paused" and not failed and not self._park_expired(state):
                # An HITL interrupt parks the queue — it drains
                # at the first boundary after the approval resumes (SSE resume
                # route calls take_hitl_pending). The WS turn ends, the state
                # stays so admission keeps rejecting with hitl_paused.
                state.parked_at = state.parked_at or time.time()
                return None
            bundle = None
            if state.queue:
                reason: DiscardReason = "turn_failed" if failed else "turn_cancelled"
                # Natural idle end with empty continuation path — if queue left
                # without drain_for_continuation, treat as cancelled strand guard.
                bundle = self._discard_locked(state, reason=reason)
            state.phase = "idle"
            # Keep last_allocated_seq / forget turn after idle
            self._by_thread.pop(thread_id.strip(), None)
            return bundle

    def stage_hitl_pending(self, thread_id: str) -> tuple[DrainBundle, int] | None:
        """Describe parked steers without removing them.

        Call :meth:`commit_staged_hitl` after the continuation is enqueued,
        or :meth:`release_staged_hitl` if enqueue fails.
        """
        tid = thread_id.strip()
        with self._lock:
            staged = self._staged_hitl.get(tid)
            if staged is not None:
                return staged
            state = self._by_thread.get(tid)
            if state is None or state.phase != "hitl_paused" or self._park_expired(state):
                return None
            if not state.queue:
                self._by_thread.pop(tid, None)
                return None
            items = list(state.queue)
            message_id = new_ulid()
            seq = self._alloc(state)
            bundle = DrainBundle(
                turn_id=state.turn_id,
                text=coalesce_texts([item.text for item in items]),
                client_pending_ids=[item.client_pending_id for item in items],
                pending_ids=[item.pending_id for item in items],
                message_id=message_id,
                content_blocks=tuple(block for item in items for block in item.content_blocks),
            )
            staged = (bundle, seq)
            self._staged_hitl[tid] = staged
            return staged

    def commit_staged_hitl(self, thread_id: str) -> None:
        """Drop the staged queue after the continuation was accepted."""
        tid = thread_id.strip()
        with self._lock:
            staged = self._staged_hitl.pop(tid, None)
            state = self._by_thread.get(tid)
            if staged is None or state is None:
                return
            bundle, _seq = staged
            pending_ids = set(bundle.pending_ids)
            drained = [item for item in state.queue if item.pending_id in pending_ids]
            state.queue = [item for item in state.queue if item.pending_id not in pending_ids]
            for item in drained:
                state.drained_message_ids[item.client_pending_id] = bundle.message_id
                state.known[item.client_pending_id] = item.pending_id
            self._by_thread.pop(tid, None)

    def release_staged_hitl(self, thread_id: str) -> None:
        """Forget a staged drain and leave the parked queue in place."""
        with self._lock:
            self._staged_hitl.pop(thread_id.strip(), None)

    def take_hitl_pending(self, thread_id: str) -> tuple[DrainBundle, int] | None:
        """Claim steers parked across an HITL pause; returns (bundle, seq)."""
        staged = self.stage_hitl_pending(thread_id)
        if staged is None:
            return None
        self.commit_staged_hitl(thread_id)
        return staged

    def mark_cancelling(self, thread_id: str) -> None:
        with self._lock:
            state = self._by_thread.get(thread_id.strip())
            if state is not None:
                state.phase = "cancelling"

    def _discard_locked(self, state: TurnSteerState, *, reason: DiscardReason) -> DiscardBundle:
        items = list(state.queue)
        state.queue.clear()
        for item in items:
            state.known.pop(item.client_pending_id, None)
        seq = self._alloc(state)
        if reason == "continuation_exhausted":
            state.phase = "idle"
        return DiscardBundle(
            turn_id=state.turn_id,
            client_pending_ids=[item.client_pending_id for item in items],
            pending_ids=[item.pending_id for item in items],
            reason=reason,
            seq=seq,
        )

    def _require(self, thread_id: str) -> TurnSteerState:
        state = self._by_thread.get(thread_id.strip())
        if state is None:
            raise KeyError(f"no steer state for thread {thread_id!r}")
        return state

    @staticmethod
    def _alloc(state: TurnSteerState) -> int:
        state.last_allocated_seq += 1
        return state.last_allocated_seq

    @staticmethod
    def is_gateway_reason(reason: str) -> bool:
        return reason in GATEWAY_REJECT_REASONS


def _normalize_blocks(blocks: list[dict[str, Any]] | None) -> tuple[dict[str, Any], ...]:
    if not blocks:
        return ()
    kept: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        path = str(block.get("workspace_path") or "").strip()
        if not path:
            continue
        kind = str(block.get("type") or "file")
        if kind not in ("image", "file"):
            continue
        kept.append(
            {
                "type": kind,
                "workspace_path": path,
                "filename": str(block.get("filename") or "").strip(),
                "media_type": str(block.get("media_type") or "").strip(),
            }
        )
    return tuple(kept)


def _blocks_bytes(blocks: tuple[dict[str, Any], ...]) -> int:
    if not blocks:
        return 0
    return len(json.dumps(list(blocks), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _block_preview(blocks: tuple[dict[str, Any], ...]) -> str:
    if not blocks:
        return ""
    name = str(blocks[0].get("filename") or blocks[0].get("workspace_path") or "").strip()
    if len(blocks) == 1:
        return name
    return f"{name} +{len(blocks) - 1}"
