"""Tests for M3 EntityPage schema (SQLite backend)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import EntityPage


def _now() -> datetime:
    return datetime.now(UTC)


def _make_page(
    *,
    entity_id: str = "ent-1",
    summary: str = "",
    headline: str = "",
    dirty: bool = True,
    version: int = 0,
) -> EntityPage:
    when = _now()
    return EntityPage(
        id=f"page_{entity_id}",
        entity_id=entity_id,
        summary_markdown=summary,
        headline=headline,
        topics=[],
        dirty=dirty,
        regen_attempt_count=0,
        summary_version=version,
        last_regen_at=None,
        last_user_edit_at=None,
        created_at=when,
        updated_at=when,
    )


@pytest.fixture
def backend(tmp_path: Path) -> SqliteMemoryBackend:
    return SqliteMemoryBackend(namespace="page", db_path=tmp_path / "page.sqlite")


class TestUpsertAndGet:
    def test_get_returns_none_for_missing(self, backend: SqliteMemoryBackend) -> None:
        assert backend.get_entity_page("missing") is None

    def test_insert_then_fetch(self, backend: SqliteMemoryBackend) -> None:
        page = _make_page(summary="hello", headline="hi", dirty=False)
        backend.upsert_entity_page(page)

        got = backend.get_entity_page("ent-1")
        assert got is not None
        assert got.summary_markdown == "hello"
        assert got.headline == "hi"
        assert got.dirty is False
        assert got.topics == []

    def test_upsert_replaces_existing(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(summary="v0", version=0))
        backend.upsert_entity_page(
            EntityPage(
                id="page_ent-1",  # same row, by entity_id
                entity_id="ent-1",
                summary_markdown="v1",
                headline="new",
                topics=["alpha", "beta"],
                dirty=False,
                regen_attempt_count=0,
                summary_version=1,
                last_regen_at=_now(),
                last_user_edit_at=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        got = backend.get_entity_page("ent-1")
        assert got is not None
        assert got.summary_markdown == "v1"
        assert got.headline == "new"
        assert got.topics == ["alpha", "beta"]
        assert got.summary_version == 1

    def test_unique_per_entity(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(entity_id="a"))
        backend.upsert_entity_page(_make_page(entity_id="b"))
        assert backend.get_entity_page("a") is not None
        assert backend.get_entity_page("b") is not None


class TestMarkDirty:
    def test_mark_dirty_inserts_stub(self, backend: SqliteMemoryBackend) -> None:
        when = _now()
        backend.mark_entity_page_dirty("brand-new", when=when)
        page = backend.get_entity_page("brand-new")
        assert page is not None
        assert page.dirty is True
        assert page.summary_markdown == ""
        assert page.headline == ""
        assert page.summary_version == 0
        assert page.regen_attempt_count == 0

    def test_mark_dirty_is_idempotent(self, backend: SqliteMemoryBackend) -> None:
        backend.mark_entity_page_dirty("ent-1", when=_now())
        backend.mark_entity_page_dirty("ent-1", when=_now())
        backend.mark_entity_page_dirty("ent-1", when=_now())
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is True

    def test_mark_dirty_on_clean_page_re_dirties(self, backend: SqliteMemoryBackend) -> None:
        # start with clean, regenerated page
        backend.upsert_entity_page(_make_page(summary="clean", dirty=False, version=3))
        backend.mark_entity_page_dirty("ent-1", when=_now())
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is True
        # data is preserved (only dirty flag flipped)
        assert page.summary_markdown == "clean"
        assert page.summary_version == 3


class TestListDirty:
    def test_only_returns_dirty(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(entity_id="dirty1", dirty=True))
        backend.upsert_entity_page(_make_page(entity_id="dirty2", dirty=True))
        backend.upsert_entity_page(_make_page(entity_id="clean", dirty=False))

        dirty = backend.list_dirty_entity_pages(limit=10)
        ids = {p.entity_id for p in dirty}
        assert ids == {"dirty1", "dirty2"}

    def test_never_regenerated_first(self, backend: SqliteMemoryBackend) -> None:
        # one page already had a regen, one never did
        page_old = _make_page(entity_id="old", dirty=True, version=2)
        page_old.last_regen_at = datetime(2024, 1, 1, tzinfo=UTC)
        backend.upsert_entity_page(page_old)
        backend.upsert_entity_page(_make_page(entity_id="never", dirty=True))

        dirty = backend.list_dirty_entity_pages(limit=10)
        # The "never regenerated" row sorts first.
        assert [p.entity_id for p in dirty] == ["never", "old"]

    def test_respects_limit(self, backend: SqliteMemoryBackend) -> None:
        for i in range(5):
            backend.upsert_entity_page(_make_page(entity_id=f"e{i}", dirty=True))
        assert len(backend.list_dirty_entity_pages(limit=3)) == 3


class TestApplyRegen:
    def test_clears_dirty_and_bumps_version(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(dirty=True, version=0))
        ok = backend.apply_entity_page_regen(
            "ent-1",
            summary_markdown="rendered body",
            headline="hello",
            topics=["t1"],
            when=_now(),
        )
        assert ok is True
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is False
        assert page.regen_attempt_count == 0
        assert page.summary_version == 1
        assert page.summary_markdown == "rendered body"
        assert page.headline == "hello"
        assert page.topics == ["t1"]
        assert page.last_regen_at is not None

    def test_returns_false_when_missing(self, backend: SqliteMemoryBackend) -> None:
        ok = backend.apply_entity_page_regen(
            "missing",
            summary_markdown="x",
            headline="x",
            topics=[],
            when=_now(),
        )
        assert ok is False


class TestRecordFailure:
    def test_increments_attempt_keeps_dirty(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(dirty=True))
        ok = backend.record_entity_page_regen_failure("ent-1", when=_now())
        assert ok is True
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is True
        assert page.regen_attempt_count == 1
        # summary preserved
        assert page.summary_markdown == ""

    def test_does_not_overwrite_summary(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(summary="v1 keep me", dirty=True, version=2))
        backend.record_entity_page_regen_failure("ent-1", when=_now())
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.summary_markdown == "v1 keep me"
        assert page.summary_version == 2  # NOT bumped on failure


class TestApplyUserEdit:
    def test_bumps_version_and_sets_last_user_edit(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(version=2))
        ok = backend.apply_entity_page_user_edit(
            "ent-1",
            summary_markdown="user wrote this",
            when=_now(),
        )
        assert ok is True
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.summary_markdown == "user wrote this"
        assert page.summary_version == 3
        assert page.last_user_edit_at is not None
        # user edit does NOT mark dirty
        assert page.dirty is True  # was True before; user edit doesn't toggle

    def test_user_edit_does_not_clear_dirty_flag(self, backend: SqliteMemoryBackend) -> None:
        backend.upsert_entity_page(_make_page(dirty=False))
        backend.apply_entity_page_user_edit("ent-1", summary_markdown="x", when=_now())
        page = backend.get_entity_page("ent-1")
        assert page is not None
        assert page.dirty is False  # user edit didn't flip it on
