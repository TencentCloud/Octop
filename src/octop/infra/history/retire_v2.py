"""One-time, read-only export of the retired versioned history archive."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args

from octop.infra.agents.memory.backend import open_memory_kwargs
from octop.infra.agents.memory.thread_cleanup import workspace_for_agent_row
from octop.infra.agents.workspace.dir import host_system_dir
from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.thread_messages import ThreadMessageInput, ThreadMessageRow
from octop.infra.history.projection import _role, message_input
from octop.infra.history.trajectory.types import TrajectoryKind

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.pool import DatabasePool
    from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

ARCHIVE_NAME = "history_v2.sqlite"
MARKER_NAME = "history_v2.required"


def has_history_v2(paths: PathLayout) -> bool:
    return (paths.root / ARCHIVE_NAME).exists() or (paths.root / MARKER_NAME).exists()


def migrate_history_v2(paths: PathLayout, db: DatabasePool, registry: AgentManager) -> None:
    """Migrate before any agent can write new history or prune checkpoint ancestors."""
    if not has_history_v2(paths):
        return
    archive_path = paths.root / ARCHIVE_NAME
    marker = paths.root / MARKER_NAME
    if not archive_path.is_file():
        raise ValueError(
            f"Cannot migrate history v2: {MARKER_NAME} exists but {ARCHIVE_NAME} is missing"
        )
    if db.dialect != "sqlite":
        raise ValueError("Cannot migrate history v2 without its SQLite control-plane database")

    with closing(
        sqlite3.connect(archive_path.resolve().as_uri() + "?mode=ro", uri=True)
    ) as archive:
        archive.row_factory = sqlite3.Row
        archive.execute("PRAGMA query_only = ON")
        archive.execute("BEGIN")
        metadata = archive.execute("SELECT version FROM archive_meta").fetchone()
        if metadata is None or metadata["version"] != 1:
            raise ValueError("Cannot migrate history v2: unsupported archive format")
        threads = archive.execute(
            "SELECT DISTINCT thread_id FROM segments ORDER BY thread_id"
        ).fetchall()
        for (thread_id,) in threads:
            try:
                with db.transaction() as conn:
                    _migrate_thread(archive, conn, registry, paths, thread_id)
            except Exception as exc:
                raise ValueError(
                    f"Cannot migrate history v2 for thread {thread_id}: {exc}"
                ) from exc

    _archive_migrated_files(archive_path, marker)
    logger.info("Migrated history v2 for %s threads", len(threads))


def _migrate_thread(
    archive: sqlite3.Connection,
    conn: sqlite3.Connection,
    registry: AgentManager,
    paths: PathLayout,
    thread_id: str,
) -> None:
    segments = archive.execute(
        "SELECT * FROM segments WHERE thread_id=? ORDER BY id", (thread_id,)
    ).fetchall()
    documents = archive.execute(
        "SELECT d.id,d.seq,d.kind,d.data,t.segment_id FROM documents d LEFT JOIN turns t ON t.id=d.turn_id "
        "WHERE d.thread_id=? ORDER BY d.seq,d.id",
        (thread_id,),
    ).fetchall()
    agent_ids = {row["agent_id"] for row in segments}
    owner = conn.execute("SELECT agent_id FROM threads WHERE thread_id=?", (thread_id,)).fetchone()
    if owner is None or agent_ids != {owner["agent_id"]}:
        raise ValueError("archive does not match a thread in the control-plane database")
    agent_id = owner["agent_id"]
    # A thread may commit before another thread fails or the process stops.
    # Record its immutable source alongside the v1 changes, in the same transaction.
    source = hashlib.sha256(
        json.dumps([list(map(tuple, segments)), list(map(tuple, documents))]).encode()
    ).hexdigest()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS history_v2_retirement ("
        "thread_id TEXT PRIMARY KEY REFERENCES threads(thread_id) ON DELETE CASCADE, source TEXT NOT NULL)"
    )
    previous = conn.execute(
        "SELECT source FROM history_v2_retirement WHERE thread_id=?", (thread_id,)
    ).fetchone()
    if previous is not None:
        if previous["source"] != source:
            raise ValueError("a different archive was already migrated for this thread")
        return

    existing = [
        ThreadMessageRow.from_row(row)
        for row in conn.execute(
            "SELECT seq,message_id,role,message_json,created_at FROM thread_messages "
            "WHERE thread_id=? ORDER BY seq",
            (thread_id,),
        )
    ]
    messages = _export_messages(
        archive, registry, paths, thread_id, agent_id, segments, documents, existing
    )
    _write_projection(conn, thread_id, messages, existing)
    for document in documents:
        if document["kind"] == "event":
            _import_event(archive, conn, thread_id, agent_id, document)
    conn.execute(
        "INSERT INTO thread_history_projection(thread_id,status,updated_at,error) VALUES (?,'ready',?,NULL) "
        "ON CONFLICT(thread_id) DO UPDATE SET status='ready',updated_at=excluded.updated_at,error=NULL",
        (thread_id, now_ts()),
    )
    conn.execute("INSERT INTO history_v2_retirement VALUES (?,?)", (thread_id, source))


def _export_messages(
    archive: sqlite3.Connection,
    registry: AgentManager,
    paths: PathLayout,
    thread_id: str,
    agent_id: str,
    segments: Sequence[sqlite3.Row],
    documents: Sequence[sqlite3.Row],
    existing: list[ThreadMessageRow],
) -> list[ThreadMessageRow | ThreadMessageInput]:
    """Read in the same segment and sequence order as the old export_messages."""
    by_segment: dict[int, list[sqlite3.Row]] = defaultdict(list)
    versioned_segments = {row["id"] for row in segments if row["format"] == "v2"}
    for document in documents:
        if document["kind"] == "message":
            if document["segment_id"] not in versioned_segments:
                raise ValueError(f"archive message {document['id']} has no valid segment")
            by_segment[document["segment_id"]].append(document)

    result: list[ThreadMessageRow | ThreadMessageInput] = []
    for segment in segments:
        if segment["format"] == "v2":
            result.extend(_wire_input(_document(archive, row)) for row in by_segment[segment["id"]])
        elif segment["anchor"]:
            anchor = json.loads(segment["anchor"])
            for message in _read_checkpoint(registry, paths, agent_id, thread_id, anchor):
                if _role(message) == "system":
                    continue
                item = message_input(message)
                if item is None:
                    raise ValueError("an anchored checkpoint message could not be decoded")
                result.append(item)
        else:
            start, end = segment["legacy_start"], segment["legacy_end"]
            result.extend(
                row for row in existing if row.seq > start and (end is None or row.seq <= end)
            )
    return result


def _wire_input(wire: dict[str, Any]) -> ThreadMessageInput:
    from langchain_core.messages import messages_from_dict  # noqa: PLC0415

    item = message_input(messages_from_dict([wire])[0])
    if item is None:
        raise ValueError("an archived message cannot be represented in thread_messages")
    return replace(item, message_json=json.dumps(wire, ensure_ascii=False))


def _write_projection(
    conn: sqlite3.Connection,
    thread_id: str,
    messages: list[ThreadMessageRow | ThreadMessageInput],
    existing: list[ThreadMessageRow],
) -> None:
    # Match exact projected messages, including id-less occurrences. Never
    # overwrite an existing body when a segment already has a projection.
    projected_seqs = [item.seq for item in messages if isinstance(item, ThreadMessageRow)]
    used = set(projected_seqs)
    if len(used) != len(projected_seqs):
        raise ValueError("archived legacy projection intervals overlap")
    available: dict[str, deque[ThreadMessageRow]] = defaultdict(deque)
    unmatched_ids = {
        row.message_id: row.seq for row in existing if row.message_id and row.seq not in used
    }

    def wire_key(item: ThreadMessageInput | ThreadMessageRow) -> str:
        return json.dumps(json.loads(item.message_json), sort_keys=True)

    for row in existing:
        if row.seq not in used:
            available[wire_key(row)].append(row)
    ordered: list[ThreadMessageInput | ThreadMessageRow] = []
    for item in messages:
        if isinstance(item, ThreadMessageInput):
            matches = available.get(wire_key(item))
            existing_seq = unmatched_ids.get(item.message_id or "")
            if matches:
                item = matches.popleft()
                used.add(item.seq)
            elif existing_seq is not None and existing_seq not in used:
                raise ValueError(
                    f"existing projected message {item.message_id!r} differs from the archive"
                )
        ordered.append(item)
    ordered.extend(row for row in existing if row.seq not in used)
    # Temporarily move existing sequence numbers if an archived segment fits
    # between two legacy intervals. Row IDs, timestamps and bodies stay intact.
    offset = 0
    if any(
        isinstance(row, ThreadMessageRow) and row.seq != seq for seq, row in enumerate(ordered, 1)
    ):
        offset = max(len(ordered), existing[-1].seq) + 1
        conn.execute("UPDATE thread_messages SET seq=seq+? WHERE thread_id=?", (offset, thread_id))
    indexed_ids = {row.message_id for row in existing if row.message_id}
    for seq, entry in enumerate(ordered, 1):
        if isinstance(entry, ThreadMessageRow):
            if offset:
                conn.execute(
                    "UPDATE thread_messages SET seq=? WHERE thread_id=? AND seq=?",
                    (seq, thread_id, entry.seq + offset),
                )
            continue
        # The archive can repeat an ID in different turns. Keep every wire but
        # index the ID once for v1's unique constraint and live deduplication.
        message_id = entry.message_id if entry.message_id not in indexed_ids else None
        conn.execute(
            "INSERT INTO thread_messages(thread_id,seq,message_id,role,message_json,created_at) VALUES (?,?,?,?,?,?)",
            (thread_id, seq, message_id, entry.role, entry.message_json, entry.created_at),
        )
        if message_id:
            indexed_ids.add(message_id)


def _document(archive: sqlite3.Connection, document: sqlite3.Row) -> dict[str, Any]:
    def decode(node: Any) -> Any:
        tag, value = node
        if tag == "body":
            row = archive.execute("SELECT value FROM bodies WHERE digest=?", (value,)).fetchone()
            if row is None:
                raise ValueError("archive body reference is missing")
            return json.loads(row[0])
        if tag == "text":
            return "".join(decode(["body", digest]) for digest in value)
        if tag == "dict":
            return {key: decode(item) for key, item in value}
        if tag == "list":
            return [decode(item) for item in value]
        if tag == "value":
            return value
        raise ValueError(f"unknown archive encoding {tag!r}")

    result = decode(json.loads(document["data"]))
    if not isinstance(result, dict):
        raise ValueError("archive document is not an object")
    return result


_EVENT_FIELDS = (
    "event_id",
    "agent_id",
    "thread_id",
    "seq",
    "ts",
    "kind",
    "turn_id",
    "request_seq",
    "is_error",
    "summary",
    "payload",
)


def _import_event(
    archive: sqlite3.Connection,
    conn: sqlite3.Connection,
    thread_id: str,
    agent_id: str,
    document: sqlite3.Row,
) -> None:
    try:
        event = _document(archive, document)
        if (
            event["thread_id"] != thread_id
            or event["agent_id"] != agent_id
            or event["seq"] != document["seq"]
            or event["kind"] not in get_args(TrajectoryKind)
            or not isinstance(event["payload"], dict)
            or not isinstance(event["event_id"], str)
        ):
            raise ValueError("event identity, kind or payload cannot be represented")
        if extra := event.keys() - set(_EVENT_FIELDS):
            logger.warning(
                "History v2 trajectory thread=%s document=%s has unsupported fields: %s",
                thread_id,
                document["id"],
                ", ".join(sorted(extra)),
            )
        values = (
            event["event_id"],
            agent_id,
            thread_id,
            event["seq"],
            event["ts"],
            event["kind"],
            event.get("turn_id"),
            event.get("request_seq"),
            int(event.get("is_error", False)),
            event.get("summary", ""),
            json.dumps(event["payload"], ensure_ascii=False),
        )
        cursor = conn.execute(
            "INSERT INTO trajectory_events(event_id,agent_id,thread_id,seq,ts,kind,turn_id,request_seq,"
            "is_error,summary,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            values,
        )
        if not cursor.rowcount:
            existing = conn.execute(
                "SELECT event_id,agent_id,thread_id,seq,ts,kind,turn_id,request_seq,is_error,summary,payload_json "
                "FROM trajectory_events WHERE event_id=?",
                (event["event_id"],),
            ).fetchone()
            if (
                existing is None
                or tuple(existing)[:-1] != values[:-1]
                or json.loads(existing["payload_json"]) != event["payload"]
            ):
                raise ValueError("event ID or sequence conflicts with a different v1 event")
    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        sqlite3.IntegrityError,
        sqlite3.InterfaceError,
    ) as exc:
        logger.warning(
            "Could not migrate history v2 trajectory thread=%s document=%s: %s",
            thread_id,
            document["id"],
            exc,
        )


def _read_checkpoint(
    registry: AgentManager,
    paths: PathLayout,
    agent_id: str,
    thread_id: str,
    anchor: Mapping[str, Any],
) -> list[Any]:
    from octop_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver  # noqa: PLC0415

    config = anchor["checkpoint_config"]
    ref = config["configurable"]
    checkpoint_id = ref["checkpoint_id"]
    if (
        ref["thread_id"] != thread_id
        or ref.get("checkpoint_ns") not in (None, "")
        or not checkpoint_id
    ):
        raise ValueError("invalid checkpoint anchor")
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": "",
            "checkpoint_id": checkpoint_id,
        }
    }
    row = registry.get_row(agent_id)
    if row is None:
        raise ValueError(f"missing agent {agent_id} for checkpoint {checkpoint_id}")
    cfg = registry.get_config(agent_id)
    workspace = workspace_for_agent_row(row, paths=paths)
    _, backend, options = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=registry.octop_config,
        workspace_dir=workspace,
    )
    assert options is not None
    memory = cfg.get("memory")
    memory_enabled = not isinstance(memory, dict) or memory.get("memory_enabled") is not False
    if backend == "postgres" and memory_enabled:
        from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415
        from psycopg import connect  # noqa: PLC0415
        from psycopg.rows import dict_row  # noqa: PLC0415

        with connect(
            options["dsn"], autocommit=True, row_factory=dict_row, prepare_threshold=0
        ) as conn:
            conn.execute("SET default_transaction_read_only=on")
            conn.execute("SET search_path TO octop_memory, public")
            messages = _checkpoint_messages(PostgresSaver(conn), config)
            if messages is not None:
                return messages
    candidates = [host_system_dir(workspace, cfg) / "checkpoints.sqlite"]
    if backend == "sqlite" and memory_enabled:
        candidates.insert(0, Path(options["db_path"]).expanduser())
    for path in candidates:
        if not path.is_file():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            if not conn.execute("SELECT 1 FROM sqlite_schema WHERE name='checkpoints'").fetchone():
                continue
            saver = CompactSqliteSaver(conn)
            saver.is_setup = True  # Read existing rows without running saver setup.
            messages = _checkpoint_messages(saver, config)
            if messages is not None:
                return messages
    raise ValueError(f"checkpoint anchor {checkpoint_id} is unavailable")


def _checkpoint_messages(saver: Any, config: dict[str, Any]) -> list[Any] | None:
    from deepagents._messages_reducer import _messages_delta_reducer  # noqa: PLC0415
    from langgraph.channels.delta import DeltaChannel  # noqa: PLC0415
    from langgraph.pregel._checkpoint import channels_from_checkpoint  # noqa: PLC0415

    record = saver.get_tuple(config)
    if record is None:
        return None
    parent = record
    seen = {record.checkpoint["id"]}
    # A missing delta parent must not turn a truncated transcript into a
    # successful migration. A stored full seed ends the dependency walk.
    while "messages" not in parent.checkpoint["channel_values"] and parent.parent_config:
        parent = saver.get_tuple(parent.parent_config)
        if parent is None or parent.checkpoint["id"] in seen:
            raise ValueError("checkpoint anchor has a missing or cyclic message ancestor")
        seen.add(parent.checkpoint["id"])
    channels, _ = channels_from_checkpoint(
        {
            "messages": DeltaChannel(
                lambda state, writes: _messages_delta_reducer(state, list(writes)), list
            )
        },
        record.checkpoint,
        saver=saver,
        config=record.config,
    )
    messages = channels["messages"].get()
    if not isinstance(messages, list):
        raise ValueError("checkpoint anchor has invalid messages")
    return messages


def _archive_migrated_files(path: Path, marker: Path) -> None:
    # Fold committed WAL frames into the retained original before renaming
    # the SQLite file. Do this only after every thread transaction succeeded.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)) as conn:
        if conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
            raise ValueError("Cannot archive migrated history v2: SQLite WAL is busy")
    suffix = datetime.now(UTC).strftime(".migrated-%Y%m%dT%H%M%S%fZ")
    moved_marker = marker.with_name(marker.name + suffix)
    marker_exists = marker.exists()
    if marker_exists:
        marker.rename(moved_marker)
    try:
        path.rename(path.with_name(path.name + suffix))
    except OSError:
        if marker_exists:
            moved_marker.rename(marker)
        raise
