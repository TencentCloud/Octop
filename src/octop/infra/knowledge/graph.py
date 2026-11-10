"""Build a knowledge base's entity graph and use it at retrieval time.

A graph is opt-in per knowledge base: it exists once its owner builds it,
and from then on newly indexed documents are added to it. Building needs
the instance-wide extraction model (see :mod:`graph_extract`); reading an
existing graph does not.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from octop.infra.knowledge.graph_extract import GraphExtractor, get_graph_capability
from octop.infra.knowledge.graph_store import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_READY,
    ChunkGraph,
    GraphRelation,
    KnowledgeGraphStore,
    PgKnowledgeGraphStore,
    SqliteKnowledgeGraphStore,
    entity_key,
)
from octop.infra.knowledge.plane import open_knowledge_index, postgres_database

logger = logging.getLogger(__name__)

# One document at a time; its chunks are extracted by a few parallel model calls.
GRAPH_CONCURRENCY = 1
_CHUNK_WORKERS = 4
_graph_semaphore: asyncio.Semaphore | None = None

_MAX_SEEDS = 8
_MAX_NEIGHBORS = 20
MAX_FACTS = 8
_MAX_ENTITY_RELATIONS = 50
_MAX_ENTITY_PASSAGES = 10
_MAX_PASSAGE_CHARS = 600
_ASCII_WORD_RE = re.compile(r"[a-z0-9_]")

ChunkExtractor = Callable[..., ChunkGraph]


def reset_graph_semaphore_for_tests() -> None:
    global _graph_semaphore
    _graph_semaphore = None


def _get_graph_semaphore() -> asyncio.Semaphore:
    global _graph_semaphore
    if _graph_semaphore is None:
        _graph_semaphore = asyncio.Semaphore(GRAPH_CONCURRENCY)
    return _graph_semaphore


def open_knowledge_graph(services: Any, kb_id: str) -> KnowledgeGraphStore:
    """SQLite sidecar graph, or PostgreSQL tables on a PostgreSQL control plane."""
    database = postgres_database(services)
    if database is None:
        return SqliteKnowledgeGraphStore(kb_id)
    return PgKnowledgeGraphStore(kb_id, database)


def graph_enabled(services: Any) -> bool:
    return bool(get_graph_capability(services.settings_repo.get)["enabled"])


# -- building ----------------------------------------------------------------


def build_document_graph(
    services: Any,
    kb_id: str,
    doc_id: str,
    *,
    extractor: ChunkExtractor | None = None,
) -> None:
    """Extract one indexed document's chunks and replace its part of the graph."""
    store = open_knowledge_graph(services, kb_id)
    document = services.knowledge_repo.get_document(doc_id)
    if document is None or document.kb_id != kb_id or document.is_dir:
        store.delete_document(doc_id)
        return
    store.mark_document(doc_id, STATUS_PROCESSING)
    try:
        if document.status != "ready":
            raise RuntimeError("knowledge document is not indexed yet")
        chunks = open_knowledge_index(services, kb_id).list_doc_chunks(doc_id)
        extract = extractor or GraphExtractor(services)

        def run(item: tuple[int, str]) -> ChunkGraph | None:
            ordinal, text = item
            try:
                return extract(filename=document.filename, ordinal=ordinal, text=text)
            except Exception:
                logger.warning(
                    "knowledge graph extraction failed for %s chunk %s",
                    doc_id,
                    ordinal,
                    exc_info=True,
                )
                return None

        with ThreadPoolExecutor(max_workers=_CHUNK_WORKERS) as pool:
            results = list(pool.map(run, chunks))
        extracted = [result for result in results if result is not None]
        failed = len(results) - len(extracted)
        if chunks and not extracted:
            raise RuntimeError("knowledge graph extraction failed for every passage")
        note = f"{failed} of {len(results)} passages could not be extracted" if failed else ""
        store.replace_document(doc_id, extracted, error=note)
    except Exception as exc:
        store.mark_document(doc_id, STATUS_FAILED, error=str(exc))
        raise


def enqueue_document_graph(services: Any, kb_id: str, doc_id: str) -> asyncio.Task[None]:
    """Schedule one document's extraction outside the event loop."""
    loop = asyncio.get_running_loop()
    sem = _get_graph_semaphore()

    async def _run() -> None:
        async with sem:
            try:
                await loop.run_in_executor(None, build_document_graph, services, kb_id, doc_id)
            except Exception:
                logger.warning("knowledge graph build failed for %s", doc_id, exc_info=True)

    return asyncio.create_task(_run())


