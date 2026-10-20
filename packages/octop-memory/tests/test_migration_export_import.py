"""Tests for export / import roundtrip (M5.1 + M5.2)."""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.operations.migration import EXPORT_VERSION
from octop_memory.operations.migration.export import export_namespace
from octop_memory.operations.migration.import_ import import_namespace
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Alias, AtomCard, Candidate, Entity, EntityPage, JournalEntry, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_full(memory: Memory) -> dict[str, str]:
    """Seed every table for end-to-end roundtrip checking."""
    raw_id = "raw-1"
    cand_id = "cand-1"
    atom_id = "atom-1"
    entity_id = "ent-1"
    when = _now()

    memory.add_raw_batch(
        [
            RawEvent(
                id=raw_id,
                host="t",
                session_id="s1",
                thread_id=None,
                user="alice",
                timestamp=when,
                event_type="user_message",
                content="Hermes 用 Postgres 16",
                payload={"meta": "yes"},
            )
        ]
    )
    memory.add_candidate(
        Candidate(
            id=cand_id,
            raw_event_ids=[raw_id],
            candidate_type="Fact",
            status="promoted",
            title="Hermes uses Postgres",
            assertion="Hermes 用 Postgres 16",
            verbatim_quote="Hermes 用 Postgres 16",
            quote_event_id=raw_id,
            subject_name="Hermes",
            subject_entity_type="Project",
            target_entity_id=None,
            confidence="high",
            importance="high",
            recommended_action="promote",
            promotion_reason="",
            extractor_version="v2.1",
            created_at=when,
            session_id="s1",
        )
    )
    memory.add_entity(
        Entity(
            id=entity_id,
            entity_type="Project",
            canonical_name="Hermes",
            aliases=["hermes"],
            atom_count=1,
            created_at=when,
        )
    )
    memory.add_atom(
        AtomCard(
            id=atom_id,
            entity_id=entity_id,
            candidate_id=cand_id,
            raw_event_ids=[raw_id],
            assertion="Hermes 用 Postgres 16",
            verbatim_quote="Hermes 用 Postgres 16",
            quote_event_id=raw_id,
            search_terms=["Hermes"],
            occurred_at=when,
            confidence="high",
            importance="high",
            created_at=when,
        )
    )
    memory.add_alias(
        Alias(
            alias="hermes",
            entity_id=entity_id,
            entity_type="Project",
            created_by="seed",
            created_at=when,
        )
    )
    memory.upsert_entity_page(
        EntityPage(
            id=f"page_{entity_id}",
            entity_id=entity_id,
            summary_markdown="## Summary\nHermes uses Postgres",
            headline="Hermes notes",
            topics=["postgres"],
            dirty=False,
            regen_attempt_count=0,
            summary_version=1,
            last_regen_at=when,
            last_user_edit_at=None,
            created_at=when,
            updated_at=when,
        )
    )
    memory.append_journal(
        JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=when,
            action="promote",
            actor="auto",
            target_entity_id=entity_id,
            target_atom_id=atom_id,
            target_candidate_id=cand_id,
            note="initial seed",
        )
    )
    memory.upsert_active_entity("thr-1", entity_id, source="manual", when=when)

    return {"raw": raw_id, "cand": cand_id, "atom": atom_id, "entity": entity_id}


@pytest.fixture
def src(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="src", db_path=tmp_path / "src.sqlite")
    return Memory(namespace="src", backend=backend)


