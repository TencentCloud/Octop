"""Retrieve readable knowledge-base chunks for one chat turn."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from octop.i18n import tr
from octop.infra.knowledge.citations import append_citations_marker, citations_from_ranked
from octop.infra.knowledge.embed import embed_knowledge_texts
from octop.infra.knowledge.gate import assert_knowledge_usable
from octop.infra.knowledge.graph import (
    MAX_FACTS,
    GraphExpansion,
    expand_query,
    graph_enabled,
    open_knowledge_graph,
)
from octop.infra.knowledge.index import Hit
from octop.infra.knowledge.plane import open_knowledge_index
from octop.infra.knowledge.rerank import candidate_count, get_rerank_capability, rerank_scores

DEFAULT_RETRIEVAL_K = 8
DEFAULT_CONTEXT_CHAR_BUDGET = 6000
# Share of the returned passages, and of the character budget, the graph may claim.
_GRAPH_PASSAGE_DIVISOR = 4
_GRAPH_FACT_BUDGET_DIVISOR = 5

logger = logging.getLogger(__name__)


async def retrieve_context(
    services: Any,
    *,
    user_id: int,
    is_admin: bool,
    query: str | None,
    knowledge_base_ids: Sequence[str],
    k: int = DEFAULT_RETRIEVAL_K,
    char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET,
    locale: str = "en",
    visible_bases: Sequence[Any] | None = None,
) -> str:
    """Return formatted readable context, skipping unavailable or failed retrieval."""
    if not (query or "").strip() or not knowledge_base_ids or k <= 0 or char_budget <= 0:
        return ""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None,
            lambda: _retrieve_context_sync(
                services,
                user_id=user_id,
                is_admin=is_admin,
                query=query,
                knowledge_base_ids=knowledge_base_ids,
                k=k,
                char_budget=char_budget,
                locale=locale,
                visible_bases=visible_bases,
            ),
        )
    except Exception:
        logger.warning("knowledge retrieval skipped for user=%s", user_id, exc_info=True)
        return ""


def _retrieve_context_sync(
    services: Any,
    *,
    user_id: int,
    is_admin: bool,
    query: str | None,
    knowledge_base_ids: Sequence[str],
    k: int,
    char_budget: int,
    locale: str,
    visible_bases: Sequence[Any] | None,
) -> str:
    assert_knowledge_usable(services.settings_repo.get, getattr(services, "provider_repo", None))
    query_vectors = embed_knowledge_texts(services, [(query or "").strip()])
    if not query_vectors:
        return ""

    visible = visible_bases
    if visible is None:
        visible = (
            services.knowledge_repo.list_all()
            if is_admin
            else services.knowledge_repo.list_visible(user_id)
        )
    visible_by_id = {base.id: base for base in visible}
    selected_ids = _unique_ids(knowledge_base_ids)
    rerank = get_rerank_capability(
        services.settings_repo.get, getattr(services, "provider_repo", None)
    )["usable"]
    # A reranker needs more than ``k`` candidates to be worth asking.
    fetch_k = candidate_count(k) if rerank else k

    use_graph = graph_enabled(services)
    ranked: list[tuple[Any, Hit, Any]] = []
    facts: list[str] = []
    related: list[tuple[Any, Any, int]] = []
    for kb_id in selected_ids:
        base = visible_by_id.get(kb_id)
        if base is None:
            continue
        ready_documents = {
            document.id: document
            for document in services.knowledge_repo.list_documents(kb_id)
            if document.status == "ready" and not document.is_dir
        }
        for hit in open_knowledge_index(services, kb_id).search(query_vectors[0], k=fetch_k):
            document = ready_documents.get(hit.doc_id)
            if document is not None:
                ranked.append((base, hit, document))
        if use_graph:
            expansion = _expand(services, kb_id, query or "")
            facts.extend(expansion.facts)
            related.extend(
                (base, ready_documents[doc_id], ordinal)
                for doc_id, ordinal in expansion.chunks
                if doc_id in ready_documents
            )

    ranked.sort(key=lambda item: item[1].score, reverse=True)
    if rerank:
        ranked = _rerank(services, (query or "").strip(), ranked[:fetch_k])
    top = _with_graph_passages(services, ranked[:k], related, k=k)
    return _format_context(top, char_budget=char_budget, locale=locale, facts=facts[:MAX_FACTS])


def _expand(services: Any, kb_id: str, query: str) -> GraphExpansion:
    """Graph lookups are an addition; a failure leaves plain vector retrieval."""
    try:
        return expand_query(open_knowledge_graph(services, kb_id), query)
    except Exception:
        logger.warning("knowledge graph lookup skipped for %s", kb_id, exc_info=True)
        return GraphExpansion()


def _with_graph_passages(
    services: Any,
    top: list[tuple[Any, Hit, Any]],
    related: Sequence[tuple[Any, Any, int]],
    *,
    k: int,
) -> list[tuple[Any, Hit, Any]]:
    """Give the last few slots to graph-linked passages the vector search missed.

    These passages are connected to the question through an entity rather
    than by wording, so they would never win on similarity; they take at
    most a quarter of the result instead of competing on score.
    """
    slots = k // _GRAPH_PASSAGE_DIVISOR
    if slots <= 0 or not related:
        return top
    present = {hit.chunk_id for _, hit, _ in top}
    texts: dict[str, dict[int, str]] = {}
    extra: list[tuple[Any, Hit, Any]] = []
    for base, document, ordinal in related:
        chunk_id = f"{document.id}:{ordinal}"
        if chunk_id in present:
            continue
        if document.id not in texts:
            texts[document.id] = dict(
                open_knowledge_index(services, base.id).list_doc_chunks(document.id)
            )
        text = texts[document.id].get(ordinal)
        if text is None:
            continue
        present.add(chunk_id)
        extra.append((base, Hit(chunk_id, document.id, ordinal, text, 0.0, {}), document))
        if len(extra) == slots:
            break
    return top[: max(k - len(extra), 0)] + extra


def _rerank(
    services: Any, query: str, ranked: list[tuple[Any, Hit, Any]]
) -> list[tuple[Any, Hit, Any]]:
    """Reorder candidates by reranker relevance; keep the vector order if it fails."""
    try:
        scores = rerank_scores(services, query, [hit.text for _, hit, _ in ranked])
    except Exception:
        logger.warning("knowledge rerank failed; using vector order", exc_info=True)
        return ranked
    if scores is None:
        return ranked
    order = sorted(range(len(ranked)), key=lambda index: scores[index], reverse=True)
    return [ranked[index] for index in order]


def _unique_ids(ids: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(kb_id).strip() for kb_id in ids if str(kb_id).strip()))


def _format_context(
    ranked: Sequence[tuple[Any, Hit, Any]],
    *,
    char_budget: int,
    locale: str,
    facts: Sequence[str] = (),
) -> str:
    sections: list[str] = []
    included: list[tuple[Any, Hit, Any]] = []
    fact_block = _format_facts(
        facts, limit=char_budget // _GRAPH_FACT_BUDGET_DIVISOR, locale=locale
    )
    remaining = char_budget - len(fact_block)
    for base, hit, document in ranked:
        citation = tr(
            "knowledge.retrieval.citation",
            locale,
            name=base.name,
            filename=document.filename,
            ordinal=hit.ordinal + 1,
        )
        if remaining <= len(citation):
            break
        text = hit.text.strip()[: remaining - len(citation)]
        if not text:
            continue
        section = f"{citation}{text}"
        sections.append(section)
        included.append((base, hit, document))
        remaining -= len(section)
    if not sections:
        return ""
    body = tr("knowledge.retrieval.preamble", locale) + "\n\n" + "\n\n".join(sections)
    return append_citations_marker(body + fact_block, citations_from_ranked(included))


def _format_facts(facts: Sequence[str], *, limit: int, locale: str) -> str:
    """Relations from the knowledge graph as a short list after the passages."""
    lines: list[str] = []
    used = 0
    for fact in dict.fromkeys(facts):
        line = f"- {fact}"
        if used + len(line) > limit:
            break
        lines.append(line)
        used += len(line) + 1
    if not lines:
        return ""
    return "\n\n" + tr("knowledge.retrieval.graph_preamble", locale) + "\n" + "\n".join(lines)
