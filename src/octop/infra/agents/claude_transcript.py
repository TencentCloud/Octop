"""Replay terminal session transcripts (Claude Code, Kiro) into an agent's memory (L0).

Claude Code already writes a complete session transcript to
``~/.claude/projects/<project>/<sessionId>.jsonl``: every user prompt, assistant
reply, tool call and tool result, each with its own timestamp. Re-capturing that
session through ``memory_capture`` cannot reproduce it — a real session has
hundreds of turns and dozens of tool calls — so this module replays the
transcript straight into L0 instead, where the normal extraction pipeline
(``extract`` → candidate → promote → atom) picks it up unchanged.

Record mapping (record types that carry no conversation content — ``progress`` /
``queue-operation`` / ``last-prompt`` / ``system`` — are ignored):

============================  =====================  ==========================
Claude Code record            L0 ``event_type``     payload
============================  =====================  ==========================
user, ``content`` str/text    ``user_message``       —
user, ``tool_result`` block   ``tool_result``        tool_use_id, is_error
assistant, ``text`` block     ``assistant_message``  —
assistant, ``tool_use`` block ``tool_call``          tool_name, input
assistant, ``thinking``       —                      skipped (scratchpad)
============================  =====================  ==========================

Every event carries ``payload["src_key"] = "<record id>:<sub index>"``, which
makes the import idempotent: keys already present in the target session are
skipped, so re-running a file (or a transcript that grew with new turns) only
appends what is missing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from octop_memory.types import RawEventType

logger = logging.getLogger(__name__)

DEFAULT_HOST = "claude-code"
"""``RawEvent.host`` stamped on imported events (``memory_raws(host=…)`` filter)."""

SESSION_PREFIX = "cc:"
"""L0 session id prefix; one Claude Code session maps onto one octop session."""

_MAX_CONTENT_CHARS = 4000
"""Cap on a stored L0 body.

A ``tool_result`` can be an entire file or build log, and the extractor prompt
receives every event's ``content`` in one call — so bodies have to stay bounded.
"""

_MAX_PAYLOAD_CHARS = 4000
"""Cap on a single serialized payload value (tool inputs are stored verbatim)."""

_MESSAGE_EVENT_TYPES: frozenset[str] = frozenset({"user_message", "assistant_message"})
"""The two event types a whole-message marker check may drop."""

_TOOL_EVENT_POLICIES: dict[str, frozenset[str]] = {
    "all": frozenset(),
    "calls": frozenset({"tool_result"}),
    "none": frozenset({"tool_call", "tool_result"}),
}
"""``tool_events`` value → the tool event types to drop from L0.

This is a *landing* policy, not an upload filter: the terminal always ships the whole
transcript (byte-delta, gzip+base64) and the parser reads every record — the policy
only decides which records become L0 rows. The product entry points (the
``memory_capture`` tool and ``octop memory import-claude``) default to ``none``:
L0 raw events feed the extractor and act as the recall fallback layer, and tool
traffic is 79% of a transcript's bytes (``tool_result`` alone 61%), so keeping it
dilutes what the session's memories look like. ``calls`` keeps what the agent did
and drops the output; ``all`` keeps the record whole for callers that want it.
"""


def _dropped_tool_types(tool_events: str) -> frozenset[str]:
    try:
        return _TOOL_EVENT_POLICIES[tool_events]
    except KeyError:
        raise ValueError(
            f"unknown tool_events {tool_events!r}; expected one of {sorted(_TOOL_EVENT_POLICIES)}"
        ) from None


_EXISTING_SCAN_LIMIT = 100_000
"""How many existing L0 rows to scan for ``cc_key`` when deduplicating."""

_OWN_READ_TOOLS: frozenset[str] = frozenset(
    {
        "memory_recall",
        "memory_search",
        "memory_get",
        "memory_raws",
        "memory_candidates",
    }
)
"""Our own memory *read* tools.

Their tool results restate what is already stored, so importing them back into L0
would close the "inject → capture → recall again" loop. They are dropped at parse
time — before the marker-based check — because a hook may format its own
injection block and lose the marker.

