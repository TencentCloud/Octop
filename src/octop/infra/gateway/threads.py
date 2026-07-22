"""ThreadRegistry — session_key → thread_id binding backed by sessions + threads tables."""

from __future__ import annotations

import asyncio
from typing import Any

from octop.infra.db.repos.sessions import SessionRepo, SessionRow
from octop.infra.db.repos.threads import ThreadRepo, ThreadRow
from octop.infra.utils.ulid import new_ulid


class ThreadRegistry:
    """Maps session_key → active thread_id; threads table holds history metadata."""

    CHANNEL_DASHBOARD = "dashboard"
    CHANNEL_CLI = "cli"
    CHAT_TYPE_DM = "dm"
    CHAT_TYPE_GROUP = "group"

    @staticmethod
    def make_key(
        *,
        agent_id: str,
        channel_type: str,
        channel_subject_id: str,
        channel_chat_type: str = CHAT_TYPE_DM,
    ) -> str:
        """Globally unique session key: agent:channel:subject:chat_type."""
        return f"{agent_id}:{channel_type}:{channel_subject_id}:{channel_chat_type}"

    @staticmethod
    def dashboard_key(*, agent_id: str, user_id: int) -> str:
        return ThreadRegistry.make_key(
            agent_id=agent_id,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            channel_subject_id=str(user_id),
            channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
        )

    @staticmethod
    def cli_key(*, agent_id: str, user_id: int) -> str:
        return ThreadRegistry.make_key(
            agent_id=agent_id,
            channel_type=ThreadRegistry.CHANNEL_CLI,
            channel_subject_id=str(user_id),
            channel_chat_type=ThreadRegistry.CHAT_TYPE_DM,
        )

    def __init__(self, *, session_repo: SessionRepo, thread_repo: ThreadRepo) -> None:
        self._sessions = session_repo
        self._threads = thread_repo
        self._lock = asyncio.Lock()

    def replace_repos(self, *, session_repo: SessionRepo, thread_repo: ThreadRepo) -> None:
        """Point at repos from a rebound control-plane pool."""
        self._sessions = session_repo
        self._threads = thread_repo

    async def get_or_create(
        self,
        *,
        agent_id: str,
        user_id: int,
        channel_type: str,
        channel_subject_id: str,
        channel_chat_type: str = "dm",
        channel_metadata: dict[str, Any] | None = None,
        channel_id: str | None = None,
    ) -> str:
        session_key = self.make_key(
            agent_id=agent_id,
            channel_type=channel_type,
            channel_subject_id=channel_subject_id,
            channel_chat_type=channel_chat_type,
        )
        row = self._sessions.get(session_key)
        if row is not None:
            merged_meta = dict(row.channel_metadata or {})
            if channel_metadata:
                merged_meta.update(channel_metadata)
            needs_upsert = (channel_id and not row.channel_id) or (
                channel_metadata and merged_meta != (row.channel_metadata or {})
            )
            if needs_upsert:
                self._sessions.upsert(
                    session_key=session_key,
                    agent_id=row.agent_id,
                    user_id=row.user_id,
                    channel_type=row.channel_type,
                    chat_type=row.chat_type,
                    thread_id=row.thread_id,
                    channel_subject_id=row.channel_subject_id,
                    channel_chat_type=row.channel_chat_type,
                    channel_metadata=merged_meta,
                    channel_id=channel_id or row.channel_id,
                )
            return row.thread_id
        async with self._lock:
            row = self._sessions.get(session_key)
            if row is not None:
                merged_meta = dict(row.channel_metadata or {})
                if channel_metadata:
                    merged_meta.update(channel_metadata)
                needs_upsert = (channel_id and not row.channel_id) or (
                    channel_metadata and merged_meta != (row.channel_metadata or {})
                )
                if needs_upsert:
                    self._sessions.upsert(
                        session_key=session_key,
                        agent_id=row.agent_id,
                        user_id=row.user_id,
                        channel_type=row.channel_type,
                        chat_type=row.chat_type,
                        thread_id=row.thread_id,
                        channel_subject_id=row.channel_subject_id,
                        channel_chat_type=row.channel_chat_type,
                        channel_metadata=merged_meta,
                        channel_id=channel_id or row.channel_id,
                    )
                return row.thread_id
            tid = _new_thread_id()
            meta = dict(channel_metadata or {})
            meta.setdefault("channel_type", channel_type)
            meta.setdefault("user_id", user_id)
            self._threads.insert(
                thread_id=tid,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                session_key=session_key,
                last_active=0,
            )
            self._sessions.upsert(
                session_key=session_key,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                chat_type=channel_chat_type,
                thread_id=tid,
                channel_subject_id=channel_subject_id,
                channel_chat_type=channel_chat_type,
                channel_metadata=meta,
                channel_id=channel_id,
            )
            return tid

    async def get_or_create_by_key(
        self,
        *,
        session_key: str,
        agent_id: str,
        user_id: int,
        channel_type: str,
        channel_chat_type: str = "dm",
        channel_metadata: dict[str, Any] | None = None,
        channel_channel_id: str | None = None,
    ) -> str:
        row = self._sessions.get(session_key)
        if row is not None:
            if row.agent_id != agent_id:
                msg = f"session {session_key!r} belongs to agent {row.agent_id!r}, not {agent_id!r}"
                raise ValueError(msg)
            merged_meta = dict(row.channel_metadata or {})
            if channel_metadata:
                merged_meta.update(channel_metadata)
            needs_upsert = (channel_channel_id and not row.channel_id) or (
                channel_metadata and merged_meta != (row.channel_metadata or {})
            )
            if needs_upsert:
                self._sessions.upsert(
                    session_key=session_key,
                    agent_id=row.agent_id,
                    user_id=row.user_id,
                    channel_type=row.channel_type,
                    chat_type=row.chat_type,
                    thread_id=row.thread_id,
                    channel_subject_id=row.channel_subject_id,
                    channel_chat_type=row.channel_chat_type,
                    channel_metadata=merged_meta,
                    channel_id=channel_channel_id or row.channel_id,
                )
            return row.thread_id
        parts = session_key.split(":", 3)
        subject_id = parts[2] if len(parts) >= 3 else str(user_id)
        return await self.get_or_create(
            agent_id=agent_id,
            user_id=user_id,
            channel_type=channel_type,
            channel_subject_id=subject_id,
            channel_chat_type=channel_chat_type if len(parts) < 4 else parts[3],
            channel_metadata=channel_metadata,
            channel_id=channel_channel_id,
        )

    def get_bound_thread_id(self, session_key: str) -> str | None:
        row = self._sessions.get(session_key)
        return row.thread_id if row else None

    def get_session(self, session_key: str) -> SessionRow | None:
        return self._sessions.get(session_key)

    async def rebind(self, *, session_key: str, thread_id: str, agent_id: str) -> None:
        row = self._threads.get(thread_id)
        if row is None:
            msg = f"thread {thread_id!r} not found"
            raise ValueError(msg)
        if row.agent_id != agent_id:
            msg = f"thread {thread_id!r} does not belong to agent {agent_id!r}"
            raise ValueError(msg)
        async with self._lock:
            session = self._sessions.get(session_key)
            ref = self._sessions.get(row.session_key)
            if ref is not None:
                channel_type = ref.channel_type
                chat_type = ref.chat_type
                subject_id = ref.channel_subject_id
                channel_chat_type = ref.channel_chat_type
                metadata = ref.channel_metadata
                channel_id = ref.channel_id
            else:
                channel_type = row.channel_type
                chat_type = "dm"
                subject_id = str(row.user_id)
                channel_chat_type = chat_type
                metadata = {"channel_type": row.channel_type, "user_id": row.user_id}
                channel_id = None
            if session is None:
                self._sessions.upsert(
                    session_key=session_key,
                    agent_id=agent_id,
                    user_id=row.user_id,
                    channel_type=channel_type,
                    chat_type=chat_type,
                    thread_id=thread_id,
                    channel_subject_id=subject_id,
                    channel_chat_type=channel_chat_type,
                    channel_metadata=metadata,
                    channel_id=channel_id,
                )
            else:
                if session.agent_id != agent_id:
                    self._sessions.set_agent_id(session_key, agent_id)
                self._sessions.set_thread(session_key, thread_id)

    async def reset(
        self,
        *,
        agent_id: str,
        user_id: int,
        channel_type: str,
        channel_subject_id: str,
        channel_chat_type: str = "dm",
        channel_metadata: dict[str, Any] | None = None,
        channel_id: str | None = None,
    ) -> str:
        session_key = self.make_key(
            agent_id=agent_id,
            channel_type=channel_type,
            channel_subject_id=channel_subject_id,
            channel_chat_type=channel_chat_type,
        )
        meta = dict(channel_metadata or {})
        meta.setdefault("channel_type", channel_type)
        meta.setdefault("user_id", user_id)
        async with self._lock:
            tid = _new_thread_id()
            self._threads.insert(
                thread_id=tid,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                session_key=session_key,
                last_active=0,
            )
            self._sessions.upsert(
                session_key=session_key,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                chat_type=channel_chat_type,
                thread_id=tid,
                channel_subject_id=channel_subject_id,
                channel_chat_type=channel_chat_type,
                channel_metadata=meta,
                channel_id=channel_id,
            )
            return tid

    async def reset_by_session_key(self, session_key: str) -> str:
        session = self._sessions.get(session_key)
        if session is None:
            msg = f"session {session_key!r} not found"
            raise ValueError(msg)
        async with self._lock:
            tid = _new_thread_id()
            self._threads.insert(
                thread_id=tid,
                agent_id=session.agent_id,
                user_id=session.user_id,
                channel_type=session.channel_type,
                session_key=session_key,
                last_active=0,
            )
            self._sessions.upsert(
                session_key=session_key,
                agent_id=session.agent_id,
                user_id=session.user_id,
                channel_type=session.channel_type,
                chat_type=session.chat_type,
                thread_id=tid,
                channel_subject_id=session.channel_subject_id,
                channel_chat_type=session.channel_chat_type,
                channel_metadata=session.channel_metadata,
                channel_id=session.channel_id,
            )
            return tid

    def set_title_if_null(self, thread_id: str, title: str) -> None:
        self._threads.set_title_if_null(thread_id, title)

    def update_title(self, thread_id: str, title: str) -> None:
        self._threads.update_title(thread_id, title)

    def set_pinned(self, thread_id: str, pinned: bool) -> None:
        self._threads.set_pinned(thread_id, pinned)

    def touch_last_active(self, thread_id: str) -> None:
        self._threads.touch_last_active(thread_id)

    def get_thread(self, thread_id: str) -> ThreadRow | None:
        return self._threads.get(thread_id)

    def list_threads(self, *, agent_id: str, limit: int = 50) -> list[ThreadRow]:
        return self._threads.list_by_agent(agent_id=agent_id, limit=limit)

    def list_threads_for_session(self, *, session_key: str, limit: int = 50) -> list[ThreadRow]:
        return self._threads.list_by_session(session_key=session_key, limit=limit)

    def delete_thread(self, thread_id: str) -> None:
        self._threads.delete(thread_id)

    def increment_unread(self, session_key: str, *, delta: int = 1) -> None:
        self._sessions.increment_unread(session_key, delta=delta)

    def mark_thread_read(self, thread_id: str) -> None:
        self._sessions.clear_unread_for_thread(thread_id)

    def mark_agent_read(self, agent_id: str, user_id: int) -> None:
        self._sessions.clear_unread_for_agent(agent_id, user_id)

    def unread_totals_by_agent(self, user_id: int, agent_ids: list[str]) -> dict[str, int]:
        return self._sessions.unread_totals_by_agent(user_id, agent_ids)

    def unread_counts_for_threads(self, thread_ids: list[str]) -> dict[str, int]:
        return self._sessions.unread_counts_for_threads(thread_ids)


def _new_thread_id() -> str:
    return f"thr_{new_ulid()}"


def thread_row_has_messages(row: ThreadRow) -> bool:
    """Infer conversation activity from thread metadata (no checkpoint I/O).

    New threads are inserted with ``last_active=0``; the first user/agent turn
    bumps ``last_active`` and usually sets ``title`` from the user text.
    """
    if row.title:
        return True
    return row.last_active > 0
