"""Turn-boundary routing and read composition for an unmigrated legacy prefix."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.history.store import HistoryStore, dumps

LegacyReader = Callable[[dict[str, Any]], Awaitable[list[Any]]]


class HistoryArchive:
    def __init__(
        self,
        store: HistoryStore,
        messages: ThreadMessageRepo,
        events: TrajectoryEventRepo,
        *,
        enabled: bool = False,
    ) -> None:
        self.store = store
        self.messages = messages
        self.events = events
        self.enabled = enabled
        self._owned_turns: set[str] = set()
        self.trajectory_errors: set[str] = set()
        self._turn_lock = threading.RLock()

    def event_head(self, thread_id: str) -> int:
        rows = self.events.list_before(thread_id, before_seq=None, limit=1, kinds=None)
        return rows[-1].seq if rows else 0

    def begin(
        self,
        agent_id: str,
        thread_id: str,
        *,
        anchor: dict[str, Any] | None = None,
        resume: bool = False,
    ) -> dict[str, Any] | None:
        with self._turn_lock:
            return self._begin(agent_id, thread_id, anchor=anchor, resume=resume)

    def _begin(
        self, agent_id: str, thread_id: str, *, anchor: dict[str, Any] | None, resume: bool
    ) -> dict[str, Any] | None:
        segments = self.store.segments(thread_id)
        if segments and segments[0]["agent_id"] != agent_id:
            raise ValueError("History belongs to another agent")
        if not segments and (not self.enabled or resume):
            return None
        previous = self.store.turn(thread_id, unfinished=True)
        if resume:
            if previous is not None and previous["id"] in self._owned_turns:
                raise ValueError("This history turn is already running")
            if previous is not None:
                self._owned_turns.add(previous["id"])
            return previous
        if previous is not None and previous["id"] in self._owned_turns:
            raise ValueError("This history turn is already running")
        if previous is not None and previous["status"] == "paused":
            raise ValueError("Finish the paused turn before changing history storage")
        message_head = self.messages.head(thread_id)
        event_head = self.event_head(thread_id)
        fmt = "v2" if self.enabled else "legacy"
        turn_id = uuid.uuid4().hex
        with self.store.transaction() as conn:
            if previous is not None:
                # A new request after restart keeps the interrupted turn readable.
                conn.execute(
                    "UPDATE turns SET status='interrupted',finished_at=? WHERE id=?",
                    (time.time(), previous["id"]),
                )
            current = conn.execute(
                "SELECT * FROM segments WHERE thread_id=? ORDER BY id DESC LIMIT 1", (thread_id,)
            ).fetchone()
            if current is None:
                conn.execute(
                    "INSERT INTO segments "
                    "(thread_id,agent_id,format,legacy_start,legacy_end,anchor,trajectory_start,trajectory_end) "
                    "VALUES (?,?,'legacy',0,?,?,0,?)",
                    (
                        thread_id,
                        agent_id,
                        message_head,
                        dumps(anchor) if anchor else None,
                        event_head,
                    ),
                )
            if current is None or current["format"] != fmt:
                if current is not None:
                    conn.execute(
                        "UPDATE segments SET legacy_end=?,trajectory_end=? WHERE id=?",
                        (message_head, event_head, current["id"]),
                    )
                cur = conn.execute(
                    "INSERT INTO segments "
                    "(thread_id,agent_id,format,legacy_start,trajectory_start) VALUES (?,?,?,?,?)",
                    (thread_id, agent_id, fmt, message_head, event_head),
                )
                segment_id = int(cur.lastrowid or 0)
            else:
                segment_id = int(current["id"])
            conn.execute(
                "INSERT INTO turns(id,segment_id,status,started_at) VALUES (?,?,'active',?)",
                (turn_id, segment_id, time.time()),
            )
        self._owned_turns.add(turn_id)
        self.trajectory_errors.discard(thread_id)
        return {
            "id": turn_id,
            "segment_id": segment_id,
            "format": fmt,
            "thread_id": thread_id,
            "agent_id": agent_id,
            "status": "active",
        }

    def is_v2(self, thread_id: str) -> bool:
        turn = self.store.turn(thread_id)
        return turn is not None and turn["format"] == "v2"

    def finish(self, turn_id: str, status: str, *, error: str | None = None) -> None:
        try:
            with self.store.transaction() as conn:
                conn.execute(
                    "UPDATE turns SET status=?,error=?,finished_at=? WHERE id=?",
                    (status, error, None if status == "paused" else time.time(), turn_id),
                )
        finally:
            with self._turn_lock:
                self._owned_turns.discard(turn_id)

    def save_messages(self, turn: dict[str, Any], wires: list[dict[str, Any]]) -> None:
        """Save a complete seed, such as an explicitly created fork."""
        self.save_message_updates(turn, list(enumerate(wires)))

    def save_message_updates(
        self, turn: dict[str, Any], updates: list[tuple[int, dict[str, Any]]]
    ) -> None:
        """Atomically write only changed messages, preserving their existing sequence."""
        with self.store.transaction() as conn:
            for index, wire in updates:
                doc_id = f"message:{turn['id']}:{index}"
                old = conn.execute("SELECT seq FROM documents WHERE id=?", (doc_id,)).fetchone()
                seq = (
                    int(old[0])
                    if old
                    else int(
                        conn.execute(
                            "SELECT COALESCE(MAX(seq),0)+1 FROM documents WHERE thread_id=? AND kind='message'",
                            (turn["thread_id"],),
                        ).fetchone()[0]
                    )
                )
                self.store.put_document(
                    conn,
                    doc_id=doc_id,
                    thread_id=turn["thread_id"],
                    turn_id=turn["id"],
                    kind="message",
                    seq=seq,
                    value=wire,
                )

    def remove_thread(self, thread_id: str) -> None:
        """Explicit thread deletion only; never called by retention or backfill."""
        with self.store.transaction() as conn:
            refs = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT r.digest FROM body_refs r JOIN documents d ON d.id=r.owner WHERE d.thread_id=?",
                    (thread_id,),
                )
            ]
            conn.execute("DELETE FROM documents WHERE thread_id=?", (thread_id,))
            conn.execute(
                "DELETE FROM turns WHERE segment_id IN (SELECT id FROM segments WHERE thread_id=?)",
                (thread_id,),
            )
            conn.execute("DELETE FROM segments WHERE thread_id=?", (thread_id,))
            for digest in refs:
                conn.execute(
                    "DELETE FROM bodies WHERE digest=? AND NOT EXISTS (SELECT 1 FROM body_refs WHERE digest=?)",
                    (digest, digest),
                )

    async def all_messages(self, thread_id: str, legacy_reader: LegacyReader) -> list[Any]:
        result = await self.page(thread_id, limit=1000, cursor=None, legacy_reader=legacy_reader)
        messages = result["messages"]
        while result["has_more"]:
            result = await self.page(
                thread_id, limit=1000, cursor=result["next_cursor"], legacy_reader=legacy_reader
            )
            messages = [*result["messages"], *messages]
        return messages  # type: ignore[no-any-return]

    async def page(
        self,
        thread_id: str,
        *,
        limit: int,
        cursor: str | None,
        legacy_reader: LegacyReader,
        offset: int = 0,
    ) -> dict[str, Any]:
        segments = await asyncio.to_thread(self.store.segments, thread_id)
        boundary = None
        if cursor:
            try:
                boundary = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if boundary["thread"] != thread_id or not isinstance(boundary["before"], int):
                    raise ValueError("Cursor belongs to another history")
                if not any(segment["id"] == boundary["segment"] for segment in segments):
                    raise ValueError("Unknown history segment")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("Invalid history cursor") from exc
        selected: list[tuple[int, int, Any]] = []
        skip = max(0, offset) if not cursor else 0
        for segment in reversed(segments):
            if boundary and segment["id"] > boundary["segment"]:
                continue
            before = (
                boundary["before"] if boundary and segment["id"] == boundary["segment"] else None
            )
            needed = limit + 1 + skip - len(selected)
            if segment["format"] == "v2":
                rows = await asyncio.to_thread(
                    self.store.message_page, thread_id, segment["id"], before, needed
                )
                items = [(row["seq"], row["value"]) for row in rows]
            elif segment["anchor"]:
                raw = await legacy_reader(json.loads(segment["anchor"]))
                end = len(raw) if before is None else min(before, len(raw))
                items = [(i, raw[i]) for i in range(end - 1, max(-1, end - needed - 1), -1)]
            else:
                end = segment["legacy_end"]
                if end is None:
                    end = await asyncio.to_thread(self.messages.head, thread_id)
                if before is not None:
                    end = min(end, before - 1)
                old_rows = await asyncio.to_thread(
                    self.messages.range_page, thread_id, segment["legacy_start"], end, needed
                )
                items = [(row.seq, json.loads(row.message_json)) for row in old_rows]
            selected.extend((segment["id"], seq, wire) for seq, wire in items)
            if len(selected) >= limit + 1 + skip:
                break
        selected = selected[skip:]
        has_more = len(selected) > limit
        selected = selected[:limit]
        next_cursor = None
        if has_more:
            segment_id, seq, _ = selected[-1]
            next_cursor = base64.urlsafe_b64encode(
                dumps({"thread": thread_id, "segment": segment_id, "before": seq}).encode()
            ).decode()
        return {
            "messages": [wire for _, _, wire in reversed(selected)],
            "has_more": has_more,
            "next_cursor": next_cursor,
            "history_status": "ready",
        }