def mark_document_reindexed(services: Any, kb_id: str, doc_id: str) -> bool:
    """After (re)indexing: return True when the document should be extracted again.

    Knowledge bases without a graph are left alone. Otherwise the document's
    old rows are dropped, since they describe text that was just replaced,
    and it waits as pending until extraction runs (now, or on the next build
    when no extraction model is available).
    """
    store = open_knowledge_graph(services, kb_id)
    if not store.exists():
        return False
    store.mark_document(doc_id, STATUS_PENDING)
    capability = get_graph_capability(
        services.settings_repo.get, getattr(services, "provider_repo", None)
    )
    return bool(capability["usable"])


def enqueue_base_graph(services: Any, kb_id: str, doc_ids: Sequence[str]) -> int:
    """Queue extraction for *doc_ids* and forget documents that no longer exist."""
    store = open_knowledge_graph(services, kb_id)
    wanted = set(doc_ids)
    for stale in set(store.document_states()) - wanted:
        store.delete_document(stale)
    for doc_id in doc_ids:
        store.mark_document(doc_id, STATUS_PENDING)
        enqueue_document_graph(services, kb_id, doc_id)
    return len(doc_ids)


def resume_pending_graph_jobs(services: Any) -> None:
    """Re-queue extraction that a previous process left queued or half done."""
    try:
        capability = get_graph_capability(
            services.settings_repo.get, getattr(services, "provider_repo", None)
        )
        if not capability["usable"]:
            return
        for base in services.knowledge_repo.list_all():
            states = open_knowledge_graph(services, base.id).document_states()
            for doc_id, state in states.items():
                if state.status in (STATUS_PENDING, STATUS_PROCESSING):
                    enqueue_document_graph(services, base.id, doc_id)
    except Exception:
        # The graph is optional; trouble reading it must not stop the server from starting.
        logger.warning("could not resume knowledge graph jobs", exc_info=True)


# -- retrieval ---------------------------------------------------------------


@dataclass(frozen=True)
class GraphExpansion:
    """What the graph adds to one query against one knowledge base."""

    facts: tuple[str, ...] = ()
    chunks: tuple[tuple[str, int], ...] = ()


def _mentions(query: str, key: str) -> bool:
    """True when *key* occurs in *query* and is not just part of a longer ASCII word."""
    start = query.find(key)
    while start >= 0:
        end = start + len(key)
        before = query[start - 1] if start else ""
        after = query[end] if end < len(query) else ""
        inside_word = (_ASCII_WORD_RE.match(key[0]) and _ASCII_WORD_RE.match(before or " ")) or (
            _ASCII_WORD_RE.match(key[-1]) and _ASCII_WORD_RE.match(after or " ")
        )
        if not inside_word:
            return True
        start = query.find(key, start + 1)
    return False


def expand_query(
    store: KnowledgeGraphStore, query: str, *, max_facts: int = MAX_FACTS
) -> GraphExpansion:
    """Find entities named in *query* and collect their relations and passages.

    Relations of the named entities come first, then relations one more hop
    away, so a question about A can still reach what is said about B when the
    documents only connect them through a shared entity.
    Passages are only taken one hop out: a relation costs a line of context,
    while a passage displaces a vector hit, and two hops away is often off topic.
    """
    folded = " ".join(query.split()).casefold()
    seeds = [key for key in store.match_keys(folded) if _mentions(folded, key)]
    if not seeds:
        return GraphExpansion()
    seeds = sorted(seeds, key=lambda key: (-len(key), key))[:_MAX_SEEDS]
    direct = store.relations_of(seeds)
    neighbors: dict[str, None] = {}
    for relation in direct:
        for end in (relation.source, relation.target):
            if end not in seeds:
                neighbors.setdefault(end)
    near = list(neighbors)[:_MAX_NEIGHBORS]
    known = {(item.source, item.target, item.label) for item in direct}
    indirect = [
        relation
        for relation in (store.relations_of(near) if near else [])
        if (relation.source, relation.target, relation.label) not in known
    ]
    # Each list is already sorted by weight.
    stated: list[GraphRelation] = [*direct, *indirect][:max_facts]
    names = store.entities([end for item in stated for end in (item.source, item.target)])
    facts: list[str] = []
    for item in stated:
        source = names[item.source].name if item.source in names else item.source
        target = names[item.target].name if item.target in names else item.target
        line = f"{source} -> {item.label} -> {target}"
        facts.append(f"{line}: {item.description}" if item.description else line)

    chunks: dict[tuple[str, int], None] = {}
    for item in direct:
        for ref in item.chunks:
            chunks.setdefault(ref)
    for seed in seeds:
        for ref in store.entity_chunks(seed):
            chunks.setdefault(ref)
    return GraphExpansion(facts=tuple(facts), chunks=tuple(chunks))


