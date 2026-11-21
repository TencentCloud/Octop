"""Unit tests for built-in knowledge-base LangChain tools."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.config import var_child_runnable_config

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.knowledge.plane import postgres_database
from octop.infra.knowledge.tools import KnowledgeToolServices, build_knowledge_tools


@contextmanager
def _configurable(**kwargs: object):
    token = var_child_runnable_config.set({"configurable": kwargs})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def _tool_by_name(tools: list, name: str):
    for tool in tools:
        if tool.name == name:
            return tool
    raise KeyError(name)


def test_tool_services_follow_control_plane_driver() -> None:
    """Search must see a driver swap; indexing already reads services.config."""
    manager = SimpleNamespace(
        _config=OctopConfig(database=DatabaseConfig(driver="sqlite")),
        _repos=SimpleNamespace(
            knowledge_repo=object(),
            settings_repo=object(),
            provider_repo=object(),
        ),
    )
    services = KnowledgeToolServices(manager)
    assert postgres_database(services) is None

    manager._config = OctopConfig(
        database=DatabaseConfig(
            driver="postgresql",
            host="db.example",
            database="octop",
            user="octop",
        )
    )
    assert postgres_database(services) is manager._config.database


def test_search_knowledge_default_description_is_empty_catalog_fallback() -> None:
    tool = _tool_by_name(build_knowledge_tools(SimpleNamespace()), "search_knowledge")
    assert tool.description == "No knowledge bases are attached this turn."


@pytest.mark.asyncio
async def test_search_knowledge_requires_selected_bases() -> None:
    services = SimpleNamespace(
        knowledge_repo=MagicMock(),
        settings_repo=MagicMock(),
        provider_repo=MagicMock(),
    )
    tool = _tool_by_name(build_knowledge_tools(services), "search_knowledge")
    with _configurable(user="1", knowledge_base_ids=[]):
        out = await tool.ainvoke({"query": "billing policy"})
    assert "No knowledge bases selected" in out


@pytest.mark.asyncio
async def test_search_knowledge_returns_retrieved_context() -> None:
    services = SimpleNamespace(
        knowledge_repo=MagicMock(),
        settings_repo=MagicMock(),
        provider_repo=MagicMock(),
    )
    tool = _tool_by_name(build_knowledge_tools(services), "search_knowledge")
    retrieved = AsyncMock(return_value="[KB: Docs]\nuseful passage")
    with (
        _configurable(
            user="7",
            user_is_admin=False,
            knowledge_base_ids=["kb-1"],
            locale="zh",
        ),
        patch("octop.infra.knowledge.tools.retrieve_context", retrieved),
    ):
        out = await tool.ainvoke({"query": "refund rules", "k": 3})

    assert out == "[KB: Docs]\nuseful passage"
    retrieved.assert_awaited_once()
    kwargs = retrieved.await_args.kwargs
    assert kwargs["user_id"] == 7
    assert kwargs["is_admin"] is False
    assert kwargs["query"] == "refund rules"
    assert kwargs["knowledge_base_ids"] == ["kb-1"]
    assert kwargs["k"] == 3
    assert kwargs["locale"] == "zh"


@pytest.mark.asyncio
async def test_search_knowledge_empty_hits_message() -> None:
    services = SimpleNamespace(
        knowledge_repo=MagicMock(),
        settings_repo=MagicMock(),
        provider_repo=MagicMock(),
    )
    tool = _tool_by_name(build_knowledge_tools(services), "search_knowledge")
    with (
        _configurable(user="1", knowledge_base_ids=["kb-1"]),
        patch(
            "octop.infra.knowledge.tools.retrieve_context",
            AsyncMock(return_value=""),
        ),
    ):
        out = await tool.ainvoke({"query": "nothing"})
    assert "No relevant passages found" in out
