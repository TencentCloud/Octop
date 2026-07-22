"""Sessions table — maps session_key to the currently bound thread_id."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from harness_gateway.models import ChannelSubject

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, now_ts, sql_in_placeholders


def _decode_metadata(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return val if isinstance(val, dict) else None


def _encode_metadata(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    return json.dumps(meta, ensure_ascii=False)


def _backfill_channel_fields(
    *,
    session_key: str,
    user_id: int,
    channel_type: str,
    chat_type: str,
    channel_subject_id: str | None,
    channel_chat_type: str | None,
    channel_metadata: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any] | None]:
    parts = session_key.split(":", 3)
    subject_id = channel_subject_id
    if subject_id is None:
        subject_id = parts[2] if len(parts) >= 3 else str(user_id)
    resolved_chat = channel_chat_type or (parts[3] if len(parts) >= 4 else chat_type)
    meta = channel_metadata
    if meta is None:
        ch = parts[1] if len(parts) >= 2 else channel_type
        meta = {"channel_type": ch, "user_id": user_id}
    return subject_id, resolved_chat, meta


@dataclass(frozen=True)
class SessionRow:
    id: int
    session_key: str
    agent_id: str
    user_id: int
    channel_type: str
    chat_type: str
    thread_id: str
    updated_at: int
    channel_subject_id: str
    channel_chat_type: str
    channel_metadata: dict[str, Any] | None = None
    channel_id: str | None = None
    unread_count: int = 0

    @classmethod
    def from_row(cls, r: DbRow) -> SessionRow:
        metadata = _decode_metadata(r["channel_metadata"])
        subject_id, chat_type, metadata = _backfill_channel_fields(
            session_key=r["session_key"],
            user_id=int(r["user_id"]),
            channel_type=str(r["channel_type"]),
            chat_type=str(r["chat_type"]),
            channel_subject_id=r["channel_subject_id"],
            channel_chat_type=r["channel_chat_type"],
            channel_metadata=metadata,
        )
        channel_id = r["channel_id"]
        return cls(
            id=r["id"],
            session_key=r["session_key"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            channel_type=r["channel_type"],
            chat_type=r["chat_type"],
            thread_id=r["thread_id"],
            updated_at=r["updated_at"],
            channel_subject_id=subject_id,
            channel_chat_type=chat_type,
            channel_metadata=metadata,
            channel_id=str(channel_id) if channel_id else None,
            unread_count=int(r["unread_count"]),
        )

    def to_channel_subject(self) -> ChannelSubject:
        meta = dict(self.channel_metadata or {})
        meta.setdefault("channel_type", self.channel_type)
        meta.setdefault("user_id", self.user_id)
        if self.channel_id:
            meta.setdefault("channel_id", self.channel_id)
        return ChannelSubject(
            subject_id=self.channel_subject_id,
            chat_type=self.channel_chat_type,
            metadata=meta,
        )


class SessionRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get(self, session_key: str) -> SessionRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM sessions WHERE session_key = ?", (session_key,)
            ).fetchone()
        return SessionRow.from_row(r) if r else None

    def upsert(
        self,
        *,
        session_key: str,
        agent_id: str,
        user_id: int,
        channel_type: str,
        chat_type: str,
        thread_id: str,
        channel_subject_id: str | None = None,
        channel_chat_type: str | None = None,
        channel_metadata: dict[str, Any] | None = None,
        channel_id: str | None = None,
    ) -> None:
        subject_id, resolved_chat, metadata = _backfill_channel_fields(
            session_key=session_key,
            user_id=user_id,
            channel_type=channel_type,
            chat_type=chat_type,
            channel_subject_id=channel_subject_id,
            channel_chat_type=channel_chat_type,
            channel_metadata=channel_metadata,
        )
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO sessions(session_key, agent_id, user_id, channel_type, "
                "chat_type, thread_id, updated_at, channel_subject_id, channel_chat_type, "
                "channel_metadata, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_key) DO UPDATE SET "
                "agent_id = excluded.agent_id, "
                "thread_id = excluded.thread_id, updated_at = excluded.updated_at, "
                "channel_subject_id = excluded.channel_subject_id, "
                "channel_chat_type = excluded.channel_chat_type, "
                "channel_metadata = excluded.channel_metadata, "
                "channel_id = COALESCE(excluded.channel_id, sessions.channel_id)",
                (
                    session_key,
                    agent_id,
                    user_id,
                    channel_type,
                    chat_type,
                    thread_id,
                    ts,
                    subject_id,
                    resolved_chat,
                    _encode_metadata(metadata),
                    channel_id,
                ),
            )

    def set_thread(self, session_key: str, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET thread_id = ?, updated_at = ? WHERE session_key = ?",
                (thread_id, now_ts(), session_key),
            )

    def set_agent_id(self, session_key: str, agent_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET agent_id = ?, updated_at = ? WHERE session_key = ?",
                (agent_id, now_ts(), session_key),
            )

    def increment_unread(self, session_key: str, *, delta: int = 1) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET unread_count = unread_count + ? WHERE session_key = ?",
                (delta, session_key),
            )

    def clear_unread_for_thread(self, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET unread_count = 0 WHERE thread_id = ?",
                (thread_id,),
            )

    def clear_unread_for_agent(self, agent_id: str, user_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET unread_count = 0 WHERE agent_id = ? AND user_id = ?",
                (agent_id, user_id),
            )

    def list_by_agent(self, agent_id: str, *, limit: int = 20) -> list[SessionRow]:
        """Query all sessions for an agent, ordered by most-recent activity (descending).

        Args:
            agent_id: the agent ID.
            limit: maximum number of rows to return; defaults to 20.

        Returns:
            A list of SessionRow objects.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE agent_id = ? ORDER BY updated_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [SessionRow.from_row(r) for r in rows]

    def unread_totals_by_agent(self, user_id: int, agent_ids: list[str]) -> dict[str, int]:
        if not agent_ids:
            return {}
        placeholders = sql_in_placeholders(len(agent_ids))
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT agent_id, SUM(unread_count) AS total FROM sessions "
                f"WHERE user_id = ? AND agent_id IN ({placeholders}) "
                f"GROUP BY agent_id HAVING SUM(unread_count) > 0",
                (user_id, *agent_ids),
            ).fetchall()
        return {str(r["agent_id"]): int(r["total"]) for r in rows}

    def unread_counts_for_threads(self, thread_ids: list[str]) -> dict[str, int]:
        if not thread_ids:
            return {}
        placeholders = sql_in_placeholders(len(thread_ids))
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT thread_id, unread_count FROM sessions "
                f"WHERE thread_id IN ({placeholders}) AND unread_count > 0",
                thread_ids,
            ).fetchall()
        return {str(r["thread_id"]): int(r["unread_count"]) for r in rows}
