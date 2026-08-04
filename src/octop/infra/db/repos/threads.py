"""Threads table — conversation metadata for history listing and /resume."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, bool_int, map_rows, now_ts


@dataclass(frozen=True)
class ThreadRow:
    id: int
    thread_id: str
    agent_id: str
    user_id: int
    channel_type: str
    session_key: str
    title: str | None
    last_active: int
    created_at: int
    pinned: bool = False

    @classmethod
    def from_row(cls, r: DbRow) -> ThreadRow:
        return cls(
            id=r["id"],
            thread_id=r["thread_id"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            channel_type=r["channel_type"],
            session_key=r["session_key"],
            title=r["title"],
            last_active=r["last_active"],
            created_at=r["created_at"],
            pinned=bool(r["pinned"]),
        )


def clip_thread_title(title: str, *, max_len: int = 40) -> str:
    """Bound stored thread titles; longer names end with an ellipsis.

    Whitespace is collapsed so auto-titles from multi-line messages stay tidy.
    Exact-length titles (no longer source) are kept without forcing ``…``.
    """
    text = " ".join((title or "").split())
    if not text:
        return ""
    if max_len <= 1:
        return "…"
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1].rstrip()}…"


def repair_legacy_thread_title(title: str | None, *, max_len: int = 40) -> str | None:
    """Rewrite hard-cut titles that hit the cap without an ellipsis.

    Pre-clipping storage truncated at ``max_len`` with no ``…``. New writes
    from :func:`clip_thread_title` always end with ``…`` when shortened.
    Title-repair migration and optional repo helpers use this.

    Legitimate full-length titles of exactly ``max_len`` without ellipsis are
    indistinguishable and get the same rewrite once during migration — rare.
    """
    if title is None:
        return None
    text = " ".join(title.split())
    if not text:
        return None
    if text.endswith("…") or text.endswith("..."):
        fixed = clip_thread_title(text, max_len=max_len)
        return fixed or None
    if len(text) == max_len:
        return f"{text[: max_len - 1].rstrip()}…"
    fixed = clip_thread_title(text, max_len=max_len)
    return fixed or None


def repair_all_legacy_thread_titles(db: DatabasePool) -> int:
    """Persist :func:`repair_legacy_thread_title` for every row. Returns update count."""
    updated = 0
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT thread_id, title FROM threads WHERE title IS NOT NULL"
        ).fetchall()
        for r in rows:
            thread_id = str(r["thread_id"])
            title = r["title"]
            fixed = repair_legacy_thread_title(title if isinstance(title, str) else str(title))
            if fixed is not None and fixed != title:
                conn.execute(
                    "UPDATE threads SET title = ? WHERE thread_id = ?",
                    (fixed, thread_id),
                )
                updated += 1
    return updated


class ThreadRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def insert(
        self,
        *,
        thread_id: str,
        agent_id: str,
        user_id: int,
        channel_type: str,
        session_key: str,
        title: str | None = None,
        last_active: int | None = None,
    ) -> None:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, "
                "session_key, title, last_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    agent_id,
                    user_id,
                    channel_type,
                    session_key,
                    clip_thread_title(title) if title else None,
                    ts if last_active is None else last_active,
                    ts,
                ),
            )

    def get(self, thread_id: str) -> ThreadRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,)).fetchone()
        return ThreadRow.from_row(r) if r else None

    def list_by_agent(self, *, agent_id: str, limit: int = 50) -> list[ThreadRow]:
        # last_active=0 is "no turns yet" (has_messages sentinel). Fall back to
        # created_at so brand-new empty threads sort to the top of the sidebar
        # instead of sinking below every previously active chat.
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM threads WHERE agent_id = ? "
                "ORDER BY pinned DESC, "
                "CASE WHEN last_active > 0 THEN last_active ELSE created_at END DESC, "
                "thread_id DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return map_rows(rows, ThreadRow)

    def list_by_session(self, *, session_key: str, limit: int = 50) -> list[ThreadRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM threads WHERE session_key = ? "
                "ORDER BY "
                "CASE WHEN last_active > 0 THEN last_active ELSE created_at END DESC, "
                "thread_id DESC LIMIT ?",
                (session_key, limit),
            ).fetchall()
        return map_rows(rows, ThreadRow)

    def set_title_if_null(self, thread_id: str, title: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET title = ? WHERE thread_id = ? AND title IS NULL",
                (clip_thread_title(title), thread_id),
            )

    def update_title(self, thread_id: str, title: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET title = ? WHERE thread_id = ?",
                (clip_thread_title(title), thread_id),
            )

    def set_pinned(self, thread_id: str, pinned: bool) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET pinned = ? WHERE thread_id = ?",
                (bool_int(pinned), thread_id),
            )

    def touch_last_active(self, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET last_active = ? WHERE thread_id = ?",
                (now_ts(), thread_id),
            )

    def delete(self, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
