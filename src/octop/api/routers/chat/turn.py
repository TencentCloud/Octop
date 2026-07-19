"""Dashboard turn preparation (thread, MCP, skills, InboundMessage)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness_gateway.models import (
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
)

from octop.api.common.agent import require_agent_row
from octop.api.common.validators import validate_chat_mcp_servers, validate_chat_skills
from octop.api.routers.chat.models import ChatTurnBody
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.media.attachment_hints import (
    inbound_attachments_from_parts,
    is_vision_attachment,
)
from octop.infra.gateway.media.inbound_store import inbound_rel_path
from octop.infra.gateway.process.message_keys import (
    COMPOSER_CTX_KEY,
    INBOUND_ATTACHMENTS_KEY,
)
from octop.infra.gateway.process.usage_record import extract_usage_from_chunk
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws import WS_CHANNEL_ID

__all__ = [
    "COMPOSER_CTX_KEY",
    "INBOUND_ATTACHMENTS_KEY",
    "build_composer_context",
    "build_dashboard_inbound",
    "content_parts_from_dashboard_turn",
    "extract_usage_from_chunk",
    "prepare_dashboard_turn",
    "turn_has_content",
]


def build_composer_context(
    *,
    mcp_servers: list[str] | None,
    skills: list[str] | None,
    target_agent_ids: list[str] | None,
    model_ref: str | None,
    default_model: str | None,
) -> dict[str, Any] | None:
    """Snapshot of per-turn composer selections for history display."""
    ctx: dict[str, Any] = {}
    if mcp_servers:
        ctx["connectors"] = list(mcp_servers)
    if skills:
        ctx["skills"] = list(skills)
    if target_agent_ids:
        ctx["targetAgents"] = [str(x) for x in target_agent_ids]
    model = (model_ref or "").strip()
    default = (default_model or "").strip()
    if model and model != default:
        ctx["model"] = model
    return ctx or None


@dataclass
class PreparedDashboardTurn:
    thread_id: str
    session_key: str
    mcp_servers: list[str] | None
    skills: list[str] | None
    model_ref: str | None
    inbound_content: list[ContentPart]
    composer_context: dict[str, Any] | None
    inbound_attachments: list[dict[str, str]]


async def resolve_thread_id(
    *,
    agent_id: str,
    user_id: int,
    thread_registry: Any,
    thread_id: str | None,
    session_key: str | None,
) -> tuple[str, str]:
    sk = session_key or ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id)
    if thread_id:
        row = thread_registry.get_thread(thread_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
        await thread_registry.rebind(session_key=sk, thread_id=thread_id, agent_id=agent_id)
        return thread_id, sk
    bound = thread_registry.get_bound_thread_id(sk)
    if bound:
        return bound, sk
    tid = await thread_registry.get_or_create_by_key(
        session_key=sk,
        agent_id=agent_id,
        user_id=user_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
    )
    return tid, sk


def _turn_plain_text(turn: ChatTurnBody) -> str:
    text = (turn.text or "").strip()
    if text:
        return text
    if not turn.messages:
        return ""
    last = turn.messages[-1]
    if not isinstance(last, dict) or str(last.get("role") or "").lower() != "user":
        return ""
    content = last.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and str(block.get("type") or "") == "text":
                t = str(block.get("text") or "").strip()
                if t:
                    return t
    return ""


def _message_content_nonempty(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "")
        if btype == "text" and str(block.get("text") or "").strip():
            return True
        if btype in ("image", "file", "image_url"):
            return True
    return False


def turn_has_content(turn: ChatTurnBody) -> bool:
    """True when the turn has user text or structured message blocks."""
    if _turn_plain_text(turn):
        return True
    for msg in reversed(turn.messages):
        if str(msg.get("role") or "").lower() != "user":
            continue
        return _message_content_nonempty(msg.get("content"))
    return False


def _mime_from_block(block: dict[str, Any]) -> str:
    source_raw = block.get("source")
    source: dict[str, Any] = source_raw if isinstance(source_raw, dict) else {}
    for key in ("media_type", "mime_type"):
        raw = source.get(key) if key in source else block.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().split(";", 1)[0].lower()
    return "application/octet-stream"


def _workspace_path_from_block(block: dict[str, Any]) -> str | None:
    for key in ("workspace_path", "workspacePath"):
        raw = block.get(key)
        if isinstance(raw, str) and raw.strip():
            return inbound_rel_path(raw.strip())
    return None


def content_parts_from_dashboard_turn(turn: ChatTurnBody) -> list[ContentPart]:
    """Convert dashboard WS ``messages`` / ``text`` into gateway ContentParts.

    Attachments must already live under workspace ``inbound/`` (via upload).
    Preview URLs are ignored — only ``workspace_path`` matters.
    """
    parts: list[ContentPart] = []
    text = _turn_plain_text(turn)
    if text:
        parts.append(TextContent(text=text))

    user_content: Any = None
    for msg in reversed(turn.messages):
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "").lower() != "user":
            continue
        user_content = msg.get("content")
        break

    if not isinstance(user_content, list):
        return parts

    seen_text = bool(text)
    for block in user_content:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "")
        if btype == "text":
            t = str(block.get("text") or "").strip()
            if t and not seen_text:
                parts.append(TextContent(text=t))
                seen_text = True
            continue

        if btype not in ("image", "file", "image_url"):
            continue

        path = _workspace_path_from_block(block)
        if not path:
            # Upload always returns workspace_path; ignore preview-only blocks.
            continue

        media_type = _mime_from_block(block)
        filename = str(
            block.get("filename") or block.get("name") or Path(path).name or "attachment"
        )
        use_vision = is_vision_attachment(
            kind="image" if btype in ("image", "image_url") else btype,
            media_type=media_type,
            path=path,
        )
        if use_vision:
            parts.append(
                ImageContent(
                    local_path=path,
                    mime_type=media_type if media_type.startswith("image/") else "image/png",
                    alt_text=filename,
                )
            )
        else:
            parts.append(
                FileContent(
                    local_path=path,
                    filename=filename,
                    mime_type=media_type or "application/octet-stream",
                )
            )
    return parts


async def prepare_dashboard_turn(
    server: Any,
    *,
    agent_id: str,
    user: Any,
    turn: ChatTurnBody,
) -> PreparedDashboardTurn:
    """Validate MCP/skills, resolve thread, return data for gateway enqueue."""
    row = require_agent_row(agent_id, user=user, as_user=None, server=server)
    default_model = (row.default_model or "").strip() or None

    mcp_servers = await validate_chat_mcp_servers(server, user_id=user.id, names=turn.mcp_servers)
    skills = await validate_chat_skills(
        server,
        agent_id=agent_id,
        user=user,
        names=turn.skills,
    )
    if mcp_servers:
        failed = await server.app_runtime.agent_registry.prepare_chat_mcp(
            agent_id,
            mcp_servers,
            connector_user_id=user.id,
        )
        if failed:
            locale = getattr(user, "locale", None) or "zh"
            raise OctopError.localized(
                ErrorCode.CONNECTOR_MCP_LOAD_FAILED,
                locale,
                servers=", ".join(failed),
            )

    thread_registry = server.app_runtime.gateway.thread_registry
    thread_id, session_key = await resolve_thread_id(
        agent_id=agent_id,
        user_id=user.id,
        thread_registry=thread_registry,
        thread_id=turn.thread_id,
        session_key=turn.session_key,
    )
    model_ref = (turn.default_model or "").strip() or None
    target_ids = [str(x) for x in turn.target_agent_ids] if turn.target_agent_ids else None
    composer_ctx = build_composer_context(
        mcp_servers=mcp_servers,
        skills=skills,
        target_agent_ids=target_ids,
        model_ref=model_ref,
        default_model=default_model,
    )
    inbound_content = content_parts_from_dashboard_turn(turn)
    inbound_attachments = inbound_attachments_from_parts(inbound_content)
    return PreparedDashboardTurn(
        thread_id=thread_id,
        session_key=session_key,
        mcp_servers=mcp_servers,
        skills=skills,
        model_ref=model_ref,
        inbound_content=inbound_content,
        composer_context=composer_ctx,
        inbound_attachments=inbound_attachments,
    )


def build_dashboard_inbound(
    *,
    agent_id: str,
    user_id: int,
    prepared: PreparedDashboardTurn,
    turn: ChatTurnBody,
    ws_connection_id: str,
    user_is_admin: bool = False,
) -> InboundMessage:
    metadata: dict[str, Any] = {
        "ws_connection_id": ws_connection_id,
        "session_key": prepared.session_key,
        "thread_id": prepared.thread_id,
        "user_is_admin": user_is_admin,
    }
    if prepared.mcp_servers:
        metadata["mcp_servers"] = prepared.mcp_servers
    if prepared.skills is not None:
        metadata["skills"] = prepared.skills
    if prepared.model_ref:
        metadata["model"] = prepared.model_ref
    if prepared.composer_context:
        metadata[COMPOSER_CTX_KEY] = prepared.composer_context
    if prepared.inbound_attachments:
        metadata[INBOUND_ATTACHMENTS_KEY] = prepared.inbound_attachments
    merge_turn_target_agents(turn, metadata)

    return InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        tenant_id=agent_id,
        channel_subject=ChannelSubject(subject_id=str(user_id)),
        channel_session_id=prepared.session_key,
        content=list(prepared.inbound_content),
        metadata=metadata,
    )


def merge_turn_target_agents(turn: ChatTurnBody, metadata: dict[str, Any]) -> None:
    if turn.target_agent_ids:
        metadata["target_agent_ids"] = [str(x) for x in turn.target_agent_ids]
