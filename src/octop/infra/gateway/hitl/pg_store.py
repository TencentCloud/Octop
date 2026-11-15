"""PostgreSQL-backed HITL pending store.

Drop-in replacement for ``HitlPendingStore`` that persists records to
``hitl_pending_records`` (migration 026). All method signatures match
the in-memory store so the coordinator can be injected transparently.

Shared types and helpers are imported from ``store.py`` so there is a
single source of truth for HitlPendingRecord and related definitions.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from octop.infra.gateway.hitl.store import (
    _DEFAULT_TTL_SECONDS,
    HitlPendingRecord,
    HitlPendingStatus,
    _actions_equivalent,
    _same_pause_slot,
)

# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _deserialize(raw: Any) -> Any:
    """Deserialise a JSONB column value.  psycopg v3 dict_row already returns
    Python objects for JSONB; we also tolerate raw strings for compatibility."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _row_to_record(row: dict[str, Any]) -> HitlPendingRecord:
    """Convert a PG dict_row result to a ``HitlPendingRecord``."""
    consumed = _deserialize(row.get("consumed_submission_ids")) or []
    if isinstance(consumed, list):
        consumed = set(consumed)
    elif isinstance(consumed, set):
        pass

    ask_answers = _deserialize(row.get("ask_answers")) or []
    if isinstance(ask_answers, dict):
        # migrate dict-format answers to list
        ask_answers = [ask_answers[str(i)] for i in sorted(int(k) for k in ask_answers)]
    elif not isinstance(ask_answers, list):
        ask_answers = []

    return HitlPendingRecord(
        pending_id=row["pending_id"],
        thread_id=row["thread_id"],
        agent_id=row["agent_id"],
        user_id=int(row["user_id"]),
        session_key=row["session_key"],
        channel_type=row.get("channel_type", ""),
        action_requests=_deserialize(row.get("action_requests")) or [],
        review_configs=_deserialize(row.get("review_configs")),
        status=row.get("status", "pending"),
        created_at=row.get("created_at", 0.0),
        ask_question_index=row.get("ask_question_index", 0),
        ask_answers=ask_answers,
        resume_agent_id=row.get("resume_agent_id"),
        resume_thread_id=row.get("resume_thread_id"),
        form_context=_deserialize(row.get("form_context")),
        consumed_submission_ids=consumed,
    )


def _thread_pending_match(
    record: HitlPendingRecord,
    *,
    thread_id: str,
    agent_id: str,
    user_id: int | None,
) -> bool:
    """True when *record* matches the thread-centric query."""
    if record.status != "pending":
        return False
    if record.thread_id == thread_id and record.agent_id == agent_id:
        return user_id is None or record.user_id == user_id
    if record.resume_thread_id == thread_id and record.resume_agent_id == agent_id:
        return user_id is None or record.user_id == user_id
    return False


# ---------------------------------------------------------------------------
# PostgreSQL-backed store
# ---------------------------------------------------------------------------


