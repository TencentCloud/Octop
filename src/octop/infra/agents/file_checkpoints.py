"""Per-turn file write checkpoints persisted outside the agent workspace.

The harness captures before/after snapshots at the write point and the
gateway drains them at turn end (``HarnessAgent.pop_file_changes``). They are
stored here, keyed by (agent, thread, assistant message), so the dashboard can
render a per-turn diff and rewind the turn. Storing under ``OCTOP_HOME`` (not
the workspace) keeps checkpoints out of ``git status``.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import os
import threading
import uuid
import weakref
from pathlib import Path
from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.read_content import coerce_read_content

# Line-level LCS cell budget; beyond it the stat falls back to a conservative
# "everything changed" estimate so a huge file cannot stall the response.
_MAX_LCS_CELLS = 400_000


def _store_path(home: Path, agent_id: str, thread_id: str, message_id: str) -> Path:
    return home / "file_checkpoints" / agent_id / thread_id / f"{message_id}.json"


def _write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique per call: save_checkpoints runs on the event loop while
    # mark_turn_reverted may run in a worker thread on the same path.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            with contextlib.suppress(OSError):
                tmp.unlink()


# Checkpoint files are read-modify-written from both the event loop (turn
# end) and worker threads (rewind); serialize per store path.
_STORE_LOCKS_GUARD = threading.Lock()
# Weak values: a lock lives only while a writer holds it, so the map does
# not retain one entry per checkpoint file the process has ever served.
_STORE_LOCKS: weakref.WeakValueDictionary[str, threading.Lock] = weakref.WeakValueDictionary()


def _store_lock(path: Path) -> threading.Lock:
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS.get(str(path))
        if lock is None:
            lock = threading.Lock()
            _STORE_LOCKS[str(path)] = lock
        return lock


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
    with _store_lock(path):
        _write_atomic(path, json.dumps({"reverted": False, "changes": changes}, ensure_ascii=False))


def latest_message_id(home: Path, agent_id: str, thread_id: str) -> str | None:
    """Newest checkpointed assistant message id for a thread, or None.

    Live dashboard turns get a client-side message id; the newest checkpoint is
    the just-finished turn, so the UI can resolve the harness id before reload.
    """
    thread_dir = home / "file_checkpoints" / agent_id / thread_id
    try:
        files = [p for p in thread_dir.glob("*.json") if p.is_file()]
    except OSError:
        return None
    if not files:
        return None
    newest = max(files, key=lambda p: p.stat().st_mtime_ns)
    return newest.stem


def load_turn_state(home: Path, agent_id: str, thread_id: str, message_id: str) -> dict[str, Any]:
    """Return ``{"reverted": bool, "changes": [...]}`` for one turn.

    Accepts the historical bare-list format as ``reverted=False``.
    """
    path = _store_path(home, agent_id, thread_id, message_id)
    if not path.exists():
        return {"reverted": False, "changes": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"reverted": False, "changes": []}
    if isinstance(data, list):
        return {"reverted": False, "changes": data}
    if isinstance(data, dict):
        return {
            "reverted": bool(data.get("reverted")),
            "changes": data.get("changes") if isinstance(data.get("changes"), list) else [],
        }
    return {"reverted": False, "changes": []}


def load_checkpoints(
    home: Path, agent_id: str, thread_id: str, message_id: str
) -> list[dict[str, Any]]:
    changes: Any = load_turn_state(home, agent_id, thread_id, message_id)["changes"]
    return changes if isinstance(changes, list) else []


def mark_turn_reverted(home: Path, agent_id: str, thread_id: str, message_id: str) -> None:
    path = _store_path(home, agent_id, thread_id, message_id)
    with _store_lock(path):
        state = load_turn_state(home, agent_id, thread_id, message_id)
        if not state["changes"]:
            return
        state["reverted"] = True
        _write_atomic(path, json.dumps(state, ensure_ascii=False))


def turn_diff(before: str | None, after: str | None, path: str) -> str:
    """Unified diff of a single turn's before→after for one file."""
    a = (before or "").splitlines(keepends=True)
    b = (after or "").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="\n")
    )


