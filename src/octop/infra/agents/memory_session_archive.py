"""Server-side markdown archive of the raw sessions uploaded to ``memory_capture``.

L0 keeps only what the extractor and recall need (user / assistant messages), so the
tool traffic and the model's scratchpad are dropped there. This writer keeps the
*uploaded* session as readable markdown next to the agent's memory store, so the full
record stays available for later review:

    {workspace}/.octop/memory-sessions/<session_id>.md

The client uploads byte-deltas of the transcript, so the file is **append-only**: each
upload renders its new records and adds them; re-sends (``mode=full`` after a lost
offset state) are deduplicated by the record key written as an HTML comment, which is
invisible when rendered. Failures must never break capture — callers treat them as
best-effort and log.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Reuse the transcript parser's record iteration and block normalization: the archive
# must agree with what the parser sees, and a second copy of those rules would drift.
from octop.infra.agents.claude_transcript import _block_text, _blocks, _iter_records

ARCHIVE_DIRNAME = "memory-sessions"
"""Subdirectory of the agent system dir (``{workspace}/.octop/``) holding the archives."""

_KEY_MARKER = "<!-- key: {} -->"
_KEY_PATTERN = re.compile(r"<!-- key: (\S+) -->")

_MAX_BODY_CHARS = 20000
"""Per-record cap in the markdown body — much looser than L0's 4000.

The archive is for human inspection, so it keeps far more of a long tool result than
the L0 row does; it still bounds a single record so one 5MB build log cannot dominate
the file.
"""


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _cap(text: str, limit: int = _MAX_BODY_CHARS) -> str:
    body = (text or "").strip()
    return body if len(body) <= limit else body[: limit - 1].rstrip() + "…"


def _fence(body: str, language: str) -> str:
    """Fence *body*, widening the fence when the body itself contains backticks."""
    fence = "```"
    while fence in body:
        fence += "`"
    return f"{fence}{language}\n{body}\n{fence}"


def _record_role(record: dict[str, Any]) -> str:
    return str(record.get("type") or "record")


def _render_record(key: str, record: dict[str, Any], index: int) -> str:
    """One transcript record → one markdown section (all blocks, nothing dropped)."""
    message = record.get("message")
    message = message if isinstance(message, dict) else {}
    role = str(message.get("role") or _record_role(record))
    stamp = record.get("timestamp")
    when = ""
    if isinstance(stamp, str) and stamp:
        when = stamp.replace("T", " ").replace("Z", "")[:19]
    lines: list[str] = [f"## {index} · {when or _now()} · {role}"]
    lines.append(_KEY_MARKER.format(key))
    lines.append("")
    sidechain = "（sidechain）" if record.get("isSidechain") else ""
    if sidechain:
        lines.append(sidechain)
        lines.append("")

    blocks = _blocks(message.get("content"))
    if not blocks:
        raw = record.get("content")
        if isinstance(raw, str) and raw.strip():
            blocks = [{"type": "text", "text": raw}]
    for block in blocks:
        kind = block.get("type")
        if kind == "text":
            body = _cap(str(block.get("text") or ""))
            if body:
                lines.append(body)
                lines.append("")
        elif kind == "thinking":
            body = _cap(str(block.get("thinking") or block.get("text") or ""))
            if body:
                lines.append("*（thinking）*")
                lines.append("")
                lines.append("\n".join(f"> {line}" for line in body.splitlines()) or "> ")
                lines.append("")
        elif kind == "tool_use":
            name = str(block.get("name") or "tool")
            args = block.get("input")
            body = json.dumps(args, ensure_ascii=False, indent=2, default=str) if args else ""
            lines.append(f"**tool_call · {name}**")
            lines.append("")
            if body:
                lines.append(_fence(_cap(body), "json"))
                lines.append("")
        elif kind == "tool_result":
            name = str(block.get("name") or "")
            body = _cap(_block_text(block.get("content")))
            flag = "（error）" if block.get("is_error") else ""
            lines.append(f"**tool_result{flag}{' · ' + name if name else ''}**")
            lines.append("")
            if body:
                lines.append(_fence(body, "text"))
                lines.append("")
        else:
            lines.append(f"*（{kind or 'unknown'} block）*")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def iter_conversation_records(text: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(record key, record)`` for the conversation records in *text*.

    Only ``user`` / ``assistant`` records — the transcript's bookkeeping records
    (``mode`` / ``cost-state`` / ``attachment`` / ``file-history-snapshot``) are not
    conversation. The key is the record's ``uuid`` — the same identity L0
    deduplicates on.
    """
    for index, record in enumerate(_iter_records(text), start=1):
        if not isinstance(record, dict):
            continue
        if str(record.get("type") or "") not in ("user", "assistant"):
            continue
        key = str(record.get("uuid") or f"line{index}")
        yield key, record


def iter_sections(text: str) -> Iterator[tuple[str, str]]:
    """Yield ``(record key, markdown section)`` for every conversation record in *text*.

    Every block is kept: text, thinking, ``tool_use`` and ``tool_result``.
    """
    for index, (key, record) in enumerate(iter_conversation_records(text), start=1):
        yield key, _render_record(key, record, index)


def _header(*, session_id: str, host: str, user: str | None) -> str:
    rows = [f"# {host} session {session_id}", "", f"- host: {host}", f"- session: {session_id}"]
    if user:
        rows.append(f"- user: {user}")
    rows += [
        f"- created: {_now()}",
        "- source: `memory_capture` 上传的原始 transcript（含工具调用与结果、thinking）",
        "",
        "---",
        "",
    ]
    return "\n".join(rows)


def archive_path(session_dir: Path, session_id: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", session_id).strip("_") or "session"
    return session_dir / f"{safe}.md"


def append_session(
    session_dir: Path,
    *,
    session_id: str,
    text: str,
    host: str,
    user: str | None = None,
) -> Path | None:
    """Append the records of one uploaded chunk to the session's markdown archive.

    Returns the file path when something was written, ``None`` when the chunk carried
    no new record (a re-send) — so callers can skip without special-casing.
    """
    path = archive_path(session_dir, session_id)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
    seen = set(_KEY_PATTERN.findall(existing))
    index = len(seen)

    sections: list[str] = []
    for key, record in iter_conversation_records(text):
        if key in seen:
            continue
        seen.add(key)
        index += 1
        sections.append(_render_record(key, record, index))
    if not sections:
        return None

    session_dir.mkdir(parents=True, exist_ok=True)
    body = "\n".join(section.rstrip() + "\n" for section in sections)
    if existing:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + body)
    else:
        path.write_text(
            _header(session_id=session_id, host=host, user=user) + body, encoding="utf-8"
        )
    return path
