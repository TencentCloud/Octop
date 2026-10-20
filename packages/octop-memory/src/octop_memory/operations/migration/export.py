"""``memory export`` — stream a namespace to JSONL (5.1, D50-C).

Output layout (one JSON object per line)::

    {"v":1,"table":"__header__","data":{...}}
    {"v":1,"table":"raw_events","data":{...}}
    {"v":1,"table":"raw_events","data":{...}}
    ...
    {"v":1,"table":"atoms","data":{...}}
    {"v":1,"table":"__footer__","data":{"counts":{...}}}

The exporter is **streaming** — large dumps don't load everything into
memory, so dogfood-scale namespaces (10k+ raw events) export without
issue. Datetimes serialise as ISO-8601 strings; everything else uses
``dataclasses.asdict``.

D50-C: gzip is opt-in via ``--gzip`` (or ``--out foo.jsonl.gz`` shorthand
detected by suffix); plain JSONL is the default for grep / debug
friendliness.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO, TypeGuard

from octop_memory.core import Memory
from octop_memory.operations.migration import EXPORT_TABLES, EXPORT_VERSION

if TYPE_CHECKING:
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

# Tool version is purely informational on the wire — bump-able without
# breaking compatibility (the ``EXPORT_VERSION`` integer is the
# breaking-change channel).
_TOOL_VERSION = "octop_memory.operations.migration/1"


@dataclass
class ExportSummary:
    """Result of one :func:`export_namespace` call.

    ``counts`` maps table → row count exported. Useful for the CLI
    summary line and for the import-side integrity check.
    """

    namespace: str
    out_path: Path
    counts: dict[str, int]
    tool_version: str = _TOOL_VERSION
    started_at: datetime = dataclasses.field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @property
    def total_rows(self) -> int:
        return sum(self.counts.values())


# ---------------------------------------------------------------------------
# Stream-iterator over each table
# ---------------------------------------------------------------------------


def _iter_table_rows(memory: Memory, table: str) -> Iterator[dict[str, Any]]:
    """Yield serialisable dicts for every row of ``table``.

    Uses ``Memory`` API surface only (no raw SQL) so this remains
    backend-agnostic. Tables not relevant to a given backend simply
    yield zero rows rather than raising.
    """
    if table == "raw_events":
        for raw_event in memory.list_raw(limit=10**9):
            yield _coerce(dataclasses.asdict(raw_event))
        return

    if table == "candidates":
        # Avoid reusing `row` across branches — mypy strict infers the
        # first loop variable type and rejects later reassignments.
        for cand in memory.list_candidates(limit=10**9):
            yield _coerce(dataclasses.asdict(cand))
        return

    if table == "atoms":
        for atom in memory.list_atoms(include_deprecated=True, limit=10**9):
            yield _coerce(dataclasses.asdict(atom))
        return

    if table == "entities":
        for entity_row in memory.list_entities(limit=10**9):
            yield _coerce(dataclasses.asdict(entity_row))
        return

    if table == "aliases":
        for alias_row in memory.list_aliases(limit=10**9):
            yield _coerce(dataclasses.asdict(alias_row))
        return

    if table == "entity_pages":
        # Iterate via list_entities → get_entity_page (no list_pages API
        # because pages are entity-keyed; iterating entities is the
        # canonical traversal).
        for entity in memory.list_entities(limit=10**9):
            page = memory.get_entity_page(entity.id)
            if page is not None:
                yield _coerce(dataclasses.asdict(page))
        return

    if table == "thread_active_entities":
        # No global "list all threads" API — we iterate via the
        # backend's underlying SQL (one tiny SELECT). Falls back to
        # zero rows if the backend doesn't expose it.
        for row in _iter_active_entities(memory):
            yield _coerce(dataclasses.asdict(row))
        return

    if table == "journal":
        # Use a distinct loop variable to avoid mypy [assignment] error:
        # strict mode infers `row` as RawEvent from the first for-loop above
        # and rejects JournalEntry being re-assigned to the same name.
        for journal_entry in memory.list_journal(limit=10**9):
            yield _coerce(dataclasses.asdict(journal_entry))
        return

    raise ValueError(f"unknown export table: {table!r}")


def _iter_active_entities(memory: Memory) -> Iterator[Any]:
    """Read every thread's active entities.

    Read-through helper for ``thread_active_entities``: the public API is
    per-thread, so there is no "list every thread" call to stream from.

    Dispatches on backend *type* rather than duck-typing ``_conn`` / ``_ns``.
    ``PostgresMemoryBackend`` exposes both, so the SQLite statement used to
    reach the psycopg connection, raise ``UndefinedTable``, and — because the
    error was swallowed without a rollback — leave the connection aborted, so
    every later write in the process failed with ``InFailedSqlTransaction``.
    That also made the dump silently lose this table on Postgres.
    """
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
    from octop_memory.types import ActiveEntity

    backend = memory._backend
    rows: list[Any]
    if isinstance(backend, SqliteMemoryBackend):
        with backend._conn_lock:
            rows = backend._conn.execute(
                f"""SELECT thread_id, entity_id, last_seen_at, source
                    FROM {backend._ns}_thread_active_entities
                    ORDER BY thread_id, last_seen_at DESC"""
            ).fetchall()
    elif _is_postgres_backend(backend):
        with backend._cursor() as cur:
            cur.execute(
                """SELECT thread_id, entity_id, last_seen_at, source
                   FROM thread_active_entities
                   WHERE namespace = %s
                   ORDER BY thread_id, last_seen_at DESC""",
                (backend._ns,),
            )
            rows = cur.fetchall()
    else:
        return

    for row in rows:
        yield ActiveEntity(
            thread_id=str(row["thread_id"]),
            entity_id=str(row["entity_id"]),
            last_seen_at=_as_datetime(row["last_seen_at"]),
            source=str(row["source"] or "recall_hit"),  # type: ignore[arg-type]
        )


def _is_postgres_backend(backend: Any) -> TypeGuard[PostgresMemoryBackend]:
    """True for ``PostgresMemoryBackend``. False when the extra isn't installed."""
    try:
        from octop_memory.storage.backends.postgres import PostgresMemoryBackend as _Pg
    except ImportError:
        return False
    return isinstance(backend, _Pg)


