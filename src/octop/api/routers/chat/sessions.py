"""Cross-agent session inbox — one aggregated row per agent for the signed-in user.

This is the only endpoint under the new ``/api/threads/*`` namespace (PLAN.md §2);
every per-agent thread route keeps living under ``/api/agents/{agent_id}/threads``.
The scan is bounded server-side by :data:`SUMMARY_SCAN_LIMIT` — deliberately not a
client parameter, so unknown query strings are ignored and the response body is
byte-identical with or without them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from octop.api.deps import current_user, get_server
from octop.infra.db.repos.projects import ThreadProjectRef
from octop.infra.db.repos.threads import ThreadRow
from octop.infra.gateway.threads import thread_row_has_messages
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter()

#: Server-side safety bound for the sidebar scan (PLAN.md §3 / SPEC §S-7).
#: Every count below is computed inside this window; it is not a request parameter.
SUMMARY_SCAN_LIMIT = 500


class SessionRowModel(BaseModel):
    """One pinned conversation, with the project it was dispatched from."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(description="Owning agent's public id.")
    thread_id: str = Field(description="Conversation id.")
    title: str | None = Field(description="Conversation title; null until the first turn.")
    channel_type: str = Field(description="Ingress channel that opened the thread.")
    last_active: int = Field(description="Unix seconds of the last turn; 0 means no turns yet.")
    created_at: int = Field(description="Unix seconds when the thread row was created.")
    has_messages: bool = Field(description="Whether any turn happened (title set or last_active).")
    pinned: bool = Field(description="Always true here — the row was pinned by the user.")
    project_id: str | None = Field(description="Project that dispatched this thread; null if none.")
    project_name: str | None = Field(description="That project's name; null if none.")


class ThreadSummaryRow(BaseModel):
    """One agent's slice of the inbox; only agents with at least one thread appear."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(description="Agent public id.")
    session_count: int = Field(description="How many of the user's threads this agent has.")
    has_activity: bool = Field(description="True when any of them had a turn.")
    last_active: int = Field(description="Newest last_active across them, in Unix seconds.")
    pinned: list[SessionRowModel] = Field(description="Pinned conversations, inbox order.")


def _session_row(row: ThreadRow, ref: ThreadProjectRef | None) -> SessionRowModel:
    return SessionRowModel(
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        title=row.title,
        channel_type=row.channel_type,
        last_active=row.last_active,
        created_at=row.created_at,
        has_messages=thread_row_has_messages(row),
        pinned=row.pinned,
        project_id=ref.project_id if ref else None,
        project_name=ref.project_name if ref else None,
    )


@router.get(
    "/threads/summary",
    summary="Cross-agent session inbox",
    response_model=list[ThreadSummaryRow],
)
async def list_thread_summary(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> list[ThreadSummaryRow]:
    """Aggregate the signed-in user's conversations into one row per agent.

    Visibility is the authenticated user, with no admin bypass (PLAN.md §5): the
    scan filters on ``threads.user_id`` only, so another user's thread ids and
    titles can never reach the response. Agents without threads are omitted rather
    than returned with a zero count; no conversations at all is ``200`` + ``[]``.
    """
    assert server.services is not None
    rows = server.services.thread_repo.list_by_user(
        user_id=user.id,
        limit=SUMMARY_SCAN_LIMIT,
    )
    if not rows:
        return []

    refs = server.services.project_repo.projects_by_thread([r.thread_id for r in rows])
    grouped: dict[str, list[ThreadRow]] = {}
    for row in rows:
        grouped.setdefault(row.agent_id, []).append(row)

    summary = [
        ThreadSummaryRow(
            agent_id=agent_id,
            session_count=len(group),
            has_activity=any(thread_row_has_messages(r) for r in group),
            last_active=max(r.last_active for r in group),
            pinned=[_session_row(r, refs.get(r.thread_id)) for r in group if r.pinned],
        )
        for agent_id, group in grouped.items()
    ]
    # Most recently active agent first; ties broken deterministically by id.
    summary.sort(key=lambda row: (-row.last_active, row.agent_id))
    return summary


__all__ = ["SUMMARY_SCAN_LIMIT", "SessionRowModel", "ThreadSummaryRow", "router"]
