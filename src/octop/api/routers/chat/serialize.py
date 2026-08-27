"""Thread history loading and LangGraph message serialization."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import messages_from_dict
from langchain_core.runnables import RunnableConfig

from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.i18n.domains.attachment import attachment_empty_image
from octop.infra.agents.context_breakdown import usage_dict_from_message
from octop.infra.gateway.process.message_keys import (
    COMPOSER_CTX_KEY,
    INBOUND_ATTACHMENTS_KEY,
)
from octop.infra.utils.llm_text import strip_thinking as _strip_thinking
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)

_THINKING_CAPTURE_RE = re.compile(
    r"<think>([\s\S]*?)</think>\s*",
    re.IGNORECASE,
)

# Matches the lightweight placeholder that ``MediaOffloadMiddleware`` writes
# into LangGraph state for already-offloaded inline images / audio. Format
# (see harness_agent.middleware.media_offload._placeholder_text_block):
#   [<btype> offloaded: sha=<short_sha> path=<path> size=<n>B mime=<m>;
#   use read_file to retrieve bytes]
# We strip these on history serialization because the original bytes are
# still available via ``inbound_attachments`` and the dashboard renders the
# thumbnail from there — leaving the placeholder visible made the chat show
# a "[image offloaded: sha=… path=…]" line under every user image after the
# second turn (when the middleware first re-encountered the block).
_OFFLOAD_PLACEHOLDER_RE = re.compile(
    r"^\s*\[\s*(?:image|audio)\s+offloaded\s*:",
    re.IGNORECASE,
)

# Must match harness_agent.agent.CHECKPOINT_TS_KEY (epoch-ms in additional_kwargs).
CHECKPOINT_TS_KEY = "checkpoint_ts"

HISTORY_DEFAULT_LIMIT = 25
HISTORY_MAX_LIMIT = 200


def _clamp_history_limit(limit: int) -> int:
    return max(1, min(limit, HISTORY_MAX_LIMIT))


def _is_offload_placeholder_block(block: Any) -> bool:
    """True when *block* is a ``MediaOffloadMiddleware`` placeholder.

    The middleware rewrites an inline image/audio block into a single text
    block of the form ``[image offloaded: sha=… path=… size=…B mime=…; use
    read_file to retrieve bytes]`` on every turn after the first one. We
    must not surface that text in the dashboard: the original attachment
    is still available via ``inbound_attachments`` and the UI renders the
    image from there. Showing the placeholder underneath is a UX bug.
    """
    if not isinstance(block, dict):
        return False
    if str(block.get("type") or "").lower() != "text":
        return False
    text = str(block.get("text") or "")
    return bool(_OFFLOAD_PLACEHOLDER_RE.match(text))


def _user_message_has_image_attachment(additional_kwargs: Any) -> bool:
    """True if the persisted ``INBOUND_ATTACHMENTS_KEY`` carries any image."""
    if not isinstance(additional_kwargs, dict):
        return False
    raw = additional_kwargs.get(INBOUND_ATTACHMENTS_KEY)
    if not isinstance(raw, list):
        return False
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").lower()
        media_type = str(item.get("media_type") or item.get("mediaType") or "")
        if kind == "image" or media_type.lower().startswith("image/"):
            return True
    return False


def _is_attachment_path_hint_text(text: str) -> bool:
    """True when *text* is an LLM-only ``[Attachment]/`` / ``[附件]`` path hint."""
    stripped = text.strip()
    if not stripped:
        return False
    first = stripped.split("\n", 1)[0].strip()
    return first.startswith("[Attachment] ") or first.startswith("[附件] ")


def _strip_attachment_hints_from_text(text: str) -> str:
    """Drop blank-line-separated attachment path-hint sections from user text."""
    parts = re.split(r"\n\n+", text)
    kept = [part for part in parts if part.strip() and not _is_attachment_path_hint_text(part)]
    return "\n\n".join(kept).strip()


def _workspace_url_path(url: str) -> str:
    if url.startswith("workspace://"):
        return url[len("workspace://") :].lstrip("/")
    return ""


def _is_history_noise_image_block(block: Any) -> bool:
    """True for vision blocks that must not appear as user-authored history text."""
    if not isinstance(block, dict):
        return False
    if str(block.get("type") or "").lower() != "image_url":
        return False
    if str(block.get("workspace_path") or "").strip():
        return True
    url_field = block.get("image_url")
    url = ""
    if isinstance(url_field, dict):
        url = str(url_field.get("url") or "")
    elif isinstance(url_field, str):
        url = url_field
    return url.startswith("data:") or url.startswith("workspace://")


def _attachment_meta_from_image_block(block: dict[str, Any]) -> dict[str, str] | None:
    """Build ``inbound_attachments`` row from a path-only / data vision block."""
    path = str(block.get("workspace_path") or "").strip()
    url_field = block.get("image_url")
    url = ""
    if isinstance(url_field, dict):
        url = str(url_field.get("url") or "")
    elif isinstance(url_field, str):
        url = url_field
    if not path:
        path = _workspace_url_path(url)
    if not path and not url.startswith("data:"):
        return None
    mime = str(
        block.get("mime_type") or block.get("media_type") or block.get("mediaType") or ""
    ).strip()
    if not mime and url.startswith("data:"):
        mime = url[5:].split(";", 1)[0] or "image/png"
    if not mime:
        mime = "image/png"
    filename = str(block.get("filename") or block.get("name") or "").strip()
    if not filename and path:
        filename = Path(path).name
    if not filename:
        filename = "image"
    entry: dict[str, str] = {
        "filename": filename,
        "media_type": mime,
        "kind": "image",
    }
    if path:
        entry["workspace_path"] = path if path.startswith("inbound/") else f"inbound/{path}"
    return entry


def _parse_image_ref_json_text(text: str) -> dict[str, Any] | None:
    """Return an ``image_url`` dict when *text* is a dumped vision ref (UI noise)."""
    stripped = text.strip()
    if not stripped.startswith("{") or "image_url" not in stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and _is_history_noise_image_block(parsed):
        return parsed
    return None


def _extract_dumped_image_refs_from_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Pull harness JSONL-style vision dumps out of user text.

    ``MemoryMiddleware._stringify_content`` joins text blocks and
    ``json.dumps(image_url_block)`` with newlines. Session-log history
    therefore arrives as one string like::

        这图是啥
        {"type": "image_url", "workspace_path": "inbound/…", …}

    Returns ``(cleaned_caption, image_ref_dicts)``.
    """
    if not text or "image_url" not in text:
        return text, []
    refs: list[dict[str, Any]] = []
    kept: list[str] = []
    for part in text.split("\n"):
        parsed = _parse_image_ref_json_text(part)
        if parsed is not None:
            refs.append(parsed)
            continue
        kept.append(part)
    if not refs:
        return text, []
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return cleaned, refs


