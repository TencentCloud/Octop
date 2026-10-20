"""Tests for MemoryService-backed LLM tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from octop_harness.builtin.tools.memory_tools import build_memory_tools


class _FakeService:
    def __init__(self) -> None:
        self.search_result: dict[str, Any] = {"hits": []}
        self.get_result: dict[str, Any] = {"content": ""}
        self.save_result = type(
            "Node", (), {"content": "User prefers dark mode", "topic": "preferences", "metadata": {}}
        )()
        self.save_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def save(self, content: str, *, topic: str | None = None) -> Any:
        self.save_calls.append({"content": content, "topic": topic})
        return self.save_result

    def search(self, query: str, *, max_results: int = 5, corpus: str = "all") -> dict[str, Any]:
        self.search_calls.append({"query": query, "max_results": max_results, "corpus": corpus})
        return self.search_result

    def get(self, path: str, *, start: int | None = None, lines: int | None = None) -> dict[str, Any]:
        self.get_calls.append({"path": path, "start": start, "lines": lines})
        return self.get_result


class TestBuildMemoryTools:
    def test_memory_save_reports_a_manual_document_conflict(self) -> None:
        service = _FakeService()
        service.save_result.metadata = {"manual_document_conflict": True}
        save = next(t for t in build_memory_tools(service) if t.name == "memory_save")
        assert "review candidate" in save.invoke({"content": "A conflicting fact"})

    def test_returns_recall_tools(self) -> None:
        tools = build_memory_tools(_FakeService())  # type: ignore[arg-type]
        assert {t.name for t in tools} == {"memory_search", "memory_get", "memory_save"}

    def test_memory_save_writes_through_service(self) -> None:
        service = _FakeService()
        save = next(t for t in build_memory_tools(service) if t.name == "memory_save")

        result = save.invoke({"content": "User prefers dark mode", "topic": "preferences"})

        assert service.save_calls == [{"content": "User prefers dark mode", "topic": "preferences"}]
        assert "saved" in result.lower()

    def test_memory_save_rejects_empty_content(self) -> None:
        service = _FakeService()
        save = next(t for t in build_memory_tools(service) if t.name == "memory_save")

        assert "empty" in save.invoke({"content": "  "}).lower()
        assert service.save_calls == []

    def test_memory_save_reports_failure_without_claiming_success(self) -> None:
        service = _FakeService()
        save = next(t for t in build_memory_tools(service) if t.name == "memory_save")
        with patch.object(service, "save", side_effect=OSError("unavailable")):
            result = save.invoke({"content": "Remember this project decision"})
        assert result == "memory_save failed: OSError"

    def test_memory_search_formats_hits(self) -> None:
        service = _FakeService()
        service.search_result = {
            "hits": [
                {
                    "path": "atom/a.md",
                    "layer": "atom",
                    "snippet": "User prefers dark mode\nfor dashboards.",
                },
            ],
        }
        tools = build_memory_tools(service)
        search_tool = next(t for t in tools if t.name == "memory_search")  # type: ignore[arg-type]

        result = search_tool.invoke({"query": "dark mode", "max_results": 3})

        assert "Memory hits:" in result
        assert "[atom] atom/a.md" in result
        assert "User prefers dark mode for dashboards." in result
        assert service.search_calls == [{"query": "dark mode", "max_results": 3, "corpus": "all"}]

    def test_memory_search_empty(self) -> None:
        service = _FakeService()
        service.search_result = {"hits": [], "empty_reason": "no_index"}
        tools = build_memory_tools(service)
        search_tool = next(t for t in tools if t.name == "memory_search")  # type: ignore[arg-type]

        result = search_tool.invoke({"query": "nothing here"})

        assert result == "No matching memory entries. (no_index)"

    def test_memory_get_returns_content(self) -> None:
        service = _FakeService()
        service.get_result = {"content": "# Memory\ncontent"}
        get_tool = next(t for t in build_memory_tools(service) if t.name == "memory_get")  # type: ignore[arg-type]

        result = get_tool.invoke({"path": "atom/a.md", "start": 2, "lines": 5})

        assert result == "# Memory\ncontent"
        assert service.get_calls == [{"path": "atom/a.md", "start": 2, "lines": 5}]

    def test_memory_get_formats_error(self) -> None:
        service = _FakeService()
        service.get_result = {"error": "not found"}
        get_tool = next(t for t in build_memory_tools(service) if t.name == "memory_get")  # type: ignore[arg-type]

        result = get_tool.invoke({"path": "missing.md"})

        assert result == "memory_get error: not found"

    def test_memory_search_swallows_unexpected_errors(self) -> None:
        class _Boom(_FakeService):
            def search(self, query: str, *, max_results: int = 5, corpus: str = "all") -> dict[str, Any]:
                raise Exception("InvalidSubscription")

        tools = build_memory_tools(_Boom())  # type: ignore[arg-type]
        search_tool = next(t for t in tools if t.name == "memory_search")
        result = search_tool.invoke({"query": "anything"})
        assert result == "memory_search failed: Exception"
