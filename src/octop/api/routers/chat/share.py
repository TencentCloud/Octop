"""Read-only conversation share links.

Owners mint an unguessable URL. Anyone with the link can read the transcript,
including thinking and tool calls. Account identifiers and in-app file links
stay off the page.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.api.routers.chat.history import _agent_is_busy, _attach_message_authors, _require_thread
from octop.api.routers.chat.serialize import (
    _OFFLOAD_PLACEHOLDER_RE,
    _backfill_thread_projection,
    _load_projected_thread_messages,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.llm_text import strip_thinking

router = APIRouter()

_SHARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_PRIVATE_MARKDOWN_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
PUBLIC_SHARE_MESSAGE_LIMIT = 400


class ShareLinkBody(BaseModel):
    """Optional flags when creating or replacing a share link."""

    rotate: bool = Field(
        default=False,
        description="Revoke the current link and mint a new token.",
    )


def _server_timezone(server: Any) -> str:
    owners = (
        getattr(server, "config", None),
        getattr(getattr(server, "services", None), "config", None),
    )
    for owner in owners:
        raw = getattr(owner, "default_timezone", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "UTC"


def _redact_private_markdown(text: str) -> str:
    """Drop in-app file links. External links stay as written."""

    def replace(match: re.Match[str]) -> str:
        image = match.group(1) == "!"
        label = match.group(2).strip()
        target = match.group(3).strip()
        private = "/api/" in target or target.startswith("api/")
        if not private:
            return match.group(0)
        if image:
            return ""
        return label

    return _PRIVATE_MARKDOWN_RE.sub(replace, text).strip()


def _visible_text(raw: str, *, strip_model_thinking: bool) -> str:
    if _OFFLOAD_PLACEHOLDER_RE.match(raw):
        return ""
    text = strip_thinking(raw) if strip_model_thinking else raw
    return _redact_private_markdown(text.strip())


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_private_markdown(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _public_block(block: Any) -> dict[str, Any] | None:
    if isinstance(block, str):
        text = _visible_text(block, strip_model_thinking=True)
        return {"type": "text", "text": text} if text else None
    if not isinstance(block, dict):
        return None
    kind = str(block.get("type") or "").lower()
    if kind == "text":
        text = _visible_text(str(block.get("text") or ""), strip_model_thinking=True)
        return {"type": "text", "text": text} if text else None
    if kind == "thinking":
        text = _visible_text(str(block.get("thinking") or ""), strip_model_thinking=False)
        return {"type": "thinking", "thinking": text} if text else None
    if kind == "tool_use":
        name = block.get("name")
        row: dict[str, Any] = {
            "type": "tool_use",
            "name": name if isinstance(name, str) else "",
        }
        tool_id = block.get("id")
        if isinstance(tool_id, str) and tool_id:
            row["id"] = tool_id
        if "input" in block:
            row["input"] = _redact_value(block.get("input"))
        return row
    if kind == "tool_result":
        row = {"type": "tool_result"}
        name = block.get("name")
        if isinstance(name, str):
            row["name"] = name
        tool_id = block.get("id")
        if isinstance(tool_id, str) and tool_id:
            row["id"] = tool_id
        if "output" in block:
            row["output"] = _redact_value(block.get("output"))
        error = block.get("error_code")
        if isinstance(error, str) and error:
            row["error_code"] = error
        code = block.get("returncode")
        if isinstance(code, int) and not isinstance(code, bool):
            row["returncode"] = code
        return row
    return None


def public_conversation_messages(
    messages: list[dict[str, Any]],
    *,
    speaker_names: dict[str, str],
    default_agent_id: str,
) -> list[dict[str, Any]]:
    """Keep dialogue, thinking, and tool blocks. Drop account identifiers."""
    out: list[dict[str, Any]] = []
    for item in messages:
        role = item.get("role")
        if role not in ("user", "assistant", "tool"):
            continue
        content = item.get("content")
        blocks = content if isinstance(content, list) else [content]
        public_blocks = [
            block for block in (_public_block(raw) for raw in blocks) if block is not None
        ]
        if not public_blocks:
            continue
        row: dict[str, Any] = {"role": role, "content": public_blocks}
        timestamp = item.get("timestamp")
        if isinstance(timestamp, int) and not isinstance(timestamp, bool) and timestamp > 0:
            row["timestamp"] = timestamp
        decision = item.get("decision")
        if (
            role == "assistant"
            and isinstance(decision, dict)
            and decision.get("kind") == "decision"
        ):
            row["decision"] = decision
        if role == "user":
            author = item.get("author")
            name = ""
            if isinstance(author, dict):
                raw_name = author.get("display_name")
                if isinstance(raw_name, str):
                    name = raw_name.strip()
            if name:
                row["author_name"] = name[:80]
        elif role == "assistant":
            raw_agent = item.get("agent_id")
            agent_key = (
                raw_agent.strip() if isinstance(raw_agent, str) and raw_agent.strip() else ""
            )
            speaker = speaker_names.get(agent_key) or speaker_names.get(default_agent_id) or ""
            if speaker:
                row["speaker_name"] = speaker
        out.append(row)
    return out


def _share_status(row: Any) -> dict[str, Any]:
    return {
        "active": True,
        "share_id": row.share_id,
        "created_at": row.created_at,
    }


def _queue_projection(server: Any, agent_id: str, thread_id: str, user: Any) -> None:
    repo = server.services.thread_message_repo
    status = repo.projection_status(thread_id)
    if status == "ready" or _agent_is_busy(server, agent_id):
        return

    async def _work() -> None:
        await _backfill_thread_projection(server, agent_id, thread_id, user=user)

    accepted = server.app_runtime.gateway.history_backfill.enqueue(thread_id, _work)
    if accepted and status not in ("queued", "running"):
        repo.mark_projection(thread_id, "queued")


def _speaker_names(server: Any, agent_ids: set[str]) -> dict[str, str]:
    repo = getattr(getattr(server, "services", None), "agent_repo", None)
    get = getattr(repo, "get", None)
    if not callable(get):
        return {}
    names: dict[str, str] = {}
    for agent_id in agent_ids:
        if not agent_id:
            continue
        row = get(agent_id)
        name = getattr(row, "name", None)
        if isinstance(name, str) and name.strip():
            names[agent_id] = name.strip()
    return names


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/share",
    summary="Conversation share link",
)
async def get_thread_share(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the owner's live read-only link, if one exists."""
    row = _require_thread(server, agent_id, thread_id, user, as_user, write=True)
    share = server.services.thread_share_repo.get_active_by_thread(row.thread_id)
    if share is None:
        return {"active": False, "share_id": None, "created_at": None}
    return _share_status(share)