def _collect_inbound_from_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Harvest attachment metadata from vision blocks / dumped JSON text blocks."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(candidate: dict[str, Any]) -> None:
        meta = _attachment_meta_from_image_block(candidate)
        if meta is None:
            return
        key = meta.get("workspace_path") or meta.get("filename") or ""
        if key in seen:
            return
        seen.add(key)
        out.append(meta)

    for block in blocks:
        if not isinstance(block, dict):
            continue
        if _is_history_noise_image_block(block):
            _push(block)
            continue
        if str(block.get("type") or "").lower() != "text":
            continue
        _cleaned, candidates = _extract_dumped_image_refs_from_text(str(block.get("text") or ""))
        for candidate in candidates:
            _push(candidate)
    return out


def _strip_image_only_text_blocks(
    blocks: list[dict[str, Any]],
    *,
    locale: str,
) -> list[dict[str, Any]]:
    """Drop placeholders + the LLM-facing "User sent an image." sentinel.

    Only safe when the original image is also being delivered to the
    dashboard via ``inbound_attachments``; if not, removing the text
    would make a pure-image turn look empty in the UI.
    """
    return _strip_attachment_llm_noise(blocks, locale=locale, strip_empty_image=True)


def _strip_attachment_llm_noise(
    blocks: list[dict[str, Any]],
    *,
    locale: str,
    strip_empty_image: bool,
) -> list[dict[str, Any]]:
    """Remove LLM-only attachment noise from history content blocks.

    Strips MediaOffload placeholders, optional empty-image sentinels, path-hint
    text sections (``[附件]`` / ``[Attachment]``), dumped ``image_url`` JSON text,
    and ``image_url`` blocks that the dashboard renders via ``inbound_attachments``.
    """
    empty_image = (
        attachment_empty_image(normalize_locale(locale)).strip() if strip_empty_image else ""
    )
    out: list[dict[str, Any]] = []
    for block in blocks:
        if _is_offload_placeholder_block(block):
            continue
        if _is_history_noise_image_block(block):
            continue
        if not isinstance(block, dict) or str(block.get("type") or "").lower() != "text":
            out.append(block)
            continue
        text = str(block.get("text") or "")
        original = text
        text, _image_refs = _extract_dumped_image_refs_from_text(text)
        if empty_image and text.strip() == empty_image:
            continue
        cleaned = _strip_attachment_hints_from_text(text)
        if not cleaned:
            continue
        if cleaned != original:
            out.append({**block, "text": cleaned})
        else:
            out.append(block)
    return out


