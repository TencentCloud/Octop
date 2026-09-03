from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from octop.infra.trajectory.types import TrajectoryEvent, TrajectoryKind

_IGNORED_TYPES = frozenset(
    {
        "reasoning",
        "state_snapshot",
        "state_update",
        "usage",
        "done",
        "error",
        "custom",
        "hitl_required",
        "slash_action",
        "attachment",
    }
)


class _Common(TypedDict):
    agent_id: str
    thread_id: str
    seq: int
    ts: float
    turn_id: str | None
    request_seq: int | None


def project_harness_chunk(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    thread_id: str,
    seq: int,
) -> list[TrajectoryEvent]:
    try:
        return _project_harness_chunk(chunk, agent_id=agent_id, thread_id=thread_id, seq=seq)
    except Exception:
        return []


def _project_harness_chunk(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    thread_id: str,
    seq: int,
) -> list[TrajectoryEvent]:
    if not isinstance(chunk, dict):
        return []

    ctype = _kind_key(chunk)
    if not ctype or ctype in _IGNORED_TYPES or ctype.startswith("state_"):
        return []
    ts = _coerce_ts(chunk.get("ts"))
    turn_id = chunk.get("turn_id") if isinstance(chunk.get("turn_id"), str) else None
    request_seq_raw = chunk.get("request_seq")
    request_seq = request_seq_raw if isinstance(request_seq_raw, int) else None
    common: _Common = {
        "agent_id": agent_id,
        "thread_id": thread_id,
        "seq": seq,
        "ts": ts,
        "turn_id": turn_id,
        "request_seq": request_seq,
    }

    if ctype == "tool_call_chunk":
        call_id = str(chunk.get("id") or chunk.get("index", 0))
        name = str(chunk.get("name") or "")
        return [
            _event(
                **common,
                kind="tool",
                suffix=f"tool:{call_id}",
                summary=f"tool {name or 'tool'}",
                payload={
                    "call_id": call_id,
                    "name": name or "tool",
                    "args": chunk.get("args"),
                },
            )
        ]

    if ctype == "tool_result":
        call_id, name, result = _tool_result_fields(chunk)
        return [
            _event(
                **common,
                kind="tool",
                suffix=f"tool:{call_id}",
                summary=f"tool {name}",
                payload={
                    "call_id": call_id,
                    "name": name,
                    "result": result,
                },
            )
        ]

    if ctype == "token":
        content = str(chunk.get("content") or "")
        if not content:
            return []
        node = str(chunk.get("node") or "agent")
        return [
            _event(
                **common,
                kind="assistant",
                summary=content,
                payload={"node": node, "content": content},
            )
        ]

    if ctype == "user":
        content = str(chunk.get("content") or "")
        user_payload: dict[str, Any] = {"content": content}
        source = chunk.get("source")
        if isinstance(source, str) and source:
            user_payload["source"] = source
        return [
            _event(
                **common,
                kind="user",
                summary=content,
                payload=user_payload,
            )
        ]

    if ctype == "context":
        source = str(chunk.get("source") or "")
        label = str(chunk.get("label") or source or "context")
        tokens = chunk.get("tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool):
            tokens = None
        content = str(chunk.get("content") or chunk.get("text") or "")
        context_payload: dict[str, Any] = {
            "source": source,
            "label": label,
            "tokens": tokens,
        }
        _copy_content_reference(chunk, context_payload)
        if content:
            context_payload["content"] = content
        summary = _clip_summary(label, content) if content else label
        return [
            _event(
                **common,
                kind="context",
                summary=summary,
                payload=context_payload,
            )
        ]

    if ctype == "system":
        label = str(chunk.get("label") or "system")
        content = str(chunk.get("content") or chunk.get("text") or "")
        system_payload: dict[str, Any] = {"label": label}
        _copy_content_reference(chunk, system_payload)
        if content:
            system_payload["content"] = content
        summary = _clip_summary(label, content) if content else label
        return [
            _event(
                **common,
                kind="system",
                summary=summary,
                payload=system_payload,
            )
        ]

    if ctype == "compacted":
        summarized = _as_int(chunk.get("summarized_count"))
        preserved = _as_int(chunk.get("preserved_count"))
        removed_tokens = _as_int(chunk.get("removed_tokens"))
        summary = str(chunk.get("summary") or f"compacted {summarized} messages")
        compacted_payload: dict[str, Any] = {
            "summarized_count": summarized,
            "preserved_count": preserved,
            "removed_tokens": removed_tokens,
            "summary": summary,
        }
        file_path = chunk.get("file_path")
        if isinstance(file_path, str) and file_path:
            compacted_payload["file_path"] = file_path
        return [
            _event(
                **common,
                kind="compacted",
                summary=summary,
                payload=compacted_payload,
            )
        ]

    return []


def _tool_result_fields(chunk: dict[str, Any]) -> tuple[str, str, Any]:
    call_id = str(chunk.get("id") or chunk.get("tool_call_id") or chunk.get("index", 0))
    name = str(chunk.get("name") or "tool")
    result: Any = chunk.get("content")
    messages = chunk.get("messages")
    if isinstance(messages, list):
        for message in messages:
            msg_id = _message_attr(message, "tool_call_id")
            msg_name = _message_attr(message, "name")
            msg_content = _message_attr(message, "content")
            if msg_id:
                call_id = str(msg_id)
            if isinstance(msg_name, str) and msg_name:
                name = msg_name
            if msg_content is not None:
                result = msg_content
            if msg_id or msg_content is not None:
                break
    return call_id, name, result


def _message_attr(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _copy_content_reference(source: dict[str, Any], target: dict[str, Any]) -> None:
    digest = source.get("content_sha256")
    chars = source.get("content_chars")
    if isinstance(digest, str) and digest:
        target["content_sha256"] = digest
    if isinstance(chars, int) and not isinstance(chars, bool) and chars >= 0:
        target["content_chars"] = chars


def _kind_key(chunk: dict[str, Any]) -> str:
    raw = chunk.get("type")
    if isinstance(raw, str) and raw:
        return raw
    if raw is not None and raw != "":
        return str(raw)
    role = chunk.get("role")
    if isinstance(role, str) and role:
        return role
    return ""


def _coerce_ts(raw: Any) -> float:
    if raw is None or isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except (ValueError, OSError):
            return 0.0
    return 0.0


def _as_int(raw: Any) -> int:
    if isinstance(raw, bool) or raw is None:
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return 0
    return 0


def _clip_summary(label: str, content: str, *, limit: int = 240) -> str:
    preview = " ".join(content.split())
    if preview:
        if len(preview) > limit:
            return preview[: max(0, limit - 1)].rstrip() + "…"
        return preview
    return label


def _event(
    *,
    agent_id: str,
    thread_id: str,
    seq: int,
    ts: float,
    kind: TrajectoryKind,
    turn_id: str | None,
    request_seq: int | None,
    summary: str,
    payload: dict[str, Any],
    suffix: str | None = None,
    is_error: bool = False,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=f"{thread_id}:{seq}:{suffix or kind}",
        thread_id=thread_id,
        agent_id=agent_id,
        seq=seq,
        ts=ts,
        kind=kind,
        turn_id=turn_id,
        request_seq=request_seq,
        is_error=is_error,
        summary=summary,
        payload=payload,
    )
