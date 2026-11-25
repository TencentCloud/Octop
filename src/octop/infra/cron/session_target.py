"""Cron session_key values that name either a channel or one historical thread."""

from __future__ import annotations

THREAD_TARGET_PREFIX = "thread:"
LATEST_TARGET = "latest"


def pinned_thread_id(session_key: str) -> str | None:
    """Return the thread id when ``session_key`` pins a historical conversation."""
    text = session_key.strip()
    if not text.startswith(THREAD_TARGET_PREFIX):
        return None
    thread_id = text[len(THREAD_TARGET_PREFIX) :].strip()
    return thread_id or None


def thread_target_key(thread_id: str) -> str:
    return f"{THREAD_TARGET_PREFIX}{thread_id.strip()}"
