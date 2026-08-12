"""Built-in LangChain tool for on-demand knowledge-base retrieval."""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import StructuredTool
from langgraph.config import get_config
from pydantic import Field

from octop.infra.knowledge.retrieve import DEFAULT_RETRIEVAL_K, retrieve_context

_SEARCH_DESC = (
    "Search knowledge bases the user attached to this turn for relevant passages. "
    "Call when the question may need uploaded documents or internal knowledge. "
    "Do not invent citations; only use returned passages."
)


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
            Field(description="Natural-language search query for the attached knowledge bases."),
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
            name="search_knowledge",
            description=_SEARCH_DESC,
        )
    ]
