"""Memory ↔ document bridge — the ``kb`` recall source (references only).

Facts and experience live in ``octop_memory``; documents live in a knowledge base
(one disk ``index.sqlite`` per KB, independent of the memory store). The bridge
keeps **only a reference** — ``project_artifacts.kb_document_id``, an existing
column, no new table and no new column — and fetches the document body **at recall
time** through the KB's own public read surface.

Hard rule (PLAN 「记忆文档桥」): **never write document text into memory**. If the
body were copied in, the same content would exist three times (original + KB chunk
+ memory atom). This module therefore has no ``Memory`` handle at all and no write
call of any kind: :class:`KbReference` carries ids and metadata only, and
:meth:`KbRecallSource.gather` returns a bounded snippet for the current turn.

The source sits **beside** the existing ``atom`` / ``raw`` / ``page_headline`` /
``vector`` / ``episode`` sources: it produces the same
:class:`~octop.infra.agents.memory.multi_ns.RecallHit` rows, with ``layer="kb"``
and ``source_layer="project"`` (a project's KB documents belong to the project
layer). Merging reuses ``multi_ns``' discipline — the same
:func:`multi_ns.normalize_memory_text` content key and the same rank key — so the
codebase keeps **one** dedup rule and **one** ordering rule.

The KB stays as it is: every call goes through the public
``KnowledgeService.preview_document`` (read-only) and no KB file is touched here.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from octop.infra.agents.memory.multi_ns import (
    MemoryLayer,
    MultiNsRecall,
    RecallHit,
    normalize_memory_text,
)

# The one ordering rule for merged recall hits lives in ``multi_ns`` (layer
# priority is part of the key). It is imported rather than re-implemented: a
# second copy of the rank rule is exactly the drift this codebase keeps paying
# for. Promoting it to a public name belongs to whoever next touches that file —
# this task is not allowed to edit it.
from octop.infra.agents.memory.multi_ns import _rank_key as _hit_rank_key

if TYPE_CHECKING:
    from octop_memory.pipeline.recall.timeout import Stopwatch

logger = logging.getLogger(__name__)

KB_LAYER = "kb"
"""The source name, beside ``atom`` / ``raw`` / ``page_headline`` / ``vector``."""

KB_SOURCE_LAYER: MemoryLayer = "project"
"""A KB document is reached through ``project_artifacts`` ⇒ it is a project-layer hit."""

DEFAULT_SNIPPET_CHARS = 280
"""How much of a document is returned per hit; the body itself never leaves the KB."""

_EPOCH = datetime.fromtimestamp(0, UTC)
"""Timestamp for a reference with no ``created_at``: documents are stable assets,
so they must not outrank a memory that was just written."""

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class KbReference:
    """A pointer to a KB document — **the only thing the memory side stores**.

    ``document_id`` is ``project_artifacts.kb_document_id``; ``kb_id`` is the
    project's KB (``projects.kb_id``). There is deliberately no body field: the
    reference is what may be persisted next to a memory, never the text.
    """

    kb_id: str
    document_id: str
    project_id: str | None = None
    artifact_id: str | None = None
    name: str | None = None
    created_at: datetime | None = None

    @property
    def source_id(self) -> str:
        """Stable recall id, unique across KBs and documents."""
        return f"{KB_LAYER}:{self.kb_id}:{self.document_id}"

    @classmethod
    def from_artifact_row(
        cls,
        row: Mapping[str, Any] | object,
        *,
        kb_id: str,
        created_at: datetime | None = None,
    ) -> KbReference | None:
        """Build a reference from a ``project_artifacts`` row (duck-typed).

        Returns ``None`` when the row carries no ``kb_document_id`` — an artifact
        that was never archived into the project KB has nothing to recall. The
        repo layer is not imported: the caller passes the row it already holds.
        """
        document_id = _row_value(row, "kb_document_id")
        if not document_id:
            return None
        return cls(
            kb_id=str(kb_id),
            document_id=str(document_id),
            project_id=_row_str(row, "project_id"),
            artifact_id=_row_str(row, "artifact_id"),
            name=_row_str(row, "name"),
            created_at=created_at or _row_datetime(row, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class KbDocument:
    """What the KB hands back for one reference: the filename plus extracted text."""

    kb_id: str
    document_id: str
    filename: str
    text: str


class KbDocumentReader(Protocol):
    """The one KB capability this module needs (read-only, by reference)."""

    def read_document(self, *, kb_id: str, document_id: str) -> KbDocument | None: ...


class KnowledgeServiceReader:
    """Read-only adapter over the public ``KnowledgeService.preview_document``.

    Nothing in ``infra/knowledge`` changes: the adapter calls the same public
    method the dashboard preview does, with the acting user supplied by the
    caller (this module never invents one, and never widens permissions). A
    document that is missing, unreadable or not parseable yields ``None`` — the
    KB is an advisory source, not a reason to fail a recall.
    """

    def __init__(
        self,
        service: Any,
        *,
        actor_user_id: int,
        is_admin: bool = False,
    ) -> None:
        self._service = service
        self._actor_user_id = actor_user_id
        self._is_admin = is_admin

    def read_document(self, *, kb_id: str, document_id: str) -> KbDocument | None:
        try:
            payload = self._service.preview_document(
                kb_id,
                document_id,
                actor_user_id=self._actor_user_id,
                is_admin=self._is_admin,
            )
        except Exception:  # noqa: BLE001 - an advisory source must not fail a recall
            # Missing row (LookupError), missing original (OSError) or a parser
            # failure from pypdf / docx / the OCR gate: all of them mean "this
            # document contributes nothing", never "the recall fails". The HTTP
            # preview endpoint maps the same errors because there it does have a
            # request to fail.
            logger.warning(
                "kb source could not read document kb=%s doc=%s", kb_id, document_id, exc_info=True
            )
            return None
        return KbDocument(
            kb_id=kb_id,
            document_id=document_id,
            filename=str(payload.get("filename") or ""),
            text=str(payload.get("text") or ""),
        )


class KbRecallSource:
    """The ``kb`` recall source: references in, bounded snippets out.

    Per-document reads run under their own deadline, clamped to the remaining
    global slice — the same advisory-source discipline
    ``multi_source.gather_candidates`` applies to ``atom`` / ``raw`` / … inside a
    namespace, and the same one ``MultiNsRecall._gather`` applies per namespace.

    A document only becomes a hit when it matches the query: ``raw_tokens`` are
    matched against the extracted text (the KB's own parser produced it), and the
    snippet is a window around the first match. No match ⇒ no hit, so an
    unrelated archived document never pollutes recall.
    """

    def __init__(
        self,
        reader: KbDocumentReader,
        *,
        snippet_chars: int = DEFAULT_SNIPPET_CHARS,
        per_document_budget_ms: int | None = None,
        total_budget_ms: int | None = None,
    ) -> None:
        self._reader = reader
        self._snippet_chars = max(1, snippet_chars)
        self._per_document_budget_ms = per_document_budget_ms
        self._total_budget_ms = total_budget_ms

    def gather(
        self,
        query: str,
        references: Sequence[KbReference],
        *,
        limit: int = 10,
    ) -> list[RecallHit]:
        """Return one hit per query-matching referenced document, best match first.

        Raises nothing: an unreadable or timed-out document contributes zero hits
        and the remaining references still produce theirs.
        """
        from octop_memory.pipeline.recall.parser import parse_query
        from octop_memory.pipeline.recall.timeout import (
            DEFAULT_TOTAL_BUDGET_MS,
            Stopwatch,
        )

        parsed = parse_query(query)
        if not parsed.text:
            return []
        tokens = tuple(token for token in (parsed.raw_tokens or (parsed.text,)) if token.strip())
        if not tokens:
            return []

        stopwatch = Stopwatch(
            total_budget_ms=(
                self._total_budget_ms
                if self._total_budget_ms is not None
                else DEFAULT_TOTAL_BUDGET_MS
            )
        )
        scored: list[tuple[int, int, KbReference, str]] = []
        for index, reference in enumerate(references):
            if stopwatch.expired:
                break
            document = self._read(reference, stopwatch)
            if document is None or not document.text.strip():
                continue
            matches = _match_count(document.text, tokens)
            if matches == 0:
                continue
            scored.append(
                (-matches, index, reference, _snippet(document.text, tokens, self._snippet_chars))
            )

        scored.sort(key=lambda item: (item[0], item[1]))
        return [
            RecallHit(
                source_id=reference.source_id,
                text=snippet,
                source_layer=KB_SOURCE_LAYER,
                layer=KB_LAYER,
                occurred_at=reference.created_at or _EPOCH,
                importance="medium",
                confidence="medium",
                entity_id=None,
            )
            for _matches, _index, reference, snippet in scored[: max(0, limit)]
        ]

    def _read(self, reference: KbReference, stopwatch: Stopwatch) -> KbDocument | None:
        """Read one referenced document under its own deadline (advisory)."""
        from octop_memory.pipeline.recall.timeout import (
            DEFAULT_ATOM_BUDGET_MS,
            TimeoutExceededError,
            with_deadline,
        )

        slice_ms = (
            self._per_document_budget_ms
            if self._per_document_budget_ms is not None
            else DEFAULT_ATOM_BUDGET_MS
        )
        try:
            document: KbDocument | None = with_deadline(
                lambda: self._reader.read_document(
                    kb_id=reference.kb_id, document_id=reference.document_id
                ),
                stage=f"kb:{reference.document_id}",
                budget_ms=min(slice_ms, max(1, stopwatch.remaining_ms)),
            )
        except TimeoutExceededError:
            logger.warning("kb recall timed out document=%s", reference.document_id)
            return None
        except Exception:  # noqa: BLE001 - same advisory contract as the reader
            logger.warning("kb recall failed document=%s", reference.document_id, exc_info=True)
            return None
        stopwatch.split(f"kb:{reference.document_id}")
        return document


def merge_recall_hits(*groups: Iterable[RecallHit]) -> list[RecallHit]:
    """Merge hit groups under the one dedup rule and the one rank key.

    Groups are consumed in order and the first occurrence of a memory wins — so
    the memory layers are passed before the ``kb`` source, and a document snippet
    that repeats a memory already recalled is dropped rather than shown twice.
    Dedup keys on both the id and the normalized text, exactly as
    :meth:`MultiNsRecall.recall` does: the same fact stored as an atom and as a
    document is two ids, so the id key alone would not catch it.
    """
    merged: list[RecallHit] = []
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    for group in groups:
        for hit in group:
            text_key = normalize_memory_text(hit.text)
            if hit.source_id in seen_ids:
                continue
            if text_key and text_key in seen_texts:
                continue
            seen_ids.add(hit.source_id)
            if text_key:
                seen_texts.add(text_key)
            merged.append(hit)
    return sorted(merged, key=_hit_rank_key)


class KbRecallBridge:
    """Recall a project's memory layers **plus** the KB documents they reference.

    One call site for the bridge: the cross-namespace merge layer
    (:class:`MultiNsRecall`) runs unchanged, the ``kb`` source adds the project's
    referenced documents, and :func:`merge_recall_hits` produces the final order.
    Without project context there are no references to resolve, so nothing is
    guessed and nothing is opened.
    """

    def __init__(self, recall: MultiNsRecall, kb: KbRecallSource) -> None:
        self._recall = recall
        self._kb = kb

    def recall(
        self,
        query: str,
        *,
        project_id: str | None = None,
        project_namespace: str | None = None,
        references: Sequence[KbReference] = (),
        limit: int = 10,
    ) -> list[RecallHit]:
        """Return the merged, deduped, ranked hits for ``query``."""
        memory_hits = self._recall.recall(
            query, project_id=project_id, project_namespace=project_namespace
        )
        kb_hits: list[RecallHit] = []
        if project_id is not None and references:
            kb_hits = self._kb.gather(query, references, limit=limit)
        return merge_recall_hits(memory_hits, kb_hits)


def _fold(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _match_count(text: str, tokens: Sequence[str]) -> int:
    """How many distinct query tokens appear in the document text."""
    folded = text.casefold()
    return sum(1 for token in tokens if token.casefold() in folded)


def _snippet(text: str, tokens: Sequence[str], max_chars: int) -> str:
    """A bounded window around the first token hit (whole text if it already fits)."""
    folded = _fold(text)
    if len(folded) <= max_chars:
        return folded
    lowered = folded.casefold()
    positions = [lowered.find(token.casefold()) for token in tokens]
    found = [position for position in positions if position >= 0]
    anchor = min(found) if found else 0
    start = max(0, anchor - max_chars // 3)
    end = min(len(folded), start + max_chars)
    start = max(0, end - max_chars)
    snippet = folded[start:end].strip()
    return f"…{snippet}…" if start > 0 or end < len(folded) else snippet


def _row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _row_str(row: Mapping[str, Any] | object, key: str) -> str | None:
    value = _row_value(row, key)
    return None if value is None else str(value)


def _row_datetime(row: Mapping[str, Any] | object, key: str) -> datetime | None:
    value = _row_value(row, key)
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, UTC)
    return None


__all__ = [
    "DEFAULT_SNIPPET_CHARS",
    "KB_LAYER",
    "KB_SOURCE_LAYER",
    "KbDocument",
    "KbDocumentReader",
    "KbRecallBridge",
    "KbRecallSource",
    "KbReference",
    "KnowledgeServiceReader",
    "merge_recall_hits",
]
