"""Sniff harness stream chunks for token usage and append to the ledger."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

_USER_ROLES = frozenset({"human", "user"})
_AI_ROLES = frozenset({"ai", "assistant"})


def _msg_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or msg.get("type") or "").lower()
    raw = getattr(msg, "type", None)
    if raw:
        return str(raw).lower()
    name = type(msg).__name__.lower()
    if "human" in name:
        return "human"
    if "ai" in name:
        return "ai"
    return ""


def _is_user(msg: Any) -> bool:
    return _msg_role(msg) in _USER_ROLES


def _is_ai(msg: Any) -> bool:
    return _msg_role(msg) in _AI_ROLES


def _msg_usage(msg: Any) -> dict[str, Any] | None:
    usage = getattr(msg, "usage_metadata", None)
    if usage is None and isinstance(msg, dict):
        usage = msg.get("usage_metadata")
    if isinstance(usage, dict) and usage:
        return usage
    return None


def _msg_model(msg: Any) -> str:
    rm = getattr(msg, "response_metadata", None)
    if rm is None and isinstance(msg, dict):
        rm = msg.get("response_metadata")
    if isinstance(rm, dict):
        return str(rm.get("model_name") or rm.get("model") or "")
    return ""


def _chunk_messages(chunk: dict[str, Any]) -> list[Any]:
    data = chunk.get("data")
    if isinstance(data, dict):
        raw = data.get("messages")
        return list(raw) if isinstance(raw, list) else []
    if isinstance(data, list):
        return data
    return []


def _token_int(value: Any) -> int:
    """Parse a token count; malformed values must not raise."""
    if isinstance(value, bool) or value is None:
        return 0
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _usage_io(usage: dict[str, Any]) -> tuple[int, int]:
    input_tokens = _token_int(usage.get("input_tokens")) or _token_int(usage.get("prompt_tokens"))
    output_tokens = _token_int(usage.get("output_tokens")) or _token_int(
        usage.get("completion_tokens")
    )
    return input_tokens, output_tokens


def turn_usage_from_messages(messages: list[Any]) -> dict[str, Any] | None:
    """Sum ``usage_metadata`` on AI messages after the last user message.

    Agent turns make multiple LLM calls (plan → tools → final reply). Each
    AIMessage carries *that call's* tokens; the ledger must record the sum,
    not the last call alone.
    """
    last_user = -1
    for i, msg in enumerate(messages):
        if _is_user(msg):
            last_user = i

    input_tokens = 0
    output_tokens = 0
    model = ""
    saw = False
    for msg in messages[last_user + 1 :]:
        if not _is_ai(msg):
            continue
        usage = _msg_usage(msg)
        if usage is None:
            continue
        inp, out = _usage_io(usage)
        if inp == 0 and out == 0:
            continue
        saw = True
        input_tokens += inp
        output_tokens += out
        name = _msg_model(msg)
        if name:
            model = name
    if not saw:
        return None
    payload: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    if model:
        payload["model"] = model
    return payload


def extract_usage_from_chunk(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort extraction of usage_metadata from a streaming chunk.

    ``state_snapshot`` carries the full thread; usage is the current turn
    total (every AI call after the last user message). ``state_update``
    usually carries only new messages — an AI-only list is that call's
    tokens, while a list that includes a user message is treated as a
    turn total.
    """
    if not isinstance(chunk, dict):
        return None

    direct = chunk.get("usage")
    if isinstance(direct, dict):
        return direct

    if chunk.get("type") not in ("state_snapshot", "state_update"):
        return None

    messages = _chunk_messages(chunk)
    if not messages:
        return None
    return turn_usage_from_messages(messages)


def _add_usage(base: dict[str, Any] | None, found: dict[str, Any]) -> dict[str, Any]:
    if base is None:
        return dict(found)
    input_tokens = _token_int(base.get("input_tokens")) + _token_int(found.get("input_tokens"))
    output_tokens = _token_int(base.get("output_tokens")) + _token_int(found.get("output_tokens"))
    model = str(found.get("model") or base.get("model") or "")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "model": model,
    }


@dataclass
class UsageTracker:
    """Collect token usage for one harness stream (one chat turn).

    ``state_snapshot`` is authoritative: each snapshot replaces the total
    with the full-turn sum. ``state_update`` is only accumulated until the
    first snapshot, so a replayed AI message after a snapshot cannot
    double-count.
    """

    usage: dict[str, Any] | None = field(default=None, init=False)
    _seen_snapshot: bool = field(default=False, init=False)

    def observe(self, chunk: dict[str, Any]) -> None:
        found = extract_usage_from_chunk(chunk)
        if not found or not isinstance(chunk, dict):
            return
        if isinstance(chunk.get("usage"), dict):
            self.usage = found
            return
        if chunk.get("type") == "state_snapshot":
            self.usage = found
            self._seen_snapshot = True
            return
        if self._seen_snapshot:
            return
        messages = _chunk_messages(chunk)
        if any(_is_user(m) for m in messages):
            self.usage = found
            return
        self.usage = _add_usage(self.usage, found)


def record_turn_usage(
    usage_repo: Any,
    *,
    agent_id: str,
    user_id: int,
    thread_id: str,
    usage: dict[str, Any],
    source: str = "chat",
) -> None:
    """Append one usage row. Best-effort — malformed payloads must not break chat."""
    with contextlib.suppress(Exception):
        inp, out = _usage_io(usage)
        usage_repo.record(
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            model=str(usage.get("model") or ""),
            input_tokens=inp,
            output_tokens=out,
            source=source,
        )