@pytest.fixture
def dst(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="dst", db_path=tmp_path / "dst.sqlite")
    return Memory(namespace="dst", backend=backend)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_writes_header_and_footer(self, src: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl"
        summary = export_namespace(src, out)

        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 2
        first = json.loads(lines[0])
        assert first["table"] == "__header__"
        assert first["data"]["namespace"] == "src"
        assert first["data"]["version"] == EXPORT_VERSION
        last = json.loads(lines[-1])
        assert last["table"] == "__footer__"
        assert last["data"]["total_rows"] == summary.total_rows

    def test_counts_match_database(self, src: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl"
        summary = export_namespace(src, out)
        # 1 raw, 1 candidate, 1 atom, 1 entity, 1 alias, 1 page,
        # 1 thread_active, 1 journal
        assert summary.counts["raw_events"] == 1
        assert summary.counts["candidates"] == 1
        assert summary.counts["atoms"] == 1
        assert summary.counts["entities"] == 1
        assert summary.counts["aliases"] == 1
        assert summary.counts["entity_pages"] == 1
        assert summary.counts["thread_active_entities"] == 1
        assert summary.counts["journal"] == 1

    def test_gzip_explicit_flag(self, src: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl"  # no .gz suffix
        export_namespace(src, out, gzip_compress=True)
        # File written via gzip should fail to decode as plain text:
        with pytest.raises(UnicodeDecodeError):
            out.read_text(encoding="utf-8")
        # But gzip read works:
        with gzip.open(out, "rt", encoding="utf-8") as fp:
            assert "__header__" in fp.read(200)

    def test_gzip_suffix_auto(self, src: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl.gz"
        export_namespace(src, out)  # auto-detect .gz
        with gzip.open(out, "rt", encoding="utf-8") as fp:
            head = fp.readline()
        assert json.loads(head)["table"] == "__header__"

    def test_empty_namespace(self, src: Memory, tmp_path: Path) -> None:
        out = tmp_path / "empty.jsonl"
        summary = export_namespace(src, out)
        # All counts should be zero
        assert summary.total_rows == 0
        # Header + footer still written
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_active_entities_are_exported(self, src: Memory, tmp_path: Path) -> None:
        from octop_memory.types import ActiveEntity

        src._backend.upsert_active_entity(
            ActiveEntity(thread_id="t1", entity_id="ent-1", last_seen_at=_now(), source="query_mention")
        )
        out = tmp_path / "ae.jsonl"
        export_namespace(src, out)

        rows = [
            json.loads(line)["data"]
            for line in out.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["table"] == "thread_active_entities"
        ]
        assert [(r["thread_id"], r["entity_id"], r["source"]) for r in rows] == [("t1", "ent-1", "query_mention")]

    def test_backend_without_the_table_is_skipped_not_crashed(self, src: Memory, tmp_path: Path) -> None:
        """A backend that is neither SQLite nor Postgres must yield nothing
        rather than have a SQLite statement reach its connection.
        """
        from octop_memory.operations.migration.export import _iter_active_entities

        class _Foreign:
            _conn = object()
            _ns = "whatever"

        class _Mem:
            _backend = _Foreign()

        assert list(_iter_active_entities(_Mem())) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class TestImport:
    def test_roundtrip_preserves_data(self, src: Memory, dst: Memory, tmp_path: Path) -> None:
        ids = _seed_full(src)
        out = tmp_path / "dump.jsonl"
        export_namespace(src, out)

        summary = import_namespace(dst, out)
        assert summary.errors == []

        # Verify each table has the expected row.
        assert dst.get_raw(ids["raw"]) is not None
        assert dst.get_candidate(ids["cand"]) is not None
        atom = dst.get_atom(ids["atom"])
        assert atom is not None
        assert atom.assertion == "Hermes 用 Postgres 16"
        assert dst.get_entity(ids["entity"]) is not None
        assert dst.find_entity_by_alias("hermes") is not None
        page = dst.get_entity_page(ids["entity"])
        assert page is not None and page.summary_version == 1
        assert dst.list_journal(target_entity_id=ids["entity"], limit=10)
        thread_rows = dst.list_active_entities("thr-1")
        assert any(r.entity_id == ids["entity"] for r in thread_rows)

    def test_skip_on_conflict(self, src: Memory, dst: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl"
        export_namespace(src, out)

        # Pre-populate dst with the same raw event so PK collides.
        when = _now()
        dst.add_raw_batch(
            [
                RawEvent(
                    id="raw-1",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=when,
                    event_type="user_message",
                    content="pre-existing",
                    payload={},
                )
            ]
        )
        summary = import_namespace(dst, out, on_conflict="skip")
        # raw_events skipped; everything else applied
        assert summary.skipped.get("raw_events", 0) == 1
        assert summary.applied.get("entities", 0) == 1

    def test_namespace_mismatch_refused(self, src: Memory, dst: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl"
        export_namespace(src, out)
        with pytest.raises(ValueError, match="namespace mismatch"):
            import_namespace(dst, out, expect_namespace="not-the-source")

    def test_gzip_input(self, src: Memory, dst: Memory, tmp_path: Path) -> None:
        _seed_full(src)
        out = tmp_path / "dump.jsonl.gz"
        export_namespace(src, out)
        summary = import_namespace(dst, out)
        assert summary.errors == []
        assert dst.get_raw("raw-1") is not None

    def test_invalid_json_raises(self, dst: Memory, tmp_path: Path) -> None:
        bad = tmp_path / "bad.jsonl"
        bad.write_text("{not json}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            import_namespace(dst, bad)

    def test_version_mismatch_refused(self, dst: Memory, tmp_path: Path) -> None:
        bad = tmp_path / "bad.jsonl"
        bad.write_text(
            json.dumps({"v": 999, "table": "raw_events", "data": {}}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="incompatible export version"):
            import_namespace(dst, bad)


# ---------------------------------------------------------------------------
# RISK-008: on_conflict policy behavior verification
# ---------------------------------------------------------------------------


class TestOnConflictPolicy:
    """Verify the actual behavior of the three on_conflict policies (RISK-008)."""

    @pytest.fixture()
    def mem(self, tmp_path: Path) -> Memory:
        return Memory("ns", backend_config={"db_path": str(tmp_path / "m.sqlite")})

    def _write_dump(self, tmp_path: Path, raw_id: str = "raw-conflict") -> Path:
        """Write a minimal dump file containing a single raw_event."""
        out = tmp_path / "dump.jsonl"
        when = _now()
        header = {
            "v": EXPORT_VERSION,
            "table": "__header__",
            "data": {"namespace": "ns", "exported_at": when.isoformat()},
        }
        row = {
            "v": EXPORT_VERSION,
            "table": "raw_events",
            "data": {
                "id": raw_id,
                "host": "t",
                "session_id": None,
                "thread_id": None,
                "user": None,
                "timestamp": when.isoformat(),
                "event_type": "user_message",
                "content": "冲突测试内容",
                "payload": {},
            },
        }
        out.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
        return out

    def test_skip_keeps_existing_row(self, mem: Memory, tmp_path: Path) -> None:
        """on_conflict='skip': the existing row is kept, counted as skipped."""
        raw_id = "raw-skip-test"
        when = _now()
        # Write an original row first
        mem.add_raw_batch(
            [
                RawEvent(
                    id=raw_id,
                    host="original",
                    session_id=None,
                    thread_id=None,
                    user=None,
                    timestamp=when,
                    event_type="user_message",
                    content="原始内容",
                    payload={},
                )
            ]
        )
        dump = self._write_dump(tmp_path, raw_id=raw_id)
        summary = import_namespace(mem, dump, on_conflict="skip")
        assert summary.skipped.get("raw_events", 0) == 1
        assert summary.applied.get("raw_events", 0) == 0
        # Original content must not be overwritten
        existing = mem.get_raw(raw_id)
        assert existing is not None
        assert existing.content == "原始内容"

    def test_replace_currently_behaves_as_skip(self, mem: Memory, tmp_path: Path) -> None:
        """on_conflict='replace': currently behaves the same as skip (RISK-008 known limitation).

        This test documents the known limitation, it is not the desired
        behavior. Once replace is actually implemented, this test should be
        updated to verify the overwrite behavior.
        """
        raw_id = "raw-replace-test"
        when = _now()
        mem.add_raw_batch(
            [
                RawEvent(
                    id=raw_id,
                    host="original",
                    session_id=None,
                    thread_id=None,
                    user=None,
                    timestamp=when,
                    event_type="user_message",
                    content="原始内容",
                    payload={},
                )
            ]
        )
        dump = self._write_dump(tmp_path, raw_id=raw_id)
        summary = import_namespace(mem, dump, on_conflict="replace")
        # Currently replace = skip: counted as skipped, not applied
        assert summary.skipped.get("raw_events", 0) == 1
        # Original content must not be overwritten (this is the current known limitation)
        existing = mem.get_raw(raw_id)
        assert existing is not None
        assert existing.content == "原始内容"

    def test_raise_aborts_on_conflict(self, mem: Memory, tmp_path: Path) -> None:
        """on_conflict='raise': raises an exception on conflict, aborting the import."""
        raw_id = "raw-raise-test"
        when = _now()
        mem.add_raw_batch(
            [
                RawEvent(
                    id=raw_id,
                    host="original",
                    session_id=None,
                    thread_id=None,
                    user=None,
                    timestamp=when,
                    event_type="user_message",
                    content="原始内容",
                    payload={},
                )
            ]
        )
        dump = self._write_dump(tmp_path, raw_id=raw_id)
        with pytest.raises((Exception, ValueError, RuntimeError)):  # IntegrityError or ValueError
            import_namespace(mem, dump, on_conflict="raise")

    def test_entity_page_replace_actually_upserts(self, mem: Memory, tmp_path: Path) -> None:
        """entity_pages is an exception: always upserts (overwrites) regardless of on_conflict."""
        from octop_memory.types import EntityPage

        entity_id = "ent-page-test"
        when = _now()
        # Write an entity first (page requires the entity to exist)
        from octop_memory.types import Entity

        mem.add_entity(
            Entity(
                id=entity_id,
                entity_type="Project",
                canonical_name="测试项目",
                aliases=["测试项目"],
                atom_count=0,
                created_at=when,
            )
        )
        # Write the initial page
        page = EntityPage(
            id=f"page-{entity_id}",
            entity_id=entity_id,
            summary_markdown="旧摘要",
            headline="旧标题",
            topics=[],
            dirty=False,
            regen_attempt_count=0,
            summary_version=1,
            created_at=when,
            updated_at=when,
        )
        mem.upsert_entity_page(page)

        # Build a dump containing the new page
        out = tmp_path / "page_dump.jsonl"
        header = {
            "v": EXPORT_VERSION,
            "table": "__header__",
            "data": {"namespace": "ns", "exported_at": when.isoformat()},
        }
        row = {
            "v": EXPORT_VERSION,
            "table": "entity_pages",
            "data": {
                "id": f"page-{entity_id}",
                "entity_id": entity_id,
                "summary_markdown": "新摘要",
                "headline": "新标题",
                "topics": [],
                "dirty": False,
                "regen_attempt_count": 0,
                "summary_version": 2,
                "created_at": when.isoformat(),
                "updated_at": when.isoformat(),
            },
        }
        out.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")

        summary = import_namespace(mem, out, on_conflict="skip")
        # entity_pages always upserts, counted as applied
        assert summary.applied.get("entity_pages", 0) == 1
        updated = mem.get_entity_page(entity_id)
        assert updated is not None
        assert updated.headline == "新标题"
