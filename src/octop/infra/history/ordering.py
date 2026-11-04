"""Stable UI positions across the first legacy-to-archive transition."""

from __future__ import annotations

import base64
import json
from typing import Any


def message_order(segment: dict[str, Any], first_segment_id: int, seq: int) -> list[int]:
    if segment["id"] == first_segment_id and segment["format"] == "legacy":
        return [0, seq + 1 if segment["anchor"] else seq]
    return [segment["id"], seq]


def projection_cursor(thread_id: str, before: int) -> str:
    value = {"thread": thread_id, "source": "projection", "before": before}
    return "legacy:" + base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def projection_boundary(thread_id: str, cursor: str | None) -> int | None:
    if cursor is None:
        return None
    try:
        if not cursor.startswith("legacy:"):
            raise ValueError("Invalid projection cursor")
        value = json.loads(base64.urlsafe_b64decode(cursor[7:]))
        before = value["before"]
        if (
            value["thread"] != thread_id
            or value["source"] != "projection"
            or type(before) is not int
            or before <= 0
        ):
            raise ValueError("Invalid projection cursor")
        return before
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Invalid projection cursor") from exc