# -- views -------------------------------------------------------------------


def graph_stats(store: KnowledgeGraphStore, doc_ids: Sequence[str]) -> dict[str, Any]:
    """Counts for the dashboard: graph size and how many documents are in it."""
    states = store.document_states()
    entities, relations = store.counts()
    tally = {STATUS_PENDING: 0, STATUS_PROCESSING: 0, STATUS_READY: 0, STATUS_FAILED: 0}
    partial = 0
    for doc_id in doc_ids:
        state = states.get(doc_id)
        if state is None:
            continue
        tally[state.status] = tally.get(state.status, 0) + 1
        if state.status == STATUS_READY and state.error:
            partial += 1
    return {
        "built": bool(states),
        "entities": entities,
        "relations": relations,
        "documents_total": len(doc_ids),
        "documents_ready": tally[STATUS_READY],
        "documents_partial": partial,
        "documents_pending": tally[STATUS_PENDING] + tally[STATUS_PROCESSING],
        "documents_failed": tally[STATUS_FAILED],
    }


def graph_view(store: KnowledgeGraphStore, *, limit: int, search: str = "") -> dict[str, Any]:
    """The most-mentioned entities and the relations between them."""
    keys = store.top_entity_keys(limit, search=search)
    entities = store.entities(keys)
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for relation in store.relations_among(keys):
        # One drawn edge per pair, whichever way the relations point.
        pair = (relation.source, relation.target)
        edge = edges.get(pair) or edges.get((pair[1], pair[0]))
        if edge is None:
            edges[pair] = {
                "source": relation.source,
                "target": relation.target,
                "labels": [relation.label],
                "weight": relation.weight,
            }
            continue
        edge["weight"] += relation.weight
        if relation.label not in edge["labels"] and len(edge["labels"]) < 3:
            edge["labels"].append(relation.label)
    degrees: dict[str, int] = {}
    for edge in edges.values():
        for end in (edge["source"], edge["target"]):
            degrees[end] = degrees.get(end, 0) + 1
    return {
        "nodes": [
            {
                "id": key,
                "name": entities[key].name,
                "type": entities[key].type,
                "mentions": entities[key].mentions,
                "degree": degrees.get(key, 0),
            }
            for key in keys
            if key in entities
        ],
        "edges": list(edges.values()),
    }


def entity_view(services: Any, kb_id: str, name: str) -> dict[str, Any]:
    """One entity with its relations and the passages that mention it."""
    store = open_knowledge_graph(services, kb_id)
    key = entity_key(name)
    entity = store.entities([key]).get(key)
    if entity is None:
        raise LookupError("knowledge graph entity not found")
    relations = store.relations_of([key])[:_MAX_ENTITY_RELATIONS]
    others = store.entities([end for item in relations for end in (item.source, item.target)])

    def end(other: str) -> dict[str, str]:
        found = others.get(other)
        return {"id": other, "name": found.name if found else other}

    documents = {
        document.id: document
        for document in services.knowledge_repo.list_documents(kb_id)
        if document.status == "ready" and not document.is_dir
    }
    index = open_knowledge_index(services, kb_id)
    texts: dict[str, dict[int, str]] = {}
    passages: list[dict[str, Any]] = []
    for doc_id, ordinal in store.entity_chunks(key, limit=_MAX_ENTITY_PASSAGES):
        document = documents.get(doc_id)
        if document is None:
            continue
        if doc_id not in texts:
            texts[doc_id] = dict(index.list_doc_chunks(doc_id))
        text = texts[doc_id].get(ordinal)
        if text is None:
            continue
        passages.append(
            {
                "doc_id": doc_id,
                "filename": document.filename,
                "path": document.path,
                "ordinal": ordinal,
                "text": text[:_MAX_PASSAGE_CHARS],
            }
        )
    return {
        "entity": {
            "id": entity.key,
            "name": entity.name,
            "type": entity.type,
            "description": entity.description,
            "mentions": entity.mentions,
        },
        "relations": [
            {
                "source": end(item.source),
                "target": end(item.target),
                "label": item.label,
                "description": item.description,
                "weight": item.weight,
            }
            for item in relations
        ],
        "passages": passages,
    }