def _logical_lines(content: str | None) -> list[str]:
    if not content:
        return []
    lines = content.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def line_change_stat(before: str | None, after: str | None) -> tuple[int, int]:
    """Real changed-line counts between two contents.

    Common prefix/suffix is trimmed, then the remaining lines are counted via
    a line-level LCS; over the cell budget the count falls back to a
    conservative "everything changed" so huge files stay cheap.
    """
    before_lines = _logical_lines(before)
    after_lines = _logical_lines(after)

    prefix = 0
    while (
        prefix < len(before_lines)
        and prefix < len(after_lines)
        and before_lines[prefix] == after_lines[prefix]
    ):
        prefix += 1

    before_tail = len(before_lines) - 1
    after_tail = len(after_lines) - 1
    while (
        before_tail >= prefix
        and after_tail >= prefix
        and before_lines[before_tail] == after_lines[after_tail]
    ):
        before_tail -= 1
        after_tail -= 1

    trimmed_before = before_lines[prefix : before_tail + 1]
    trimmed_after = after_lines[prefix : after_tail + 1]

    if not trimmed_before:
        return len(trimmed_after), 0
    if not trimmed_after:
        return 0, len(trimmed_before)
    if len(trimmed_before) * len(trimmed_after) > _MAX_LCS_CELLS:
        return len(trimmed_after), len(trimmed_before)

    row = [0] * (len(trimmed_after) + 1)
    for b_index in range(1, len(trimmed_before) + 1):
        previous_diagonal = 0
        for a_index in range(1, len(trimmed_after) + 1):
            previous_row = row[a_index]
            if trimmed_before[b_index - 1] == trimmed_after[a_index - 1]:
                row[a_index] = previous_diagonal + 1
            else:
                row[a_index] = max(row[a_index], row[a_index - 1])
            previous_diagonal = previous_row
    unchanged = row[len(trimmed_after)]
    return len(trimmed_after) - unchanged, len(trimmed_before) - unchanged


def turn_summary(changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one turn's checkpoints into display stats, sorted by path."""
    files: list[dict[str, Any]] = []
    additions = 0
    removed = 0
    for ch in changes:
        path = str(ch.get("path") or "")
        if not path:
            continue
        added, deleted = line_change_stat(ch.get("before"), ch.get("after"))
        additions += added
        removed += deleted
        files.append(
            {
                "path": path,
                "added": added,
                "removed": deleted,
                "write_count": int(ch.get("write_count") or 1),
                "tool_names": list(ch.get("tool_names") or []),
            }
        )
    files.sort(key=lambda item: item["path"])
    return {"files": files, "additions": additions, "deletions": removed}


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


def _read_prior_content(workspace: Any, path: str) -> str:
    """Normalize a workspace read the way the dashboard viewer does.

    Backends can return a list of lines or the deepagents empty-content
    sentinel; journaling those verbatim would corrupt the file on rollback.
    """
    return coerce_read_content(workspace.read_text(path))


def _compensate(workspace: Any, journal: list[tuple[str, str | None]]) -> str | None:
    """Roll back already-restored files in reverse; return a failure summary."""
    failures: list[str] = []
    for path, prior in reversed(journal):
        try:
            if prior is None:
                if workspace.exists(path):
                    workspace.delete(path)
            else:
                workspace.write_text(path, prior, force=True)
        except Exception as exc:  # noqa: BLE001 - aggregate all failures
            failures.append(f"{path}: {exc}")
    return "; ".join(failures) or None


def apply_rewind(workspace: Any, safe: list[dict[str, Any]]) -> list[str]:
    """Restore each safe file to its before-content (``None`` => delete).

    Journal-rollback: every file's prior content is captured before the write;
    if any step fails, already-restored files are compensated in reverse so
    the workspace is never left half-rewound.
    """
    applied: list[str] = []
    journal: list[tuple[str, str | None]] = []
    for ch in safe:
        path = ch["path"]
        before = ch.get("before")
        try:
            prior = _read_prior_content(workspace, path) if workspace.exists(path) else None
        except Exception as exc:  # noqa: BLE001 - abort before touching anything else
            rollback_failures = _compensate(workspace, journal)
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"rewind aborted for {path}: {exc}"
                + (f"; compensation failures: {rollback_failures}" if rollback_failures else ""),
            ) from exc
        journal.append((path, prior))
        try:
            if before is None:
                if workspace.exists(path):
                    workspace.delete(path)
            else:
                workspace.write_text(path, before, force=True)
        except Exception as exc:  # noqa: BLE001 - report per-file failure
            rollback_failures = _compensate(workspace, journal)
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"rewind failed for {path}: {exc}"
                + (f"; compensation failures: {rollback_failures}" if rollback_failures else ""),
            ) from exc
        applied.append(path)
    return applied


__all__ = [
    "save_checkpoints",
    "load_checkpoints",
    "load_turn_state",
    "mark_turn_reverted",
    "turn_diff",
    "line_change_stat",
    "turn_summary",
    "classify_rewind",
    "apply_rewind",
]
