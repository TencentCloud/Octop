"""Unit tests for the DeepSeek ``web_search`` / ``web_fetch`` LangChain tools."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.websearch import tools as tools_module
from octop.infra.websearch.client import (
    DeepSeekSearchError,
    FetchResult,
    SearchResult,
)
from octop.infra.websearch.tools import build_deepseek_web_tools


class FakeClient:
    """Stand-in for :class:`DeepSeekSearchClient`; no network involved."""

    last: FakeClient | None = None
    search_args: tuple[str, int | None] = ("", None)
    fetch_args: str = ""

    def __init__(self, config: Any) -> None:
        self.config = config
        FakeClient.last = self

    async def search(self, query: str, *, count: int | None = None) -> list[SearchResult]:
        FakeClient.search_args = (query, count)
        if query == "boom":
            raise DeepSeekSearchError(
                "invalid key",
                error_type="auth_error",
                status_code=401,
            )
        if query == "explode":
            raise RuntimeError("kaput")
        return [
            SearchResult(
                title="DeepSeek V4 released",
                url="https://example.com/deepseek-v4",
                summary="Version four is out.",
                site_name="Example News",
                rerank_score=2.4,
                authority=3,
            )
        ]

    async def fetch(self, url: str) -> FetchResult:
        FakeClient.fetch_args = url
        if url == "https://missing.test":
            raise DeepSeekSearchError(
                "no content",
                error_type="not_found",
                status_code=404,
                operation="fetch",
            )
        if url == "https://explode.test":
            raise RuntimeError("kaput")
        return FetchResult(url=url, title="Example", content="# Hello\n\nBody text.")


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    harness_has_deepseek: bool = False,
) -> Any:
    monkeypatch.setattr(tools_module, "DeepSeekSearchClient", FakeClient)
    monkeypatch.setattr(
        tools_module,
        "harness_deepseek_provider_available",
        lambda: harness_has_deepseek,
    )
    built = build_deepseek_web_tools({"DEEPSEEK_API_KEY": "sk-test"})
    assert built is not None
    return built


def _by_name(built: Any) -> dict[str, Any]:
    return {tool.name: tool for tool in built.tools}


def test_build_returns_none_without_api_key() -> None:
    assert build_deepseek_web_tools({}) is None
    assert build_deepseek_web_tools({"DEEPSEEK_SEARCH_COUNT": "5"}) is None


def test_build_mounts_both_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(monkeypatch)
    assert sorted(_by_name(built)) == ["web_fetch", "web_search"]
    assert built.config.count == 10
    search = _by_name(built)["web_search"]
    assert "site:" in search.description
    assert "rerank_score" in search.description
    fetch = _by_name(built)["web_fetch"]
    assert "Markdown" in fetch.description


def test_build_yields_search_when_harness_ships_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build(monkeypatch, harness_has_deepseek=True)
    assert [tool.name for tool in built.tools] == ["web_fetch"]
    assert built.includes_search is False


@pytest.mark.asyncio
async def test_web_search_tool_returns_ranked_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build(monkeypatch)
    tool = _by_name(built)["web_search"]

    out = await tool.ainvoke({"query": "deepseek v4"})
    assert "https://example.com/deepseek-v4" in out
    assert "rerank_score: 2.4/3" in out
    assert "authority: 3/4" in out
    assert FakeClient.search_args == ("deepseek v4", None)

    await tool.ainvoke({"query": "deepseek v4", "count": 3})
    assert FakeClient.search_args == ("deepseek v4", 3)


@pytest.mark.asyncio
async def test_web_search_tool_returns_readable_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build(monkeypatch)
    tool = _by_name(built)["web_search"]

    auth = await tool.ainvoke({"query": "boom"})
    assert auth.startswith("Error: ")
    assert "API key" in auth

    generic = await tool.ainvoke({"query": "explode"})
    assert generic == "Error: DeepSeek web search failed: kaput"


@pytest.mark.asyncio
async def test_web_fetch_tool_returns_page_and_readable_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build(monkeypatch)
    tool = _by_name(built)["web_fetch"]

    page = await tool.ainvoke({"url": "https://example.com/a"})
    assert page.startswith("Fetched page: Example")
    assert "# Hello" in page
    assert FakeClient.fetch_args == "https://example.com/a"

    missing = await tool.ainvoke({"url": "https://missing.test"})
    assert missing.startswith("Error: ")
    assert "could not extract" in missing

    generic = await tool.ainvoke({"url": "https://explode.test"})
    assert generic == "Error: DeepSeek web fetch failed: kaput"
