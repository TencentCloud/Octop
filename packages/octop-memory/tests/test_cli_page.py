"""Smoke tests for the ``memory page`` CLI subcommand group (M3.10)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Entity, EntityPage


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_page(db_path: Path, *, entity_id: str = "ent-001", dirty: bool = True) -> Memory:
    backend = SqliteMemoryBackend(namespace="cli", db_path=db_path)
    memory = Memory(namespace="cli", backend=backend)

    memory.add_entity(
        Entity(
            id=entity_id,
            entity_type="Project",
            canonical_name="Octop Memory",
            aliases=[],
            atom_count=0,
            created_at=_now(),
        )
    )
    memory.upsert_entity_page(
        EntityPage(
            id=f"page_{entity_id}",
            entity_id=entity_id,
            summary_markdown="## Summary\nbody\n\n## My Notes\nuser said this",
            headline="hot summary",
            topics=["python", "memory"],
            dirty=dirty,
            regen_attempt_count=0,
            summary_version=2,
            last_regen_at=_now(),
            last_user_edit_at=None,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    return memory


def _invoke(args: list[str], db_path: Path) -> object:
    runner = CliRunner()
    return runner.invoke(
        main,
        [
            "--backend",
            "sqlite",
            "--db",
            str(db_path),
            "--namespace",
            "cli",
            *args,
        ],
    )


class TestShow:
    def test_text_output(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db)
        result = _invoke(["page", "show", "ent-001"], db)
        assert result.exit_code == 0
        assert "Octop Memory" in result.output
        assert "hot summary" in result.output
        assert "## My Notes" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db)
        result = _invoke(["--json", "page", "show", "ent-001"], db)
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["entity_id"] == "ent-001"
        assert payload["headline"] == "hot summary"
        assert payload["topics"] == ["python", "memory"]
        assert payload["summary_version"] == 2

    def test_missing_entity(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db)
        result = _invoke(["page", "show", "missing"], db)
        assert result.exit_code != 0


class TestListDirty:
    def test_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db, dirty=False)
        result = _invoke(["page", "list-dirty"], db)
        assert result.exit_code == 0
        assert "No dirty pages" in result.output

    def test_lists_dirty(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db, dirty=True)
        result = _invoke(["page", "list-dirty"], db)
        assert result.exit_code == 0
        assert "ent-001"[:8] in result.output

    def test_json_listing(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db, dirty=True)
        result = _invoke(["--json", "page", "list-dirty"], db)
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert payload[0]["entity_id"] == "ent-001"


class TestRegenUsageErrors:
    def test_no_args_errors(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db)
        result = _invoke(["page", "regen"], db)
        assert result.exit_code != 0
        assert "ENTITY_ID" in result.output or "Usage" in result.output

    def test_dirty_and_id_mutually_exclusive(self, tmp_path: Path) -> None:
        db = tmp_path / "p.sqlite"
        _seed_page(db)
        result = _invoke(["page", "regen", "ent-001", "--dirty"], db)
        assert result.exit_code != 0


class TestRegenWithoutLLM:
    def test_no_dev_llm_flag_uses_noop_and_records_failure(self, tmp_path: Path) -> None:
        # When neither --dev-llm nor --dev-remote is passed, the CLI uses
        # NoopLLMClient which raises on every call. The regen path must
        # gracefully record this as a failure (not crash the CLI).
        db = tmp_path / "p.sqlite"
        memory = _seed_page(db, dirty=True)
        # The seeded page already has a summary; need to also have an atom
        # so the regen path doesn't take the "empty entity" early-out.
        from octop_memory.types import AtomCard

        memory.add_atom(
            AtomCard(
                id=str(uuid.uuid4()),
                entity_id="ent-001",
                candidate_id="c1",
                raw_event_ids=[],
                assertion="x",
                verbatim_quote="x",
                quote_event_id="raw-x",
                search_terms=[],
                occurred_at=_now(),
                confidence="high",
                importance="high",
                created_at=_now(),
            )
        )
        backend = memory._backend  # type: ignore[attr-defined]  # close so CLI's connection is fresh
        backend.close()

        result = _invoke(["page", "regen", "ent-001"], db)
        # CLI exits cleanly even though the LLM call failed (D35-A behaviour).
        assert result.exit_code == 0
        assert "success" in result.output.lower()
