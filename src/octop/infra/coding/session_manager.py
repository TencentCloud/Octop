"""Coding session lifecycle manager (S3).

The repository is the single source of truth for session metadata; this
manager adds id generation, ownership checks, startup reconciliation and
conversational-history replay-prefix construction.
"""

from __future__ import annotations

import os
import time
from typing import Any

from octop.infra.db.repos.agent_events import AgentEventRepo
from octop.infra.db.repos.coding_sessions import (
    STATUS_AWAITING,
    STATUS_IDLE,
    STATUS_INTERRUPTED,
    STATUS_READY,
    STATUS_RUNNING,
    CodingSessionRepo,
    CodingSessionRow,
)

DEFAULT_REPLAY_MESSAGES = 20
DEFAULT_REPLAY_CHARS = 32_000


def new_session_id() -> str:
    return f"cc_{int(time.time())}_{os.urandom(3).hex()}"


class SessionManager:
    def __init__(
        self,
        session_repo: CodingSessionRepo,
        event_repo: AgentEventRepo,
    ) -> None:
        self._sessions = session_repo
        self._events = event_repo

    # ----- lifecycle -----

    def create_session(self, *, user_id: int, runner: str, cwd: str) -> CodingSessionRow:
        return self._sessions.create(
            session_id=new_session_id(),
            user_id=user_id,
            runner=runner,
            cwd=cwd,
            status=STATUS_READY,
        )

    def get(self, session_id: str) -> CodingSessionRow | None:
        return self._sessions.get(session_id)

    @staticmethod
    def can_access(row: CodingSessionRow, *, user_id: int, is_admin: bool) -> bool:
        return is_admin or row.user_id == user_id

    def get_owned(
        self, session_id: str, *, user_id: int, is_admin: bool
    ) -> CodingSessionRow | None:
        """Return the row when owned (or admin); ``None`` for missing/forbidden."""
        row = self.get(session_id)
        if row is None or not self.can_access(row, user_id=user_id, is_admin=is_admin):
            return None
        return row

    def list_visible(self, *, user_id: int, is_admin: bool) -> list[CodingSessionRow]:
        return self._sessions.list_visible(user_id=user_id, is_admin=is_admin)

    def mark_running(self, session_id: str) -> None:
        self._sessions.update_status(session_id, STATUS_RUNNING)

    def mark_awaiting(self, session_id: str) -> None:
        self._sessions.update_status(session_id, STATUS_AWAITING)

    def mark_idle(self, session_id: str) -> None:
        self._sessions.update_status(session_id, STATUS_IDLE)

    def mark_interrupted(self, session_id: str) -> None:
        self._sessions.update_status(session_id, STATUS_INTERRUPTED)

    def close(self, session_id: str) -> None:
        self._sessions.close(session_id)

    def bump_turns(self, session_id: str) -> None:
        self._sessions.bump_turns(session_id)

    def bind_acp(self, session_id: str, acp_session_id: str | None) -> None:
        self._sessions.bind_acp(session_id, acp_session_id)

    def has_history(self, session_id: str) -> bool:
        row = self.get(session_id)
        return bool(row and row.turns > 0)

    def list_events(self, session_id: str, *, after_seq: int = 0, limit: int = 500) -> list[Any]:
        return self._events.list_for_session(session_id, after_seq=after_seq, limit=limit)

    def recover_on_startup(self) -> int:
        """Mark sessions orphaned by a restart/crash as interrupted."""
        return self._sessions.mark_interrupted_pending()

    # ----- context replay -----

    def build_replay_prefix(
        self,
        session_id: str,
        *,
        max_messages: int = DEFAULT_REPLAY_MESSAGES,
        max_chars: int = DEFAULT_REPLAY_CHARS,
    ) -> str | None:
        """Build a single text block recreating conversational context.

        Uses only user/assistant text events (never tool events). The most
        recent messages win under both a count budget and a character budget;
        older dropped content is announced in the header.
        """
        events = self._events.list_text_events(session_id, max_messages=max_messages)
        if not events:
            return None

        messages: list[tuple[str, str]] = []
        for ev in events:
            role = "用户" if ev.kind == "user_prompt" else "助手"
            text = str(ev.payload.get("text") or "").strip()
            if text:
                messages.append((role, text))
        if not messages:
            return None

        # Character budget: keep newest messages first.
        kept_rev: list[tuple[str, str]] = []
        used = 0
        for role, text in reversed(messages):
            extra = len(role) + len(text) + 4
            if used + extra > max_chars and kept_rev:
                truncated = True
                break
            kept_rev.append((role, text))
            used += extra
        else:
            truncated = False
        kept = list(reversed(kept_rev))

        lines = ["<历史对话开始>"]
        if truncated or len(kept) < len(messages):
            lines.append("（注：更早的对话因长度限制已省略）")
        for role, text in kept:
            lines.append(f"[{role}] {text}")
        lines.append("<历史对话结束>")
        lines.append("请基于以上历史继续，不要重复执行其中已描述过的操作。")
        return "\n".join(lines)

    # ----- helpers for router runtime cache -----

    def runtime_view(self, row: CodingSessionRow, *, streaming: bool) -> dict[str, Any]:
        return {
            "id": row.session_id,
            "runner": row.runner,
            "cwd": row.cwd,
            "turns": row.turns,
            "created_at": row.created_at,
            "status": row.status,
            "streaming": streaming,
        }
