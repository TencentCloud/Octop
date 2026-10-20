"""Checkpoint retention pruning — shrink the LangGraph checkpointer tables.

LangGraph's ``SqliteSaver`` has no built-in retention: every graph step
(every AI turn / tool call) inserts a full-state ``checkpoints`` row (plus
``writes`` rows) and nothing ever deletes it, short of
:meth:`Memory.delete_thread` which is all-or-nothing (wipe the *entire*
thread history). For long-lived threads that are never deleted outright,
the ``checkpoints``/``writes`` tables grow without bound — this is the
#1 driver of unbounded ``.sqlite`` file growth (see repo-wide sqlite
bloat investigation).

This module adds the missing middle ground: per ``(thread_id,
checkpoint_ns)`` stream, keep only

* the newest ``keep_last`` checkpoints (default **1** — chat history
  and the next turn read the latest parent snapshot, not a stitch of
  older copies), and/or
* checkpoints newer than ``keep_days`` days,

and delete everything else (plus their ``writes`` rows). The two knobs
are OR'd together — a checkpoint survives if it satisfies *either*
condition — and the single newest **parent** checkpoint
(``checkpoint_ns=""``) is always kept, so ``get_thread_state()`` /
``get_tuple()`` never breaks.

SqliteSaver is a **delta** store: the newest parent row often omits
``messages`` from ``channel_values`` even when ``channel_versions``
shows they exist. The transcript is reconstructed by walking the parent
chain plus ``writes``. Deleting ancestors before inlining that list
leaves a self-inconsistent survivor (dangling ``parent_checkpoint_id``,
empty ``messages``) — chat history then falls back to JSONL text.

So this module **seals** the latest parent first: replay ``messages``
into ``channel_values`` as a new root snapshot, *then* delete older
rows. If replay yields nothing while the channel is still versioned,
ancestor deletion is skipped for that thread.

Finished ``tools:*`` (and any other non-empty ``checkpoint_ns``)
subgraph streams can be dropped entirely **after** the parent is
sealed. In-flight and HITL-paused threads are skipped unless
``force_drop_subgraphs`` is set.

SQLite-only (same restriction as :mod:`octop_memory.pipeline.lifecycle.gc`,
D46-C): checkpoint_id is a UUIDv6 string (see
``langgraph.checkpoint.base.id.uuid6``) whose lexicographic string order
matches chronological order (LangGraph's own ``list()`` relies on this
via ``ORDER BY checkpoint_id DESC``). That means both "keep last N" and
"keep last X days" can be expressed as plain SQL — no need to
deserialize any checkpoint blob to find a timestamp.

Unlike :mod:`octop_memory.pipeline.lifecycle.gc`, deletions here are
NOT journaled: checkpoint/write rows are LangGraph execution-state
plumbing, not user-facing memory facts, and :meth:`Memory.delete_thread`
(the existing all-or-nothing path) doesn't journal either — this keeps
behaviour consistent.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

_LOG = logging.getLogger(__name__)

if TYPE_CHECKING:
    from octop_memory.core import Memory

DEFAULT_KEEP_LAST_CHECKPOINTS = 1
"""Default per-stream checkpoint count to retain when the CLI doesn't override it.