@router.post(
    "/agents/{agent_id}/threads/{thread_id}/share",
    summary="Create a conversation share link",
)
async def create_thread_share(
    agent_id: str,
    thread_id: str,
    body: ShareLinkBody | None = None,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Mint a read-only link, or return the one that is already live.

    ``rotate`` revokes the previous token. The public page shows the
    transcript, including thinking and tool calls.
    """
    row = _require_thread(server, agent_id, thread_id, user, as_user, write=True)
    effective_uid = as_user if as_user is not None else user.id
    repo = server.services.thread_share_repo
    if body is not None and body.rotate:
        share = repo.rotate(
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            created_by=effective_uid,
        )
    else:
        share = repo.ensure(
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            created_by=effective_uid,
        )
    _queue_projection(server, row.agent_id, row.thread_id, user)
    return _share_status(share)


@router.delete(
    "/agents/{agent_id}/threads/{thread_id}/share",
    status_code=204,
    summary="Revoke a conversation share link",
)
async def revoke_thread_share(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Invalidate the live link. Older tokens stop opening the transcript."""
    row = _require_thread(server, agent_id, thread_id, user, as_user, write=True)
    server.services.thread_share_repo.revoke(row.thread_id)


@router.get(
    "/shares/{share_id}",
    summary="Read a shared conversation",
    description=(
        "Public, read-only transcript for one share token. "
        "Includes thinking and tool calls. Omits account ids and in-app file links."
    ),
)
async def get_public_share(
    share_id: str,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Serve the shared dialogue. A missing or revoked token is not found."""
    if not _SHARE_ID_RE.fullmatch(share_id):
        raise OctopError(ErrorCode.NOT_FOUND, "share not found")
    share = server.services.thread_share_repo.get_active_by_token(share_id)
    if share is None:
        raise OctopError(ErrorCode.NOT_FOUND, "share not found")
    thread = server.services.thread_repo.get(share.thread_id)
    if thread is None or thread.agent_id != share.agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "share not found")
    projection = server.services.thread_message_repo.projection_status(share.thread_id)
    messages, truncated = _load_projected_thread_messages(
        server,
        share.agent_id,
        share.thread_id,
        PUBLIC_SHARE_MESSAGE_LIMIT,
        user=None,
        include_tool_media=False,
    )
    _attach_message_authors(server, messages, owner_user_id=thread.user_id)
    agent_ids = {share.agent_id}
    for item in messages:
        raw_agent = item.get("agent_id")
        if isinstance(raw_agent, str) and raw_agent.strip():
            agent_ids.add(raw_agent.strip())
    names = _speaker_names(server, agent_ids)
    agent_name = names.get(share.agent_id, "")
    title = thread.title.strip() if isinstance(thread.title, str) else ""
    return {
        "title": title,
        "agent_name": agent_name,
        "timezone": _server_timezone(server),
        "ready": projection == "ready",
        "truncated": truncated,
        "messages": public_conversation_messages(
            messages,
            speaker_names=names,
            default_agent_id=share.agent_id,
        ),
    }
