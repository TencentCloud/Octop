"""Per-agent trajectory switch and persist-size limits.

``config_json.enable_trajectory`` defaults to enabled. Only the explicit boolean
``false`` disables observation and writes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from octop.infra.trajectory.types import TrajectoryEvent

ENABLE_TRAJECTORY_KEY = "enable_trajectory"

# Persist caps — live SSE still throttles; these bound SQLite row size.
PAYLOAD_MAX_CHARS = 64_000
SUMMARY_MAX_CHARS = 240
TRAJECTORY_RETENTION_USER_TURNS = 50
TRAJECTORY_SSE_REPLAY_MAX = 2_000

_CLIP_PAYLOAD_KEYS = ("content", "text", "thinking", "args", "result")


def agent_trajectory_enabled(cfg: Mapping[str, Any] | None) -> bool:
    """Return false only when the agent explicitly opted out."""
    if not cfg:
        return True
    return cfg.get(ENABLE_TRAJECTORY_KEY) is not False


def apply_enable_trajectory(config: dict[str, Any], enabled: bool) -> dict[str, Any]:
    """Persist only the non-default opt-out value."""
    if enabled:
        config.pop(ENABLE_TRAJECTORY_KEY, None)
    else:
        config[ENABLE_TRAJECTORY_KEY] = False
    return config


def clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 1:
        return "…"
    return value[: limit - 1].rstrip() + "…"


def clip_payload_value(value: Any, *, limit: int = PAYLOAD_MAX_CHARS) -> Any:
    if isinstance(value, str):
        return clip_text(value, limit)
    if isinstance(value, (dict, list)):
        raw = json.dumps(value, ensure_ascii=False, default=str)
        if len(raw) <= limit:
            return value
        return clip_text(raw, limit)
    return value


def clip_persisted_event(event: TrajectoryEvent) -> TrajectoryEvent:
    """Bound summary + large payload fields before SQLite write."""
    summary = clip_text(event.summary or "", SUMMARY_MAX_CHARS)
    payload = event.payload
    if not isinstance(payload, dict):
        return replace(event, summary=summary, payload={})
    clipped = dict(payload)
    changed = summary != event.summary
    for key in _CLIP_PAYLOAD_KEYS:
        if key not in clipped:
            continue
        new_value = clip_payload_value(clipped[key])
        if new_value is not clipped[key]:
            clipped[key] = new_value
            changed = True
    if not changed:
        return event
    return replace(event, summary=summary, payload=clipped)
