"""``memory import`` — replay a JSONL dump into a target namespace (5.2).

Streaming reader matched against :mod:`octop_memory.operations.migration.export`.
Robust against:

- gzipped files (``.gz`` suffix)
- mid-file partial dumps (no ``__footer__``) — we still apply what we
  saw; counts get returned regardless
- header-version mismatch — strict refuse with a clear error
- duplicate rows already present in the target — depends on
  ``on_conflict``: ``"skip"`` (default), ``"replace"``, or ``"raise"``

The importer dispatches each table to a small per-table apply function
keyed on the envelope's ``"table"`` field; this keeps the JSON shape
detached from the storage backend.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TextIO, cast

from octop_memory.core import Memory
from octop_memory.operations.migration import EXPORT_VERSION
from octop_memory.types import (
    ActiveEntity,
    Alias,
    AtomCard,
    Candidate,
    DecidedBy,
    Entity,
    EntityPage,
    JournalEntry,
    RawEvent,
)

OnConflict = Literal["skip", "replace", "raise"]


@dataclass
class ImportSummary:
    """Outcome of one :func:`import_namespace` call.

    ``applied`` counts rows successfully written; ``skipped`` counts
    rows we deliberately bypassed (e.g. ``on_conflict="skip"`` and the
    row already existed); ``errors`` is the count of rows we couldn't
    apply (typically schema mismatch — never silently swallowed,
    always surfaced).
    """

    applied: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    header: dict[str, Any] = field(default_factory=dict)
    footer: dict[str, Any] = field(default_factory=dict)

    @property
    def total_applied(self) -> int:
        return sum(self.applied.values())

    @property
    def total_skipped(self) -> int:
        return sum(self.skipped.values())


# ---------------------------------------------------------------------------
# Stream reader
# ---------------------------------------------------------------------------


@contextmanager
def _open_input(path: Path) -> Iterator[TextIO]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fp:
            yield fp
    else:
        with path.open("r", encoding="utf-8") as fp:
            yield fp


def _iter_records(fp: TextIO) -> Iterator[tuple[int, str, Any]]:
    for lineno, raw_line in enumerate(fp, 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {lineno}: invalid JSON: {exc.msg}") from exc
        if not isinstance(envelope, dict):
            raise ValueError(f"line {lineno}: expected JSON object, got {type(envelope).__name__}")
        version = envelope.get("v")
        if version != EXPORT_VERSION:
            raise ValueError(
                f"line {lineno}: incompatible export version v={version!r}; this build supports v={EXPORT_VERSION}"
            )
        table = envelope.get("table")
        if not isinstance(table, str):
            raise ValueError(f"line {lineno}: missing 'table' field")
        yield lineno, table, envelope.get("data")


# ---------------------------------------------------------------------------
# Per-row constructors
# ---------------------------------------------------------------------------


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _build_raw_event(d: dict[str, Any]) -> RawEvent:
    return RawEvent(
        id=str(d["id"]),
        host=str(d["host"]),
        session_id=d.get("session_id"),
        thread_id=d.get("thread_id"),
        user=d.get("user"),
        timestamp=_dt(d["timestamp"]),  # type: ignore[arg-type]
        event_type=str(d["event_type"]),  # type: ignore[arg-type]
        content=str(d.get("content") or ""),
        payload=dict(d.get("payload") or {}),
    )


def _build_candidate(d: dict[str, Any]) -> Candidate:
    return Candidate(
        id=str(d["id"]),
        raw_event_ids=list(d.get("raw_event_ids") or []),
        candidate_type=str(d["candidate_type"]),  # type: ignore[arg-type]
        status=str(d.get("status") or "pending"),  # type: ignore[arg-type]
        title=str(d.get("title") or ""),
        assertion=str(d.get("assertion") or ""),
        verbatim_quote=str(d.get("verbatim_quote") or ""),
        quote_event_id=str(d.get("quote_event_id") or ""),
        subject_name=str(d.get("subject_name") or ""),
        subject_entity_type=str(d.get("subject_entity_type") or "Fact"),  # type: ignore[arg-type]
        target_entity_id=d.get("target_entity_id"),
        confidence=str(d.get("confidence") or "medium"),  # type: ignore[arg-type]
        importance=str(d.get("importance") or "medium"),  # type: ignore[arg-type]
        recommended_action=str(d.get("recommended_action") or "promote"),  # type: ignore[arg-type]
        promotion_reason=str(d.get("promotion_reason") or ""),
        extractor_version=str(d.get("extractor_version") or ""),
        created_at=_dt(d["created_at"]),  # type: ignore[arg-type]
        decided_at=_dt(d.get("decided_at")),
        decided_by=d.get("decided_by"),
        session_id=d.get("session_id"),
        payload=dict(d.get("payload") or {}),
    )


def _build_atom(d: dict[str, Any]) -> AtomCard:
    return AtomCard(
        id=str(d["id"]),
        entity_id=str(d["entity_id"]),
        candidate_id=str(d["candidate_id"]),
        raw_event_ids=list(d.get("raw_event_ids") or []),
        assertion=str(d["assertion"]),
        verbatim_quote=str(d["verbatim_quote"]),
        quote_event_id=str(d["quote_event_id"]),
        search_terms=list(d.get("search_terms") or []),
        occurred_at=_dt(d["occurred_at"]),  # type: ignore[arg-type]
        confidence=str(d.get("confidence") or "medium"),  # type: ignore[arg-type]
        importance=str(d.get("importance") or "medium"),  # type: ignore[arg-type]
        created_at=_dt(d["created_at"]),  # type: ignore[arg-type]
        superseded_by=d.get("superseded_by"),
        deprecated_at=_dt(d.get("deprecated_at")),
    )


def _build_entity(d: dict[str, Any]) -> Entity:
    return Entity(
        id=str(d["id"]),
        entity_type=str(d["entity_type"]),  # type: ignore[arg-type]
        canonical_name=str(d["canonical_name"]),
        aliases=list(d.get("aliases") or []),
        atom_count=int(d.get("atom_count") or 0),
        last_promoted_at=_dt(d.get("last_promoted_at")),
        created_at=_dt(d["created_at"]),  # type: ignore[arg-type]
    )


def _build_alias(d: dict[str, Any]) -> Alias:
    raw_created_by = str(d.get("created_by") or "auto")
    created_by = cast(DecidedBy, raw_created_by if raw_created_by in {"auto", "user", "rule"} else "auto")
    return Alias(
        alias=str(d["alias"]),
        entity_id=str(d["entity_id"]),
        entity_type=str(d["entity_type"]),  # type: ignore[arg-type]
        created_by=created_by,
        created_at=_dt(d["created_at"]),  # type: ignore[arg-type]
    )


def _build_entity_page(d: dict[str, Any]) -> EntityPage:
    return EntityPage(
        id=str(d["id"]),
        entity_id=str(d["entity_id"]),
        summary_markdown=str(d.get("summary_markdown") or ""),
        headline=str(d.get("headline") or ""),
        topics=list(d.get("topics") or []),
        dirty=bool(d.get("dirty", True)),
        regen_attempt_count=int(d.get("regen_attempt_count") or 0),
        summary_version=int(d.get("summary_version") or 0),
        last_regen_at=_dt(d.get("last_regen_at")),
        last_user_edit_at=_dt(d.get("last_user_edit_at")),
        created_at=_dt(d["created_at"]),  # type: ignore[arg-type]
        updated_at=_dt(d["updated_at"]),  # type: ignore[arg-type]
    )


def _build_active_entity(d: dict[str, Any]) -> ActiveEntity:
    return ActiveEntity(
        thread_id=str(d["thread_id"]),
        entity_id=str(d["entity_id"]),
        last_seen_at=_dt(d["last_seen_at"]),  # type: ignore[arg-type]
        source=str(d.get("source") or "recall_hit"),  # type: ignore[arg-type]
    )


def _build_journal(d: dict[str, Any]) -> JournalEntry:
    return JournalEntry(
        id=str(d["id"]),
        timestamp=_dt(d["timestamp"]),  # type: ignore[arg-type]
        action=str(d["action"]),  # type: ignore[arg-type]
        actor=str(d.get("actor") or "auto"),  # type: ignore[arg-type]
        target_entity_id=d.get("target_entity_id"),
        target_atom_id=d.get("target_atom_id"),
        target_candidate_id=d.get("target_candidate_id"),
        before=d.get("before"),
        after=d.get("after"),
        note=str(d.get("note") or ""),
    )


# ---------------------------------------------------------------------------
# Per-table apply
# ---------------------------------------------------------------------------


def _apply_row(
    memory: Memory,
    table: str,
    data: Any,
    *,
    on_conflict: OnConflict,
) -> tuple[bool, bool]:
    """Return ``(applied, skipped)``. Raises on hard schema errors.

    Conflicts (PK already exists) are handled per ``on_conflict``:
    - ``"skip"`` (default): return ``(False, True)``
    - ``"replace"``: behaves the same as ``"skip"`` for tables that
      don't yet expose an upsert API; logged as skipped so the user
      sees what happened. Full upsert support lands with the M6
      Postgres pass.
    - ``"raise"``: re-raise the underlying ``IntegrityError`` so the
      caller can inspect it.
    """
    if not isinstance(data, dict):
        raise ValueError(f"{table}: data must be object, got {type(data).__name__}")

    try:
        if table == "raw_events":
            memory.add_raw_batch([_build_raw_event(data)])
            return True, False

        if table == "candidates":
            memory.add_candidate(_build_candidate(data))
            return True, False

        if table == "atoms":
            memory.add_atom(_build_atom(data))
            return True, False

        if table == "entities":
            memory.add_entity(_build_entity(data))
            return True, False

        if table == "aliases":
            memory.add_alias(_build_alias(data))
            return True, False

        if table == "entity_pages":
            # upsert-by-entity_id semantics — always replaces, so
            # on_conflict is N/A here.
            memory.upsert_entity_page(_build_entity_page(data))
            return True, False

        if table == "thread_active_entities":
            ae = _build_active_entity(data)
            memory.upsert_active_entity(
                ae.thread_id,
                ae.entity_id,
                source=ae.source,
                when=ae.last_seen_at,
                # Don't auto-evict during import — preserve dump order.
                keep=10**9,
            )
            return True, False

        if table == "journal":
            memory.append_journal(_build_journal(data))
            return True, False

        raise ValueError(f"unknown import table: {table!r}")
    except sqlite3.IntegrityError:
        if on_conflict == "raise":
            raise
        # ``skip`` and ``replace`` both surface as skipped here. Real
        # replace semantics arrive with M6's full-upsert backend pass.
        return False, True
    except KeyError as exc:
        raise ValueError(f"{table}: missing required field {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_namespace(
    memory: Memory,
    in_path: str | Path,
    *,
    on_conflict: OnConflict = "skip",
    expect_namespace: str | None = None,
) -> ImportSummary:
    """Replay a JSONL dump into ``memory``.

    Args:
        memory: target backend (already opened against the destination
            namespace).
        in_path: source file. ``.gz`` suffix triggers gzip read.
        on_conflict: behaviour when a row's PK already exists in the
            target. See :data:`OnConflict`.
        expect_namespace: if set, raise if the dump's header advertises
            a different namespace. Useful as a sanity check when the
            CLI passes the namespace explicitly.

    Header / footer envelopes are stored on the returned summary for
    diagnostics; they don't carry data on the wire.
    """
    summary = ImportSummary()
    path = Path(in_path).expanduser()

    with _open_input(path) as fp:
        for lineno, table, data in _iter_records(fp):
            if table == "__header__":
                summary.header = data or {}
                if expect_namespace and summary.header.get("namespace") != expect_namespace:
                    raise ValueError(
                        f"namespace mismatch: dump says "
                        f"{summary.header.get('namespace')!r}, expected {expect_namespace!r}"
                    )
                continue
            if table == "__footer__":
                summary.footer = data or {}
                continue

            try:
                applied, skipped = _apply_row(memory, table, data, on_conflict=on_conflict)
            except ValueError as exc:
                summary.errors.append(f"line {lineno}: {exc}")
                continue
            if applied:
                summary.applied[table] = summary.applied.get(table, 0) + 1
            if skipped:
                summary.skipped[table] = summary.skipped.get(table, 0) + 1

    return summary


__all__ = ["ImportSummary", "OnConflict", "import_namespace"]
