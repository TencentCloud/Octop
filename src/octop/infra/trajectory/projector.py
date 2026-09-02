from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from octop.infra.trajectory.types import TrajectoryEvent, TrajectoryKind


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
        return [
            _event(
                agent_id=agent_id,
                thread_id=thread_id,
                seq=seq,
                ts=0.0,
                kind="unknown",
                turn_id=None,
                request_seq=None,
                summary="unknown",
                payload={},
            )
        ]


def _project_harness_chunk(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    thread_id: str,
    seq: int,
) -> list[TrajectoryEvent]:
    if not isinstance(chunk, dict):
        return [
            _event(
                agent_id=agent_id,
                thread_id=thread_id,
                seq=seq,
                ts=0.0,
                kind="unknown",
                turn_id=None,
                request_seq=None,
                summary="unknown",
                payload={"type": type(chunk).__name__},
            )
        ]

    ctype = _kind_key(chunk)
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
        name = str(chunk.get("name") or "tool")
        return [
            _event(
                **common,
                kind="tool",
                suffix=f"tool:{call_id}",
                summary=f"tool {name}",
                payload={
                    "call_id": call_id,
                    "name": name,
                    "args": chunk.get("args"),
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
        payload: dict[str, Any] = {"content": content}
        source = chunk.get("source")
        if isinstance(source, str) and source:
            payload["source"] = source
        return [
            _event(
                **common,
                kind="user",
                summary=content,
                payload=payload,
            )
        ]

    if ctype == "context":
        source = str(chunk.get("source") or "")
        label = str(chunk.get("label") or source or "context")
        tokens = chunk.get("tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool):
            tokens = None
        payload = {"source": source, "label": label, "tokens": tokens}
        return [
            _event(
                **common,
                kind="context",
                summary=label,
                payload=payload,
            )
        ]

    if ctype == "compacted":
        summarized = _as_int(chunk.get("summarized_count"))
        preserved = _as_int(chunk.get("preserved_count"))
        removed_tokens = _as_int(chunk.get("removed_tokens"))
        summary = str(chunk.get("summary") or f"compacted {summarized} messages")
        payload = {
            "summarized_count": summarized,
            "preserved_count": preserved,
            "removed_tokens": removed_tokens,
            "summary": summary,
        }
        file_path = chunk.get("file_path")
        if isinstance(file_path, str) and file_path:
            payload["file_path"] = file_path
        return [
            _event(
                **common,
                kind="compacted",
                summary=summary,
                payload=payload,
            )
        ]

    return [
        _event(
            **common,
            kind="unknown",
            summary=str(ctype or "unknown"),
            payload={"type": ctype},
        )
    ]


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
