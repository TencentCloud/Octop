from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TrajectoryKind = Literal[
    "user",
    "assistant",
    "tool",
    "context",
    "compacted",
    "system",
    "unknown",
]


@dataclass(frozen=True)
class TrajectoryEvent:
    event_id: str
    thread_id: str
    agent_id: str
    seq: int
    ts: float
    kind: TrajectoryKind
    turn_id: str | None
    request_seq: int | None
    is_error: bool
    summary: str
    payload: dict[str, Any]
