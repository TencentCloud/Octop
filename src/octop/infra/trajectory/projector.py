from __future__ import annotations

from typing import Any

from octop.infra.trajectory.types import TrajectoryEvent


def project_harness_chunk(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    thread_id: str,
    seq: int,
) -> list[TrajectoryEvent]:
    ctype = chunk.get("type", "")
    ts = float(chunk.get("ts") or 0.0)
    turn_id = chunk.get("turn_id") if isinstance(chunk.get("turn_id"), str) else None
    request_seq_raw = chunk.get("request_seq")
    request_seq = request_seq_raw if isinstance(request_seq_raw, int) else None

    if ctype == "tool_call_chunk":
        call_id = str(chunk.get("id") or chunk.get("index", 0))
        name = str(chunk.get("name") or "tool")
        return [
            TrajectoryEvent(
                event_id=f"{thread_id}:{seq}:tool:{call_id}",
                thread_id=thread_id,
                agent_id=agent_id,
                seq=seq,
                ts=ts,
                kind="tool",
                turn_id=turn_id,
                request_seq=request_seq,
                is_error=False,
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
            TrajectoryEvent(
                event_id=f"{thread_id}:{seq}:assistant",
                thread_id=thread_id,
                agent_id=agent_id,
                seq=seq,
                ts=ts,
                kind="assistant",
                turn_id=turn_id,
                request_seq=request_seq,
                is_error=False,
                summary=content,
                payload={"node": node, "content": content},
            )
        ]

    return [
        TrajectoryEvent(
            event_id=f"{thread_id}:{seq}:unknown",
            thread_id=thread_id,
            agent_id=agent_id,
            seq=seq,
            ts=ts,
            kind="unknown",
            turn_id=turn_id,
            request_seq=request_seq,
            is_error=False,
            summary=str(ctype or "unknown"),
            payload={"type": ctype},
        )
    ]
