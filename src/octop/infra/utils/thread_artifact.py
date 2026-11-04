"""Thread artifact ref — leaf type for ``threads.artifacts`` JSON.

No gateway / workspace imports: safe for ``infra.db.repos`` and API layers.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

MAX_THREAD_ARTIFACTS = 200


@dataclass(frozen=True)
class ThreadArtifact:
    """One workspace file produced during a thread (optionally stamped by agent)."""

    path: str
    agent_id: str = ""

    def dedupe_key(self) -> str:
        path_key = self.path.casefold() if os.name == "nt" else self.path
        return f"{self.agent_id}\0{path_key}"

    def as_ref(self) -> dict[str, str]:
        """Structured API item (always includes path; agent_id when set)."""
        item: dict[str, str] = {"path": self.path}
        if self.agent_id:
            item["agent_id"] = self.agent_id
        return item


def coerce_thread_artifact(item: object) -> ThreadArtifact | None:
    if isinstance(item, ThreadArtifact):
        path = item.path.strip()
        if not path:
            return None
        return ThreadArtifact(path=path, agent_id=(item.agent_id or "").strip())
    if isinstance(item, str):
        path = item.strip()
        return ThreadArtifact(path=path) if path else None
    if isinstance(item, Mapping):
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        raw_agent = item.get("agent_id")
        agent_id = raw_agent.strip() if isinstance(raw_agent, str) else ""
        return ThreadArtifact(path=raw_path.strip(), agent_id=agent_id)
    return None


def parse_thread_artifacts(raw: object) -> list[ThreadArtifact]:
    """Decode the threads.artifacts JSON column into unique entries.

    Legacy rows are plain path strings. Newer rows may be
    ``{"path": "...", "agent_id": "..."}``.
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        parsed: object = list(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return []
    else:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[ThreadArtifact] = []
    seen: set[str] = set()
    for item in parsed:
        entry = coerce_thread_artifact(item)
        if entry is None:
            continue
        key = entry.dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def serialize_thread_artifacts(entries: Sequence[ThreadArtifact]) -> list[str | dict[str, str]]:
    """Encode artifacts for the JSON column (strings when agent_id is empty)."""
    payload: list[str | dict[str, str]] = []
    for entry in entries:
        if entry.agent_id:
            payload.append({"path": entry.path, "agent_id": entry.agent_id})
        else:
            payload.append(entry.path)
    return payload


def merge_thread_artifacts(
    existing: Sequence[ThreadArtifact | str | Mapping[str, object]],
    incoming: Sequence[ThreadArtifact | str | Mapping[str, object]],
) -> list[ThreadArtifact]:
    """Append new entries, keeping insertion order and capping length."""
    merged = parse_thread_artifacts([*existing, *incoming])
    if len(merged) <= MAX_THREAD_ARTIFACTS:
        return merged
    return merged[-MAX_THREAD_ARTIFACTS:]


__all__ = [
    "MAX_THREAD_ARTIFACTS",
    "ThreadArtifact",
    "coerce_thread_artifact",
    "merge_thread_artifacts",
    "parse_thread_artifacts",
    "serialize_thread_artifacts",
]
