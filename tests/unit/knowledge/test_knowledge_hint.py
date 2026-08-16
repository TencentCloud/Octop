"""Unit tests for knowledge-base tool description enrichment."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import MagicMock

from langchain.agents.middleware import ModelRequest
from langchain_core.tools import StructuredTool
from langgraph.config import var_child_runnable_config
from pydantic import Field

from octop.infra.knowledge.hint import (
    KnowledgeSearchHintMiddleware,
    catalog_for_selected_bases,
)
from octop.infra.knowledge.tools import format_search_knowledge_description


@contextmanager
def _configurable(**kwargs: object):
    token = var_child_runnable_config.set({"configurable": kwargs})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def _dummy_tool(description: str = "base") -> StructuredTool:
    async def search_knowledge(
        query: Annotated[str, Field(description="q")],
    ) -> str:
        return query

    return StructuredTool.from_function(
        coroutine=search_knowledge,
        name="search_knowledge",
        description=description,
    )


def test_catalog_for_selected_bases_includes_name_and_description() -> None:
    bases = [
        SimpleNamespace(id="kb-1", name="Refund policy", description="Retail refund rules"),
        SimpleNamespace(id="kb-2", name="", description=""),
    ]
    assert catalog_for_selected_bases(bases, ["kb-1", "kb-2", "missing"]) == [
        {"id": "kb-1", "name": "Refund policy", "description": "Retail refund rules"},
        {"id": "kb-2", "name": "kb-2", "description": ""},
    ]


def test_format_description_lists_titles_and_descriptions() -> None:
    text = format_search_knowledge_description(
        [
            {"id": "kb-1", "name": "Refund policy", "description": "Retail refund rules"},
            {"id": "kb-2", "name": "HR handbook", "description": ""},
        ]
    )
    assert "Attached this turn:" in text
    assert "- Refund policy: Retail refund rules" in text
    assert "- HR handbook" in text
    assert "overlaps any of those topics" in text


def test_format_description_clips_long_fields() -> None:
    text = format_search_knowledge_description(
        [{"id": "kb-1", "name": "Policy", "description": "x" * 400}]
    )
    line = next(part for part in text.splitlines() if part.startswith("- Policy:"))
    assert line.endswith("...")
    assert len(line) < 260


def test_format_description_none_selected() -> None:
    text = format_search_knowledge_description([])
    assert text == "No knowledge bases are attached this turn."


def test_middleware_rewrites_search_knowledge_description() -> None:
    other = StructuredTool.from_function(
        func=lambda: "x",
        name="other",
        description="keep",
    )
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[_dummy_tool("stale"), other],
    )
    captured: list[ModelRequest] = []

    def handler(req: ModelRequest) -> object:
        captured.append(req)
        return object()

    with _configurable(
        knowledge_base_catalog=[
            {
                "id": "kb-1",
                "name": "Refund policy",
                "description": "Retail refund rules",
            }
        ],
    ):
        KnowledgeSearchHintMiddleware().wrap_model_call(request, handler)

    tools = list(captured[0].tools or [])
    kb_tool = next(t for t in tools if getattr(t, "name", None) == "search_knowledge")
    assert "Refund policy: Retail refund rules" in kb_tool.description
    assert next(t for t in tools if getattr(t, "name", None) == "other").description == "keep"
    assert request.tools[0].description == "stale"


def test_middleware_hides_tool_when_catalog_empty() -> None:
    other = StructuredTool.from_function(
        func=lambda: "x",
        name="other",
        description="keep",
    )
    request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[_dummy_tool("stale"), other],
    )
    captured: list[ModelRequest] = []

    def handler(req: ModelRequest) -> object:
        captured.append(req)
        return object()

    with _configurable(knowledge_base_catalog=[]):
        KnowledgeSearchHintMiddleware().wrap_model_call(request, handler)

    names = [getattr(t, "name", None) for t in (captured[0].tools or [])]
    assert names == ["other"]
