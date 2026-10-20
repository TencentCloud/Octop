"""Tests for the page-trigger helpers (D33-B mark-dirty + cold-skip)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.page.trigger import mark_entity_dirty_after_promote, should_regenerate
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import EntityPage


def _now() -> datetime:
    return datetime.now(UTC)


def _make(*, dirty: bool = True, attempts: int = 0) -> EntityPage:
    return EntityPage(
        id="page_x",
        entity_id="ent-x",
        summary_markdown="",
        headline="",
        topics=[],
        dirty=dirty,
        regen_attempt_count=attempts,
        summary_version=0,
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="trig", db_path=tmp_path / "trig.sqlite")
    return Memory(namespace="trig", backend=backend)


class TestMarkDirty:
    def test_creates_stub_for_brand_new_entity(self, memory: Memory) -> None:
        mark_entity_dirty_after_promote(memory, "new-ent")
        page = memory.get_entity_page("new-ent")
        assert page is not None
        assert page.dirty is True
        assert page.summary_markdown == ""

    def test_idempotent(self, memory: Memory) -> None:
        for _ in range(5):
            mark_entity_dirty_after_promote(memory, "e")
        page = memory.get_entity_page("e")
        assert page is not None
        assert page.dirty is True


class TestShouldRegenerate:
    def test_clean_returns_false(self) -> None:
        ok, reason = should_regenerate(_make(dirty=False))
        assert ok is False
        assert reason == "clean"

    def test_dirty_default_returns_true(self) -> None:
        ok, reason = should_regenerate(_make(dirty=True, attempts=0))
        assert ok is True
        assert reason == ""

    def test_too_many_failures_returns_false(self) -> None:
        ok, reason = should_regenerate(_make(dirty=True, attempts=10), max_attempt_count=5)
        assert ok is False
        assert reason == "too_many_failures"

    def test_backoff_warns_but_proceeds(self) -> None:
        # 3 failures still allowed but caller can choose to skip.
        ok, reason = should_regenerate(_make(dirty=True, attempts=3), backoff_after_failures=3)
        assert ok is True
        assert reason == "backoff"
