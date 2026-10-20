"""Tests for migrate (rename namespace) + dry-run preview (M5.3 + M5.4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.operations.migration.preview import render_rename_plan
from octop_memory.operations.migration.rename import apply_rename, plan_rename
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, Entity, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


def _seed(memory: Memory) -> None:
    memory.add_raw_batch(
        [
            RawEvent(
                id="r1",
                host="t",
                session_id="s",
                thread_id=None,
                user=None,
                timestamp=_now(),
                event_type="user_message",
                content="Hermes 用 Postgres",
                payload={},
            )
        ]
    )
    memory.add_entity(
        Entity(
            id="e1",
            entity_type="Project",
            canonical_name="Hermes",
            aliases=[],
            atom_count=1,
            created_at=_now(),
        )
    )
    memory.add_atom(
        AtomCard(
            id="a1",
            entity_id="e1",
            candidate_id="c1",
            raw_event_ids=["r1"],
            assertion="Hermes uses Postgres",
            verbatim_quote="Hermes uses Postgres",
            quote_event_id="r1",
            search_terms=["Hermes"],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
    )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    db_path = tmp_path / "src.sqlite"
    backend = SqliteMemoryBackend(namespace="oc", db_path=db_path)
    memory = Memory(namespace="oc", backend=backend)
    _seed(memory)
    backend.close()
    return db_path


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_lists_all_namespace_tables(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        assert plan.steps
        # Every step's src_table starts with the source prefix and the
        # dst_table starts with the destination prefix.
        for step in plan.steps:
            assert step.src_table.startswith("oc_")
            assert step.dst_table.startswith("hermes_")

    def test_skips_fts_shadow_tables(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        names = [s.src_table for s in plan.steps]
        # No shadow table directly listed.
        for shadow_suffix in ("_fts_data", "_fts_idx", "_fts_docsize", "_fts_config"):
            assert not any(n.endswith(shadow_suffix) for n in names), names

    def test_row_count_for_seeded_table(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        raw_step = next(s for s in plan.steps if s.src_table.endswith("raw_events"))
        assert raw_step.row_count == 1

    def test_no_conflicts_on_clean_target(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="brandnew")
        assert plan.conflicts == []
        assert not plan.has_conflicts

    def test_detects_conflict(self, tmp_path: Path) -> None:
        db_path = tmp_path / "x.sqlite"
        # Create both src + dst by opening Memory against each.
        m1 = Memory(namespace="oc", backend=SqliteMemoryBackend(namespace="oc", db_path=db_path))
        m1._backend.close()
        m2 = Memory(namespace="hermes", backend=SqliteMemoryBackend(namespace="hermes", db_path=db_path))
        m2._backend.close()

        plan = plan_rename(db_path, src_namespace="oc", dst_namespace="hermes")
        assert plan.has_conflicts
        # All non-shadow dst tables should conflict because we already
        # initialised the dst namespace.
        assert len(plan.conflicts) == len(plan.steps)

    def test_same_namespace_rejected(self, db: Path) -> None:
        with pytest.raises(ValueError, match="identical"):
            plan_rename(db, src_namespace="x", dst_namespace="x")

    def test_missing_db(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            plan_rename(tmp_path / "missing.sqlite", src_namespace="a", dst_namespace="b")


# ---------------------------------------------------------------------------
# Apply (rename mode)
# ---------------------------------------------------------------------------


class TestApplyRename:
    def test_data_visible_under_new_namespace(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        apply_rename(plan)

        m = Memory(namespace="hermes", backend=SqliteMemoryBackend(namespace="hermes", db_path=db))
        try:
            assert len(m.list_raw()) == 1
            assert len(m.list_atoms()) == 1
            # FTS still works after rename + reopen.
            assert len(m.search_atoms("Hermes")) == 1
        finally:
            m._backend.close()

    def test_old_namespace_gone(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        apply_rename(plan)
        # Re-planning from src=oc should now find nothing.
        plan2 = plan_rename(db, src_namespace="oc", dst_namespace="anything")
        assert plan2.steps == []

    def test_refuses_when_conflicts_without_overwrite(self, tmp_path: Path) -> None:
        db_path = tmp_path / "x.sqlite"
        m1 = Memory(namespace="oc", backend=SqliteMemoryBackend(namespace="oc", db_path=db_path))
        m1._backend.close()
        m2 = Memory(namespace="hermes", backend=SqliteMemoryBackend(namespace="hermes", db_path=db_path))
        m2._backend.close()

        plan = plan_rename(db_path, src_namespace="oc", dst_namespace="hermes")
        assert plan.has_conflicts
        with pytest.raises(ValueError, match="already exist"):
            apply_rename(plan)

    def test_allow_overwrite_drops_conflicts(self, tmp_path: Path) -> None:
        db_path = tmp_path / "x.sqlite"
        m_src = Memory(namespace="oc", backend=SqliteMemoryBackend(namespace="oc", db_path=db_path))
        _seed(m_src)
        m_src._backend.close()
        m_dst = Memory(namespace="hermes", backend=SqliteMemoryBackend(namespace="hermes", db_path=db_path))
        m_dst._backend.close()

        plan = plan_rename(db_path, src_namespace="oc", dst_namespace="hermes")
        affected = apply_rename(plan, allow_overwrite=True)
        assert affected > 0
        m = Memory(namespace="hermes", backend=SqliteMemoryBackend(namespace="hermes", db_path=db_path))
        try:
            # Source data wins after overwrite.
            assert len(m.list_raw()) == 1
        finally:
            m._backend.close()


# ---------------------------------------------------------------------------
# Preview rendering (D49-C dual format)
# ---------------------------------------------------------------------------


class TestPreview:
    def test_text_contains_table_names(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        text = render_rename_plan(plan, fmt="text")
        assert "oc_raw_events" in text
        assert "hermes_raw_events" in text
        assert "Total:" in text

    def test_json_round_trips(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        text = render_rename_plan(plan, fmt="json")
        payload = json.loads(text)
        assert payload["src_namespace"] == "oc"
        assert payload["dst_namespace"] == "hermes"
        assert isinstance(payload["steps"], list)
        assert payload["steps"]

    def test_invalid_format(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="oc", dst_namespace="hermes")
        with pytest.raises(ValueError, match="unknown preview format"):
            render_rename_plan(plan, fmt="xml")  # type: ignore[arg-type]

    def test_empty_namespace_render(self, db: Path) -> None:
        plan = plan_rename(db, src_namespace="missing", dst_namespace="anywhere")
        text = render_rename_plan(plan, fmt="text")
        assert "no tables found" in text
