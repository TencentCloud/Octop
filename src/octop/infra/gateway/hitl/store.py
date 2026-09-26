"""In-memory registry of pending HITL approvals for IM channels."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from octop.infra.db.repos.hitl_pending import HitlPendingRepo

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
    ask_question_index: int = 0
    ask_answers: list[str] = field(default_factory=list)


@dataclass
class HitlPendingStore:
    """Session-scoped pending HITL records (in-memory hot cache, TTL-gc).

    With a repo bound (server boot), every state transition is written through
    so a restart can hydrate the still-pending records from SQL.
    """

    ttl_seconds: float = _DEFAULT_TTL_SECONDS
    _records: dict[str, HitlPendingRecord] = field(default_factory=dict)
    _repo: HitlPendingRepo | None = field(default=None, repr=False, compare=False)

    def replace_repo(self, repo: HitlPendingRepo | None) -> None:
        """Bind the durability layer (server boot). In-memory records are kept."""
        self._repo = repo

    def hydrate_from_repo(self) -> None:
        """Load records persisted by a previous process into the hot cache.

        Rows older than the TTL hydrate as ``expired`` so a restart can never
        resurrect an actionable card; in-memory records always win.
        """
        repo = self._repo
        if repo is None:
            return
        now = time.time()
        for row in repo.list_pending():
            if row.pending_id in self._records:
                continue
            status: HitlPendingStatus = (
                "expired" if now - row.created_at > self.ttl_seconds else "pending"
            )
            self._records[row.pending_id] = HitlPendingRecord(
                pending_id=row.pending_id,
                thread_id=row.thread_id,
                agent_id=row.agent_id,
                user_id=row.user_id,
                session_key=row.session_key,
                channel_type=row.channel_type,
                action_requests=row.action_requests,
                review_configs=row.review_configs,
                created_at=row.created_at,
                status=status,
                ask_question_index=row.ask_question_index,
                ask_answers=row.ask_answers,
            )

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
                self._persist(existing)
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
        self._persist(record)
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
            self._persist(record)
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
                self._persist(record)
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
                self._persist(record)
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
            self._persist(record)

    def mark_resolved(
        self,
        pending_id: str,
        status: Literal["approved", "rejected", "expired"],
    ) -> None:
        record = self._records.get(pending_id)
        if record is not None:
            record.status = status
            self._persist(record)

    def append_ask_answer(self, pending_id: str, answer: str) -> HitlPendingRecord | None:
        """Record one IM answer and advance to the next question."""
        record = self.get(pending_id)
        if record is None or record.status != "pending":
            return None
        record.ask_answers.append(answer)
        record.ask_question_index += 1
        self._persist(record)
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
            self._forget(pending_id)

    def _persist(self, record: HitlPendingRecord) -> None:
        repo = self._repo
        if repo is None:
            return
        repo.upsert(
            pending_id=record.pending_id,
            thread_id=record.thread_id,
            agent_id=record.agent_id,
            user_id=record.user_id,
            session_key=record.session_key,
            channel_type=record.channel_type,
            action_requests=record.action_requests,
            review_configs=record.review_configs,
            created_at=record.created_at,
            status=record.status,
            ask_question_index=record.ask_question_index,
            ask_answers=record.ask_answers,
        )

    def _forget(self, pending_id: str) -> None:
        if self._repo is not None:
            self._repo.delete(pending_id)
