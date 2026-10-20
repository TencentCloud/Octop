"""D51-C / D52-C — host-written real-file index.

OpenClaw's compaction silent turn writes ``memory/YYYY-MM-DD.md`` and
the user may hand-edit ``MEMORY.md``. Both are real files on disk, NOT
passing through the core Memory tables. This module keeps an
inverted-index sidecar table so:

1. ``memory_search`` can also surface these files.
2. ``memory_get`` for ``host_root`` / ``host_daily`` / ``host_dreams``
   paths reads the indexed body (stable + line-sliceable) instead of
   round-tripping the live filesystem.

Design (D51-C / 2026-06-04 locked):

- **Polling, not inotify.** 30s ``stat`` loop in a background thread.
  Rationale: the memory plugin runs on dual-core small machines (D39-A);
  ``watchdog`` adds a native dependency for negligible benefit at this
  cadence. ``mtime`` comparison is enough.
- **Self-contained schema.** ``{ns}_host_files`` + ``{ns}_host_files_fts``
  live on the same SQLite db as Memory but are managed entirely by this
  module. The :class:`Memory` class is unaware (no Protocol changes).
- **Idempotent scans.** ``scan_once()`` is safe to call repeatedly;
  unchanged files are detected via ``(size, mtime_ns)`` and skipped.

Threading model:

- One :class:`sqlite3.Connection` per :class:`HostFilesIndex` instance.
  All writes happen on the polling thread; reads from the bridge call
  path acquire a short lock (`_lock`) to serialize.
- ``WAL`` mode is honoured by Memory's connection so reads from this
  index don't block Memory's atom/raw queries.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from octop_memory.storage.backends.fts_text import (
    FTS_TEXT_VERSION,
    fts_match_phrase,
    register_fts_functions,
)
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path discriminator — which real files we index
# ---------------------------------------------------------------------------

_DAILY_RE = re.compile(r"^memory/(\d{4}-\d{2}-\d{2})(?:-([A-Za-z0-9_\-]+))?\.md$")

# Fixed root-relative paths we index unconditionally if present. ``USER.md``
# covers Hermes' built-in profile memory when the root is $HERMES_HOME/memories.
_ROOT_FILES: frozenset[str] = frozenset({"MEMORY.md", "DREAMS.md", "USER.md"})

# Safe topical memory directories. We intentionally do not default to
# ``**/*.md`` because workspaces commonly contain README/docs files and private
# notes that are not memory.
DEFAULT_HOST_FILE_GLOBS: tuple[str, ...] = ("topics/*.md", "projects/*.md")


@dataclass(frozen=True)
class HostFile:
    """One row of the host-files index — a snapshot of a real file."""

    path: str
    """Workspace-relative path, e.g. ``"memory/2026-06-04.md"``."""

    content: str
    """Full file body. UTF-8 decoded; binary files are skipped."""

    size: int
    """``stat().st_size`` at the time of the last successful index."""

    mtime_ns: int
    """``stat().st_mtime_ns`` at the time of the last successful index."""

    indexed_at: float
    """Unix time at which this row was written."""


@dataclass(frozen=True)
class HostFileHit:
    """A search hit from the host-files index."""

    path: str
    snippet: str
    """A trimmed prefix of the file body for quick previewing."""

    indexed_at: float


@dataclass(frozen=True)
class ScanReport:
    """Returned by :meth:`HostFilesIndex.scan_once` so callers can log."""

    scanned: int
    """Files we touched (regardless of whether they had changed)."""

    indexed: int
    """Files whose content was (re)written into the index."""

    removed: int
    """Files that disappeared from disk and were dropped from the index."""

    skipped_binary: int
    """Files we found but could not decode as UTF-8."""


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


class HostFilesIndex:
    """SQLite-backed index over host-written real files.

    Owns its own :class:`sqlite3.Connection` so reads from the bridge
    don't contend with Memory's connection (the alternative — sharing
    one connection — would serialize the agent_end capture path).
    """

    def __init__(
        self,
        db_path: str | Path,
        namespace: str,
        *,
        include_globs: Iterable[str] | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._ns = namespace
        patterns = DEFAULT_HOST_FILE_GLOBS if include_globs is None else include_globs
        self._include_globs = tuple(_safe_include_globs(patterns))
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # FTS-sync triggers call hm_cjk_seg(); register before any write.
        register_fts_functions(self._conn)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.root: Path | None = None
        self.poll_interval_s: float | None = None
        self.last_scan_iso: str | None = None
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        ns = self._ns
        self._conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS {ns}_host_files (
                path TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                indexed_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS {ns}_host_files_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self._ensure_fts_and_triggers()
        self._conn.commit()
        self._migrate_fts_text_version()

    def _ensure_fts_and_triggers(self) -> None:
        """Create the FTS table + sync triggers (idempotent).

        Trigger bodies run content through ``hm_cjk_seg`` so CJK text is
        indexed per-character (see :mod:`octop_memory.storage.backends.fts_text`).
        """
        ns = self._ns
        self._conn.executescript(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {ns}_host_files_fts USING fts5(
                content,
                content='{ns}_host_files',
                content_rowid='rowid',
                tokenize='unicode61'
            );

            CREATE TRIGGER IF NOT EXISTS {ns}_host_files_ai
            AFTER INSERT ON {ns}_host_files BEGIN
                INSERT INTO {ns}_host_files_fts(rowid, content)
                VALUES (new.rowid, hm_cjk_seg(new.content));
            END;

            CREATE TRIGGER IF NOT EXISTS {ns}_host_files_ad
            AFTER DELETE ON {ns}_host_files BEGIN
                INSERT INTO {ns}_host_files_fts({ns}_host_files_fts, rowid, content)
                VALUES ('delete', old.rowid, hm_cjk_seg(old.content));
            END;

            CREATE TRIGGER IF NOT EXISTS {ns}_host_files_au
            AFTER UPDATE ON {ns}_host_files BEGIN
                INSERT INTO {ns}_host_files_fts({ns}_host_files_fts, rowid, content)
                VALUES ('delete', old.rowid, hm_cjk_seg(old.content));
                INSERT INTO {ns}_host_files_fts(rowid, content)
                VALUES (new.rowid, hm_cjk_seg(new.content));
            END;
        """)

    def _migrate_fts_text_version(self) -> None:
        """Rebuild triggers + FTS index when CJK segmentation changes.

        Mirrors SqliteMemoryBackend._migrate_fts_text_version: pre-v2
        databases indexed raw text, which is unsearchable for Chinese.
        CREATE TRIGGER IF NOT EXISTS keeps old trigger bodies, so the
        upgrade must drop + recreate them explicitly.
        """
        ns = self._ns
        row = self._conn.execute(f"SELECT value FROM {ns}_host_files_meta WHERE key = 'fts_text_version'").fetchone()
        if row is not None and row["value"] == FTS_TEXT_VERSION:
            return
        for suffix in ("ai", "ad", "au"):
            self._conn.execute(f"DROP TRIGGER IF EXISTS {ns}_host_files_{suffix}")
        # Recreate with the current (segmented) bodies, then re-derive
        # the index from the content table.
        self._conn.execute(f"DROP TABLE IF EXISTS {ns}_host_files_fts")
        self._conn.commit()
        self._ensure_fts_and_triggers()
        self._conn.execute(
            f"INSERT INTO {ns}_host_files_fts(rowid, content) SELECT rowid, hm_cjk_seg(content) FROM {ns}_host_files"
        )
        self._conn.execute(
            f"INSERT INTO {ns}_host_files_meta (key, value) VALUES ('fts_text_version', ?) "
            f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (FTS_TEXT_VERSION,),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public reads
    # ------------------------------------------------------------------

    def get(self, path: str) -> HostFile | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT path, content, size, mtime_ns, indexed_at FROM {self._ns}_host_files WHERE path = ?",
                (path,),
            ).fetchone()
        if row is None:
            return None
        return HostFile(
            path=row["path"],
            content=row["content"],
            size=int(row["size"]),
            mtime_ns=int(row["mtime_ns"]),
            indexed_at=float(row["indexed_at"]),
        )

    def search(self, query: str, *, limit: int = 10, snippet_chars: int = 200) -> list[HostFileHit]:
        """Run an FTS5 query and return ranked hits.

        ``snippet_chars`` clips each body to a leading window so the
        bridge can include hits in a recall response without blowing
        token budget. The agent can pull the full body via
        ``memory_get(path=...)``.
        """
        if not query.strip():
            return []
        # FTS5 is space-tokenized; we OR-join tokens for natural-language
        # queries (mirrors recall.parser's strategy for atoms/raw).
        tokens = [t for t in re.split(r"\s+", query.strip()) if t]
        if not tokens:
            return []
        # Each token becomes a CJK-segmented quoted phrase so Chinese
        # queries match the per-character index.
        match_expr = " OR ".join(fts_match_phrase(t) for t in tokens)

        with self._lock:
            rows = self._conn.execute(
                f"SELECT h.path, h.content, h.indexed_at "
                f"FROM {self._ns}_host_files_fts f "
                f"JOIN {self._ns}_host_files h ON f.rowid = h.rowid "
                f"WHERE f.{self._ns}_host_files_fts MATCH ? "
                f"ORDER BY rank LIMIT ?",
                (match_expr, limit),
            ).fetchall()

        out: list[HostFileHit] = []
        for r in rows:
            body = r["content"]
            snippet = body if len(body) <= snippet_chars else body[: snippet_chars - 1] + "…"
            out.append(
                HostFileHit(
                    path=r["path"],
                    snippet=snippet.strip(),
                    indexed_at=float(r["indexed_at"]),
                )
            )
        return out

    def stats(self) -> dict[str, object]:
        """Return a lightweight status snapshot for CLI / doctor output."""
        with self._lock:
            indexed = int(self._conn.execute(f"SELECT COUNT(*) AS c FROM {self._ns}_host_files").fetchone()["c"])
        return {
            "root": str(self.root) if self.root is not None else None,
            "indexed": indexed,
            "last_scan_iso": self.last_scan_iso,
            "poll_interval_s": self.poll_interval_s,
        }

    # ------------------------------------------------------------------
    # Scan loop
    # ------------------------------------------------------------------

    def scan_once(self, workspace_root: Path) -> ScanReport:
        """Walk the workspace + sync the index to current disk state.

        - Files NEW on disk → INSERT row + FTS sync (via trigger).
        - Files CHANGED (mtime or size differ) → UPDATE row.
        - Files MISSING from disk but present in index → DELETE row.

        Idempotent: calling twice with no disk changes does zero work
        beyond the stat calls.
        """
        self.root = workspace_root
        self.last_scan_iso = datetime.now(UTC).isoformat()
        scanned = 0
        indexed = 0
        skipped_binary = 0

        on_disk: dict[str, tuple[int, int]] = {}  # path → (size, mtime_ns)
        for relative in _candidate_paths(workspace_root, include_globs=self._include_globs):
            scanned += 1
            full = workspace_root / relative
            try:
                stat = full.stat()
            except FileNotFoundError:
                continue
            on_disk[relative] = (stat.st_size, stat.st_mtime_ns)

        # Pull current index state once.
        with self._lock:
            cursor = self._conn.execute(f"SELECT path, size, mtime_ns FROM {self._ns}_host_files")
            current = {r["path"]: (int(r["size"]), int(r["mtime_ns"])) for r in cursor.fetchall()}

        # Inserts + updates.
        for relative, (size, mtime_ns) in on_disk.items():
            if current.get(relative) == (size, mtime_ns):
                continue  # unchanged
            try:
                content = (workspace_root / relative).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skipped_binary += 1
                continue
            now = time.time()
            with self._lock:
                self._conn.execute(
                    f"""INSERT INTO {self._ns}_host_files
                        (path, content, size, mtime_ns, indexed_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            content = excluded.content,
                            size = excluded.size,
                            mtime_ns = excluded.mtime_ns,
                            indexed_at = excluded.indexed_at""",
                    (relative, content, size, mtime_ns, now),
                )
                self._conn.commit()
            indexed += 1

        # Deletions: anything in current that's gone from disk.
        removed_paths = set(current.keys()) - set(on_disk.keys())
        if removed_paths:
            with self._lock:
                self._conn.executemany(
                    f"DELETE FROM {self._ns}_host_files WHERE path = ?",
                    [(p,) for p in removed_paths],
                )
                self._conn.commit()

        return ScanReport(
            scanned=scanned,
            indexed=indexed,
            removed=len(removed_paths),
            skipped_binary=skipped_binary,
        )

    # ------------------------------------------------------------------
    # Background polling
    # ------------------------------------------------------------------

    def start_polling(self, workspace_root: Path, *, interval: float = 30.0) -> None:
        """Spawn a daemon thread that calls :meth:`scan_once` every ``interval`` seconds.

        Idempotent: starting twice is a no-op (we keep the first thread).
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self.root = workspace_root
        self.poll_interval_s = interval
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    report = self.scan_once(workspace_root)
                    if report.indexed or report.removed:
                        logger.info(
                            "host_files index: scanned=%d indexed=%d removed=%d skipped_binary=%d",
                            report.scanned,
                            report.indexed,
                            report.removed,
                            report.skipped_binary,
                        )
                except REPORTABLE_ERRORS:
                    logger.exception("host_files: scan_once failed; will retry next tick")
                # Sleep responsive to stop signal.
                self._stop.wait(timeout=interval)

        self._thread = threading.Thread(target=_loop, name="octopmemory-host-files-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to exit and close the connection."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with suppress(sqlite3.Error):
            self._conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate_paths(root: Path, *, include_globs: Iterable[str] = DEFAULT_HOST_FILE_GLOBS) -> Iterable[str]:
    """Yield workspace-relative paths we index, given a workspace root.

    Rules:
    - ``MEMORY.md``, ``USER.md``, and ``DREAMS.md`` at root.
    - Any ``memory/<YYYY-MM-DD>.md`` or ``memory/<YYYY-MM-DD>-<slug>.md``.
    - Safe allowlist globs such as ``topics/*.md`` and ``projects/*.md``.

    Other files (PDFs, configs, ad-hoc notes the user dropped in) are
    out of scope unless they match the explicit allowlist.
    """
    seen: set[str] = set()

    def emit(relative: str) -> str | None:
        if relative in seen:
            return None
        full = root / relative
        if not full.is_file() or full.is_symlink():
            return None
        seen.add(relative)
        return relative

    for fixed in _ROOT_FILES:
        if candidate := emit(fixed):
            yield candidate
    memory_dir = root / "memory"
    if memory_dir.is_dir():
        for entry in memory_dir.iterdir():
            if not entry.is_file() or entry.is_symlink():
                continue
            relative = f"memory/{entry.name}"
            if _DAILY_RE.match(relative) and (candidate := emit(relative)):
                yield candidate

    for pattern in _safe_include_globs(include_globs):
        for entry in root.glob(pattern):
            try:
                relative = entry.relative_to(root).as_posix()
            except ValueError:
                continue
            if candidate := emit(relative):
                yield candidate


def _safe_include_globs(patterns: Iterable[str]) -> Iterable[str]:
    """Filter user-supplied host-file patterns to safe relative markdown globs."""
    for raw in patterns:
        pattern = raw.strip()
        if not pattern or not pattern.endswith(".md"):
            continue
        path = Path(pattern)
        if path.is_absolute():
            continue
        parts = path.parts
        if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
            continue
        yield pattern


__all__ = [
    "DEFAULT_HOST_FILE_GLOBS",
    "HostFile",
    "HostFileHit",
    "HostFilesIndex",
    "ScanReport",
]
