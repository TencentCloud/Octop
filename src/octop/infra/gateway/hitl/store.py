"""In-memory registry of pending HITL approvals for IM channels."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

HitlPendingStatus = Literal["pending", "approved", "rejected", "expired"]

_DEFAULT_TTL_SECONDS = 30 * 60


def _same_pause_slot(
    existing: HitlPendingRecord,
    *,
    session_key: str,
    resume_agent_id: str | None,
) -> bool:
    if existing.session_key != session_key or existing.status != "pending":
        return False
    if resume_agent_id:
        return existing.resume_agent_id == resume_agent_id
    return not existing.resume_agent_id


def _actions_equivalent(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(
        right, sort_keys=True, default=str
    )


@dataclass
class HitlPendingRecord:
    pending_id: str
    thread_id: str
    agent_id: str
    user_id: int
    session_key: str
    channel_type: str
    action_requests: list[dict[str, Any]]
    review_configs: list[dict[str, Any]] | None
    created_at: float
    status: HitlPendingStatus = "pending"
    ask_question_index: int = 0
    ask_answers: list[str] = field(default_factory=list)
    # Team member pauses are stored on the room thread the user is viewing.
    # Resume still targets the member agent and ``room~member`` thread.
    resume_agent_id: str | None = None
    resume_thread_id: str | None = None


@dataclass
class HitlPendingStore:
    """Session-scoped pending HITL records (process-local, TTL-gc)."""

    ttl_seconds: float = _DEFAULT_TTL_SECONDS
    _records: dict[str, HitlPendingRecord] = field(default_factory=dict)

    def register(
        self,
        *,
        thread_id: str,
        agent_id: str,
        user_id: int,
        session_key: str,
        channel_type: str,
        action_requests: list[dict[str, Any]],
        review_configs: list[dict[str, Any]] | None,
        resume_agent_id: str | None = None,
    ) -> HitlPendingRecord:
        self._gc()
        # A new pause replaces only the same slot. Two team members share the
        # room session, so one member's card must not expire the other's.
        # The same interrupt is often projected twice; reuse that pending id
        # so an automatic resume of the first frame is not already expired.
        for existing in list(self._records.values()):
            if not _same_pause_slot(
                existing,
                session_key=session_key,
                resume_agent_id=resume_agent_id,
            ):
                continue
            if _actions_equivalent(existing.action_requests, action_requests):
                return existing
        for existing in list(self._records.values()):
            if not _same_pause_slot(
                existing,
                session_key=session_key,
                resume_agent_id=resume_agent_id,
            ):
                continue
            existing.status = "expired"
        pending_id = secrets.token_hex(2)
        while pending_id in self._records:
            pending_id = secrets.token_hex(2)
        record = HitlPendingRecord(
            pending_id=pending_id,
            thread_id=thread_id,
            agent_id=agent_id,
            user_id=user_id,
            session_key=session_key,
            channel_type=channel_type,
            action_requests=list(action_requests),
            review_configs=list(review_configs) if review_configs else None,
            created_at=time.time(),
            resume_agent_id=resume_agent_id,
        )
        self._records[pending_id] = record
        return record

    def get(self, pending_id: str) -> HitlPendingRecord | None:
        self._gc()
        record = self._records.get(pending_id)
        if record is None:
            return None
        if record.status != "pending":
            return record
        if time.time() - record.created_at > self.ttl_seconds:
            record.status = "expired"
            return record
        return record

    def get_pending(
        self,
        pending_id: str,
        *,
        session_key: str,
        agent_id: str,
    ) -> HitlPendingRecord | None:
        record = self.get(pending_id)
        if record is None or record.status != "pending":
            return None
        if record.session_key != session_key or record.agent_id != agent_id:
            return None
        return record

    def resolve_for_session(
        self,
        session_key: str,
        pending_id: str | None = None,
        *,
        agent_id: str | None = None,
    ) -> HitlPendingRecord | None:
        self._gc()
        if pending_id:
            record = self.get(pending_id)
            if record is None or record.session_key != session_key:
                return None
            if agent_id is not None and record.agent_id != agent_id:
                return None
            return record if record.status == "pending" else None
        latest: HitlPendingRecord | None = None
        for record in self._records.values():
            if record.session_key != session_key or record.status != "pending":
                continue
            if agent_id is not None and record.agent_id != agent_id:
                continue
            if time.time() - record.created_at > self.ttl_seconds:
                record.status = "expired"
                continue
            if latest is None or record.created_at > latest.created_at:
                latest = record
        return latest

    def resolve_pending_for_thread(
        self,
        thread_id: str,
        *,
        agent_id: str,
        user_id: int | None = None,
        pending_id: str | None = None,
    ) -> HitlPendingRecord | None:
        """Return a pending approval for a dashboard thread, if any.

        ``pending_id`` selects that card. Without it, the newest pending card
        on the thread is returned.
        """
        self._gc()
        if pending_id:
            record = self._records.get(pending_id)
            if record is None or record.status != "pending":
                return None
            if not self._thread_pending_match(
                record,
                thread_id=thread_id,
                agent_id=agent_id,
                user_id=user_id,
            ):
                return None
            return record
        latest: HitlPendingRecord | None = None
        for record in self._records.values():
            if record.status != "pending":
                continue
            if not self._thread_pending_match(
                record,
                thread_id=thread_id,
                agent_id=agent_id,
                user_id=user_id,
            ):
                continue
            if latest is None or record.created_at > latest.created_at:
                latest = record
        return latest

    def _thread_pending_match(
        self,
        record: HitlPendingRecord,
        *,
        thread_id: str,
        agent_id: str,
        user_id: int | None,
    ) -> bool:
        if record.status != "pending":
            return False
        room_match = record.thread_id == thread_id and record.agent_id == agent_id
        member_match = bool(
            record.resume_thread_id
            and record.resume_thread_id == thread_id
            and record.resume_agent_id == agent_id
        )
        if not room_match and not member_match:
            return False
        if user_id is not None and record.user_id != user_id:
            return False
        if time.time() - record.created_at > self.ttl_seconds:
            record.status = "expired"
            return False
        return True

    def list_pending_for_session(
        self,
        session_key: str,
        *,
        agent_id: str | None = None,
    ) -> list[HitlPendingRecord]:
        self._gc()
        rows = [
            r
            for r in self._records.values()
            if r.session_key == session_key
            and r.status == "pending"
            and (agent_id is None or r.agent_id == agent_id)
        ]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows

    def pending_thread_ids(self, *, agent_id: str, user_id: int) -> frozenset[str]:
        """Thread ids with a still-pending HITL pause for this agent/user."""
        self._gc()
        now = time.time()
        out: set[str] = set()
        for record in self._records.values():
            if record.status != "pending":
                continue
            if record.user_id != user_id:
                continue
            if now - record.created_at > self.ttl_seconds:
                continue
            if record.agent_id == agent_id:
                tid = (record.thread_id or "").strip()
            elif record.resume_agent_id == agent_id:
                tid = (record.resume_thread_id or "").strip()
            else:
                continue
            if tid:
                out.add(tid)
        return frozenset(out)

    def expire_pending_for_thread(
        self,
        thread_id: str,
        *,
        agent_id: str,
        user_id: int | None = None,
    ) -> None:
        """Drop leftover dashboard pauses so history reload cannot reinject them."""
        self._gc()
        for record in self._records.values():
            if record.thread_id != thread_id or record.status != "pending":
                continue
            if record.agent_id != agent_id:
                continue
            if user_id is not None and record.user_id != user_id:
                continue
            record.status = "expired"

    def mark_resolved(
        self,
        pending_id: str,
        status: Literal["approved", "rejected", "expired"],
    ) -> None:
        record = self._records.get(pending_id)
        if record is not None:
            record.status = status

    def append_ask_answer(self, pending_id: str, answer: str) -> HitlPendingRecord | None:
        """Record one IM answer and advance to the next question."""
        record = self.get(pending_id)
        if record is None or record.status != "pending":
            return None
        record.ask_answers.append(answer)
        record.ask_question_index += 1
        return record

    def _gc(self) -> None:
        now = time.time()
        stale_ids: list[str] = []
        for pending_id, record in self._records.items():
            age = now - record.created_at
            if record.status == "pending" and age > self.ttl_seconds:
                record.status = "expired"
            if record.status != "pending" and age > self.ttl_seconds:
                stale_ids.append(pending_id)
        for pending_id in stale_ids:
            del self._records[pending_id]
