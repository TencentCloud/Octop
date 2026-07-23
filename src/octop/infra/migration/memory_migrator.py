"""Migrate conversation history (sessions + threads) from LightClaw export into Octop.

LightClaw stores sessions as JSONL files under WORKING_DIR/sessions/ and a
session_index.json index. The JSONL format is self-contained (messages serialised
as LangChain dicts inside event objects).

Octop represents conversations as:
  - A ``threads`` row (thread_id, agent_id, user_id, channel_type, session_key, …).
  - A ``sessions`` row mapping session_key → thread_id.
  - The checkpoint data in harness-agent's ``checkpoints.sqlite`` (per workspace_dir).

Strategy:
  1. Parse ``sessions/session_index.json`` to discover sessions.
  2. For each session, copy the JSONL file into
     ``{workspace_dir}/sessions/{filename}`` (the canonical path harness-agent
     reads at startup).
  3. Register a (session_key, thread_id) pair in the Octop DB so the chat
     history is discoverable in the dashboard.
  4. Write a LangGraph checkpoint via ``SqliteSaver.put()`` so ``aget_history``
     returns proper ``BaseMessage`` objects and the LLM can continue the
     conversation with full awareness of previous context.

This gives the user visible conversation history in the Octop dashboard
immediately after import, and allows the agent to continue where it left off.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from octop.infra.utils.ulid import new_ulid

from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.migration.archive_reader import ArchiveReader
from octop.infra.migration.report import MigrationReport

logger = logging.getLogger(__name__)

# Maximum JSONL session file size we'll process (10 MB).
_MAX_JSONL_BYTES = 10 * 1024 * 1024

# LightClaw → Octop channel_type name normalization
_CHANNEL_TYPE_MAP: dict[str, str] = {
    "dashboard": "dashboard",
    "feishu": "feishu",
    "dingtalk": "dingtalk",
    "wecom": "wecom",
    "qqbot": "qq",
    "qq": "qq",
    "weixin": "weixin",
    "yuanbao": "yuanbao",
    "discord": "discord",
    "unknown": "dashboard",
}


def _build_langchain_messages(messages: list[dict[str, Any]]) -> list[Any]:
    """Convert raw LangChain-style dicts to actual LangChain BaseMessage objects.

    ``aget_history`` filters checkpoint messages with ``isinstance(m, BaseMessage)``,
    so writing plain dicts into the checkpoint makes the history invisible to the
    LLM when a new message arrives.  This function reconstructs proper
    ``HumanMessage`` / ``AIMessage`` instances so they survive the isinstance check
    and are fed to the model as real conversation context.
    """
    try:
        from langchain_core.messages import AIMessage, HumanMessage
    except ImportError:
        logger.warning("langchain_core not available; checkpoint messages will be dicts only")
        return messages

    out: list[Any] = []
    for msg in messages:
        msg_type = str(msg.get("type") or "")
        data = msg.get("data") or {}
        content = data.get("content") or "" if isinstance(data, dict) else ""
        if not content:
            continue
        if msg_type == "human":
            out.append(HumanMessage(content=content))
        elif msg_type == "ai":
            out.append(AIMessage(content=content))
    return out


def _map_channel_type(lc_channel: str) -> str:
    return _CHANNEL_TYPE_MAP.get((lc_channel or "").lower(), "dashboard")


def _extract_title_from_jsonl(lines: list[dict[str, Any]]) -> str | None:
    """Extract the first user message text as thread title."""
    for event in lines:
        if not isinstance(event, dict) or event.get("type") != "message":
            continue
        msg = event.get("message")
        if not isinstance(msg, dict):
            continue
        if msg.get("role") not in {"user", "human"}:
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = str(block.get("text") or "").strip()
                    if text:
                        return text[:40]
        elif isinstance(content, str):
            text = content.strip()
            if text:
                return text[:40]
    return None


def _parse_session_index(reader: ArchiveReader) -> list[dict[str, Any]]:
    """Parse sessions/session_index.json entries."""
    raw = reader.read_json("sessions/session_index.json")
    if not isinstance(raw, dict):
        return []
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return []
    out = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = entry.get("filename")
        session_id = entry.get("session_id")
        if not (
            isinstance(filename, str) and filename and isinstance(session_id, str) and session_id
        ):
            continue
        out.append(entry)
    return out


def _put_checkpoint_to_db(db_path: Path, *, thread_id: str, lc_messages: list[Any]) -> None:
    """Write a single checkpoint row to *db_path* via ``SqliteSaver.put()``.

    Using the official LangGraph API guarantees:
    - Correct schema (``SqliteSaver.setup()`` runs internally).
    - Serialization via ``JsonPlusSerializer``, producing the exact msgpack
      format ``aget_history`` expects.
    - ``BaseMessage`` objects survive the ``isinstance(m, BaseMessage)`` filter
      so the LLM receives full conversation context on continuation.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver  # ImportError propagates to caller

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        checkpoint_id = str(uuid.uuid4())
        config: dict[str, Any] = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }
        checkpoint: dict[str, Any] = {
            "v": 1,
            "id": checkpoint_id,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "channel_values": {"messages": lc_messages},
            "channel_versions": {"messages": 1},
            "versions_seen": {},
            "pending_sends": [],
        }
        metadata: dict[str, Any] = {
            "source": "migration",
            "step": -1,
            "writes": {},
            "parents": {},
        }
        saver.put(config, checkpoint, metadata, {})