``memory_recall`` is no longer exposed by the MCP server; it stays listed so
transcripts recorded by earlier installs still get filtered.
"""


def _is_own_read_tool(tool_name: str) -> bool:
    """True for our read tools under any client naming.

    The MCP entry may be called ``octop-memory-local`` / ``-prod`` / ``-oauth`` or
    anything the user renamed it to, so only the tool name decides: the bare
    ``memory_search``, Claude Code's ``mcp__<server>__memory_search`` and Kiro's
    ``mcp_<server>_memory_search``.
    """
    tail = tool_name.rsplit("__", 1)[-1]
    return tail in _OWN_READ_TOOLS or any(tool_name.endswith(name) for name in _OWN_READ_TOOLS)


@dataclass(frozen=True)
class TranscriptEvent:
    """One L0 event mapped out of a Claude Code transcript record."""

    key: str
    event_type: RawEventType
    content: str
    timestamp: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class ParsedSession:
    """Result of parsing one ``.jsonl`` transcript."""

    session_id: str | None
    """The Claude Code ``sessionId`` (``None`` when no record carried one)."""

    events: list[TranscriptEvent]

    skipped_own_results: int = 0
    """Tool results dropped because they came from our own memory read tools."""
    skipped_tools: int = 0
    """Tool events dropped by the caller's ``tool_events`` policy."""


@dataclass
class ImportStats:
    """Per-file import counters, reported back to the caller."""

    session_id: str
    parsed: int = 0
    imported: int = 0
    skipped_existing: int = 0
    skipped_echo: int = 0
    """Events dropped because their content carried a recall-injection marker."""
    skipped_own_results: int = 0
    """Tool results dropped because they came from our own memory read tools."""
    skipped_tools: int = 0
    """Tool events dropped by the caller's ``tool_events`` policy."""
    sidechain: int = 0
    dry_run: bool = False
    warnings: list[str] = field(default_factory=list)
    by_type: dict[str, int] = field(default_factory=dict)
    """Parsed-event histogram (``event_type`` -> count), for caller verification."""


# ---------------------------------------------------------------------------
# parsing (pure — no writes, no memory instance)
# ---------------------------------------------------------------------------


def _iter_records(text: str) -> Iterator[Any]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            logger.debug("claude_transcript: skipping malformed transcript line")


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)) and value:
        # DSH writes epoch milliseconds (``time``), older hosts seconds.
        seconds = value / 1000 if value > 1e11 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return datetime.now(UTC)
    if isinstance(value, str) and value:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _block_text(value: Any) -> str:
    """Flatten a tool-result body (string, or a list of content blocks) to text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [
            str(block.get("text") or "")
            for block in value
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def _cap(text: str, limit: int = _MAX_CONTENT_CHARS) -> str:
    body = (text or "").strip()
    return body if len(body) <= limit else body[: limit - 1].rstrip() + "…"


def _bounded(value: Any) -> Any:
    """Keep a payload value structured but bounded (payload is stored verbatim)."""
    if isinstance(value, str):
        return _cap(value, _MAX_PAYLOAD_CHARS)
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)[:_MAX_PAYLOAD_CHARS]
    if len(encoded) <= _MAX_PAYLOAD_CHARS:
        return value
    return {"truncated_json": encoded[:_MAX_PAYLOAD_CHARS]}


def _blocks(content: Any) -> list[dict[str, Any]]:
    """Normalize a message body to a list of content blocks."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _map_block(
    block: dict[str, Any], *, role: str
) -> tuple[RawEventType, str, dict[str, Any]] | None:
    """Map one content block to ``(event_type, content, payload extras)``."""
    block_type = block.get("type")
    if block_type == "text":
        text = str(block.get("text") or "")
        if not text.strip():
            return None
        event_type: RawEventType = "user_message" if role == "user" else "assistant_message"
        return event_type, _cap(text), {}
    if block_type == "tool_use":
        name = str(block.get("name") or "tool")
        args = block.get("input")
        summary = json.dumps(args, ensure_ascii=False, default=str) if args else ""
        return (
            "tool_call",
            _cap(f"{name} {summary}".strip()),
            {"tool_use_id": block.get("id"), "tool_name": name, "input": _bounded(args)},
        )
    if block_type == "tool_result":
        body = _cap(_block_text(block.get("content")))
        return (
            "tool_result",
            body or "(empty tool result)",
            {"tool_use_id": block.get("tool_use_id"), "is_error": bool(block.get("is_error"))},
        )
    # ``thinking`` (model scratchpad), images and unknown blocks are not L0 material.
    return None


