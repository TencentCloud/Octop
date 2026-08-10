"""In-memory registry of pending HITL approvals for IM channels."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

HitlPendingStatus = Literal["pending", "approved", "rejected", "expired"]

_DEFAULT_TTL_SECONDS = 30 * 60


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
    ) -> HitlPendingRecord:
        self._gc()
        for existing in list(self._records.values()):
            if existing.session_key == session_key and existing.status == "pending":
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
    ) -> HitlPendingRecord | None:
        """Return the newest pending approval for a dashboard thread, if any."""
        self._gc()
        latest: HitlPendingRecord | None = None
        for record in self._records.values():
            if record.thread_id != thread_id or record.status != "pending":
                continue
            if record.agent_id != agent_id:
                continue
            if user_id is not None and record.user_id != user_id:
                continue
            if time.time() - record.created_at > self.ttl_seconds:
                record.status = "expired"
                continue
            if latest is None or record.created_at > latest.created_at:
                latest = record
        return latest

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

    def mark_resolved(self, pending_id: str, status: Literal["approved", "rejected"]) -> None:
        record = self._records.get(pending_id)
        if record is not None:
            record.status = status

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