def _write_checkpoint_for_thread(
    workspace_dir: Path,
    *,
    thread_id: str,
    messages: list[dict[str, Any]],
) -> bool:
    """Write a checkpoint for *thread_id* into the agent's workspace.

    harness-agent resolves its checkpointer in priority order:
      1. ``memory_enabled=True``  → ``Memory`` backed by ``memory.sqlite``
      2. fallback               → ``AsyncSqliteSaver`` on ``checkpoints.sqlite``

    Since the import runs *before* the agent starts, we don't know which path
    will be taken at runtime.  Writing to both files ensures the checkpoint is
    found regardless of which checkpointer ends up active:

    - ``memory.sqlite`` is used when the Memory integration is enabled (default).
    - ``checkpoints.sqlite`` is the fallback for agents without Memory.

    Both writes use ``SqliteSaver.put()`` so the schema and serialization
    format are identical to what harness-agent produces.
    """
    if not messages:
        return False

    lc_messages = _build_langchain_messages(messages)
    if not lc_messages:
        return False

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver as _  # noqa: F401
    except ImportError:
        logger.warning("langgraph-checkpoint-sqlite unavailable; skipping checkpoint write")
        return False

    wrote_any = False
    for db_name in ("memory.sqlite", "checkpoints.sqlite"):
        db_path = workspace_dir / db_name
        try:
            _put_checkpoint_to_db(db_path, thread_id=thread_id, lc_messages=lc_messages)
            wrote_any = True
        except Exception:
            logger.exception(
                "Failed to write checkpoint for thread %s into %s", thread_id, db_name
            )

    return wrote_any


def _write_octop_session_jsonl(
    dst_path: Path,
    *,
    thread_id: str,
    messages: list[dict[str, Any]],
    base_ts: float,
) -> None:
    """Write messages as an Octop-format JSONL file.

    Each line is a JSON object with ``role``, ``content``, ``thread_id``, and
    ``ts`` fields that ``_entry_matches_thread`` in serialize.py can match by
    ``thread_id`` directly — no timestamp-range guessing required.

    Args:
        dst_path: Destination ``.jsonl`` file path.
        thread_id: The Octop thread ID to embed in every line.
        messages: LangChain-style message dicts (type + data keys).
        base_ts: A base epoch-second float; messages get synthetic 1-second
                 intervals so the timeline is preserved.
    """
    lines: list[str] = []
    for i, msg in enumerate(messages):
        msg_type = str(msg.get("type") or "")
        data = msg.get("data") or {}
        if isinstance(data, dict):
            content = str(data.get("content") or "")
        else:
            content = ""
        if not content:
            continue
        if msg_type == "human":
            role = "user"
        elif msg_type in {"ai", "tool", "system"}:
            role = "assistant"
        else:
            continue
        ts_iso = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(base_ts + i),
        )
        entry: dict[str, Any] = {
            "role": role,
            "content": content,
            "thread_id": thread_id,
            "ts": ts_iso,
        }
        lines.append(json.dumps(entry, ensure_ascii=False))
    if lines:
        dst_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _extract_messages_from_jsonl(raw_bytes: bytes) -> list[dict[str, Any]]:
    """Parse a JSONL session file and return LangChain message dicts."""
    message_dicts: list[dict[str, Any]] = []
    for raw_line in raw_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "message":
            continue
        msg_payload = event.get("message")
        if not isinstance(msg_payload, dict):
            continue
        # Prefer the stored LangChain dict (_lc key) if available
        lc = msg_payload.get("_lc")
        if isinstance(lc, dict) and lc.get("type") in {"human", "ai", "tool", "system"}:
            message_dicts.append(lc)
            continue
        # Reconstruct a minimal LangChain dict from the simplified payload
        role = str(msg_payload.get("role") or "")
        content_raw = msg_payload.get("content")
        if isinstance(content_raw, list):
            parts = []
            for block in content_raw:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif isinstance(block, str):
                    parts.append(block)
            content = "\n".join(p for p in parts if p)
        else:
            content = str(content_raw or "").strip()
        if not content:
            continue
        if role in {"user", "human"}:
            message_dicts.append(
                {
                    "type": "human",
                    "data": {"content": content, "additional_kwargs": {}, "type": "human"},
                }
            )
        elif role in {"assistant", "ai"}:
            message_dicts.append(
                {
                    "type": "ai",
                    "data": {
                        "content": content,
                        "additional_kwargs": {},
                        "type": "ai",
                        "tool_calls": [],
                    },
                }
            )
    return message_dicts


