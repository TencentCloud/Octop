"""Tests for the host-files watcher (D51-C real-file index)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from octop_memory.application.host_files import HostFilesIndex

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A clean workspace with the standard memory layout."""
    (tmp_path / "memory").mkdir()
    return tmp_path


@pytest.fixture
def index(tmp_path: Path) -> HostFilesIndex:
    db_path = tmp_path / "host_files.sqlite"
    idx = HostFilesIndex(db_path=db_path, namespace="test_hf")
    yield idx
    idx.stop()


# ---------------------------------------------------------------------------
# scan_once
# ---------------------------------------------------------------------------


class TestScanOnce:
    def test_indexes_root_files(self, index: HostFilesIndex, workspace: Path) -> None:
        (workspace / "MEMORY.md").write_text("Long-term preferences and facts.\n", encoding="utf-8")
        (workspace / "DREAMS.md").write_text("Dream diary.\n", encoding="utf-8")
        (workspace / "USER.md").write_text("Hermes user profile.\n", encoding="utf-8")

        report = index.scan_once(workspace)
        assert report.scanned == 3
        assert report.indexed == 3
        assert report.removed == 0

        memory_md = index.get("MEMORY.md")
        assert memory_md is not None
        assert "Long-term preferences" in memory_md.content
        assert index.get("USER.md") is not None

    def test_indexes_daily_files(self, index: HostFilesIndex, workspace: Path) -> None:
        (workspace / "memory" / "2026-06-04.md").write_text("Today's notes.", encoding="utf-8")
        (workspace / "memory" / "2026-06-04-design-review.md").write_text("Slugged variant.", encoding="utf-8")

        report = index.scan_once(workspace)
        assert report.indexed == 2
        assert index.get("memory/2026-06-04.md") is not None
        assert index.get("memory/2026-06-04-design-review.md") is not None

    def test_skips_unrelated_files(self, index: HostFilesIndex, workspace: Path) -> None:
        # Files outside the contract are ignored even if dropped into
        # the workspace.
        (workspace / "scratch.txt").write_text("not memory", encoding="utf-8")
        (workspace / "memory" / "notes.md").write_text("not a daily file", encoding="utf-8")

        report = index.scan_once(workspace)
        # Both filtered before we call stat.
        assert report.scanned == 0
        assert report.indexed == 0

    def test_indexes_default_topical_files(self, index: HostFilesIndex, workspace: Path) -> None:
        (workspace / "topics").mkdir()
        (workspace / "projects").mkdir()
        (workspace / "topics" / "billing.md").write_text("Billing renewal policy.", encoding="utf-8")
        (workspace / "projects" / "atlas.md").write_text("Atlas launch decision.", encoding="utf-8")

        report = index.scan_once(workspace)
        assert report.indexed == 2
        assert index.get("topics/billing.md") is not None
        assert index.get("projects/atlas.md") is not None

    def test_custom_allowlist_indexes_user_topic_dir(self, tmp_path: Path, workspace: Path) -> None:
        custom = HostFilesIndex(
            db_path=tmp_path / "custom_host_files.sqlite",
            namespace="custom_hf",
            include_globs=["areas/*.md"],
        )
        try:
            (workspace / "areas").mkdir()
            (workspace / "areas" / "infra.md").write_text("Infra runbook memory.", encoding="utf-8")

            report = custom.scan_once(workspace)
            assert report.indexed == 1
            assert custom.get("areas/infra.md") is not None
        finally:
            custom.stop()

    def test_unsafe_allowlist_patterns_are_ignored(self, tmp_path: Path, workspace: Path) -> None:
        custom = HostFilesIndex(
            db_path=tmp_path / "unsafe_host_files.sqlite",
            namespace="unsafe_hf",
            include_globs=["../*.md", "/tmp/*.md", ".secret/*.md", "topics/*.txt"],
        )
        try:
            (workspace / "topics").mkdir()
            (workspace / "topics" / "ignored.md").write_text("This should not be indexed.", encoding="utf-8")

            report = custom.scan_once(workspace)
            assert report.indexed == 0
            assert custom.get("topics/ignored.md") is None
        finally:
            custom.stop()

    def test_unchanged_file_not_reindexed(self, index: HostFilesIndex, workspace: Path) -> None:
        (workspace / "MEMORY.md").write_text("v1", encoding="utf-8")
        first = index.scan_once(workspace)
        assert first.indexed == 1

        # Second call with no changes → indexed == 0
        second = index.scan_once(workspace)
        assert second.indexed == 0
        assert second.scanned == 1  # we still stat it

    def test_changed_file_is_reindexed(self, index: HostFilesIndex, workspace: Path) -> None:
        path = workspace / "MEMORY.md"
        path.write_text("v1", encoding="utf-8")
        index.scan_once(workspace)

        # Bump mtime by writing new content. Sleep so mtime_ns differs
        # on coarse-resolution filesystems (HFS+ has 1s granularity).
        time.sleep(0.01)
        path.write_text("v2 with new content", encoding="utf-8")

        report = index.scan_once(workspace)
        assert report.indexed == 1
        record = index.get("MEMORY.md")
        assert record is not None
        assert "v2 with new content" in record.content

    def test_deleted_file_is_removed_from_index(self, index: HostFilesIndex, workspace: Path) -> None:
        path = workspace / "MEMORY.md"
        path.write_text("here", encoding="utf-8")
        index.scan_once(workspace)
        assert index.get("MEMORY.md") is not None

        path.unlink()
        report = index.scan_once(workspace)
        assert report.removed == 1
        assert index.get("MEMORY.md") is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_empty_query_returns_empty(self, index: HostFilesIndex, workspace: Path) -> None:
        (workspace / "MEMORY.md").write_text("hello world", encoding="utf-8")
        index.scan_once(workspace)
        assert index.search("") == []
        assert index.search("   ") == []

    def test_finds_match(self, index: HostFilesIndex, workspace: Path) -> None:
        (workspace / "MEMORY.md").write_text("Hermes adapter uses the MemoryProvider abstract class.", encoding="utf-8")
        index.scan_once(workspace)
        hits = index.search("Hermes")
        assert len(hits) == 1
        assert hits[0].path == "MEMORY.md"

    def test_or_match_natural_language(self, index: HostFilesIndex, workspace: Path) -> None:
        # FTS5 phrase mode would miss "Hermes adapter" if the doc says
        # "Adapter for Hermes". OR-match recovers it.
        (workspace / "memory" / "2026-06-04.md").write_text(
            "Adapter for Hermes uses the standard interface.", encoding="utf-8"
        )
        index.scan_once(workspace)
        hits = index.search("Hermes adapter")
        assert len(hits) == 1

    def test_snippet_truncated(self, index: HostFilesIndex, workspace: Path) -> None:
        long_body = "Hermes " + ("X" * 1000)
        (workspace / "MEMORY.md").write_text(long_body, encoding="utf-8")
        index.scan_once(workspace)
        hits = index.search("Hermes", snippet_chars=50)
        assert len(hits[0].snippet) <= 50

    def test_changed_file_search_reflects_new_content(self, index: HostFilesIndex, workspace: Path) -> None:
        path = workspace / "MEMORY.md"
        path.write_text("first version mentions Alpha", encoding="utf-8")
        index.scan_once(workspace)
        assert index.search("Alpha") != []
        assert index.search("Beta") == []

        time.sleep(0.01)
        path.write_text("second version mentions Beta only", encoding="utf-8")
        index.scan_once(workspace)
        assert index.search("Alpha") == []
        assert index.search("Beta") != []


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


class TestPolling:
    def test_polling_picks_up_new_file(self, index: HostFilesIndex, workspace: Path) -> None:
        index.start_polling(workspace, interval=0.05)
        # Before any file exists.
        time.sleep(0.1)
        assert index.get("MEMORY.md") is None

        (workspace / "MEMORY.md").write_text("hello", encoding="utf-8")
        # Allow the next tick to fire.
        time.sleep(0.2)
        assert index.get("MEMORY.md") is not None

    def test_start_polling_idempotent(self, index: HostFilesIndex, workspace: Path) -> None:
        index.start_polling(workspace, interval=10.0)
        first_thread = index._thread
        index.start_polling(workspace, interval=10.0)
        # Second call kept the same thread.
        assert index._thread is first_thread

    def test_stop_terminates_thread(self, index: HostFilesIndex, workspace: Path) -> None:
        index.start_polling(workspace, interval=10.0)
        assert index._thread is not None
        index.stop()
        assert index._thread is None
