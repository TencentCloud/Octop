"""Capture the current turn from harness stream state for cheap UI history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import convert_to_messages, message_to_dict

from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.thread_messages import ThreadMessageInput

_USER_ROLES = frozenset({"human", "user"})


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


@dataclass
class TurnHistoryTracker:
    """Keep only the current user turn from replay-prone state chunks."""

    seed_messages: list[Any] = field(default_factory=list)
    _state_messages: list[Any] = field(default_factory=list, init=False)

    @classmethod
    def from_request(cls, request: dict[str, Any]) -> TurnHistoryTracker:
        raw = request.get("messages")
        return cls(seed_messages=list(raw) if isinstance(raw, list) else [])

    def observe(self, chunk: dict[str, Any]) -> None:
        if chunk.get("type") not in ("state_snapshot", "state_update"):
            return
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

    @property
    def inputs(self) -> list[ThreadMessageInput]:
        state_has_user = any(_role(msg) in _USER_ROLES for msg in self._state_messages)
        source = (
            self._state_messages if state_has_user else [*self.seed_messages, *self._state_messages]
        )
        return message_inputs(
            source,
            dedupe_missing_ids=True,
        )