async def migrate_sessions(
    reader: ArchiveReader,
    *,
    agent_id: str,
    user_id: int,
    workspace_dir: Path,
    thread_repo: ThreadRepo,
    session_repo: SessionRepo,
    report: MigrationReport,
) -> None:
    """Import conversation sessions from the archive into Octop.

    Steps:
      1. Parse session_index.json.
      2. Copy each JSONL to {workspace_dir}/sessions/.
      3. Extract messages → write to checkpoints.sqlite via SqliteSaver.put().
      4. Insert thread + session rows.
    """
    index_entries = _parse_session_index(reader)
    if not index_entries:
        # Try to infer sessions from raw JSONL files without an index
        for name, _ in reader.iter_prefix("sessions/"):
            if name == "sessions/session_index.json":
                continue
            if name.endswith(".jsonl"):
                basename = name[len("sessions/") :]
                index_entries.append(
                    {
                        "filename": basename,
                        "session_id": basename.replace(".jsonl", ""),
                        "channel": "dashboard",
                        "user_id": str(user_id),
                    }
                )

    sessions_dst = workspace_dir / "sessions"
    sessions_dst.mkdir(parents=True, exist_ok=True)

    imported = 0
    skipped = 0

    for entry in index_entries:
        filename = str(entry.get("filename") or "")
        session_id = str(entry.get("session_id") or "")
        lc_channel = str(entry.get("channel") or "dashboard")
        channel_type = _map_channel_type(lc_channel)

        if not (filename and session_id):
            skipped += 1
            continue

        raw = reader.read_bytes(f"sessions/{filename}")
        if not raw:
            report.warn(f"Session file {filename!r} not found in archive")
            skipped += 1
            continue

        if len(raw) > _MAX_JSONL_BYTES:
            report.warn(f"Skipping large session file {filename!r} ({len(raw) // 1024} KB)")
            skipped += 1
            continue

        try:
            # 1. Copy JSONL to workspace sessions dir
            dst_path = sessions_dst / filename
            dst_path.write_bytes(raw)

            # 2. Extract messages and write checkpoint
            messages = _extract_messages_from_jsonl(raw)
            if not messages:
                # Keep the JSONL but skip checkpoint / DB entry for empty sessions
                skipped += 1
                continue

            # 3. Derive thread_id and session_key
            thread_id = f"thr_{new_ulid()}"
            session_key = ThreadRegistry.make_key(
                agent_id=agent_id,
                channel_type=channel_type,
                channel_subject_id=str(user_id),
                channel_chat_type="dm",
            )
            # Avoid collisions: append session_id suffix when multiple sessions
            # share the same (agent, channel, user) tuple.
            existing = session_repo.get(session_key)
            if existing is not None:
                session_key = f"{session_key}:{session_id}"

            ts_now = int(time.time() * 1000)

            # 4. Write checkpoint via official SqliteSaver.put() API.
            #    Written to both memory.sqlite and checkpoints.sqlite so the
            #    history is available regardless of whether the agent uses the
            #    Memory integration (memory.sqlite) or the plain fallback
            #    (checkpoints.sqlite) as its LangGraph checkpointer.
            _write_checkpoint_for_thread(workspace_dir, thread_id=thread_id, messages=messages)

            # 4b. Write an Octop-format JSONL alongside the original so the
            #     fallback history reader (_load_thread_messages_from_sessions)
            #     can match messages by thread_id without time-range guessing.
            octop_jsonl_path = sessions_dst / f"octop_{thread_id}.jsonl"
            _write_octop_session_jsonl(
                octop_jsonl_path,
                thread_id=thread_id,
                messages=messages,
                base_ts=ts_now / 1000.0 - len(messages),
            )

            # 5. Extract title
            try:
                jsonl_events = [
                    json.loads(line)
                    for line in raw.decode("utf-8", errors="replace").splitlines()
                    if line.strip()
                ]
            except Exception:
                jsonl_events = []
            title = _extract_title_from_jsonl(jsonl_events)

            # 6. Insert thread row
            thread_repo.insert(
                thread_id=thread_id,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                session_key=session_key,
                title=title,
                last_active=ts_now,
            )

            # 7. Upsert session row
            session_repo.upsert(
                session_key=session_key,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                chat_type="dm",
                thread_id=thread_id,
                channel_subject_id=str(user_id),
                channel_chat_type="dm",
                channel_metadata={"channel_type": channel_type, "user_id": user_id},
                channel_id=None,
            )

            imported += 1
        except Exception:
            logger.exception("Failed to migrate session %s", session_id)
            report.warn(f"Failed to migrate session {session_id!r}")
            skipped += 1

    report.sessions_imported = imported
    report.sessions_skipped = skipped
    logger.info("Sessions migrated: %d imported, %d skipped", imported, skipped)