class HitlPendingPostgresStore:
    """PostgreSQL-backed pending record store.

    Drop-in replacement for ``HitlPendingStore``.  Requires migration 026.
    All public method signatures match the in-memory store exactly so the
    coordinator can be injected with either implementation.
    """

    def __init__(
        self,
        conninfo: str,
        *,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        min_size: int = 1,
        max_size: int = 4,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> float:
        return time.time()

    def _expire_stale(self, conn: Any, now: float) -> None:
        cutoff = now - self.ttl_seconds
        conn.execute(
            """
            UPDATE hitl_pending_records
               SET status = 'expired'
             WHERE status = 'pending' AND created_at < %s
            """,
            (cutoff,),
        )

    # ------------------------------------------------------------------
    # Public API — exact signatures matching HitlPendingStore
    # ------------------------------------------------------------------

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
        resume_thread_id: str | None = None,
        form_context: dict[str, Any] | None = None,
    ) -> HitlPendingRecord:
        now = self._now()
        with self._pool.connection() as conn:
            conn.execute("BEGIN")
            try:
                self._expire_stale(conn, now)

                # Look for an existing equivalent record in the same slot.
                r = conn.execute(
                    """
                    SELECT * FROM hitl_pending_records
                     WHERE session_key = %s
                       AND COALESCE(thread_id, '') = %s
                       AND COALESCE(resume_agent_id, '') = %s
                     ORDER BY created_at DESC
                     LIMIT 1
                    """,
                    (session_key, thread_id or "", resume_agent_id or ""),
                ).fetchone()

                if r is not None:
                    existing = _row_to_record(r)
                    if _same_pause_slot(
                        existing,
                        session_key=session_key,
                        thread_id=thread_id,
                        resume_agent_id=resume_agent_id,
                    ) and _actions_equivalent(existing.action_requests, action_requests):
                        conn.execute("COMMIT")
                        return existing

                    # Expire all pending records in this slot.
                    conn.execute(
                        """
                        UPDATE hitl_pending_records
                           SET status = 'expired'
                         WHERE session_key = %s
                           AND COALESCE(thread_id, '') = %s
                           AND COALESCE(resume_agent_id, '') = %s
                           AND status = 'pending'
                        """,
                        (session_key, thread_id or "", resume_agent_id or ""),
                    )

                pending_id = secrets.token_hex(2)
                record = HitlPendingRecord(
                    pending_id=pending_id,
                    thread_id=thread_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    session_key=session_key,
                    channel_type=channel_type,
                    action_requests=action_requests,
                    review_configs=review_configs,
                    created_at=now,
                    resume_agent_id=resume_agent_id,
                    resume_thread_id=resume_thread_id,
                    form_context=form_context,
                )

                conn.execute(
                    """
                    INSERT INTO hitl_pending_records
                        (pending_id, thread_id, agent_id, user_id, session_key,
                         channel_type, action_requests, review_configs, status,
                         created_at, updated_at, resume_agent_id, resume_thread_id,
                         form_context, consumed_submission_ids, ask_question_index,
                         ask_answers)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, 'pending',
                         %s, %s, %s, %s, %s, %s, 0, %s)
                    """,
                    (
                        pending_id,
                        thread_id,
                        agent_id,
                        str(user_id),
                        session_key,
                        channel_type,
                        Json(action_requests),
                        Json(review_configs) if review_configs else None,
                        now,
                        now,
                        resume_agent_id,
                        resume_thread_id,
                        Json(form_context) if form_context else None,
                        Json([]),
                        Json([]),
                    ),
                )
                conn.execute("COMMIT")
                return record
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get(self, pending_id: str) -> HitlPendingRecord | None:
        now = self._now()
        with self._pool.connection() as conn:
            self._expire_stale(conn, now)
            r = conn.execute(
                "SELECT * FROM hitl_pending_records WHERE pending_id = %s",
                (pending_id,),
            ).fetchone()
            if r is None:
                return None
            record = _row_to_record(r)
            if record.status == "pending" and now - record.created_at > self.ttl_seconds:
                record.status = "expired"
                conn.execute(
                    "UPDATE hitl_pending_records SET status = 'expired' WHERE pending_id = %s",
                    (pending_id,),
                )
            return record

    def get_pending(
        self, pending_id: str, session_key: str, agent_id: str
    ) -> HitlPendingRecord | None:
        record = self.get(pending_id)
        if record is None:
            return None
        if record.session_key != session_key or record.agent_id != agent_id:
            return None
        if record.status != "pending":
            return None
        return record

    def resolve_for_session(
        self,
        session_key: str,
        *,
        pending_id: str | None = None,
        agent_id: str | None = None,
    ) -> HitlPendingRecord | None:
        now = self._now()
        with self._pool.connection() as conn:
            self._expire_stale(conn, now)
            if pending_id:
                r = conn.execute(
                    """
                    SELECT * FROM hitl_pending_records
                     WHERE pending_id = %s AND session_key = %s AND status = 'pending'
                    """,
                    (pending_id, session_key),
                ).fetchone()
                if r is not None:
                    rec = _row_to_record(r)
                    if agent_id is None or rec.agent_id == agent_id:
                        return rec
                return None

            if agent_id:
                r = conn.execute(
                    """
                    SELECT * FROM hitl_pending_records
                     WHERE session_key = %s AND agent_id = %s AND status = 'pending'
                     ORDER BY created_at DESC LIMIT 1
                    """,
                    (session_key, agent_id),
                ).fetchone()
            else:
                r = conn.execute(
                    """
                    SELECT * FROM hitl_pending_records
                     WHERE session_key = %s AND status = 'pending'
                     ORDER BY created_at DESC LIMIT 1
                    """,
                    (session_key,),
                ).fetchone()
            if r is None:
                return None
            return _row_to_record(r)

    def list_pending_for_session(
        self, session_key: str, agent_id: str | None = None
    ) -> list[HitlPendingRecord]:
        now = self._now()
        with self._pool.connection() as conn:
            self._expire_stale(conn, now)
            if agent_id:
                rows = conn.execute(
                    """
                    SELECT * FROM hitl_pending_records
                     WHERE session_key = %s AND agent_id = %s AND status = 'pending'
                     ORDER BY created_at DESC
                    """,
                    (session_key, agent_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM hitl_pending_records
                     WHERE session_key = %s AND status = 'pending'
                     ORDER BY created_at DESC
                    """,
                    (session_key,),
                ).fetchall()
            return [_row_to_record(r) for r in rows]

    def resolve_pending_for_thread(
        self,
        thread_id: str,
        agent_id: str,
        *,
        user_id: int | None = None,
        pending_id: str | None = None,
    ) -> HitlPendingRecord | None:
        now = self._now()
        with self._pool.connection() as conn:
            self._expire_stale(conn, now)

            if pending_id:
                r = conn.execute(
                    "SELECT * FROM hitl_pending_records WHERE pending_id = %s",
                    (pending_id,),
                ).fetchone()
                if r is not None:
                    rec = _row_to_record(r)
                    if rec.status == "pending" and _thread_pending_match(
                        rec, thread_id=thread_id, agent_id=agent_id, user_id=user_id
                    ):
                        return rec
                return None

            # Direct thread match.
            r = conn.execute(
                """
                SELECT * FROM hitl_pending_records
                 WHERE thread_id = %s AND agent_id = %s AND status = 'pending'
                 ORDER BY created_at DESC LIMIT 1
                """,
                (thread_id, agent_id),
            ).fetchone()
            if r is not None:
                rec = _row_to_record(r)
                if user_id is None or rec.user_id == user_id:
                    return rec

            # Member thread match (via resume_thread_id).
            r = conn.execute(
                """
                SELECT * FROM hitl_pending_records
                 WHERE resume_thread_id = %s AND resume_agent_id = %s AND status = 'pending'
                 ORDER BY created_at DESC LIMIT 1
                """,
                (thread_id, agent_id),
            ).fetchone()
            if r is not None:
                rec = _row_to_record(r)
                if user_id is None or rec.user_id == user_id:
                    return rec
            return None

    def pending_thread_ids(
        self,
        agent_id: str,
        user_id: int | None = None,
        *,
        any_user: bool = False,
    ) -> frozenset[str]:
        now = self._now()
        with self._pool.connection() as conn:
            self._expire_stale(conn, now)
            if any_user:
                rows = conn.execute(
                    """
                    SELECT DISTINCT thread_id FROM hitl_pending_records
                     WHERE agent_id = %s AND status = 'pending'
                    """,
                    (agent_id,),
                ).fetchall()
            elif user_id is not None:
                rows = conn.execute(
                    """
                    SELECT DISTINCT thread_id FROM hitl_pending_records
                     WHERE agent_id = %s AND user_id = %s AND status = 'pending'
                    """,
                    (agent_id, str(user_id)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT thread_id FROM hitl_pending_records
                     WHERE agent_id = %s AND status = 'pending'
                    """,
                    (agent_id,),
                ).fetchall()
            return frozenset(r["thread_id"] for r in rows)

    def expire_pending_for_thread(
        self,
        thread_id: str,
        agent_id: str | None = None,
        user_id: int | None = None,
    ) -> None:
        now = self._now()
        with self._pool.connection() as conn:
            params: list[Any] = [now, thread_id]
            extra = ""
            if agent_id:
                extra += " AND agent_id = %s"
                params.append(agent_id)
            if user_id is not None:
                extra += " AND user_id = %s"
                params.append(str(user_id))
            conn.execute(
                f"""
                UPDATE hitl_pending_records
                   SET status = 'expired', updated_at = %s
                 WHERE thread_id = %s AND status = 'pending'{extra}
                """,
                params,
            )

    def mark_resolved(self, pending_id: str, status: HitlPendingStatus) -> None:
        now = self._now()
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE hitl_pending_records SET status = %s, updated_at = %s WHERE pending_id = %s",
                (status, now, pending_id),
            )

    def append_ask_answer(self, pending_id: str, answer: str) -> HitlPendingRecord | None:
        now = self._now()
        with self._pool.connection() as conn:
            conn.execute("BEGIN")
            try:
                r = conn.execute(
                    "SELECT * FROM hitl_pending_records"
                    " WHERE pending_id = %s AND status = 'pending' FOR UPDATE",
                    (pending_id,),
                ).fetchone()
                if r is None:
                    conn.execute("COMMIT")
                    return None
                rec = _row_to_record(r)
                rec.ask_answers.append(answer)
                rec.ask_question_index = len(rec.ask_answers)
                conn.execute(
                    """
                    UPDATE hitl_pending_records
                       SET ask_answers = %s,
                           ask_question_index = %s,
                           updated_at = %s
                     WHERE pending_id = %s
                    """,
                    (Json(rec.ask_answers), rec.ask_question_index, now, pending_id),
                )
                conn.execute("COMMIT")
                return rec
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def mark_form_consumed(self, pending_id: str, submission_id: str) -> bool:
        now = self._now()
        with self._pool.connection() as conn:
            conn.execute("BEGIN")
            try:
                r = conn.execute(
                    "SELECT consumed_submission_ids FROM hitl_pending_records"
                    " WHERE pending_id = %s FOR UPDATE",
                    (pending_id,),
                ).fetchone()
                if r is None:
                    conn.execute("COMMIT")
                    return False
                consumed: list = _deserialize(r["consumed_submission_ids"]) or []
                if not isinstance(consumed, list):
                    consumed = []
                if submission_id in consumed:
                    conn.execute("COMMIT")
                    return False
                consumed.append(submission_id)
                conn.execute(
                    """
                    UPDATE hitl_pending_records
                       SET consumed_submission_ids = %s, updated_at = %s
                     WHERE pending_id = %s
                    """,
                    (Json(consumed), now, pending_id),
                )
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def cancel_pending_by_form_id(
        self,
        form_id: str,
        agent_id: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        now = self._now()
        with self._pool.connection() as conn:
            conn.execute("BEGIN")
            try:
                params: list[Any] = [now, form_id]
                extra = ""
                if agent_id:
                    extra += " AND agent_id = %s"
                    params.append(agent_id)
                if user_id is not None:
                    extra += " AND user_id = %s"
                    params.append(str(user_id))
                r = conn.execute(
                    f"""
                    UPDATE hitl_pending_records
                       SET status = 'expired', updated_at = %s
                     WHERE status = 'pending'
                       AND form_context->>'form_id' = %s
                       AND (consumed_submission_ids IS NULL
                            OR consumed_submission_ids = '[]'::jsonb
                            OR jsonb_array_length(consumed_submission_ids) = 0){extra}
                    """,
                    params,
                )
                count = r.rowcount
                conn.execute("COMMIT")
                return count > 0
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _gc(self) -> None:
        now = self._now()
        cutoff = now - self.ttl_seconds
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE hitl_pending_records SET status = 'expired'"
                " WHERE status = 'pending' AND created_at < %s",
                (cutoff,),
            )
            conn.execute(
                "DELETE FROM hitl_pending_records WHERE status != 'pending' AND created_at < %s",
                (now - self.ttl_seconds * 2,),
            )

    def close(self) -> None:
        self._pool.close()