Keep the newest **sealed** parent snapshot (``messages`` inlined). Older
parent rows are delta-chain links, not extra chat turns.
"""


@dataclass
class CheckpointGcStats:
    """Row counts for one :func:`prune_checkpoints` call. ``dry_run`` reports what *would* be deleted."""

    threads_scanned: int = 0
    streams_scanned: int = 0
    streams_dropped: int = 0
    checkpoints_deleted: int = 0
    writes_deleted: int = 0
    parents_sealed: int = 0
    parent_prunes_skipped: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class _ParentSealDecision:
    """Whether ancestors of the latest parent may be deleted."""

    can_prune_ancestors: bool
    sealed: bool


def prune_checkpoints(
    memory: Memory,
    *,
    keep_last: int | None = None,
    keep_days: int | None = None,
    thread_id: str | None = None,
    drop_subgraph_streams: bool = False,
    force_drop_subgraphs: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
) -> CheckpointGcStats:
    """Delete old checkpoints (and their writes) beyond the retention window.

    Args:
        memory: The :class:`Memory` instance whose checkpointer to prune.
            Must be backed by LangGraph's SQLite ``SqliteSaver`` (the
            only checkpointer octop-memory currently supports pruning
            for; PostgreSQL is deferred, same as lifecycle GC).
        keep_last: Always keep the newest N checkpoints per
            ``(thread_id, checkpoint_ns)`` stream, regardless of age.
        keep_days: Always keep checkpoints newer than this many days,
            regardless of rank.
        thread_id: Restrict pruning to a single thread. ``None`` (default)
            scans every thread in the checkpointer.
        drop_subgraph_streams: When True, delete every row in non-empty
            ``checkpoint_ns`` streams (``tools:*`` subagent / tool graphs)
            for threads whose parent turn looks finished. In-flight and
            HITL-paused threads keep their subgraphs (still trimmed by
            ``keep_last``).
        force_drop_subgraphs: Skip the finished-parent / subgraph-ahead
            guards. Tests and ops only.
        dry_run: Count what would be deleted without modifying anything.
        now: Override "current time" for ``keep_days`` cutoff computation
            (tests use this instead of ``datetime.now()``).

    At least one of ``keep_last`` / ``keep_days`` must be given. The two
    are OR'd: a checkpoint is deleted only if it fails BOTH the rank
    check and the age check. The single newest parent checkpoint is
    always kept even if it fails both checks.

    Before deleting parent ancestors, the latest parent is sealed when
    ``messages`` is versioned but omitted from ``channel_values`` (LangGraph
    delta). Seal failure skips ancestor deletion for that thread.
    """
    if keep_last is None and keep_days is None:
        raise ValueError("prune_checkpoints requires keep_last and/or keep_days")
    if keep_last is not None and keep_last < 1:
        raise ValueError("keep_last must be >= 1")
    if keep_days is not None and keep_days < 0:
        raise ValueError("keep_days must be >= 0")

    conn = _get_checkpointer_conn(memory)
    stats = CheckpointGcStats(started_at=datetime.now(UTC), dry_run=dry_run)
    _LOG.info(
        "prune_checkpoints start keep_last=%s keep_days=%s thread_id=%s drop_subgraph=%s force_drop=%s dry_run=%s",
        keep_last,
        keep_days,
        thread_id,
        drop_subgraph_streams,
        force_drop_subgraphs,
        dry_run,
    )

    cutoff_id = None
    if keep_days is not None:
        cutoff_id = _cutoff_checkpoint_id((now or datetime.now(UTC)) - timedelta(days=keep_days))

    pairs = _thread_ns_pairs(conn, thread_id=thread_id)
    stats.streams_scanned = len(pairs)
    stats.threads_scanned = len({tid for tid, _ns in pairs})
    drop_ok: dict[str, bool] = {}

    by_thread: dict[str, list[str]] = defaultdict(list)
    for tid, ns in pairs:
        by_thread[tid].append(ns)

    for tid, nss in by_thread.items():
        # Seal parent before touching subgraphs so the finished-turn guard
        # can see inlined messages, and so we never drop tools:* while the
        # only remaining transcript is still on a delta chain.
        nss.sort(key=lambda ns: (bool(ns), ns))
        skip_parent_victims = False
        if "" in nss:
            decision = _ensure_parent_sealed(memory, tid, dry_run=dry_run)
            if decision.sealed:
                stats.parents_sealed += 1
            if not decision.can_prune_ancestors:
                skip_parent_victims = True
                stats.parent_prunes_skipped += 1
                _LOG.warning(
                    "prune_checkpoints: skip parent ancestor delete thread=%s (delta messages could not be sealed)",
                    tid,
                )
        for ns in nss:
            if drop_subgraph_streams and ns:
                if tid not in drop_ok:
                    drop_ok[tid] = force_drop_subgraphs or _safe_to_drop_subgraphs(memory, conn, tid)
                if drop_ok[tid]:
                    deleted_cp, deleted_wr = _delete_stream(conn, tid, ns, dry_run=dry_run)
                    stats.checkpoints_deleted += deleted_cp
                    stats.writes_deleted += deleted_wr
                    if deleted_cp or deleted_wr:
                        stats.streams_dropped += 1
                    continue
            if ns == "" and skip_parent_victims:
                continue
            victims = _victim_checkpoint_ids(conn, tid, ns, keep_last=keep_last, cutoff_id=cutoff_id)
            if not victims:
                continue
            deleted_cp, deleted_wr = _delete_checkpoint_ids(conn, tid, ns, victims, dry_run=dry_run)
            stats.checkpoints_deleted += deleted_cp
            stats.writes_deleted += deleted_wr

    stats.finished_at = datetime.now(UTC)
    _LOG.info(
        "prune_checkpoints done streams=%s streams_dropped=%s checkpoints_deleted=%s "
        "writes_deleted=%s sealed=%s skipped=%s dry_run=%s",
        stats.streams_scanned,
        stats.streams_dropped,
        stats.checkpoints_deleted,
        stats.writes_deleted,
        stats.parents_sealed,
        stats.parent_prunes_skipped,
        dry_run,
    )
    return stats


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _messages_omitted(checkpoint: dict[str, Any]) -> bool:
    """True when ``messages`` is versioned on this row but not stored inline."""
    versions = checkpoint.get("channel_versions") or {}
    values = checkpoint.get("channel_values") or {}
    if not isinstance(versions, dict) or not isinstance(values, dict):
        return False
    return versions.get("messages") is not None and "messages" not in values


def _ensure_parent_sealed(memory: Memory, thread_id: str, *, dry_run: bool) -> _ParentSealDecision:
    """Inline ``messages`` on the latest parent before ancestors are deleted.

    Returns ``can_prune_ancestors=False`` when the latest parent is a delta
    omit and replay produced no messages — deleting the chain would drop the
    transcript. Deserialization failures on fixture/raw rows do not block prune.
    """
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        tup = memory.get_tuple(config)
    except REPORTABLE_ERRORS:
        _LOG.warning("prune_checkpoints: get_tuple failed thread=%s", thread_id, exc_info=True)
        return _ParentSealDecision(can_prune_ancestors=True, sealed=False)
    if tup is None:
        return _ParentSealDecision(can_prune_ancestors=True, sealed=False)
    checkpoint = getattr(tup, "checkpoint", None)
    if not isinstance(checkpoint, dict) or not _messages_omitted(checkpoint):
        return _ParentSealDecision(can_prune_ancestors=True, sealed=False)
    try:
        messages = _reconstruct_parent_messages(memory, tup)
    except REPORTABLE_ERRORS:
        _LOG.warning("prune_checkpoints: message replay failed thread=%s", thread_id, exc_info=True)
        return _ParentSealDecision(can_prune_ancestors=False, sealed=False)
    if not messages:
        return _ParentSealDecision(can_prune_ancestors=False, sealed=False)
    if dry_run:
        return _ParentSealDecision(can_prune_ancestors=True, sealed=True)
    try:
        _write_sealed_parent(memory, thread_id, tup, messages)
    except REPORTABLE_ERRORS:
        _LOG.warning("prune_checkpoints: seal write failed thread=%s", thread_id, exc_info=True)
        return _ParentSealDecision(can_prune_ancestors=False, sealed=False)
    return _ParentSealDecision(can_prune_ancestors=True, sealed=True)


def _reconstruct_parent_messages(memory: Memory, tup: Any) -> list[Any]:
    """Replay ``messages`` from the delta chain plus pending writes on *tup*."""
    messages: list[Any] = []
    saver = memory._checkpointer
    config = getattr(tup, "config", None)
    if not isinstance(config, dict):
        config = {"configurable": {}}
    delta_fn = getattr(saver, "get_delta_channel_history", None)
    if callable(delta_fn):
        hist = delta_fn(config=config, channels=["messages"])
        if isinstance(hist, dict):
            entry = hist.get("messages") or {}
            if isinstance(entry, dict):
                seed = entry.get("seed")
                if isinstance(seed, list):
                    messages = list(seed)
                for write in entry.get("writes") or []:
                    if isinstance(write, tuple) and len(write) >= 3:
                        messages = _apply_message_write(messages, write[2])
    if not messages:
        messages = _walk_parent_message_seed(saver, tup)
    pending = getattr(tup, "pending_writes", None) or []
    for item in pending:
        if isinstance(item, tuple) and len(item) >= 3 and item[1] == "messages":
            messages = _apply_message_write(messages, item[2])
    return messages


def _walk_parent_message_seed(saver: Any, tup: Any) -> list[Any]:
    """Fallback: first ancestor that still has ``channel_values['messages']``."""
    current: Any = tup
    seen: set[str] = set()
    while current is not None:
        cfg = getattr(current, "config", None) or {}
        cid = ""
        if isinstance(cfg, dict):
            cid = str((cfg.get("configurable") or {}).get("checkpoint_id") or "")
        if cid:
            if cid in seen:
                break
            seen.add(cid)
        checkpoint = getattr(current, "checkpoint", None)
        values = checkpoint.get("channel_values") if isinstance(checkpoint, dict) else None
        if isinstance(values, dict) and "messages" in values:
            raw = values.get("messages")
            return list(raw) if isinstance(raw, list) else []
        parent = getattr(current, "parent_config", None)
        if not isinstance(parent, dict):
            break
        current = saver.get_tuple(parent)
    return []


def _apply_message_write(messages: list[Any], value: Any) -> list[Any]:
    """Apply one LangGraph ``messages`` channel write.

    An empty write is a no-op. Guarded before ``add_messages`` because that
    reducer rejects a null right-hand side: the raise would bubble up through
    ``_reconstruct_parent_messages`` into ``_ensure_parent_sealed``, which
    fails closed and stops pruning that thread's ancestors forever.
    """
    if value is None:
        return messages
    try:
        from langgraph.graph.message import add_messages
    except ImportError:
        add_messages = None  # type: ignore[assignment]
    if add_messages is not None:
        result = add_messages(messages, value)
        return list(result) if not isinstance(result, list) else result
    if isinstance(value, list):
        return [*messages, *value]
    return [*messages, value]


def _write_sealed_parent(memory: Memory, thread_id: str, tup: Any, messages: list[Any]) -> None:
    """Insert a new root parent snapshot with ``messages`` inlined."""
    from copy import deepcopy

    from langgraph.checkpoint.base.id import uuid6

    checkpoint = getattr(tup, "checkpoint", None)
    if not isinstance(checkpoint, dict):
        raise TypeError("latest parent checkpoint is not a dict")
    sealed = deepcopy(checkpoint)
    values = dict(sealed.get("channel_values") or {})
    values["messages"] = messages
    sealed["channel_values"] = values
    sealed["id"] = str(uuid6())
    metadata = getattr(tup, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
    memory.put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        sealed,
        metadata,
        {},
    )


def _delete_stream(
    conn: sqlite3.Connection,
    thread_id: str,
    checkpoint_ns: str,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """Delete every checkpoint/write in one stream. Returns (checkpoints, writes)."""
    if dry_run:
        cp = conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ?",
            (thread_id, checkpoint_ns),
        ).fetchone()
        wr = conn.execute(
            "SELECT COUNT(*) FROM writes WHERE thread_id = ? AND checkpoint_ns = ?",
            (thread_id, checkpoint_ns),
        ).fetchone()
        return (cp[0] if cp else 0, wr[0] if wr else 0)
    wr_cur = conn.execute(
        "DELETE FROM writes WHERE thread_id = ? AND checkpoint_ns = ?",
        (thread_id, checkpoint_ns),
    )
    cp_cur = conn.execute(
        "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ?",
        (thread_id, checkpoint_ns),
    )
    conn.commit()
    writes = wr_cur.rowcount if wr_cur.rowcount and wr_cur.rowcount > 0 else 0
    checkpoints = cp_cur.rowcount if cp_cur.rowcount and cp_cur.rowcount > 0 else 0
    return checkpoints, writes


def _delete_checkpoint_ids(
    conn: sqlite3.Connection,
    thread_id: str,
    checkpoint_ns: str,
    victims: list[str],
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """Delete the given checkpoint ids (and their writes) in one stream."""
    placeholders = ",".join("?" for _ in victims)
    if dry_run:
        row = conn.execute(
            f"SELECT COUNT(*) FROM writes "
            f"WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id IN ({placeholders})",
            (thread_id, checkpoint_ns, *victims),
        ).fetchone()
        return len(victims), (row[0] if row else 0)
    wr_cur = conn.execute(
        f"DELETE FROM writes WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id IN ({placeholders})",
        (thread_id, checkpoint_ns, *victims),
    )
    conn.execute(
        f"DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id IN ({placeholders})",
        (thread_id, checkpoint_ns, *victims),
    )
    conn.commit()
    writes = wr_cur.rowcount if wr_cur.rowcount and wr_cur.rowcount > 0 else 0
    return len(victims), writes


def _safe_to_drop_subgraphs(memory: Memory, conn: sqlite3.Connection, thread_id: str) -> bool:
    """True when this thread's parent turn looks finished and no subgraph is ahead.

    In-flight / HITL: parent ends on an AI tool-call, or a ``tools:*`` row
    is newer than the latest parent (subgraph still writing). Those stay.
    """
    if _subgraph_newer_than_parent(conn, thread_id):
        return False
    try:
        return _parent_turn_finished(memory, thread_id)
    except REPORTABLE_ERRORS:
        _LOG.warning("prune_checkpoints: parent-state check failed thread=%s", thread_id, exc_info=True)
        return False


def _subgraph_newer_than_parent(conn: sqlite3.Connection, thread_id: str) -> bool:
    """True when any non-parent checkpoint_id sorts after the latest parent."""
    parent = conn.execute(
        "SELECT MAX(checkpoint_id) FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ?",
        (thread_id, ""),
    ).fetchone()
    parent_id = parent[0] if parent else None
    if not parent_id:
        return True
    newer = conn.execute(
        "SELECT 1 FROM checkpoints WHERE thread_id = ? AND checkpoint_ns != '' AND checkpoint_id > ? LIMIT 1",
        (thread_id, parent_id),
    ).fetchone()
    return newer is not None


def _parent_turn_finished(memory: Memory, thread_id: str) -> bool:
    """True when the latest parent snapshot ends on a final AI reply."""
    state = memory.get_thread_state(thread_id)
    if state is None:
        return False
    values = state.channel_values or {}
    if values.get("__interrupt__"):
        return False
    messages = values.get("messages") or []
    if not messages:
        return False
    last = messages[-1]
    if _message_has_tool_calls(last):
        return False
    return _message_is_ai(last)


def _message_has_tool_calls(msg: object) -> bool:
    if isinstance(msg, dict):
        return bool(msg.get("tool_calls"))
    return bool(getattr(msg, "tool_calls", None))


def _message_is_ai(msg: object) -> bool:
    if isinstance(msg, dict):
        return str(msg.get("type") or "") in {"ai", "AIMessage", "AIMessageChunk"}
    name = type(msg).__name__
    if name in {"AIMessage", "AIMessageChunk"}:
        return True
    return getattr(msg, "type", None) == "ai"


def _postgres_memory(memory: Any) -> bool:
    """True when ``memory`` stores on Postgres.

    Idle maintenance calls pruning for every loaded agent. Opening the
    checkpointer there builds a connection pool, so Postgres has to be
    rejected before ``_ensure_checkpointer`` (TencentCloud/Octop#1795).
    """
    backend = getattr(memory, "_backend", None)
    if backend is None:
        return False
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

    return isinstance(backend, PostgresMemoryBackend)


def _get_checkpointer_conn(memory: Memory) -> sqlite3.Connection:
    """Return the raw sqlite3 connection backing ``memory``'s checkpointer.

    Raises if the checkpointer isn't LangGraph's SQLite ``SqliteSaver``
    (e.g. no ``langgraph`` extra installed, or PostgreSQL backend) —
    silently no-op'ing would hide the fact that nothing got pruned.

    PostgreSQL is rejected before ``_ensure_checkpointer``. That call builds
    a connection pool, and the hourly maintenance tick would otherwise open
    one per loaded agent even though Postgres pruning always fails.
    """
    if _postgres_memory(memory):
        raise RuntimeError(
            "Checkpoint pruning requires the SQLite checkpointer (langgraph SqliteSaver); "
            "got 'PostgresMemoryBackend' with no usable 'conn' attribute "
            "(PostgreSQL checkpoint pruning is not yet supported)"
        )
    memory._ensure_checkpointer()
    saver = memory._checkpointer
    # getattr on an untyped saver yields Any; narrow explicitly so the
    # declared sqlite3.Connection return type is actually enforced rather
    # than silently satisfied by Any.
    conn = getattr(saver, "conn", None)
    if not isinstance(conn, sqlite3.Connection):
        raise RuntimeError(
            "Checkpoint pruning requires the SQLite checkpointer (langgraph SqliteSaver); "
            f"got {type(saver).__name__!r} with no usable 'conn' attribute "
            "(PostgreSQL checkpoint pruning is not yet supported)"
        )
    return conn


def _thread_ns_pairs(conn: sqlite3.Connection, *, thread_id: str | None) -> list[tuple[str, str]]:
    """Distinct ``(thread_id, checkpoint_ns)`` streams present in the checkpoints table."""
    if thread_id is not None:
        rows = conn.execute(
            "SELECT DISTINCT checkpoint_ns FROM checkpoints WHERE thread_id = ?",
            (thread_id,),
        ).fetchall()
        return [(thread_id, r[0]) for r in rows]
    rows = conn.execute("SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoints").fetchall()
    return [(r[0], r[1]) for r in rows]


def _victim_checkpoint_ids(
    conn: sqlite3.Connection,
    thread_id: str,
    checkpoint_ns: str,
    *,
    keep_last: int | None,
    cutoff_id: str | None,
) -> list[str]:
    """Checkpoint ids in this stream that fail both retention checks (candidates for deletion)."""
    rows = conn.execute(
        "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = ? ORDER BY checkpoint_id DESC",
        (thread_id, checkpoint_ns),
    ).fetchall()
    ids = [r[0] for r in rows]
    if not ids:
        return []

    # Safety net: never prune the single latest checkpoint of an active
    # stream, even if it somehow fails both checks (e.g. keep_last=0
    # would be rejected earlier, but a huge keep_days on a stale clock
    # shouldn't be able to erase the only usable state either).
    survivors: set[str] = {ids[0]}
    if keep_last is not None:
        survivors.update(ids[:keep_last])
    if cutoff_id is not None:
        survivors.update(cid for cid in ids if cid >= cutoff_id)

    return [cid for cid in ids if cid not in survivors]


def _cutoff_checkpoint_id(cutoff: datetime) -> str:
    """Smallest possible checkpoint_id (UUIDv6 string) for the given instant.

    Any real checkpoint_id that string-sorts below this value was
    created strictly before ``cutoff``. Mirrors the bit layout of
    ``langgraph.checkpoint.base.id.uuid6`` with ``clock_seq=0, node=0``
    zeroed out, which yields a lower bound: a real checkpoint minted at
    exactly ``cutoff`` will have non-zero low bits and therefore sort
    at or above this synthetic id.
    """
    nanoseconds = int(cutoff.timestamp() * 1_000_000_000)
    # 0x01b21dd213814000 = 100-ns intervals between the UUID epoch
    # (1582-10-15) and the Unix epoch (1970-01-01).
    timestamp = nanoseconds // 100 + 0x01B21DD213814000
    time_high_and_time_mid = (timestamp >> 12) & 0xFFFFFFFFFFFF
    time_low_and_version = timestamp & 0x0FFF
    uuid_int = time_high_and_time_mid << 80
    uuid_int |= time_low_and_version << 64
    # RFC4122 variant bits + version=6 nibble; clock_seq/node bits are
    # left at 0 (the lower-bound property this function relies on).
    uuid_int &= ~(0xC000 << 48)
    uuid_int |= 0x8000 << 48
    uuid_int &= ~(0xF000 << 64)
    uuid_int |= 6 << 76
    return str(uuid.UUID(int=uuid_int))


__all__ = [
    "DEFAULT_KEEP_LAST_CHECKPOINTS",
    "CheckpointGcStats",
    "prune_checkpoints",
]
