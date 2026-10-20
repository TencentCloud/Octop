"""Tests for Memory core class."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from octop_memory import Memory


@pytest.fixture
def memory(tmp_path: Path) -> Iterator[Memory]:
    mem = Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})
    yield mem


class TestStore:
    def test_store_creates_leaf_node(self, memory: Memory) -> None:
        node = memory.store("User prefers Python over Java")
        assert node.level == "leaf"
        assert "Python" in node.content

    def test_store_with_topic(self, memory: Memory) -> None:
        node = memory.store("Likes TDD", topic="preferences")
        assert node.topic == "preferences"


class TestRecall:
    def test_recall_finds_stored_memory(self, memory: Memory) -> None:
        memory.store("User works on octop-harness project")
        memory.store("User likes sushi for lunch")
        results = memory.recall("octop-harness")
        assert len(results) >= 1
        assert any("octop-harness" in r.content for r in results)

    def test_recall_empty_returns_empty(self, memory: Memory) -> None:
        results = memory.recall("nonexistent topic")
        assert results == []


class TestRawEvents:
    def test_store_writes_l0_raw_event(self, memory: Memory) -> None:
        memory.store("User deploys with Docker", topic="infra")
        events = memory.list_raw(limit=10)
        assert len(events) >= 1
        assert any("Docker" in e.content for e in events)

    def test_search_raw(self, memory: Memory) -> None:
        memory.store("How to configure memory?", topic="faq")
        results = memory.search_raw("configure memory")
        assert len(results) >= 1


class TestGetTree:
    def test_get_tree_initially_empty(self, memory: Memory) -> None:
        assert memory.get_tree() == []

    def test_get_tree_after_store(self, memory: Memory) -> None:
        memory.store("Some fact")
        tree = memory.get_tree()
        assert len(tree) >= 1