def _user_locale(user: Any) -> str:
    raw = getattr(user, "locale", None) if user is not None else None
    return normalize_locale(str(raw) if raw else None)


def _slice_message_page(
    raw: list[Any],
    *,
    limit: int,
    offset: int,
) -> tuple[list[Any], bool]:
    """Return a chronological page skipping *offset* messages from the end."""
    if not raw:
        return [], False
    offset = max(0, offset)
    end_idx = len(raw) - offset
    if end_idx <= 0:
        return [], False
    start_idx = max(0, end_idx - limit)
    page = raw[start_idx:end_idx]
    has_more = len(raw) > offset + limit
    return page, has_more


def _epoch_to_ms(raw: int | float) -> int:
    return int(raw) if raw > 1_000_000_000_000 else int(raw * 1000)


async def _load_checkpoint_messages(
    harness: Any,
    thread_id: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[Any], bool]:
    """Load LangGraph messages for a thread from the agent checkpointer."""
    fetch_limit = offset + limit + 1
    if hasattr(harness, "aget_history"):
        try:
            msgs = list(await harness.aget_history(thread_id, limit=fetch_limit))
            if msgs:
                return _slice_message_page(msgs, limit=limit, offset=offset)
        except Exception:
            logger.warning(
                "aget_history failed for thread=%s",
                thread_id,
                exc_info=True,
            )
    if hasattr(harness, "graph"):
        try:
            state = await harness.graph.aget_state({"configurable": {"thread_id": thread_id}})
            raw = list((state.values or {}).get("messages") or [])
            return _slice_message_page(raw, limit=limit, offset=offset)
        except Exception:
            logger.warning(
                "graph.aget_state failed for thread=%s",
                thread_id,
                exc_info=True,
            )
    return [], False


