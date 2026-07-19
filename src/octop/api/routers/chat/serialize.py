"""Thread history loading and LangGraph message serialization."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from octop.infra.gateway.process.message_keys import (
    COMPOSER_CTX_KEY,
    INBOUND_ATTACHMENTS_KEY,
)
from octop.infra.utils.llm_text import strip_thinking as _strip_thinking

logger = logging.getLogger(__name__)

_THINKING_CAPTURE_RE = re.compile(
    r"<think>([\s\S]*?)</think>\s*",
    re.IGNORECASE,
)

# Must match harness_agent.agent.CHECKPOINT_TS_KEY (epoch-ms in additional_kwargs).
CHECKPOINT_TS_KEY = "checkpoint_ts"

HISTORY_DEFAULT_LIMIT = 25
HISTORY_MAX_LIMIT = 200


def _clamp_history_limit(limit: int) -> int:
    return max(1, min(limit, HISTORY_MAX_LIMIT))


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
            entry = _serialize_history_message(m)
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
    local_workspace = server.services.paths.ensure_agent_workspace(agent_id)
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
            if role == "assistant":
                content: Any = _split_string_thinking(raw_content) or raw_content
            else:
                content = raw_content
            collected.append({"role": str(role), "content": content, "ts": obj.get("ts")})

        collected.sort(key=lambda item: _parse_jsonl_ts(item.get("ts")) or 0.0)
        if len(collected) >= needed:
            break

    collected.sort(key=lambda item: _parse_jsonl_ts(item.get("ts")) or 0.0)
    page, has_more = _slice_message_page(collected, limit=limit, offset=offset)
    out: list[dict[str, Any]] = []
    for m in page:
        entry: dict[str, Any] = {"role": m["role"], "content": m["content"]}
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


def _serialize_history_message(msg: Any) -> dict[str, Any] | None:
    """Project a LangGraph checkpoint message into dashboard history shape."""
    role = _message_role(msg)
    if role in ("system", ""):
        return None

    mid = _msg_attr(msg, "id")
    usage = _msg_attr(msg, "usage_metadata")
    additional_kwargs = _msg_attr(msg, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        additional_kwargs = {}

    if role == "tool":
        content = _msg_attr(msg, "content", "")
        output = _message_content(msg) if isinstance(content, list) else str(content or "")
        if not output.strip():
            return None
        blocks = [
            {
                "type": "tool_result",
                "id": str(_msg_attr(msg, "tool_call_id") or ""),
                "name": str(_msg_attr(msg, "name") or ""),
                "output": output,
            }
        ]
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

    if not blocks:
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
        raw_att = additional_kwargs.get(INBOUND_ATTACHMENTS_KEY)
        if isinstance(raw_att, list) and raw_att:
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
