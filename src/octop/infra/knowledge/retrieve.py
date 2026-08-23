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
from octop.infra.knowledge.index import Hit, KnowledgeIndex

DEFAULT_RETRIEVAL_K = 8
DEFAULT_CONTEXT_CHAR_BUDGET = 6000

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

    ranked: list[tuple[Any, Hit, Any]] = []
    for kb_id in selected_ids:
        base = visible_by_id.get(kb_id)
        if base is None:
            continue
        ready_documents = {
            document.id: document
            for document in services.knowledge_repo.list_documents(kb_id)
            if document.status == "ready" and not document.is_dir
        }
        for hit in KnowledgeIndex(kb_id).search(query_vectors[0], k=k):
            document = ready_documents.get(hit.doc_id)
            if document is not None:
                ranked.append((base, hit, document))

    ranked.sort(key=lambda item: item[1].score, reverse=True)
    return _format_context(ranked[:k], char_budget=char_budget, locale=locale)


def _unique_ids(ids: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(kb_id).strip() for kb_id in ids if str(kb_id).strip()))


def _format_context(
    ranked: Sequence[tuple[Any, Hit, Any]], *, char_budget: int, locale: str
) -> str:
    sections: list[str] = []
    remaining = char_budget
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
        remaining -= len(section)
    if not sections:
        return ""
    body = tr("knowledge.retrieval.preamble", locale) + "\n\n" + "\n\n".join(sections)
    return append_citations_marker(body, citations_from_ranked(ranked))