def _as_datetime(value: Any) -> datetime:
    """SQLite stores ``last_seen_at`` as ISO text; Postgres returns a datetime."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


# ---------------------------------------------------------------------------
# Coercion: datetime / Path / etc. → JSON-safe primitives
# ---------------------------------------------------------------------------


def _coerce(obj: Any) -> Any:
    """Recursively convert ``obj`` so :func:`json.dumps` accepts it.

    Handles: ``datetime`` → ISO string; ``Path`` → str; plain dict /
    list / tuple / scalar pass through.
    """
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _coerce(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_coerce(v) for v in obj]
    # Fallback: stringify so we don't lose data; importer can ignore
    # unexpected fields.
    return str(obj)


# ---------------------------------------------------------------------------
# Output stream helpers
# ---------------------------------------------------------------------------


@contextmanager
def _open_output(path: Path, *, gzip_compress: bool) -> Iterator[TextIO]:
    """Open ``path`` for text-mode write. Auto-detects ``.gz`` suffix."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if gzip_compress or path.suffix == ".gz":
        # gzip.open in 'wt' returns a TextIOWrapper-compatible stream.
        with gzip.open(path, "wt", encoding="utf-8") as fp:
            yield fp
    else:
        with path.open("w", encoding="utf-8") as fp:
            yield fp


def _write_record(fp: TextIO, table: str, data: Any) -> None:
    fp.write(json.dumps({"v": EXPORT_VERSION, "table": table, "data": data}, ensure_ascii=False))
    fp.write("\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_namespace(
    memory: Memory,
    out_path: str | Path,
    *,
    gzip_compress: bool = False,
    tables: tuple[str, ...] = EXPORT_TABLES,
) -> ExportSummary:
    """Stream ``memory`` to a JSONL file.

    Args:
        memory: backing :class:`Memory` instance.
        out_path: destination file path. ``.gz`` suffix triggers gzip
            automatically regardless of ``gzip_compress``.
        gzip_compress: force gzip even if the suffix isn't ``.gz``.
        tables: subset to export. Defaults to :data:`EXPORT_TABLES`.

    Returns an :class:`ExportSummary`. Raises ``ValueError`` if any
    table name is unknown — strict so typos in ``--tables`` don't
    silently produce empty dumps.
    """
    out = Path(out_path).expanduser()
    summary = ExportSummary(namespace=memory.namespace, out_path=out, counts={t: 0 for t in tables})

    with _open_output(out, gzip_compress=gzip_compress) as fp:
        # Header first so partial writes are still self-identifying.
        _write_record(
            fp,
            "__header__",
            {
                "version": EXPORT_VERSION,
                "tool_version": _TOOL_VERSION,
                "namespace": memory.namespace,
                "created_at": summary.started_at.isoformat(),
                "tables": list(tables),
            },
        )

        for table in tables:
            for row in _iter_table_rows(memory, table):
                _write_record(fp, table, row)
                summary.counts[table] += 1

        summary.finished_at = datetime.now(UTC)
        _write_record(
            fp,
            "__footer__",
            {
                "finished_at": summary.finished_at.isoformat(),
                "counts": summary.counts,
                "total_rows": summary.total_rows,
            },
        )

    return summary


__all__ = ["ExportSummary", "export_namespace"]
