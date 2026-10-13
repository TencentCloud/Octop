"""Independent SQLite archive. No control-plane schema migrations or backfill.

Message and trajectory documents share content-addressed bodies. Replacing a
live document releases only its own obsolete bodies, in the same transaction.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from octop.infra.db.pool import SqlitePool

_BODY_KEYS = frozenset(
    {"content", "text", "reasoning_content", "thinking", "summary", "args", "result"}
)
# Stable boundaries let an appended token reuse every completed text block.
# Count Unicode characters so splitting and rejoining never damages UTF-8.
TEXT_BLOCK_SIZE = 1024
_SCHEMA = """
CREATE TABLE archive_meta (version INTEGER NOT NULL, identity TEXT NOT NULL);
CREATE TABLE segments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL, agent_id TEXT NOT NULL,
 format TEXT NOT NULL CHECK(format IN ('legacy','v2')),
 legacy_start INTEGER NOT NULL, legacy_end INTEGER, anchor TEXT,
 trajectory_start INTEGER NOT NULL, trajectory_end INTEGER
);
CREATE INDEX segments_thread ON segments(thread_id,id);
CREATE TABLE turns (
 id TEXT PRIMARY KEY, segment_id INTEGER NOT NULL REFERENCES segments(id),
 status TEXT NOT NULL, error TEXT, started_at REAL NOT NULL, finished_at REAL
);
CREATE TABLE bodies (digest TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE documents (
 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL REFERENCES turns(id),
 kind TEXT NOT NULL CHECK(kind IN ('message','event')), seq INTEGER NOT NULL,
 data TEXT NOT NULL, UNIQUE(thread_id,kind,seq)
);
CREATE INDEX documents_turn ON documents(turn_id,kind,seq);
CREATE TABLE body_refs (
 owner TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 digest TEXT NOT NULL REFERENCES bodies(digest), PRIMARY KEY(owner,digest)
);
CREATE INDEX refs_digest ON body_refs(digest);
"""


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class HistoryStore:
    def __init__(self, path: Path, *, identity: str) -> None:
        existed = path.exists()
        marker = path.with_suffix(".required")
        if not existed and marker.exists():
            raise FileNotFoundError("The required history archive is missing: " + str(path))
        self.path = path
        self.db = SqlitePool(path)
        try:
            with self.db.connect() as conn:
                conn.execute("PRAGMA synchronous = FULL")
                conn.execute("PRAGMA busy_timeout = 5000")
                if not existed:
                    conn.executescript("BEGIN IMMEDIATE;" + _SCHEMA)
                    conn.execute("INSERT INTO archive_meta VALUES (1, ?)", (identity,))
                    conn.commit()
                row = conn.execute("SELECT version, identity FROM archive_meta").fetchone()
                if row is None or row["version"] != 1 or row["identity"] != identity:
                    raise ValueError("History archive version or control-plane identity mismatch")
            marker.write_text(
                "History archive required; do not remove independently.\n", encoding="utf-8"
            )
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        # Refuse to recreate a missing archive: absence is not an empty history.
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.db.transaction() as conn:
            yield conn

    def segments(self, thread_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM segments WHERE thread_id = ? ORDER BY id", (thread_id,)
                )
            ]

    def turn(self, thread_id: str, *, unfinished: bool = False) -> dict[str, Any] | None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT t.*, s.format, s.thread_id, s.agent_id FROM turns t "
                "JOIN segments s ON s.id=t.segment_id WHERE s.thread_id=? "
                + ("AND t.status IN ('active','paused') " if unfinished else "")
                + "ORDER BY t.started_at DESC, t.id DESC LIMIT 1",
                (thread_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def put_document(
        self,
        conn: sqlite3.Connection,
        *,
        doc_id: str,
        thread_id: str,
        turn_id: str,
        kind: str,
        seq: int,
        value: dict[str, Any],
    ) -> None:
        old = conn.execute("SELECT data FROM documents WHERE id=?", (doc_id,)).fetchone()
        old_refs = {
            str(r[0]) for r in conn.execute("SELECT digest FROM body_refs WHERE owner=?", (doc_id,))
        }
        refs: set[str] = set()

        def intern(item: Any) -> str:
            body = dumps(item)
            digest = hashlib.sha256(body.encode()).hexdigest()
            if digest not in old_refs and digest not in refs:
                conn.execute("INSERT OR IGNORE INTO bodies VALUES (?,?)", (digest, body))
            refs.add(digest)
            return digest

        def encode(item: Any, key: str = "") -> Any:
            if isinstance(item, str) and len(item) > TEXT_BLOCK_SIZE:
                return [
                    "text",
                    [
                        intern(item[start : start + TEXT_BLOCK_SIZE])
                        for start in range(0, len(item), TEXT_BLOCK_SIZE)
                    ],
                ]
            if isinstance(item, dict):
                return ["dict", [[k, encode(v, k)] for k, v in item.items()]]
            if isinstance(item, list):
                return ["list", [encode(v) for v in item]]
            if key in _BODY_KEYS and item not in (None, ""):
                return ["body", intern(item)]
            return ["value", item]

        encoded = dumps(encode(value))
        if old is not None and old["data"] == encoded:
            return
        conn.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "data=excluded.data",
            (doc_id, thread_id, turn_id, kind, seq, encoded),
        )
        conn.executemany(
            "DELETE FROM body_refs WHERE owner=? AND digest=?",
            [(doc_id, ref) for ref in old_refs - refs],
        )
        conn.executemany(
            "INSERT INTO body_refs VALUES (?,?)", [(doc_id, ref) for ref in refs - old_refs]
        )
        for digest in old_refs - refs:
            conn.execute(
                "DELETE FROM bodies WHERE digest=? AND NOT EXISTS "
                "(SELECT 1 FROM body_refs WHERE digest=?)",
                (digest, digest),
            )

    def _decode(self, conn: sqlite3.Connection, node: Any) -> Any:
        tag, value = node
        if tag == "body":
            row = conn.execute("SELECT value FROM bodies WHERE digest=?", (value,)).fetchone()
            if row is None:
                raise ValueError("History body reference is missing")
            return json.loads(row[0])
        if tag == "text":
            return "".join(self._decode(conn, ["body", digest]) for digest in value)
        if tag == "dict":
            return {k: self._decode(conn, v) for k, v in value}
        if tag == "list":
            return [self._decode(conn, v) for v in value]
        if tag == "value":
            return value
        raise ValueError("Unknown history encoding")

    def documents(
        self,
        thread_id: str,
        kind: str,
        *,
        segment_id: int | None = None,
        turn_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        conditions = ["d.thread_id=?", "d.kind=?"]
        args: list[Any] = [thread_id, kind]
        if segment_id is not None:
            conditions.append("t.segment_id=?")
            args.append(segment_id)
        if turn_id is not None:
            conditions.append("d.turn_id=?")
            args.append(turn_id)
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT d.*,t.status FROM documents d JOIN turns t ON t.id=d.turn_id WHERE "
                + " AND ".join(conditions)
                + " ORDER BY d.seq",
                args,
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "seq": row["seq"],
                    "turn_id": row["turn_id"],
                    "status": row["status"],
                    "value": self._decode(conn, json.loads(row["data"])),
                }
                for row in rows
            ]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT data FROM documents WHERE id=? AND kind='event'", ("event:" + event_id,)
            ).fetchone()
            if row is None:
                return None
            value: dict[str, Any] = self._decode(conn, json.loads(row[0]))
            return value

    def message_page(
        self, thread_id: str, segment_id: int, before: int | None, limit: int
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT d.seq,d.data FROM documents d JOIN turns t ON t.id=d.turn_id "
                "WHERE d.thread_id=? AND t.segment_id=? AND d.kind='message' "
                "AND (? IS NULL OR d.seq<?) ORDER BY d.seq DESC LIMIT ?",
                (thread_id, segment_id, before, before, limit),
            ).fetchall()
            return [
                {"seq": row["seq"], "value": self._decode(conn, json.loads(row["data"]))}
                for row in rows
            ]

    def event_page(self, thread_id: str, before: int | None, limit: int) -> list[dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT data FROM documents WHERE thread_id=? AND kind='event' "
                "AND (? IS NULL OR seq<?) ORDER BY seq DESC LIMIT ?",
                (thread_id, before, before, limit),
            ).fetchall()
            return [self._decode(conn, json.loads(row[0])) for row in rows]

    def close(self) -> None:
        self.db.close()
