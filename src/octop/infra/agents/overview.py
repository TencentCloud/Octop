"""Per-agent kanban status aggregation for the dashboard overview.

Signals come from Octop's own infra layer (not the harness runtime):
lifecycle state in ``agents.last_state``, live invocation tracking in
``AgentManager``, pending HITL records in the gateway coordinator's store,
turn flags in ``WebSocketHub``, and thread/message persistence in the repos.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

KANBAN_NEEDS_YOU = "needs_you"
KANBAN_WORKING = "working"
KANBAN_DONE = "done"
KANBAN_IDLE = "idle"

KANBAN_STATUSES = (KANBAN_NEEDS_YOU, KANBAN_WORKING, KANBAN_DONE, KANBAN_IDLE)

_SNIPPET_MAX_CHARS = 80
_SNIPPET_SOURCE_ROLES = frozenset({"human", "user", "ai", "assistant"})
_SNIPPET_FETCH_ROWS = 5
# A reply that just landed reads as "done" even without unread (interactive
# dashboard turns never bump unread — only cron/proactive pushes and team
# replies do). Older resting conversations decay back to idle.
_DONE_WINDOW_SECONDS = 10 * 60


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _clean_block_text(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()


def _wire_text(wire: Any) -> str:
    """Best-effort plain text from one serialized message.

    Handles both shapes in ``thread_messages``: flat wires (``content`` at the
    top level) and LangChain ``message_to_dict`` envelopes (``data.content``).
    Thinking blocks (``<think>…</think>``) are stripped from model replies.
    """
    if not isinstance(wire, dict):
        return ""
    envelope = wire.get("data")
    payload = envelope if isinstance(envelope, dict) else wire
    content = payload.get("content")
    if isinstance(content, str):
        return _clean_block_text(content)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    cleaned = _clean_block_text(text)
                    if cleaned:
                        parts.append(cleaned)
        return " ".join(parts)
    return ""


def _clip_snippet(text: str) -> str:
    if len(text) <= _SNIPPET_MAX_CHARS:
        return text
    return text[: _SNIPPET_MAX_CHARS - 1].rstrip() + "…"


def _display_role(role: str) -> str:
    return "assistant" if role in ("ai", "assistant") else "user"


def _latest_message_snippet(services: Any, thread_id: str) -> dict[str, Any] | None:
    """Short text of the newest user/assistant message in *thread_id*."""
    try:
        rows, _has_more = services.thread_message_repo.page(thread_id, limit=_SNIPPET_FETCH_ROWS)
    except Exception:
        logger.debug("kanban snippet unavailable for thread %s", thread_id, exc_info=True)
        return None
    for row in reversed(rows):
        if row.role not in _SNIPPET_SOURCE_ROLES:
            continue
        try:
            text = _clip_snippet(_wire_text(json.loads(row.message_json)))
        except (TypeError, ValueError):
            continue
        if text:
            return {"role": _display_role(row.role), "text": text}
    return None


def _hitl_pending_payload(records: Sequence[Any]) -> dict[str, Any]:
    newest = records[0]
    return {
        "count": len(records),
        "thread_id": newest.thread_id,
        "created_at": newest.created_at,
    }


def _recently_replied(latest: Any, snippet: dict[str, Any] | None) -> bool:
    """True when the newest thread rests on a fresh assistant reply."""
    if latest is None or snippet is None:
        return False
    if snippet.get("role") != "assistant":
        return False
    return (latest.last_active or 0) >= time.time() - _DONE_WINDOW_SECONDS


def agent_kanban_statuses(
    server: Any,
    user_id: int,
    agent_rows: Sequence[Any],
    *,
    unread_by_agent: dict[str, int],
) -> dict[str, dict[str, Any]]:
    """Kanban extras per agent: bucket, busy flag, HITL/plan waits, latest thread."""
    app_runtime = server.app_runtime
    registry = app_runtime.agent_registry
    gateway = app_runtime.gateway
    services = server.services
    agent_ids = {row.agent_id for row in agent_rows}

    hitl_by_agent: dict[str, list[Any]] = {}
    for record in gateway.processor.hitl_coordinator.store.list_pending_by_user(user_id):
        hitl_by_agent.setdefault(record.agent_id, []).append(record)

    busy_agents = {aid for aid in agent_ids if registry.is_agent_active(aid)}
    for thread_id in gateway.ws_hub.active_turn_thread_ids():
        thread_row = gateway.thread_registry.get_thread(thread_id)
        if thread_row is not None and thread_row.agent_id in agent_ids:
            busy_agents.add(thread_row.agent_id)

    pending_plans = services.thread_repo.pending_plan_thread_ids(
        agent_ids=sorted(agent_ids), user_id=user_id
    )

    statuses: dict[str, dict[str, Any]] = {}
    for row in agent_rows:
        state = row.last_state or "unknown"
        hitl_records = hitl_by_agent.get(row.agent_id, [])
        plan_thread_ids = pending_plans.get(row.agent_id, [])
        threads = services.thread_repo.list_by_agent_user(
            agent_id=row.agent_id, user_id=user_id, limit=1
        )
        latest = threads[0] if threads else None
        snippet = _latest_message_snippet(services, latest.thread_id) if latest else None
        unread = unread_by_agent.get(row.agent_id, 0)

        if hitl_records or plan_thread_ids or state == "failed":
            bucket = KANBAN_NEEDS_YOU
        elif row.agent_id in busy_agents or state == "starting":
            bucket = KANBAN_WORKING
        elif unread > 0 or _recently_replied(latest, snippet):
            bucket = KANBAN_DONE
        else:
            bucket = KANBAN_IDLE

        # Cards deep-link to the conversation that needs the user, not just
        # the newest one: pending approval first, pending plan second.
        attention_thread_id: str | None = None
        if hitl_records:
            attention_thread_id = hitl_records[0].thread_id
        elif plan_thread_ids:
            attention_thread_id = plan_thread_ids[0]
        elif latest is not None:
            attention_thread_id = latest.thread_id

        statuses[row.agent_id] = {
            "kanban_status": bucket,
            "busy": row.agent_id in busy_agents,
            "hitl_pending": _hitl_pending_payload(hitl_records) if hitl_records else None,
            "pending_plan": bool(plan_thread_ids),
            "attention_thread_id": attention_thread_id,
            "latest_thread": (
                None
                if latest is None
                else {
                    "thread_id": latest.thread_id,
                    "title": latest.title,
                    "last_active": latest.last_active,
                    "message": snippet,
                }
            ),
        }
    return statuses
