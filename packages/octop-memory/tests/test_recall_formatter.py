"""Tests for recall formatter (M1.7)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.recall import recall_multi_source


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})


def test_recall_empty_query_returns_empty(memory: Memory) -> None:
    result = recall_multi_source(memory, "")
    assert result.snippets == []
    assert result.rendered == ""


def test_recall_no_match_returns_empty(memory: Memory) -> None:
    memory.add_raw("hello world", event_type="user_message")
    result = recall_multi_source(memory, "nothing matches xyzzy")
    assert result.snippets == []
    assert result.rendered == ""


def test_recall_single_match(memory: Memory) -> None:
    memory.add_raw(
        "I decided to use enhancement mode for Hermes adapter",
        event_type="user_message",
        payload={"role": "user"},
        timestamp=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )
    result = recall_multi_source(memory, "Hermes")
    assert len(result.snippets) == 1
    snippet = result.snippets[0]
    assert "Hermes" in snippet.text
    assert snippet.role_hint == "user"
    assert snippet.timestamp_iso.startswith("2026-06-01")
    # Rendered block contains markers + the snippet
    assert "[memory]" in result.rendered
    assert "[/memory]" in result.rendered
    assert "Hermes" in result.rendered


def test_recall_truncation_per_snippet(memory: Memory) -> None:
    long = "Hermes " + ("x" * 500)
    memory.add_raw(long, event_type="user_message")
    result = recall_multi_source(memory, "Hermes", per_snippet_chars=80)
    assert len(result.snippets[0].text) <= 80
    assert result.snippets[0].text.endswith("…")


def test_recall_total_char_budget(memory: Memory) -> None:
    """Once the total budget is hit, further snippets are dropped (not truncated)."""
    base = "Hermes adapter discussion " * 10  # ~ 250 chars each
    for i in range(5):
        memory.add_raw(f"#{i} {base}", event_type="user_message")
    result = recall_multi_source(
        memory,
        "Hermes",
        limit=5,
        per_snippet_chars=200,
        total_chars=400,  # only ~2 snippets fit
    )
    assert len(result.snippets) <= 2


def test_recall_role_hint_falls_back_to_event_type(memory: Memory) -> None:
    """When payload has no 'role', use event_type."""
    memory.add_raw(
        "tool finished writing file Hermes",
        event_type="tool_result",
        payload={},  # no role
    )
    result = recall_multi_source(memory, "Hermes")
    assert result.snippets[0].role_hint == "tool_result"


def test_recall_renders_query_in_footer(memory: Memory) -> None:
    memory.add_raw("anything containing Hermes adapter", event_type="user_message")
    result = recall_multi_source(memory, "Hermes")
    assert "Hermes" in result.rendered.split("\n")[-1]


def test_recall_long_query_truncated_in_footer(memory: Memory) -> None:
    memory.add_raw("Hermes content", event_type="user_message")
    long_query = "Hermes " * 30
    result = recall_multi_source(memory, long_query)
    footer = result.rendered.split("\n")[-1]
    # Footer fits on one line, query truncated to ~60 chars + ellipsis
    assert len(footer) < 100