def parse_text(text: str) -> ParsedSession:
    """Map transcript JSONL *content* to L0 events (pure, no writes).

    This is the entry point for callers that receive the transcript over the
    wire (a cloud deployment cannot read the client's ``~/.claude`` directory).
    """
    session_id: str | None = None
    events: list[TranscriptEvent] = []
    tool_names: dict[str, str] = {}
    skipped_own = 0
    for index, record in enumerate(_iter_records(text)):
        if not isinstance(record, dict):
            continue
        record_type = record.get("type")
        if record_type not in ("user", "assistant"):
            continue
        raw_session = record.get("sessionId")
        if session_id is None and raw_session:
            session_id = str(raw_session)
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or record_type)
        timestamp = _parse_timestamp(record.get("timestamp"))
        record_uuid = str(record.get("uuid") or f"line{index}")
        sidechain = bool(record.get("isSidechain"))
        for block_index, block in enumerate(_blocks(message.get("content"))):
            if block.get("type") == "tool_use":
                call_id = block.get("id")
                if isinstance(call_id, str):
                    tool_names[call_id] = str(block.get("name") or "")
            elif block.get("type") == "tool_result":
                call_id = block.get("tool_use_id")
                origin = tool_names.get(str(call_id) or "", "")
                if origin and _is_own_read_tool(origin):
                    skipped_own += 1
                    continue
            mapped = _map_block(block, role=role)
            if mapped is None:
                continue
            event_type, content, extra = mapped
            key = f"{record_uuid}:{block_index}"
            events.append(
                TranscriptEvent(
                    key=key,
                    event_type=event_type,
                    content=content,
                    timestamp=timestamp,
                    payload={
                        "source": DEFAULT_HOST,
                        "src_key": key,
                        "role": role,
                        "sidechain": sidechain,
                        **{name: value for name, value in extra.items() if value is not None},
                    },
                )
            )
    return ParsedSession(session_id=session_id, events=events, skipped_own_results=skipped_own)


