"""Show ACP file edits with the same chat card as ``write_file`` / ``edit_file``.

External agents report edits as ACP ``diff`` content and ``locations``. The
harness keeps only a title, so the chat never sees a path or a line count.
This restores the native tool arguments on the managed-agent stream and on
the checkpoint that history reloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_INSTALLED = False
_FILE_KINDS = frozenset({"edit", "delete", "move"})
_NATIVE_FILE_TOOLS = frozenset({"edit_file", "write_file"})
# Full-file diffs can be large. Past this, keep the path and skip the body
# so the chip still opens and the transcript stays bounded.
_BODY_CHAR_CAP = 200_000
_PATH_KEYS = ("path", "file_path", "filePath", "filepath")


@dataclass
class _Pending:
    by_path: dict[str, dict[str, Any]] = field(default_factory=dict)
    emitted: set[str] = field(default_factory=set)
    extras: list[str] = field(default_factory=list)
    primary_emitted: bool = False


_PENDING: dict[str, _Pending] = {}


def _block_map(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    dump = getattr(block, "model_dump", None)
    if callable(dump):
        data = dump(by_alias=True)
        if isinstance(data, dict):
            return data
    return {}


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _too_big(value: str | None) -> bool:
    return isinstance(value, str) and len(value) > _BODY_CHAR_CAP


def file_edits_from_update(update: Any) -> list[dict[str, Any]]:
    """Paths and optional before/after text from one ACP tool update."""
    diffs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in getattr(update, "content", None) or []:
        data = _block_map(block)
        if str(data.get("type") or "") != "diff":
            continue
        path = str(data.get("path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        old = _text(data.get("oldText", data.get("old_text")))
        new = _text(data.get("newText", data.get("new_text")))
        diffs.append({"path": path, "old": old, "new": new})
    if diffs:
        return diffs

    kind = str(getattr(update, "kind", "") or "").strip().lower()
    if kind not in _FILE_KINDS:
        return []
    paths: list[str] = []
    for loc in getattr(update, "locations", None) or []:
        path = str(_block_map(loc).get("path") or "").strip()
        if path:
            paths.append(path)
    raw = getattr(update, "raw_input", None)
    if isinstance(raw, dict):
        for key in _PATH_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value.strip())
    out: list[dict[str, Any]] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append({"path": path, "old": None, "new": None})
    return out


def _merge(pending: _Pending, files: Any) -> None:
    if not isinstance(files, list):
        return
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path or path in pending.emitted:
            continue
        old = item.get("old") if isinstance(item.get("old"), str) else None
        new = item.get("new") if isinstance(item.get("new"), str) else None
        current = pending.by_path.get(path)
        if current is None or (
            current.get("old") is None
            and current.get("new") is None
            and (old is not None or new is not None)
        ):
            pending.by_path[path] = {"path": path, "old": old, "new": new}


def _ready(pending: _Pending, *, finished: bool) -> list[dict[str, Any]]:
    ready: list[dict[str, Any]] = []
    for path, item in pending.by_path.items():
        if path in pending.emitted:
            continue
        has_body = item.get("old") is not None or item.get("new") is not None
        if has_body or finished:
            ready.append(item)
    return ready


def _file_tool_args(item: dict[str, Any]) -> tuple[str, str]:
    path = str(item.get("path") or "")
    old = item.get("old") if isinstance(item.get("old"), str) else None
    new = item.get("new") if isinstance(item.get("new"), str) else None
    if _too_big(old) or _too_big(new):
        old = None
        new = None
    if isinstance(new, str) and old is None:
        payload: dict[str, Any] = {"file_path": path, "content": new}
        return "write_file", json.dumps(payload, ensure_ascii=False)
    if isinstance(old, str) and isinstance(new, str):
        payload = {"file_path": path, "old_string": old, "new_string": new}
        return "edit_file", json.dumps(payload, ensure_ascii=False)
    return "edit_file", json.dumps({"file_path": path}, ensure_ascii=False)


def _open_chunk(name: str, args: str, call_id: str, index: int) -> Any:
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    return ChatGenerationChunk(
        message=AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "name": name,
                    "args": args,
                    "id": call_id,
                    "index": index,
                }
            ],
        )
    )


def _call_field(call: Any, key: str) -> Any:
    if isinstance(call, dict):
        return call.get(key)
    return getattr(call, key, None)


def install_acp_file_edits() -> None:
    """Map ACP file edits onto ``write_file`` / ``edit_file`` tool calls."""
    global _INSTALLED
    if _INSTALLED:
        return
    import octop_harness.acp.managed as managed
    from octop_harness.acp.client import ACPHostedClient
    from octop_harness.acp.managed import (
        _collect_managed_chunk,
        _managed_history_messages,
        _tool_finished,
        _tool_result_chunk,
    )

    original_event = ACPHostedClient._tool_event_from_state
    original_collect = _collect_managed_chunk
    original_history = _managed_history_messages

    def _tool_event_from_state(self: Any, update: Any) -> dict[str, Any] | None:
        event = original_event(self, update)
        if not isinstance(event, dict):
            return event
        files = file_edits_from_update(update)
        if files:
            event["files"] = files
        return event

    def tool_chunks(
        payload: dict[str, Any],
        opened: dict[str, int],
        tool_index: int,
    ) -> tuple[list[Any], int]:
        call_id = str(payload.get("call_id") or "")
        chunks: list[Any] = []
        pending = _PENDING.setdefault(call_id, _Pending())
        _merge(pending, payload.get("files"))
        finished = _tool_finished(payload)
        ready = _ready(pending, finished=finished)

        if not ready and call_id not in opened:
            opened[call_id] = tool_index
            tool_index += 1
            chunks.append(
                _open_chunk(
                    str(payload.get("name") or "tool"),
                    "",
                    call_id,
                    opened[call_id],
                )
            )

        for item in ready:
            name, args = _file_tool_args(item)
            if not pending.primary_emitted:
                if call_id not in opened:
                    opened[call_id] = tool_index
                    tool_index += 1
                file_id = call_id
                index = opened[call_id]
                pending.primary_emitted = True
            else:
                file_id = f"{call_id}:{len(pending.extras) + 1}"
                opened[file_id] = tool_index
                tool_index += 1
                index = opened[file_id]
                pending.extras.append(file_id)
            pending.emitted.add(str(item.get("path") or ""))
            chunks.append(_open_chunk(name, args, file_id, index))

        if finished:
            extras = list(pending.extras)
            opened.pop(call_id, None)
            chunks.append(_tool_result_chunk(payload))
            status = str(payload.get("status") or "completed")
            for file_id in extras:
                opened.pop(file_id, None)
                chunks.append(
                    _tool_result_chunk(
                        {"call_id": file_id, "status": status, "output": ""},
                    )
                )
            _PENDING.pop(call_id, None)
        return chunks, tool_index

    def collect(
        chunk: Any,
        text_parts: list[str],
        reasoning_parts: list[str],
        tools: list[dict[str, Any]],
        tools_by_id: dict[str, dict[str, Any]],
    ) -> None:
        original_collect(chunk, text_parts, reasoning_parts, tools, tools_by_id)
        message = getattr(chunk, "message", None)
        if message is None:
            message = chunk
        for call in getattr(message, "tool_call_chunks", None) or []:
            call_id = str(_call_field(call, "id") or "")
            if not call_id:
                continue
            record = tools_by_id.get(call_id)
            name = str(_call_field(call, "name") or "")
            args = _call_field(call, "args") or ""
            if record is None:
                record = {
                    "id": call_id,
                    "name": name or "tool",
                    "output": "",
                    "failed": False,
                }
                tools_by_id[call_id] = record
                tools.append(record)
            if name in _NATIVE_FILE_TOOLS:
                record["name"] = name
            if isinstance(args, str) and args.strip():
                record["args_json"] = str(record.get("args_json") or "") + args

    def history(
        text_parts: list[str],
        reasoning_parts: list[str],
        tools: list[dict[str, Any]],
    ) -> list[Any]:
        messages = original_history(text_parts, reasoning_parts, tools)
        by_id = {str(record.get("id") or ""): record for record in tools}
        rewritten: list[Any] = []
        for message in messages:
            calls = getattr(message, "tool_calls", None)
            if not calls:
                rewritten.append(message)
                continue
            new_calls: list[Any] = []
            changed = False
            for call in calls:
                if not isinstance(call, dict):
                    new_calls.append(call)
                    continue
                record = by_id.get(str(call.get("id") or ""))
                args_json = str(record.get("args_json") or "") if record else ""
                parsed: dict[str, Any] | None = None
                if args_json.strip():
                    try:
                        loaded = json.loads(args_json)
                    except json.JSONDecodeError:
                        loaded = None
                    if isinstance(loaded, dict):
                        parsed = loaded
                name = str(record.get("name") or "") if record else ""
                if parsed is None and not name:
                    new_calls.append(call)
                    continue
                updated = dict(call)
                if name:
                    updated["name"] = name
                if parsed is not None:
                    updated["args"] = parsed
                changed = True
                new_calls.append(updated)
            if not changed:
                rewritten.append(message)
                continue
            copy = getattr(message, "model_copy", None)
            if callable(copy):
                rewritten.append(copy(update={"tool_calls": new_calls}))
            else:
                rewritten.append(message)
        return rewritten

    ACPHostedClient._tool_event_from_state = _tool_event_from_state  # type: ignore[method-assign]
    managed._tool_chunks = tool_chunks
    managed._collect_managed_chunk = collect
    managed._managed_history_messages = history
    _INSTALLED = True


__all__ = ["file_edits_from_update", "install_acp_file_edits"]
