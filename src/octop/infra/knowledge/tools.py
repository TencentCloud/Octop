"""Built-in LangChain tool for on-demand knowledge-base retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from langchain_core.tools import StructuredTool
from langgraph.config import get_config
from pydantic import Field

from octop.infra.knowledge.retrieve import DEFAULT_RETRIEVAL_K, retrieve_context

SEARCH_KNOWLEDGE_TOOL = "search_knowledge"

# API allows 2000-char KB descriptions; keep the tool schema compact.
_MAX_CATALOG_DESC_CHARS = 240

_SEARCH_DESC_BASE = (
    "Search the knowledge bases listed below for relevant passages. "
    "Use this tool when the user's question overlaps any of those topics. "
    "Write `query` as a focused search string (key terms, names, synonyms), "
    "not a chat reply. Do not invent citations; only use returned passages."
)

_SEARCH_DESC_NONE = "No knowledge bases are attached this turn."


def _clip_catalog_text(text: str, limit: int = _MAX_CATALOG_DESC_CHARS) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3].rstrip() + "..."


def format_search_knowledge_description(
    catalog: Sequence[Mapping[str, str]] | None,
) -> str:
    """Build the LLM-facing tool description, including attached KB titles/descriptions."""
    entries: list[str] = []
    for item in catalog or ():
        name = _clip_catalog_text(str(item.get("name") or item.get("id") or ""), 80)
        if not name:
            continue
        description = _clip_catalog_text(str(item.get("description") or ""))
        if description:
            entries.append(f"- {name}: {description}")
        else:
            entries.append(f"- {name}")
    if not entries:
        return _SEARCH_DESC_NONE
    listed = "\n".join(entries)
    return f"{_SEARCH_DESC_BASE}\nAttached this turn:\n{listed}"


def _tool_ctx() -> tuple[int, bool, list[str], str]:
    cfg = get_config().get("configurable") or {}
    user_raw = cfg.get("user")
    if user_raw is None:
        raise ValueError("missing configurable.user")
    user_id = int(user_raw)
    is_admin = bool(cfg.get("user_is_admin"))
    raw_ids = cfg.get("knowledge_base_ids")
    ids: list[str] = []
    if isinstance(raw_ids, list):
        ids = [str(item).strip() for item in raw_ids if str(item).strip()]
    locale = str(cfg.get("locale") or "en")
    return user_id, is_admin, ids, locale


def build_knowledge_tools(services: Any) -> list[StructuredTool]:
    """Return built-in knowledge retrieval tools (wired via HarnessAgentConfig.tools)."""

    async def search_knowledge(
        query: Annotated[
            str,
            Field(
                description=(
                    "Focused search string for the selected knowledge bases: "
                    "key terms, names, and synonyms from the user's question. "
                    "Not a chat reply."
                ),
            ),
        ],
        k: Annotated[
            int,
            Field(
                description="Max passages to return (default 8).",
                ge=1,
                le=20,
            ),
        ] = DEFAULT_RETRIEVAL_K,
    ) -> str:
        try:
            user_id, is_admin, kb_ids, locale = _tool_ctx()
            if not kb_ids:
                return "No knowledge bases selected for this turn."
            context = await retrieve_context(
                services,
                user_id=user_id,
                is_admin=is_admin,
                query=query,
                knowledge_base_ids=kb_ids,
                k=k,
                locale=locale,
            )
            if not context:
                return "No relevant passages found."
            return context
        except Exception as exc:
            return f"Knowledge search failed: {exc}"

    return [
        StructuredTool.from_function(
            coroutine=search_knowledge,
            name=SEARCH_KNOWLEDGE_TOOL,
            # Static fallback; middleware hides or rewrites this per turn.
            description=format_search_knowledge_description([]),
        )
    ]
