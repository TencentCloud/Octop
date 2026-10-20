"""SQLite checkpoint field reuse; old inline rows remain readable.

Only the two large, stable DeepAgents channels are externalized. The public
checkpoint is unchanged: every read path (including delta history) uses the
same decoding serializer. Blob bytes and their checkpoint commit together.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata, get_checkpoint_metadata
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.sqlite import SqliteSaver

FORMAT = "harness-checkpoint-v1"
CHANNELS = ("skills_metadata", "memory_contents")
MIN_FIELD_BYTES = 256
CACHE_BYTES = 4 * 1024 * 1024


def content_digest(kind: str, value: bytes) -> str:
    """Hash typed bytes; serializer types are part of the content identity."""
    return hashlib.sha256(kind.encode() + b"\0" + value).hexdigest()


def unpack_envelope(data: bytes) -> tuple[str, dict[str, str], bytes]:
    """Read the versioned header without deserializing user state."""
    if len(data) < 4:
        raise ValueError("Truncated checkpoint reference envelope")
    size = struct.unpack(">I", data[:4])[0]
    if size > len(data) - 4:
        raise ValueError("Truncated checkpoint reference header")
    header = json.loads(data[4 : 4 + size])
    kind, refs = header["type"], header["refs"]
    if not isinstance(kind, str) or kind.startswith("harness-checkpoint-") or not isinstance(refs, dict):
        raise ValueError("Invalid checkpoint reference header")
    if any(k not in CHANNELS or not isinstance(v, str) or len(v) != 64 for k, v in refs.items()):
        raise ValueError("Invalid checkpoint content reference")
    return kind, refs, data[4 + size :]


class CheckpointSerializer:
    """Decode references on all SqliteSaver reads; cache bytes, never objects.

    Callers use the saver lock for DB access. The byte-bounded cache cannot be
    mutated by graph reducers; each read deserializes a fresh field value.
    """

    def __init__(self, conn: sqlite3.Connection, base: SerializerProtocol) -> None:
        self.conn = conn
        self.base = base
        self.cache: OrderedDict[str, tuple[str, bytes]] = OrderedDict()
        self.cache_size = 0

    def with_connection(self, conn: sqlite3.Connection) -> CheckpointSerializer:
        """Bind reference reads to another connection with an independent cache.

        Preserve the underlying serializer's configuration. The caller owns
        the new connection's transaction and lock, just as a saver normally does.
        """
        return CheckpointSerializer(conn, self.base)

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        # put_writes stays inline. Compaction is explicit in saver.put, inside
        # its transaction, rather than a serializer with hidden write effects.
        return self.base.dumps_typed(obj)

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        kind, value = data
        if kind != FORMAT:
            if kind.startswith("harness-checkpoint-"):
                raise ValueError(f"Unsupported checkpoint format: {kind}")
            return self.base.loads_typed(data)
        inner_kind, refs, payload = unpack_envelope(value)
        missing = sorted(set(refs.values()) - self.cache.keys())
        fetched: dict[str, tuple[str, bytes]] = {}
        if missing:
            marks = ",".join("?" for _ in missing)
            rows = self.conn.execute(
                f"SELECT digest, type, value FROM hm_checkpoint_blobs WHERE digest IN ({marks})", missing
            ).fetchall()
            for digest, blob_kind, blob in rows:
                if content_digest(blob_kind, blob) != digest:
                    raise ValueError(f"Corrupt checkpoint content: {digest}")
                fetched[digest] = (blob_kind, blob)
            if set(missing) != fetched.keys():
                raise ValueError("Missing checkpoint content; restore the matching database backup")
        # Resolve before populating the cache: a large field may evict another
        # field needed by this very checkpoint.
        resolved = {digest: fetched[digest] if digest in fetched else self.cache[digest] for digest in refs.values()}
        for digest, item in resolved.items():
            if digest in self.cache:
                self.cache.move_to_end(digest)
            elif len(item[1]) <= CACHE_BYTES:
                self.cache[digest] = item
                self.cache_size += len(item[1])
            while self.cache_size > CACHE_BYTES:
                _, evicted = self.cache.popitem(last=False)
                self.cache_size -= len(evicted[1])
        checkpoint = self.base.loads_typed((inner_kind, payload))
        values = checkpoint["channel_values"]
        if any(channel in values for channel in refs):
            raise ValueError("Checkpoint contains both inline and referenced channel values")
        for channel, digest in refs.items():
            values[channel] = self.base.loads_typed(resolved[digest])
        return checkpoint

    def encode(self, checkpoint: Checkpoint) -> tuple[str, bytes, dict[str, tuple[str, bytes]]]:
        """Produce a reduced checkpoint and typed content without DB writes."""
        values = checkpoint["channel_values"].copy()
        refs: dict[str, str] = {}
        blobs: dict[str, tuple[str, bytes]] = {}
        for channel in CHANNELS:
            if channel not in values:
                continue
            kind, value = self.base.dumps_typed(values[channel])
            if len(value) < MIN_FIELD_BYTES:
                continue
            digest = content_digest(kind, value)
            blobs[digest] = (kind, value)
            refs[channel] = digest
            del values[channel]
        if not refs:
            kind, value = self.base.dumps_typed(checkpoint)
            return kind, value, {}
        reduced = checkpoint.copy()
        reduced["channel_values"] = values
        kind, value = self.base.dumps_typed(reduced)
        header = json.dumps({"type": kind, "refs": refs}, separators=(",", ":")).encode()
        return FORMAT, struct.pack(">I", len(header)) + header + value, blobs


class CompactSqliteSaver(SqliteSaver):
    """Drop-in synchronous saver with compatible reads and atomic field reuse.

    Memory provides the asynchronous to_thread delegation. Set ``compact=False``
    to stop new reference writes while continuing to read both formats.
    """

    def __init__(
        self, conn: sqlite3.Connection, *, serde: SerializerProtocol | None = None, compact: bool = True
    ) -> None:
        super().__init__(conn, serde=serde)
        self.codec = CheckpointSerializer(conn, self.serde)
        self.serde = self.codec
        self.compact = compact

    def setup(self) -> None:
        if self.is_setup:
            return
        super().setup()
        committed = False
        try:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS hm_checkpoint_blobs "
                "(digest TEXT PRIMARY KEY, type TEXT NOT NULL, value BLOB NOT NULL)"
            )
            self.conn.commit()
            committed = True
        finally:
            if not committed:
                self.is_setup = False

    @contextmanager
    def cursor(self, transaction: bool = True) -> Iterator[sqlite3.Cursor]:
        # Upstream's cursor commits in finally, including failed statements.
        # A shared-content write needs actual rollback on errors/cancellation.
        with self.lock:
            self.setup()
            cur = self.conn.cursor()
            committed = False
            try:
                cur.execute("BEGIN IMMEDIATE" if transaction else "BEGIN")
                yield cur
                self.conn.commit()
                committed = True
            finally:
                try:
                    if not committed:
                        self.conn.rollback()
                finally:
                    cur.close()

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        blobs: dict[str, tuple[str, bytes]] = {}
        if self.compact:
            kind, value, blobs = self.codec.encode(checkpoint)
        else:
            kind, value = self.codec.dumps_typed(checkpoint)
        meta = json.dumps(get_checkpoint_metadata(config, metadata), ensure_ascii=False).encode("utf-8", "ignore")
        cfg = config["configurable"]
        ns = cfg.get("checkpoint_ns", "")
        with self.cursor() as cur:
            cur.executemany(
                "INSERT OR IGNORE INTO hm_checkpoint_blobs (digest, type, value) VALUES (?, ?, ?)",
                [(digest, *item) for digest, item in blobs.items()],
            )
            cur.execute(
                "INSERT OR REPLACE INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(cfg["thread_id"]), ns, checkpoint["id"], cfg.get("checkpoint_id"), kind, value, meta),
            )
        return {"configurable": {"thread_id": cfg["thread_id"], "checkpoint_ns": ns, "checkpoint_id": checkpoint["id"]}}
