"""Per-turn file write checkpoints persisted outside the agent workspace.

The harness captures before/after snapshots at the write point and the
gateway drains them at turn end (``HarnessAgent.pop_file_changes``). They are
stored here, keyed by (agent, thread, assistant message), so the dashboard can
render a per-turn diff and offer a ZCode-style rewind. Storing under
``OCTOP_HOME`` (not the workspace) keeps checkpoints out of ``git status``.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from octop.infra.errors import ErrorCode, OctopError


def _store_path(home: Path, agent_id: str, thread_id: str, message_id: str) -> Path:
    return home / "file_checkpoints" / agent_id / thread_id / f"{message_id}.json"


def save_checkpoints(
    home: Path,
    agent_id: str,
    thread_id: str,
    message_id: str,
    changes: list[dict[str, Any]],
) -> None:
    if not changes:
        return
    path = _store_path(home, agent_id, thread_id, message_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(changes, ensure_ascii=False), encoding="utf-8")


def load_checkpoints(
    home: Path, agent_id: str, thread_id: str, message_id: str
) -> list[dict[str, Any]]:
    path = _store_path(home, agent_id, thread_id, message_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def turn_diff(before: str | None, after: str | None, path: str) -> str:
    """Unified diff of a single turn's before→after for one file."""
    a = (before or "").splitlines(keepends=True)
    b = (after or "").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="\n")
    )


def classify_rewind(
    changes: list[dict[str, Any]], current: dict[str, str | None]
) -> dict[str, list[dict[str, Any]]]:
    """Split checkpointed files into safe / unsafe / ignored for rewind.

    safe: current content still equals the recorded after (nothing else touched
    it since the turn). unsafe: externally modified since. ignored: no change.
    """
    safe: list[dict[str, Any]] = []
    unsafe: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for ch in changes:
        path = ch["path"]
        before, after = ch.get("before"), ch.get("after")
        if before == after:
            ignored.append(ch)
            continue
        now = current.get(path)
        if now == after:
            safe.append(ch)
        else:
            unsafe.append({**ch, "reason": "external_modified"})
    return {"safe": safe, "unsafe": unsafe, "ignored": ignored}


def apply_rewind(workspace: Any, safe: list[dict[str, Any]]) -> list[str]:
    """Restore each safe file to its before-content (None => delete)."""
    applied: list[str] = []
    for ch in safe:
        path = ch["path"]
        before = ch.get("before")
        try:
            if before is None:
                if workspace.exists(path):
                    workspace.delete(path)
            else:
                workspace.write_text(path, before, force=True)
            applied.append(path)
        except Exception as exc:  # noqa: BLE001 - report per-file failure
            raise OctopError(ErrorCode.INTERNAL_ERROR, f"rewind failed for {path}: {exc}") from exc
    return applied


__all__ = [
    "save_checkpoints",
    "load_checkpoints",
    "turn_diff",
    "classify_rewind",
    "apply_rewind",
]