def parse_session(path: Path) -> ParsedSession:
    """Map a transcript *file* to L0 events (same-host callers)."""
    return parse_text(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Kiro (``~/.kiro/sessions/<workspace>/<session_id>/messages.jsonl``)
# ---------------------------------------------------------------------------

_KIRO_KINDS: dict[str, str] = {
    "user": "user_message",
    "assistant": "assistant_message",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
}
"""Kiro ``payload.type`` → L0 ``event_type``.

Everything else Kiro writes (``turn_start`` / ``turn_end`` / ``session_metadata`` /
``usage_summary`` / ``session_event`` / ``pending_interaction`` /
``interaction_resolved``) carries no conversation content. ``ContextualHookInvoked``
is deliberately absent: that is our own hook invocation — it even carries the hook's
``output`` — i.e. exactly the plumbing that must not become memory.
"""

_KIRO_SCRATCHPAD: frozenset[str] = frozenset({"Reasoning"})
"""``assistant.operationType`` that is the model's scratchpad (Kiro's thinking)."""


def _map_kiro_payload(payload: dict[str, Any]) -> tuple[RawEventType, str, dict[str, Any]] | None:
    kind = payload.get("type")
    event_type = _KIRO_KINDS.get(kind) if isinstance(kind, str) else None
    if event_type is None:
        return None
    if event_type in ("user_message", "assistant_message"):
        if str(payload.get("operationType") or "") in _KIRO_SCRATCHPAD:
            return None
        text = str(payload.get("content") or "")
        if not text.strip():
            return None
        return event_type, _cap(text), {}
    if event_type == "tool_call":
        name = str(payload.get("toolName") or "tool")
        args = payload.get("args")
        summary = json.dumps(args, ensure_ascii=False, default=str) if args else ""
        return (
            "tool_call",
            _cap(f"{name} {summary}".strip()),
            {
                "tool_use_id": payload.get("toolCallId"),
                "tool_name": name,
                "input": _bounded(args),
            },
        )
    body = _cap(str(payload.get("content") or ""))
    return (
        "tool_result",
        body or "(empty tool result)",
        {"tool_use_id": payload.get("toolCallId"), "success": payload.get("success")},
    )


def parse_kiro_text(text: str) -> ParsedSession:
    """Map a Kiro ``messages.jsonl`` to L0 events (pure, no writes).

    The Kiro session id is the **directory** name, not a record field, so callers
    pass it explicitly (the hook does: ``session_id="kiro:<id>"``).
    """
    events: list[TranscriptEvent] = []
    skipped_own = 0
    for index, record in enumerate(_iter_records(text)):
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "ContextualHookInvoked":
            skipped_own += 1
            continue
        mapped = _map_kiro_payload(payload)
        if mapped is None:
            continue
        event_type, content, extra = mapped
        record_id = str(record.get("id") or f"line{index}")
        key = f"{record_id}:0"
        events.append(
            TranscriptEvent(
                key=key,
                event_type=event_type,
                content=content,
                timestamp=_parse_timestamp(record.get("timestamp")),
                payload={
                    "source": DEFAULT_HOST,
                    "src_key": key,
                    "role": "user"
                    if event_type in ("user_message", "tool_result")
                    else "assistant",
                    "sidechain": False,
                    **{name: value for name, value in extra.items() if value is not None},
                },
            )
        )
    return ParsedSession(session_id=None, events=events, skipped_own_results=skipped_own)


# ---------------------------------------------------------------------------
# DSH (``~/.dsh/sessions/<escaped-cwd>/<session-id>/session.jsonl.zstd``)
# ---------------------------------------------------------------------------

_DSH_TOOL_BLOCK_TYPES: frozenset[str] = frozenset({"tool-call"})
"""Block types that restate a call already emitted as its own ``tool/call`` record."""


def _dsh_text_blocks(blocks: Any) -> str:
    """Join the ``text`` blocks of a DSH content array (images / attachments dropped)."""
    if not isinstance(blocks, list):
        return ""
    parts = [
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(part for part in parts if part)


def _dsh_event(
    key: str,
    event_type: RawEventType,
    content: str,
    timestamp: datetime,
    role: str,
    extra: dict[str, Any] | None = None,
) -> TranscriptEvent:
    return TranscriptEvent(
        key=key,
        event_type=event_type,
        content=content,
        timestamp=timestamp,
        payload={
            "source": DEFAULT_HOST,
            "src_key": key,
            "role": role,
            "sidechain": False,
            **(extra or {}),
        },
    )


def parse_dsh_text(text: str) -> ParsedSession:
    """Map a DSH ``session.jsonl`` to L0 events (pure, no writes).

    DSH streams its answer in ``assistant/chunk`` / ``reasoning-chunks`` /
    ``text-chunks`` records and then writes the finished message — only the finished
    records are mapped, otherwise every token would land in L0 twice. A call also
    appears twice (as a ``tool/call`` record and as a ``tool-call`` block inside
    ``assistant/message``), so the record wins and the block is skipped by call id.
    """
    records = [record for record in _iter_records(text) if isinstance(record, dict)]
    canonical_calls = {
        str((record.get("data") or {}).get("callId") or "")
        for record in records
        if record.get("type") == "tool/call"
    }
    session_id: str | None = None
    events: list[TranscriptEvent] = []
    skipped_own = 0
    for index, record in enumerate(records):
        record_type = record.get("type")
        raw_data = record.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        timestamp = _parse_timestamp(record.get("time"))
        seq = record.get("seq", f"line{index}")
        if record_type == "session":
            session_id = session_id or str(record.get("id") or "") or None
        elif record_type == "user/message":
            raw_source = data.get("source")
            kind = str(raw_source.get("kind") or "") if isinstance(raw_source, dict) else ""
            if kind and kind != "user":
                skipped_own += 1
                continue
            body = _cap(_dsh_text_blocks(data.get("content")))
            if body.strip():
                events.append(_dsh_event(f"{seq}:0", "user_message", body, timestamp, "user"))
        elif record_type == "assistant/message":
            raw_message = data.get("message")
            message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
            for block_index, block in enumerate(message.get("content") or []):
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    body = _cap(str(block.get("text") or ""))
                    if body.strip():
                        events.append(
                            _dsh_event(
                                f"{seq}:{block_index}",
                                "assistant_message",
                                body,
                                timestamp,
                                "assistant",
                            )
                        )
                elif (
                    block_type in _DSH_TOOL_BLOCK_TYPES
                    and str(block.get("id") or "") not in canonical_calls
                ):
                    events.append(_dsh_tool_call(block, f"{seq}:{block_index}", timestamp))
        elif record_type == "tool/call":
            events.append(
                _dsh_tool_call(
                    {
                        "id": data.get("callId"),
                        "name": data.get("name"),
                        "arguments": data.get("arguments"),
                    },
                    f"{seq}:0",
                    timestamp,
                )
            )
        elif record_type == "tool/result":
            raw_result = data.get("message")
            result_message: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
            for block_index, block in enumerate(result_message.get("content") or []):
                if not isinstance(block, dict) or block.get("type") != "tool-result":
                    continue
                body = _cap(_dsh_text_blocks(block.get("content")))
                events.append(
                    _dsh_event(
                        f"{seq}:{block_index}",
                        "tool_result",
                        body or "(empty tool result)",
                        timestamp,
                        "user",
                        {
                            "tool_use_id": block.get("toolCallId"),
                            "is_error": block.get("isError"),
                        },
                    )
                )
        # every other record type is streaming delta / turn-step / metadata noise
    return ParsedSession(session_id=session_id, events=events, skipped_own_results=skipped_own)


def _dsh_tool_call(block: dict[str, Any], key: str, timestamp: datetime) -> TranscriptEvent:
    name = str(block.get("name") or "tool")
    raw_args = block.get("arguments")
    parsed: Any = raw_args
    if isinstance(raw_args, str) and raw_args.strip():
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            parsed = raw_args
    summary = json.dumps(parsed, ensure_ascii=False, default=str) if parsed else ""
    return _dsh_event(
        key,
        "tool_call",
        _cap(f"{name} {summary}".strip()),
        timestamp,
        "assistant",
        {"tool_use_id": block.get("id"), "tool_name": name, "input": _bounded(parsed)},
    )


# ---------------------------------------------------------------------------
# Codex CLI (``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``)
# ---------------------------------------------------------------------------

_CODEX_TOOL_ITEM_TYPES: frozenset[str] = frozenset(
    {"function_call", "local_shell_call", "custom_tool_call", "web_search_call"}
)
_CODEX_TOOL_OUTPUT_TYPES: frozenset[str] = frozenset(
    {"function_call_output", "local_shell_call_output", "custom_tool_call_output"}
)
_CODEX_TEXT_ITEM_TYPES: frozenset[str] = frozenset({"input_text", "output_text", "text"})
"""Codex rollout records: ``event_msg`` carries the conversation, ``response_item``
the wire-level items (developer instructions, tool calls, and a copy of the
messages). Both are folded here with a text-level dedupe so a turn is never stored
twice."""


def _codex_item_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in _CODEX_TEXT_ITEM_TYPES:
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
        elif isinstance(block, str) and block.strip():
            parts.append(block)
    return "\n".join(parts)


def parse_codex_text(text: str) -> ParsedSession:
    """Map a Codex rollout JSONL to L0 events (pure, no writes)."""
    events: list[TranscriptEvent] = []
    skipped_own = 0
    seen_messages: set[str] = set()
    for index, record in enumerate(_iter_records(text)):
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        record_type = str(record.get("type") or "")
        payload_type = str(payload.get("type") or "")
        record_id = str(payload.get("id") or record.get("id") or f"line{index}")
        key = f"{record_id}:0"
        event_type = ""
        content = ""
        extra: dict[str, Any] = {}

        if record_type == "event_msg":
            if payload_type == "user_message":
                event_type, content = "user_message", str(payload.get("message") or "")
            elif payload_type == "agent_message":
                event_type, content = "assistant_message", str(payload.get("message") or "")
            else:
                continue  # task_started / token_count / turn_aborted … plumbing
            if not content.strip():
                continue
            seen_messages.add(content.strip())
        elif record_type == "response_item":
            if payload_type in _CODEX_TOOL_ITEM_TYPES:
                event_type = "tool_call"
                name = str(payload.get("name") or payload_type)
                content = f"{name} {json.dumps(payload.get('arguments') or payload.get('action') or {}, ensure_ascii=False)}"
            elif payload_type in _CODEX_TOOL_OUTPUT_TYPES:
                event_type = "tool_result"
                output = payload.get("output")
                content = (
                    output
                    if isinstance(output, str)
                    else json.dumps(output or "", ensure_ascii=False)
                )
            elif payload_type == "message":
                role = str(payload.get("role") or "")
                if role not in ("user", "assistant"):
                    skipped_own += 1  # developer/system instructions are host plumbing
                    continue
                body = _codex_item_text(payload.get("content"))
                if not body.strip():
                    continue
                event_type = "user_message" if role == "user" else "assistant_message"
                content = body
                if content.strip() in seen_messages:
                    skipped_own += 1  # same turn already taken from event_msg
                    continue
                seen_messages.add(content.strip())
            else:
                continue  # reasoning / other wire items
        else:
            continue  # session_meta / turn_context / world_state

        events.append(
            TranscriptEvent(
                key=key,
                event_type=event_type,
                content=content,
                timestamp=_parse_timestamp(record.get("timestamp")),
                payload={
                    "source": DEFAULT_HOST,
                    "src_key": key,
                    "role": "user"
                    if event_type in ("user_message", "tool_result")
                    else "assistant",
                    "sidechain": False,
                    **{name: value for name, value in extra.items() if value is not None},
                },
            )
        )
    return ParsedSession(session_id=None, events=events, skipped_own_results=skipped_own)


# ---------------------------------------------------------------------------
# Cursor (``~/.cursor/hooks.json`` -> ``transcript_path``)
# ---------------------------------------------------------------------------

_CURSOR_ROLE_KEYS: tuple[str, ...] = ("role", "type", "author", "sender")
_CURSOR_TEXT_KEYS: tuple[str, ...] = ("text", "content", "message", "value")


def _cursor_role(record: dict[str, Any]) -> str:
    for name in _CURSOR_ROLE_KEYS:
        value = record.get(name)
        if isinstance(value, str) and value.lower() in (
            "user",
            "human",
            "assistant",
            "ai",
            "agent",
            "bot",
        ):
            return "user" if value.lower() in ("user", "human") else "assistant"
    return ""


def _cursor_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _codex_item_text(value)
    if isinstance(value, dict):
        for name in _CURSOR_TEXT_KEYS:
            if name in value:
                nested = _cursor_text(value[name])
                if nested.strip():
                    return nested
    return ""


def _cursor_stable_key(record: dict[str, Any], *, role: str, body: str) -> str:
    """Idempotency key that stays stable across byte-delta uploads.

    Cursor agent-transcript lines usually have no ``id`` / ``uuid``. The old
    fallback ``line{index}:0`` renumbered from 0 inside every delta the stop
    hook ships, so the user turn at the head of each chunk reused ``line0:0``
    and was dropped as ``skipped_existing`` while later assistant lines
    (higher indices) still imported. Prefer a real id when present; otherwise
    hash ``role`` + body so re-sends dedupe but distinct turns do not collide.
    """
    for name in ("id", "uuid"):
        value = record.get(name)
        if isinstance(value, str) and value.strip():
            return f"{value.strip()}:0"
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return f"{text}:0"
    digest = hashlib.sha256(f"{role}\0{body}".encode()).hexdigest()[:16]
    return f"c{digest}:0"


def parse_cursor_text(text: str) -> ParsedSession:
    """Map a Cursor transcript to L0 events (pure, no writes).

    The ``stop`` hook's ``transcript_path`` points at
    ``~/.cursor/projects/<workspace>/agent-transcripts/<id>/<id>.jsonl``.
    Each line is ``{"role","message":{"content":[{"type":"text","text":…}]}}``;
    tool blocks in that array are dropped. A JSON array or
    ``{"messages":[…]}`` / ``{"turns":[…]}`` is still accepted.

    ``src_key`` is content-stable (see :func:`_cursor_stable_key`) so the hook's
    byte-delta uploads stay idempotent without colliding across chunks.
    """
    events: list[TranscriptEvent] = []
    skipped_own = 0
    records: list[Any] = []
    stripped = text.lstrip()
    if stripped.startswith("["):
        loaded = json.loads(text)
        records = loaded if isinstance(loaded, list) else []
    elif stripped.startswith("{"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            for name in ("messages", "turns", "items", "conversation"):
                if isinstance(loaded.get(name), list):
                    records = loaded[name]
                    break
            else:
                records = [loaded]
        else:
            records = list(_iter_records(text))  # JSONL fallback
    else:
        records = list(_iter_records(text))

    for record in records:
        if not isinstance(record, dict):
            continue
        role = _cursor_role(record)
        if not role:
            skipped_own += 1  # tool/system entries carry no conversational role
            continue
        body = ""
        for name in _CURSOR_TEXT_KEYS:
            if name in record:
                body = _cursor_text(record[name])
                if body.strip():
                    break
        if not body.strip():
            continue
        key = _cursor_stable_key(record, role=role, body=body)
        events.append(
            TranscriptEvent(
                key=key,
                event_type="user_message" if role == "user" else "assistant_message",
                content=body,
                timestamp=_parse_timestamp(
                    record.get("timestamp") or record.get("createdAt") or record.get("created_at")
                ),
                payload={
                    "source": DEFAULT_HOST,
                    "src_key": key,
                    "role": role,
                    "sidechain": False,
                },
            )
        )
    return ParsedSession(session_id=None, events=events, skipped_own_results=skipped_own)


_PARSERS: dict[str, Callable[[str], ParsedSession]] = {
    "claude-code": parse_text,
    "kiro": parse_kiro_text,
    "dsh": parse_dsh_text,
    "codex": parse_codex_text,
    "cursor": parse_cursor_text,
}
"""``source`` → transcript parser. A terminal's name picks its parser."""

SESSION_PREFIXES: dict[str, str] = {
    "claude-code": "cc:",
    "kiro": "kiro:",
    "dsh": "dsh:",
    "codex": "codex:",
    "cursor": "cursor:",
}
"""L0 session-id prefix per terminal, so one terminal's sessions never collide."""

# ---------------------------------------------------------------------------
# import (writes L0 through the target agent's memory store)
# ---------------------------------------------------------------------------


USER_MESSAGE = "user_message"
"""The user side of a transcript; used to tell injected context from a reply."""


def attribute_user(content: str, caller: str | None) -> str:
    """Prefix ``<caller>说：`` so the sender survives into the extracted atom.

    harness-memory serialises only ``event_id / event_type / content / timestamp /
    session_id`` for the extractor prompt (``pipeline/extractor/__init__.py``), and
    ``AtomCard`` has no user column — so the raw event's ``user`` field never reaches
    the model. Writing the sender into the content is the only way "who said it"
    survives extraction, stays FTS-searchable and shows up verbatim on recall.
    Already-prefixed content is left alone, so a re-send cannot double it.
    """
    name = (caller or "").strip()
    if not name:
        return content
    prefix = f"{name}说："
    return content if content.startswith(prefix) else prefix + content


def _is_echo(content: str, event_type: str, markers: tuple[str, ...]) -> bool:
    """This event is our own injected text coming back, not the user's words.

    Two shapes, because the two roles differ:

    * assistant side — only a block that *starts* with the marker is ours. A reply
      that merely quotes the marker (explaining how the hooks work) is real content
      and must survive;
    * user side — the marker anywhere means it is the context we injected (Claude
      Code also prefixes it, e.g. ``Stop hook feedback:``), so it is dropped.
    """
    if any(content.lstrip().startswith(marker) for marker in markers):
        return True
    return event_type == USER_MESSAGE and any(marker in content for marker in markers)


def _persist(
    memory: Any,
    parsed: ParsedSession,
    *,
    fallback_session: str,
    session_id: str | None,
    user: str | None,
    host: str,
    dry_run: bool,
    skip_markers: tuple[str, ...] = (),
    skip_message_markers: tuple[str, ...] = (),
    tool_events: str = "all",
    session_prefix: str = SESSION_PREFIX,
) -> ImportStats:
    """Deduplicate a parsed session against L0 and append only the missing events.

    Accounting: ``parsed = imported + skipped_existing + skipped_echo + skipped_tools``
    plus the ``skipped_own_results`` the parser already dropped.
    """
    from octop_memory.types import RawEvent  # noqa: PLC0415

    resolved_session = session_id or f"{session_prefix}{parsed.session_id or fallback_session}"
    stats = ImportStats(
        session_id=resolved_session,
        parsed=len(parsed.events),
        dry_run=dry_run,
        skipped_own_results=parsed.skipped_own_results,
    )

    candidates = parsed.events
    if skip_markers or skip_message_markers:
        kept = [
            event
            for event in candidates
            # 我们的注入块以标记**开头**；模型回答里只是引用该标记（例如解释接入方式）
            # 时必须保留——否则会把正常对话当回声丢掉。
            if not _is_echo(event.content, event.event_type, skip_markers)
            # Injected *messages* are plumbing; the same string inside tool output is
            # just data (a file being read may quote it), so that check is narrower.
            and not (
                event.event_type in _MESSAGE_EVENT_TYPES
                and any(marker in event.content for marker in skip_message_markers)
            )
        ]
        stats.skipped_echo = len(candidates) - len(kept)
        candidates = kept

    drop_types = _dropped_tool_types(tool_events)
    if drop_types:
        kept = [event for event in candidates if event.event_type not in drop_types]
        stats.skipped_tools = len(candidates) - len(kept)
        candidates = kept

    stats.sidechain = sum(1 for event in candidates if event.payload.get("sidechain"))
    for event in candidates:
        stats.by_type[event.event_type] = stats.by_type.get(event.event_type, 0) + 1

    seen: set[str] = set()
    try:
        for existing in memory.list_raw(session_id=resolved_session, limit=_EXISTING_SCAN_LIMIT):
            # ``cc_key`` is the pre-Kiro name of the same field; old rows keep it.
            key = (existing.payload or {}).get("src_key") or (existing.payload or {}).get("cc_key")
            if isinstance(key, str):
                seen.add(key)
    except Exception:  # noqa: BLE001 - an audit scan must not lose the import
        logger.warning("claude_transcript: existing-event scan failed", exc_info=True)
        stats.warnings.append("existing-event scan failed; duplicate check degraded")

    pending = [event for event in candidates if event.key not in seen]
    stats.skipped_existing = len(candidates) - len(pending)
    if dry_run or not pending:
        return stats

    memory.add_raw_batch(
        [
            RawEvent(
                id=str(uuid.uuid4()),
                host=host,
                session_id=resolved_session,
                thread_id=resolved_session,
                user=user,
                timestamp=event.timestamp,
                event_type=event.event_type,
                # Only the human side is attributed (``event_type`` already marks the
                # other), and never a sidechain record — those "user" messages are a
                # subagent's synthetic prompt, not something the caller said.
                content=(
                    attribute_user(event.content, user)
                    if event.event_type == USER_MESSAGE and not event.payload.get("sidechain")
                    else event.content
                ),
                payload={**event.payload, "source": host},
            )
            for event in pending
        ]
    )
    stats.imported = len(pending)
    return stats


def import_content(
    memory: Any,
    content: str,
    *,
    session_id: str | None = None,
    user: str | None = None,
    host: str = DEFAULT_HOST,
    dry_run: bool = False,
    skip_markers: tuple[str, ...] = (),
    skip_message_markers: tuple[str, ...] = (),
    tool_events: str = "all",
    parser: str = "claude-code",
) -> ImportStats:
    """Replay transcript *content* (JSONL text) into L0.

    This is the upload path: a cloud deployment cannot read the client's
    ``~/.claude`` directory, so the terminal sends the file body instead.
    ``skip_markers`` drops events whose content carries one of those strings
    (e.g. this service's own recall-injection markers).
    """
    if parser not in _PARSERS:
        raise ValueError(
            f"unknown transcript parser {parser!r}; expected one of {sorted(_PARSERS)}"
        )
    return _persist(
        memory,
        _PARSERS[parser](content),
        fallback_session="upload",
        session_id=session_id,
        user=user,
        host=host,
        dry_run=dry_run,
        skip_markers=skip_markers,
        skip_message_markers=skip_message_markers,
        tool_events=tool_events,
        session_prefix=SESSION_PREFIXES.get(parser, SESSION_PREFIX),
    )


def import_session(
    memory: Any,
    path: Path,
    *,
    session_id: str | None = None,
    user: str | None = None,
    host: str = DEFAULT_HOST,
    dry_run: bool = False,
    skip_markers: tuple[str, ...] = (),
    skip_message_markers: tuple[str, ...] = (),
    tool_events: str = "all",
    parser: str = "claude-code",
) -> ImportStats:
    """Replay one transcript *file* into L0 (same-host callers).

    ``session_id`` defaults to ``cc:<claude session id>`` so one Claude Code
    session maps onto one octop session (extraction groups by session).
    """
    if parser not in _PARSERS:
        raise ValueError(
            f"unknown transcript parser {parser!r}; expected one of {sorted(_PARSERS)}"
        )
    # Kiro names every file ``messages.jsonl``; the session id is its parent dir.
    fallback = path.parent.name if path.name.startswith("messages") else path.stem
    return _persist(
        memory,
        _PARSERS[parser](path.read_text(encoding="utf-8")),
        fallback_session=fallback,
        session_id=session_id,
        user=user,
        host=host,
        dry_run=dry_run,
        skip_markers=skip_markers,
        skip_message_markers=skip_message_markers,
        tool_events=tool_events,
        session_prefix=SESSION_PREFIXES.get(parser, SESSION_PREFIX),
    )


__all__ = [
    "DEFAULT_HOST",
    "SESSION_PREFIX",
    "ImportStats",
    "ParsedSession",
    "TranscriptEvent",
    "SESSION_PREFIXES",
    "import_content",
    "import_session",
    "parse_dsh_text",
    "parse_kiro_text",
    "parse_session",
    "parse_text",
]
