"""Per-agent kanban status aggregation for the dashboard overview.

Signals come from Octop's own infra layer (not the harness runtime):
lifecycle state in ``agents.last_state``, live invocation tracking in
``AgentManager``, pending HITL records in the gateway coordinator's store,
turn flags in ``WebSocketHub``, and thread/message persistence in the repos.

Kanban FSM (two-layer, aligned with the industry agent-board pattern):

1. **activity_state** — mutually exclusive live state::

       blocked  → HITL pending, or agent failed
       waiting  → plan awaiting approval (and not currently executing)
       working  → turn in flight / starting
       done     → latest turn finished on an assistant reply
       idle     → nothing to show

2. **unseen** — the current activity has not been acknowledged
   (``sessions.last_read_at`` / unread). Opening chat mark-reads.

3. **display_state** — ``done && !unseen → idle``; otherwise ``activity_state``.
   Completed work stays in Done until the user opens it, then settles to Idle.

4. **kanban_status** (bucket) — column for the card::

       blocked|waiting → needs_you
       working         → working
       done            → done
       idle            → idle
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any, Literal

logger = logging.getLogger(__name__)

KANBAN_NEEDS_YOU = "needs_you"
KANBAN_WORKING = "working"
KANBAN_DONE = "done"
KANBAN_IDLE = "idle"

KANBAN_STATUSES = (KANBAN_NEEDS_YOU, KANBAN_WORKING, KANBAN_DONE, KANBAN_IDLE)

ActivityState = Literal["working", "blocked", "waiting", "done", "idle"]
ACTIVITY_WORKING: ActivityState = "working"
ACTIVITY_BLOCKED: ActivityState = "blocked"
ACTIVITY_WAITING: ActivityState = "waiting"
ACTIVITY_DONE: ActivityState = "done"
ACTIVITY_IDLE: ActivityState = "idle"

_SNIPPET_MAX_CHARS = 80
_SNIPPET_SOURCE_ROLES = frozenset({"human", "user", "ai", "assistant"})
_SNIPPET_FETCH_ROWS = 5


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# Card previews are plain text — strip common markdown emphasis markers.
_MD_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_MD_CODE_RE = re.compile(r"`([^`]+)`")


def _clean_block_text(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()


def _plain_snippet_text(text: str) -> str:
    """Collapse light markdown so Kanban cards do not show raw ``**`` / backticks."""
    plain = _MD_BOLD_RE.sub(r"\2", text)
    return _MD_CODE_RE.sub(r"\1", plain)


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
    plain = _plain_snippet_text(text)
    if len(plain) <= _SNIPPET_MAX_CHARS:
        return plain
    return plain[: _SNIPPET_MAX_CHARS - 1].rstrip() + "…"


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


def resolve_activity_state(
    *,
    hitl_pending: bool,
    failed: bool,
    awaiting_plan: bool,
    busy: bool,
    assistant_last: bool,
    has_unread: bool = False,
) -> ActivityState:
    """Mutually exclusive live state (priority: blocked > working > waiting > done > idle).

    Working outranks a leftover plan wait: once execution has started, the card
    must not stay in attention for a stale ``pending_plan_path``. Unread without
    a snippet still counts as a finished turn waiting to be opened.
    """
    if hitl_pending or failed:
        return ACTIVITY_BLOCKED
    if busy:
        return ACTIVITY_WORKING
    if awaiting_plan:
        return ACTIVITY_WAITING
    if assistant_last or has_unread:
        return ACTIVITY_DONE
    return ACTIVITY_IDLE


def resolve_unseen(
    *,
    activity: ActivityState,
    unread: int,
    latest_active: int,
    last_read_at: int,
) -> bool:
    """Whether the current activity still needs the user's eyes.

    Attention (blocked/waiting) is always unseen while the wait exists.
    Done is unseen until mark-read moves ``last_read_at`` past the turn, or
    while unread remains. Working/idle do not pin the Done column.
    """
    if activity in (ACTIVITY_BLOCKED, ACTIVITY_WAITING):
        return True
    if unread > 0:
        return True
    if activity == ACTIVITY_DONE:
        return latest_active > last_read_at
    return False


def resolve_display_state(activity: ActivityState, *, unseen: bool) -> ActivityState:
    """Completed work settles to idle once acknowledged."""
    if activity == ACTIVITY_DONE and not unseen:
        return ACTIVITY_IDLE
    return activity


def bucket_for_display_state(display: ActivityState) -> str:
    if display in (ACTIVITY_BLOCKED, ACTIVITY_WAITING):
        return KANBAN_NEEDS_YOU
    if display == ACTIVITY_WORKING:
        return KANBAN_WORKING
    if display == ACTIVITY_DONE:
        return KANBAN_DONE
    return KANBAN_IDLE


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
    sorted_ids = sorted(agent_ids)

    hitl_by_agent: dict[str, list[Any]] = {}
    for record in gateway.processor.hitl_coordinator.store.list_pending_by_user(user_id):
        hitl_by_agent.setdefault(record.agent_id, []).append(record)

    busy_agents = {aid for aid in agent_ids if registry.is_agent_active(aid)}
    for thread_id in gateway.ws_hub.active_turn_thread_ids():
        thread_row = gateway.thread_registry.get_thread(thread_id)
        if thread_row is not None and thread_row.agent_id in agent_ids:
            busy_agents.add(thread_row.agent_id)

    pending_plans = services.thread_repo.pending_plan_thread_ids(
        agent_ids=sorted_ids, user_id=user_id
    )
    last_read_by_agent = services.session_repo.last_read_at_by_agent(user_id, sorted_ids)

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
        last_read_at = last_read_by_agent.get(row.agent_id, 0)

        busy = row.agent_id in busy_agents or state == "starting"
        # Stale pending_plan_path must not pin attention once execution started.
        awaiting_plan = bool(plan_thread_ids) and not busy
        assistant_last = bool(snippet and snippet.get("role") == "assistant")

        activity = resolve_activity_state(
            hitl_pending=bool(hitl_records),
            failed=state == "failed",
            awaiting_plan=awaiting_plan,
            busy=busy,
            assistant_last=assistant_last,
            has_unread=unread > 0,
        )
        unseen = resolve_unseen(
            activity=activity,
            unread=unread,
            latest_active=(latest.last_active or 0) if latest is not None else 0,
            last_read_at=last_read_at,
        )
        display = resolve_display_state(activity, unseen=unseen)
        bucket = bucket_for_display_state(display)

        # Cards deep-link to the conversation that needs the user, not just
        # the newest one: pending approval first, pending plan second.
        attention_thread_id: str | None = None
        if hitl_records:
            attention_thread_id = hitl_records[0].thread_id
        elif awaiting_plan:
            attention_thread_id = plan_thread_ids[0]
        elif latest is not None:
            attention_thread_id = latest.thread_id

        statuses[row.agent_id] = {
            "kanban_status": bucket,
            "activity_state": activity,
            "unseen": unseen,
            "busy": row.agent_id in busy_agents,
            "hitl_pending": _hitl_pending_payload(hitl_records) if hitl_records else None,
            "pending_plan": awaiting_plan,
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
