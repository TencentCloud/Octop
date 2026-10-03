"""Track unresolved file-write tool failures for a single agent turn."""

from __future__ import annotations

from typing import Any

_FILE_WRITE_TOOLS = frozenset({"edit_file", "write_file"})


def _tool_name(name: Any) -> str:
    raw = str(name or "").strip().lower()
    return raw.rsplit("/", 1)[-1]


def _is_error_message(message: Any) -> bool:
    status = getattr(message, "status", None)
    if status is None and isinstance(message, dict):
        status = message.get("status")
    return str(status or "").lower() == "error"


class FileDeliveryTracker:
    """Keep file-write failures that have not been followed by recovery."""

    def __init__(self) -> None:
        self._call_names: dict[str, str] = {}
        self._unresolved: set[str] = set()

    def observe(self, chunk: dict[str, Any]) -> None:
        kind = chunk.get("type")
        if kind == "tool_call_chunk":
            call_id = str(chunk.get("id") or chunk.get("tool_call_id") or "")
            name = _tool_name(chunk.get("name"))
            if call_id and name in _FILE_WRITE_TOOLS:
                self._call_names[call_id] = name
            return
        if kind != "tool_result":
            return

        messages = chunk.get("messages")
        candidates = messages if isinstance(messages, list) else [chunk]
        for message in candidates:
            call_id = str(
                (
                    message.get("tool_call_id")
                    if isinstance(message, dict)
                    else getattr(message, "tool_call_id", "")
                )
                or chunk.get("id")
                or chunk.get("tool_call_id")
                or ""
            )
            name = _tool_name(
                (message.get("name") if isinstance(message, dict) else getattr(message, "name", ""))
                or chunk.get("name")
                or self._call_names.get(call_id)
            )
            if name not in _FILE_WRITE_TOOLS:
                continue
            failed = _is_error_message(message) or str(chunk.get("status") or "").lower() == "error"
            if failed:
                self._unresolved.add(call_id or name)
            else:
                self._unresolved.clear()
            if call_id:
                self._call_names.pop(call_id, None)

    @property
    def incomplete(self) -> bool:
        return bool(self._unresolved)


__all__ = ["FileDeliveryTracker"]
