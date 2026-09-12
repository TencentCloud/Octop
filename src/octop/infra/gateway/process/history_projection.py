"""Capture the current turn from harness stream state for cheap UI history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, convert_to_messages, message_to_dict

from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.thread_messages import ThreadMessageInput
from octop.infra.gateway.process.message_keys import STREAM_ERROR_CODE_KEY, STREAM_ERROR_FLAG

_USER_ROLES = frozenset({"human", "user"})
_ASSISTANT_ROLES = frozenset({"ai", "assistant"})


def _role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "").lower()
    return str(getattr(message, "type", None) or getattr(message, "role", "")).lower()


def _chunk_messages(chunk: dict[str, Any]) -> list[Any]:
    data = chunk.get("data")
    if isinstance(data, dict) and isinstance(data.get("messages"), list):
        return list(data["messages"])
    if isinstance(data, list):
        return list(data)
    return []


def message_input(message: Any) -> ThreadMessageInput | None:
    """Serialize one LangChain/dict message before entering a DB transaction."""
    try:
        converted = convert_to_messages([message])[0] if isinstance(message, dict) else message
        wire = message_to_dict(converted)
        role = _role(converted)
        if role in ("", "system"):
            return None
        return ThreadMessageInput(
            message_id=str(getattr(converted, "id", "") or "") or None,
            role=role,
            message_json=json.dumps(wire, ensure_ascii=False, default=str),
            created_at=now_ts(),
        )
    except Exception:
        return None


def message_inputs(
    messages: list[Any],
    *,
    dedupe_missing_ids: bool = False,
) -> list[ThreadMessageInput]:
    """Serialize and de-duplicate replays within one stream/backfill batch."""
    out: list[ThreadMessageInput] = []
    seen: set[str] = set()
    for message in messages:
        item = message_input(message)
        if item is None:
            continue
        key = f"id:{item.message_id}" if item.message_id else ""
        if not key and dedupe_missing_ids:
            key = "wire:" + hashlib.sha256(item.message_json.encode()).hexdigest()
        if not key:
            out.append(item)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _wire_text(item: ThreadMessageInput) -> str:
    try:
        wire = json.loads(item.message_json)
    except json.JSONDecodeError:
        return ""
    data = wire.get("data") if isinstance(wire, dict) else None
    content = data.get("content") if isinstance(data, dict) else None
    if content is None and isinstance(wire, dict):
        content = wire.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


@dataclass
class TurnHistoryTracker:
    """Keep only the current user turn from replay-prone state chunks."""

    seed_messages: list[Any] = field(default_factory=list)
    _state_messages: list[Any] = field(default_factory=list, init=False)
    _stream_text: str = field(default="", init=False)
    _reasoning_text: str = field(default="", init=False)
    _error_message: str = field(default="", init=False)
    _error_code: str | None = field(default=None, init=False)

    @classmethod
    def from_request(cls, request: dict[str, Any]) -> TurnHistoryTracker:
        raw = request.get("messages")
        return cls(seed_messages=list(raw) if isinstance(raw, list) else [])

    def observe(self, chunk: dict[str, Any]) -> None:
        kind = chunk.get("type")
        if kind in ("state_snapshot", "state_update"):
            messages = _chunk_messages(chunk)
            if not messages:
                return
            last_user = max(
                (index for index, msg in enumerate(messages) if _role(msg) in _USER_ROLES),
                default=-1,
            )
            if last_user >= 0:
                self._state_messages = messages[last_user:]
            else:
                self._state_messages.extend(messages)
            return
        if kind == "token":
            self._stream_text += str(chunk.get("content") or "")
            return
        if kind == "reasoning":
            self._reasoning_text += str(chunk.get("content") or "")
            return
        if kind == "error":
            text = str(chunk.get("message") or chunk.get("content") or "")
            if text:
                self._error_message = text
            code = chunk.get("error_code")
            if code:
                self._error_code = str(code)

    def _stream_message(self) -> ThreadMessageInput | None:
        if not self._stream_text and not self._reasoning_text:
            return None
        extra: dict[str, Any] = {}
        if self._reasoning_text:
            extra["reasoning_content"] = self._reasoning_text
        return message_input(AIMessage(content=self._stream_text, additional_kwargs=extra))

    def _error_input(self) -> ThreadMessageInput | None:
        if not self._error_message:
            return None
        extra: dict[str, Any] = {STREAM_ERROR_FLAG: True}
        if self._error_code:
            extra[STREAM_ERROR_CODE_KEY] = self._error_code
        return message_input(AIMessage(content=self._error_message, additional_kwargs=extra))

    def _inputs_cover_stream(self, items: list[ThreadMessageInput]) -> bool:
        if not self._stream_text:
            return False
        return any(
            item.role in _ASSISTANT_ROLES and self._stream_text in _wire_text(item)
            for item in items
        )

    @property
    def inputs(self) -> list[ThreadMessageInput]:
        state_has_user = any(_role(msg) in _USER_ROLES for msg in self._state_messages)
        source = (
            self._state_messages if state_has_user else [*self.seed_messages, *self._state_messages]
        )
        items = message_inputs(
            source,
            dedupe_missing_ids=True,
        )
        if not self._inputs_cover_stream(items):
            streamed = self._stream_message()
            if streamed is not None:
                items.append(streamed)
        error = self._error_input()
        if error is not None:
            items.append(error)
        return items