async def _load_thread_messages(
    server: Any,
    agent_id: str,
    thread_id: str,
    limit: int,
    *,
    user: Any,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    out: list[dict[str, Any]] = []
    has_more = False
    registry = server.app_runtime.agent_registry
    try:
        harness = registry.get_agent(agent_id)
        raw_messages, has_more = await _load_checkpoint_messages(
            harness,
            thread_id,
            limit,
            offset,
        )
        for m in raw_messages:
            entry = _serialize_history_message(m, user=user)
            if entry is not None:
                out.append(entry)
    except Exception:
        logger.exception("failed to load history for agent=%s thread=%s", agent_id, thread_id)

    if out:
        # Sync URL rewrite only — no workspace file import (that belongs on live stream).
        return _enrich_history_tool_media(out, agent_id=agent_id), has_more

    return await _load_thread_messages_from_sessions(
        server,
        agent_id,
        thread_id,
        limit,
        offset=offset,
        user=user,
    )


def _isolated_sqlite_checkpoint_messages(
    harness: Any,
    thread_id: str,
) -> list[Any] | None:
    """Read the newest SQLite checkpoint through a separate read-only connection.

    ``None`` means the harness is not backed by a discoverable SQLite saver.
    Once SQLite is detected, failures are raised instead of falling back to the
    live saver connection: availability of new turns is more important than a
    legacy UI backfill.
    """
    checkpoint = getattr(harness, "_checkpointer_instance", None)
    if checkpoint is None:
        return None

    backend = getattr(checkpoint, "_backend", None)
    raw_path = getattr(backend, "_db_path", None)
    saver = getattr(checkpoint, "_checkpointer", checkpoint)
    disk_saver = getattr(saver, "_disk", saver)
    live_conn = getattr(disk_saver, "conn", None)
    if raw_path is None and isinstance(live_conn, sqlite3.Connection):
        rows = live_conn.execute("PRAGMA database_list").fetchall()
        raw_path = next((row[2] for row in rows if row[1] == "main"), None)
    if raw_path is None or str(raw_path) == ":memory:":
        return None

    from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: PLC0415

    uri = f"{Path(raw_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        isolated = SqliteSaver(conn=conn, serde=getattr(disk_saver, "serde", None))
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        for checkpoint_tuple in isolated.list(config, limit=1):
            messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])
            return list(messages) if isinstance(messages, list) else []
        return []
    finally:
        conn.close()


