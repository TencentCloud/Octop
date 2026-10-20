"""One-click pack implementation (requirements 2, 6).

Exports the memory of a given namespace into a .hmpkg file (a zip container
holding manifest.json + data.jsonl.gz).
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import sqlite3
import sys
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from octop_memory.core import Memory
from octop_memory.operations.migration import EXPORT_VERSION
from octop_memory.operations.migration.export import export_namespace
from octop_memory.operations.migration.portable.models import (
    HOST_DEFAULT_PATHS,
    PKG_VERSION,
    PackSummary,
    SourceInfo,
)
from octop_memory.operations.migration.portable.sources import list_sources

try:
    from octop_memory._version import __version__ as _HM_VERSION  # type: ignore[import-untyped]
except ImportError:
    _HM_VERSION = "unknown"

logger = logging.getLogger(__name__)

_TOOL_VERSION = f"octop_memory.portable/{_HM_VERSION}"

# Default output directory
_DEFAULT_OUT_DIR = Path("~/.octop-memory/portable")


def _resolve_source(source: SourceInfo | str) -> SourceInfo:
    """Resolve a 'host:name' string or a SourceInfo into a SourceInfo.

    String format: 'agent:my-agent' / 'openclaw:myns' / 'hermes', etc.
    """
    if isinstance(source, SourceInfo):
        return source

    # Parse the 'host:name' format
    if ":" in source:
        host_kind, name = source.split(":", 1)
    else:
        host_kind = source
        name = ""

    host_kind = host_kind.strip().lower()
    name = name.strip()

    # First, try to find a match in list_sources
    all_sources = list_sources()
    for src in all_sources:
        if src.host_kind == host_kind:
            if not name:
                return src
            # Match against agent_name or namespace
            if src.agent_name.lower() == name.lower():
                return src
            if src.namespace.lower() == name.lower():
                return src
            # Also match when name is contained in namespace (e.g. agent_zywztd_ contains zywztd)
            if name.lower() in src.namespace.lower():
                return src

    # If not found, try constructing the path directly
    if host_kind in HOST_DEFAULT_PATHS:
        template = HOST_DEFAULT_PATHS[host_kind]
        db_path = Path(template.format(name=name or "default")).expanduser()
        if db_path.exists():
            return SourceInfo(
                host_kind=host_kind,
                db_path=str(db_path),
                namespace=f"{host_kind}__{name.lower()}_" if name else host_kind,
                agent_name=name,
            )

    raise ValueError(
        f"source memory store not found: {source!r}. Run 'octop-memory portable list-sources' to see available sources."
    )


def _open_memory_ro(db_path: str, namespace: str) -> Memory:
    """Open the SQLite db in read-only mode and return a Memory instance.

    Note: Memory itself does not support a read-only mode. We first verify the
    db can be opened read-only, then open it normally (read-only usage only).
    """
    # First verify it can be opened read-only
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        # Check whether there are un-checkpointed WAL writes
        try:
            wal_path = Path(db_path + "-wal")
            if wal_path.exists() and wal_path.stat().st_size > 0:
                print(
                    f"[portable] warning: {db_path} is in WAL mode with un-checkpointed "
                    f"writes; read-only access still works but data may not be up to date.",
                    file=sys.stderr,
                )
        except OSError:
            logger.warning("failed to inspect WAL for %s", db_path, exc_info=True)
        conn.close()
    except (sqlite3.Error, OSError) as exc:
        raise ValueError(f"failed to open source database {db_path} read-only: {exc}") from exc

    return Memory(
        namespace=namespace,
        backend="sqlite",
        backend_config={"db_path": db_path},
    )


def pack(
    source: SourceInfo | str,
    out: Path | str | None = None,
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> PackSummary:
    """Pack the memory of a given namespace into a .hmpkg file.

    Args:
        source: A SourceInfo object or a 'host:name' format string.
        out: Output file path. If not given, writes to
            ~/.octop-memory/portable/<ns>-<yyyymmdd-HHMM>.hmpkg.
        progress: Progress callback (done, total, phase).

    Returns:
        A PackSummary object.

    Raises:
        ValueError: The source is empty (0 raw_events) or the source db cannot be opened.
    """
    src = _resolve_source(source)

    # Verify the source is not empty
    if src.raw_event_count == 0:
        # Recount (SourceInfo may have been constructed manually)
        from octop_memory.operations.migration.portable.sources import _count_table

        uri = f"file:{src.db_path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            count = _count_table(conn, f"{src.namespace}_raw_events")
            conn.close()
        except sqlite3.Error:
            logger.warning("failed to recount raw events for %s", src.namespace, exc_info=True)
            count = 0

        if count == 0:
            raise ValueError(f"nothing to migrate: namespace {src.namespace!r} has no raw_events data.")

    # Determine the output path
    packed_at = datetime.now(UTC)
    ts = packed_at.strftime("%Y%m%d-%H%M")

    if out is None:
        out_dir = _DEFAULT_OUT_DIR.expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{src.namespace}-{ts}.hmpkg"
    else:
        out_path = Path(out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    if progress:
        progress(0, -1, "opening")

    # Open Memory (after read-only verification, open normally to use the export API)
    memory = _open_memory_ro(src.db_path, src.namespace)

    # First export to an in-memory gzip JSONL
    if progress:
        progress(0, -1, "exporting")

    tmp_jsonl_gz = out_path.with_suffix(".tmp.jsonl.gz")
    try:
        export_summary = export_namespace(
            memory,
            tmp_jsonl_gz,
            gzip_compress=True,
        )

        if progress:
            progress(export_summary.total_rows, export_summary.total_rows, "packing")

        # Build the manifest
        manifest: dict[str, Any] = {
            "pkg_version": PKG_VERSION,
            "export_version": EXPORT_VERSION,
            "source_host_kind": src.host_kind,
            "source_namespace": src.namespace,
            "source_db_path": src.db_path,
            "agent_name": src.agent_name,
            "packed_at": packed_at.isoformat(),
            "tool_version": _TOOL_VERSION,
            "schema_version": src.schema_version,
            "row_counts": export_summary.counts,
            "total_rows": export_summary.total_rows,
        }

        # Assemble the .hmpkg (zip container)
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write manifest.json
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            # Write data.jsonl.gz
            zf.write(tmp_jsonl_gz, "data.jsonl.gz")

    finally:
        # Clean up the temp file
        if tmp_jsonl_gz.exists():
            tmp_jsonl_gz.unlink()

    file_size = out_path.stat().st_size

    if progress:
        progress(export_summary.total_rows, export_summary.total_rows, "done")

    return PackSummary(
        source_namespace=src.namespace,
        out_path=str(out_path),
        total_rows=export_summary.total_rows,
        file_size_bytes=file_size,
        row_counts=export_summary.counts,
        packed_at=packed_at,
        tool_version=_TOOL_VERSION,
        schema_version=src.schema_version,
        pkg_version=PKG_VERSION,
    )


def read_manifest(pkg_path: Path | str) -> dict[str, Any]:
    """Read manifest.json from a .hmpkg file without unpacking the data section."""
    path = Path(pkg_path).expanduser()
    with zipfile.ZipFile(path, "r") as zf, zf.open("manifest.json") as f:
        return dict(json.loads(f.read().decode("utf-8")))


def extract_data_stream(pkg_path: Path | str) -> io.IOBase:
    """Extract the decompressed stream of data.jsonl.gz from a .hmpkg file.

    Returns a readable text stream (gzip already decompressed).
    The caller is responsible for closing it.
    """
    path = Path(pkg_path).expanduser()
    zf = zipfile.ZipFile(path, "r")
    gz_bytes = zf.read("data.jsonl.gz")
    zf.close()
    return gzip.open(io.BytesIO(gz_bytes), "rt", encoding="utf-8")


__all__ = ["extract_data_stream", "pack", "read_manifest"]