def _load_projected_thread_messages(
    server: Any,
    agent_id: str,
    thread_id: str,
    limit: int,
    *,
    user: Any,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    """Read one page without touching the agent checkpoint database."""
    rows, has_more = server.services.thread_message_repo.page(
        thread_id,
        limit=limit,
        offset=offset,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            wire = json.loads(row.message_json)
            message = messages_from_dict([wire])[0]
        except Exception:
            logger.warning(
                "invalid projected history row thread=%s seq=%s",
                thread_id,
                row.seq,
                exc_info=True,
            )
            continue
        entry = _serialize_history_message(message, user=user)
        if entry is not None:
            out.append(entry)
    return _enrich_history_tool_media(out, agent_id=agent_id), has_more


async def _backfill_thread_projection(
    server: Any,
    agent_id: str,
    thread_id: str,
    *,
    user: Any,
) -> None:
    """Decode one legacy checkpoint off-request and atomically publish it."""
    repo = server.services.thread_message_repo
    registry = server.app_runtime.agent_registry
    reserve = getattr(registry, "try_begin_history_backfill", None)
    release = getattr(registry, "end_history_backfill", None)
    reserved = reserve(agent_id) if callable(reserve) else True
    if reserved is False:
        await asyncio.to_thread(repo.mark_projection, thread_id, "pending")
        return
    try:
        await asyncio.to_thread(repo.mark_projection, thread_id, "running")
        harness = registry.get_agent(agent_id)
        raw = await asyncio.to_thread(
            _isolated_sqlite_checkpoint_messages,
            harness,
            thread_id,
        )
        if raw is None:
            raw, _has_more = await _load_checkpoint_messages(
                harness,
                thread_id,
                1_000_000,
                0,
            )
        if not raw:
            session_rows, _ = await _load_thread_messages_from_sessions(
                server,
                agent_id,
                thread_id,
                1_000_000,
                offset=0,
                user=user,
            )
            raw = session_rows
        from octop.infra.gateway.process.history_projection import message_inputs  # noqa: PLC0415

        projected = await asyncio.to_thread(message_inputs, list(raw))
        await asyncio.to_thread(repo.replace_all, thread_id, projected)
    except Exception as exc:
        logger.exception("history projection backfill failed for thread=%s", thread_id)
        await asyncio.to_thread(
            repo.mark_projection,
            thread_id,
            "failed",
            error=str(exc)[:500],
        )
    finally:
        if callable(release):
            release(agent_id)


def _enrich_history_tool_media(
    messages: list[dict[str, Any]],
    *,
    agent_id: str,
) -> list[dict[str, Any]]:
    """Attach preview URLs for tool media without disk I/O."""
    from octop.infra.gateway.media.tool_media import enrich_tool_output_string_sync  # noqa: PLC0415

    enriched: list[dict[str, Any]] = []
    for entry in messages:
        content = entry.get("content")
        if not isinstance(content, list):
            enriched.append(entry)
            continue
        blocks: list[Any] = []
        changed = False
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                blocks.append(block)
                continue
            output = block.get("output")
            if not isinstance(output, str) or not output.strip():
                blocks.append(block)
                continue
            new_output = enrich_tool_output_string_sync(output, agent_id=agent_id)
            if new_output != output:
                blocks.append({**block, "output": new_output})
                changed = True
            else:
                blocks.append(block)
        enriched.append({**entry, "content": blocks} if changed else entry)
    return enriched


def _ts_to_ms(ts: float | None) -> int | None:
    if ts is None or ts <= 0:
        return None
    return int(ts * 1000)


def _extract_message_timestamp_ms(msg: Any) -> int | None:
    additional_kwargs = _msg_attr(msg, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        return None
    raw = additional_kwargs.get(CHECKPOINT_TS_KEY)
    if isinstance(raw, int | float) and raw > 0:
        return _epoch_to_ms(raw)
    if isinstance(raw, str) and raw.strip():
        return _ts_to_ms(_parse_jsonl_ts(raw))
    return None


def _parse_jsonl_ts(ts: str | None) -> float | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _entry_matches_thread(
    entry: dict[str, Any],
    *,
    thread_id: str,
    created_at: int,
    last_active: int,
) -> bool:
    tid = entry.get("thread_id")
    if tid:
        return str(tid) == thread_id

    ts = _parse_jsonl_ts(entry.get("ts"))
    if ts is not None and created_at > 0:
        start = created_at - 120
        end = (last_active or created_at) + 120
        return start <= ts <= end

    return False


def _merge_adjacent_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse fragmented assistant text; keep each user turn separate."""
    merged: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if not content:
            continue
        entry = {
            "role": role,
            "content": content,
            **({"id": msg["id"]} if msg.get("id") else {}),
        }
        if role == "user":
            merged.append(entry)
            continue
        if merged and merged[-1]["role"] == role:
            merged[-1]["content"] = f"{merged[-1]['content']}\n\n{content}"
            if msg.get("id"):
                merged[-1]["id"] = msg["id"]
            continue
        merged.append(entry)
    return merged


def _collect_jsonl_from_workspace_backend(workspace: Any) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    entries = workspace.list_dir("sessions")
    if not entries:
        return sources
    for entry in entries:
        if isinstance(entry, dict):
            path = entry.get("path")
            is_dir = entry.get("is_dir")
        else:
            path = getattr(entry, "path", None)
            is_dir = getattr(entry, "is_dir", False)
        if not path or is_dir:
            continue
        rel = str(path).replace("\\", "/")
        if not rel.endswith(".jsonl"):
            continue
        workspace_path = rel if rel.startswith("sessions/") else f"sessions/{Path(rel).name}"
        text = workspace.read_text(workspace_path)
        if text:
            sources.append((Path(rel).name, text))
    sources.sort(key=lambda item: item[0], reverse=True)
    return sources


async def _iter_session_jsonl_sources(
    server: Any,
    agent_id: str,
    *,
    user: Any,
) -> list[tuple[str, str]]:
    """Return ``(label, text)`` pairs for session JSONL files (remote backend aware)."""
    registry = server.app_runtime.agent_registry
    workspace = registry.workspace_for_agent(agent_id)
    if workspace is not None:
        try:
            from_ws = await asyncio.to_thread(_collect_jsonl_from_workspace_backend, workspace)
            if from_ws:
                return from_ws
        except Exception:
            logger.warning(
                "failed to read session logs via workspace for agent=%s",
                agent_id,
                exc_info=True,
            )

    sources: list[tuple[str, str]] = []
    local_workspace = resolve_agent_workspace_dir(server, agent_id)
    sessions_dir = Path(local_workspace) / "sessions"
    if sessions_dir.is_dir():
        for path in sorted(sessions_dir.glob("*.jsonl"), reverse=True):
            try:
                sources.append((path.name, path.read_text(encoding="utf-8")))
            except OSError:
                logger.warning("failed to read session log %s", path, exc_info=True)

    return sources


async def _load_thread_messages_from_sessions(
    server: Any,
    agent_id: str,
    thread_id: str,
    limit: int,
    *,
    user: Any,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    """Fallback when LangGraph checkpoints lack a ``messages`` channel."""
    row = server.app_runtime.gateway.thread_registry.get_thread(thread_id)
    created_at = int(row.created_at or 0) if row else 0
    last_active = int(row.last_active or 0) if row else 0
    needed = offset + limit + 1

    collected: list[dict[str, Any]] = []
    for _label, text in await _iter_session_jsonl_sources(server, agent_id, user=user):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            role = obj.get("role")
            if role not in ("user", "assistant"):
                continue
            if not _entry_matches_thread(
                obj,
                thread_id=thread_id,
                created_at=created_at,
                last_active=last_active,
            ):
                continue
            raw_content = str(obj.get("content") or "")
            if not raw_content.strip():
                continue
            collected.append(
                {
                    "role": str(role),
                    "content": raw_content,
                    "ts": obj.get("ts"),
                }
            )

        collected.sort(key=lambda item: _parse_jsonl_ts(item.get("ts")) or 0.0)
        if len(collected) >= needed:
            break

    collected.sort(key=lambda item: _parse_jsonl_ts(item.get("ts")) or 0.0)
    page, has_more = _slice_message_page(collected, limit=limit, offset=offset)
    out: list[dict[str, Any]] = []
    for m in page:
        # Reuse checkpoint polish so JSONL stringified ``image_url`` dumps
        # become ``inbound_attachments`` instead of raw JSON in the bubble.
        entry = _serialize_history_message(
            {"role": m["role"], "content": m["content"]},
            user=user,
        )
        if entry is None:
            continue
        ts_ms = _ts_to_ms(_parse_jsonl_ts(m.get("ts")))
        if ts_ms is not None:
            entry["timestamp"] = ts_ms
        if m.get("id"):
            entry["id"] = m["id"]
        out.append(entry)
    return out, has_more


def _msg_attr(msg: Any, name: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(name, default)
    return getattr(msg, name, default)


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        role = msg.get("role")
        if role:
            return str(role)
        msg_type = str(msg.get("type") or "")
        if msg_type in ("human", "user"):
            return "user"
        if msg_type in ("ai", "assistant"):
            return "assistant"
        if msg_type == "tool":
            return "tool"
        if msg_type == "system":
            return "system"
        return msg_type
    t = type(msg).__name__
    if "HumanMessage" in t:
        return "user"
    if "AIMessage" in t:
        return "assistant"
    if "ToolMessage" in t:
        return "tool"
    if "SystemMessage" in t:
        return "system"
    role = getattr(msg, "role", None) or getattr(msg, "type", "")
    return str(role)


def _tool_use_blocks(tool_calls: Any) -> list[dict[str, Any]]:
    if not isinstance(tool_calls, list):
        return []
    blocks: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or "")
        call_id = str(tc.get("id") or "")
        args = tc.get("args")
        if args is None:
            args = tc.get("input")
        if args is None:
            args = {}
        blocks.append(
            {
                "type": "tool_use",
                "name": name,
                "id": call_id,
                "input": args,
            }
        )
    return blocks


def _content_blocks_from_raw(
    content: Any,
    additional_kwargs: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(additional_kwargs, dict):
        reasoning = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            blocks.append({"type": "thinking", "thinking": reasoning.strip()})

    if isinstance(content, str):
        if content.strip():
            blocks.extend(_split_string_thinking(content))
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                if block.strip():
                    blocks.append({"type": "text", "text": block})
                continue
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").lower()
            if btype in ("thinking", "reasoning"):
                thinking = block.get("thinking") or block.get("reasoning") or block.get("text")
                if isinstance(thinking, str) and thinking.strip():
                    blocks.append({"type": "thinking", "thinking": thinking.strip()})
            elif btype == "text":
                text = str(block.get("text") or "")
                if text:
                    blocks.append({"type": "text", "text": text})
            else:
                blocks.append(dict(block))
    return blocks


def _split_string_thinking(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    last_end = 0
    for match in _THINKING_CAPTURE_RE.finditer(text):
        prefix = text[last_end : match.start()].strip()
        if prefix:
            blocks.append({"type": "text", "text": prefix})
        thinking = match.group(1).strip()
        if thinking:
            blocks.append({"type": "thinking", "thinking": thinking})
        last_end = match.end()
    suffix = text[last_end:].strip()
    if suffix:
        blocks.append({"type": "text", "text": suffix})
    if not blocks and text.strip():
        blocks.append({"type": "text", "text": text.strip()})
    return blocks


def _serialize_history_message(msg: Any, *, user: Any = None) -> dict[str, Any] | None:
    """Project a LangGraph checkpoint message into dashboard history shape."""
    role = _message_role(msg)
    if role in ("system", ""):
        return None

    mid = _msg_attr(msg, "id")
    usage = usage_dict_from_message(msg)
    additional_kwargs = _msg_attr(msg, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        additional_kwargs = {}

    if role == "tool":
        content = _msg_attr(msg, "content", "")
        output = _message_content(msg) if isinstance(content, list) else str(content or "")
        if not output.strip():
            return None
        result_block = {
            "type": "tool_result",
            "id": str(_msg_attr(msg, "tool_call_id") or ""),
            "name": str(_msg_attr(msg, "name") or ""),
            "output": output,
        }
        if _msg_attr(msg, "status") == "error":
            result_block["error_code"] = "tool_error"
        blocks = [result_block]
        entry: dict[str, Any] = {"role": "tool", "content": blocks}
        if mid:
            entry["id"] = mid
        ts_ms = _extract_message_timestamp_ms(msg)
        if ts_ms is not None:
            entry["timestamp"] = ts_ms
        return entry

    content = _msg_attr(msg, "content", "")
    blocks = _content_blocks_from_raw(content, additional_kwargs)
    if role == "assistant":
        blocks.extend(_tool_use_blocks(_msg_attr(msg, "tool_calls")))

    raw_att = (
        additional_kwargs.get(INBOUND_ATTACHMENTS_KEY)
        if isinstance(additional_kwargs, dict)
        else None
    )
    synthesized: list[dict[str, str]] = []
    if role == "user":
        # Path-only vision refs (plan B) must become inbound_attachments for the
        # dashboard thumbnail UI — never leave the raw ``image_url`` JSON in
        # history content (that looked like "流式输入" thumbnails before).
        synthesized = _collect_inbound_from_blocks(blocks)
        if isinstance(raw_att, list) and raw_att:
            merged = [item for item in raw_att if isinstance(item, dict)]
            seen = {
                str(item.get("workspace_path") or item.get("filename") or "") for item in merged
            }
            for item in synthesized:
                key = item.get("workspace_path") or item.get("filename") or ""
                if key and key not in seen:
                    merged.append(item)
                    seen.add(key)
            raw_att = merged
        elif synthesized:
            raw_att = synthesized

    has_user_attachments = isinstance(raw_att, list) and bool(raw_att)
    if role == "user" and (has_user_attachments or synthesized):
        blocks = _strip_attachment_llm_noise(
            blocks,
            locale=_user_locale(user),
            strip_empty_image=True,
        )

    if not blocks and not (role == "user" and has_user_attachments):
        return None

    entry = {"role": role, "content": blocks}
    if mid:
        entry["id"] = mid
    if isinstance(usage, dict) and usage:
        entry["usage"] = usage
    if role == "user":
        raw_ctx = additional_kwargs.get(COMPOSER_CTX_KEY)
        if isinstance(raw_ctx, dict) and raw_ctx:
            entry["composer_context"] = raw_ctx
        if has_user_attachments:
            entry["inbound_attachments"] = raw_att
    ts_ms = _extract_message_timestamp_ms(msg)
    if ts_ms is not None:
        entry["timestamp"] = ts_ms
    return entry


def _message_content(msg: Any) -> str:
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    if isinstance(content, str):
        return _strip_thinking(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return _strip_thinking("\n".join(p for p in parts if p))
    return _strip_thinking(str(content) if content else "")
