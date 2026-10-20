"""Smoke tests for ``memory atom / entity / journal`` read-only CLI subcommands
plus the interactive ``memory candidate review`` queue.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import (
    Alias,
    AtomCard,
    Candidate,
    Entity,
    JournalEntry,
    RawEvent,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_full_namespace(db_path: str) -> dict[str, str]:
    """Seed one entity + alias + 2 atoms + 1 needs_review candidate.

    Returns a dict of useful ids for assertions.
    """
    backend = SqliteMemoryBackend(namespace="cli", db_path=db_path)
    mem = Memory(namespace="cli", backend=backend)

    raw = RawEvent(
        id=str(uuid.uuid4()),
        host="t",
        session_id="s1",
        thread_id=None,
        user=None,
        timestamp=_now(),
        event_type="user_message",
        content="我们项目用 PostgreSQL 16",
        payload={},
    )
    mem.add_raw_batch([raw])

    entity_id = str(uuid.uuid4())
    mem.add_entity(
        Entity(
            id=entity_id,
            entity_type="Project",
            canonical_name="Project",
            aliases=[],
            atom_count=2,
            created_at=_now(),
        )
    )
    mem.add_alias(
        Alias(
            alias="project",
            entity_id=entity_id,
            entity_type="Project",
            created_by="rule",
            created_at=_now(),
        )
    )

    atom_a_id = str(uuid.uuid4())
    atom_b_id = str(uuid.uuid4())
    mem.add_atom(
        AtomCard(
            id=atom_a_id,
            entity_id=entity_id,
            candidate_id="c-a",
            raw_event_ids=[raw.id],
            assertion="项目用 PostgreSQL 16",
            verbatim_quote="项目用 PostgreSQL 16",
            quote_event_id=raw.id,
            search_terms=["PostgreSQL"],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
    )
    mem.add_atom(
        AtomCard(
            id=atom_b_id,
            entity_id=entity_id,
            candidate_id="c-b",
            raw_event_ids=[raw.id],
            assertion="项目数据库版本 16",
            verbatim_quote="项目数据库版本 16",
            quote_event_id=raw.id,
            search_terms=["PostgreSQL"],
            occurred_at=_now(),
            confidence="medium",
            importance="medium",
            created_at=_now(),
        )
    )

    nr_id = str(uuid.uuid4())
    mem.add_candidate(
        Candidate(
            id=nr_id,
            raw_event_ids=[raw.id],
            candidate_type="Fact",
            status="needs_review",
            title="suspicious fact",
            assertion="某个不确定的断言",
            verbatim_quote="某个不确定的断言",
            quote_event_id=raw.id,
            subject_name="ProjectX",
            subject_entity_type="Project",
            target_entity_id=None,
            confidence="low",
            importance="medium",
            recommended_action="needs_review",
            promotion_reason="rule path uncertain",
            extractor_version="v2.1",
            created_at=_now(),
            session_id="s1",
        )
    )

    mem.append_journal(
        JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=_now(),
            action="promote",
            actor="auto",
            target_entity_id=entity_id,
            target_atom_id=atom_a_id,
            target_candidate_id="c-a",
            note="seeded fixture",
        )
    )

    return {
        "entity_id": entity_id,
        "atom_a_id": atom_a_id,
        "atom_b_id": atom_b_id,
        "needs_review_id": nr_id,
        "raw_id": raw.id,
    }


# ---------------------------------------------------------------------------
# atom CLI
# ---------------------------------------------------------------------------


class TestAtomCLI:
    def test_atom_list_human(self, tmp_path: Path) -> None:
        db = str(tmp_path / "a.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "atom", "list"])
        assert result.exit_code == 0, result.output
        assert ids["atom_a_id"][:8] in result.output
        assert ids["atom_b_id"][:8] in result.output

    def test_atom_list_filter_importance(self, tmp_path: Path) -> None:
        db = str(tmp_path / "a.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "atom", "list", "--importance", "high"])
        assert result.exit_code == 0, result.output
        # Only the high-importance atom shows up
        assert ids["atom_a_id"][:8] in result.output
        assert ids["atom_b_id"][:8] not in result.output

    def test_atom_list_json(self, tmp_path: Path) -> None:
        db = str(tmp_path / "a.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "--json", "atom", "list"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert len(payload) == 2
        atom_ids = {a["id"] for a in payload}
        assert {ids["atom_a_id"], ids["atom_b_id"]} <= atom_ids

    def test_atom_show_full(self, tmp_path: Path) -> None:
        db = str(tmp_path / "a.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "atom", "show", ids["atom_a_id"]])
        assert result.exit_code == 0, result.output
        assert "PostgreSQL" in result.output
        assert "verbatim_quote" in result.output

    def test_atom_show_missing(self, tmp_path: Path) -> None:
        db = str(tmp_path / "a.db")
        _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "atom", "show", "nope"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_atom_search(self, tmp_path: Path) -> None:
        db = str(tmp_path / "a.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "atom", "search", "PostgreSQL"])
        assert result.exit_code == 0, result.output
        assert ids["atom_a_id"][:8] in result.output


# ---------------------------------------------------------------------------
# entity CLI
# ---------------------------------------------------------------------------


class TestEntityCLI:
    def test_entity_list(self, tmp_path: Path) -> None:
        db = str(tmp_path / "e.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "entity", "list"])
        assert result.exit_code == 0, result.output
        assert ids["entity_id"][:8] in result.output
        assert "Project" in result.output

    def test_entity_show_includes_atoms_and_aliases(self, tmp_path: Path) -> None:
        db = str(tmp_path / "e.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "entity", "show", ids["entity_id"]])
        assert result.exit_code == 0, result.output
        assert "atoms (2)" in result.output
        assert "aliases (1)" in result.output
        assert "'project'" in result.output

    def test_entity_list_json(self, tmp_path: Path) -> None:
        db = str(tmp_path / "e.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "--json", "entity", "list"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert len(payload) == 1
        assert payload[0]["id"] == ids["entity_id"]


# ---------------------------------------------------------------------------
# journal CLI
# ---------------------------------------------------------------------------


class TestJournalCLI:
    def test_journal_list(self, tmp_path: Path) -> None:
        db = str(tmp_path / "j.db")
        _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "journal", "list"])
        assert result.exit_code == 0, result.output
        assert "promote" in result.output
        assert "auto" in result.output

    def test_journal_filter_action(self, tmp_path: Path) -> None:
        db = str(tmp_path / "j.db")
        _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "journal", "list", "--action", "reject"])
        assert result.exit_code == 0, result.output
        assert "No journal entries found." in result.output


# ---------------------------------------------------------------------------
# candidate review CLI
# ---------------------------------------------------------------------------


class TestCandidateReviewCLI:
    def test_review_non_interactive_lists_queue(self, tmp_path: Path) -> None:
        db = str(tmp_path / "r.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db,
                "-n",
                "cli",
                "candidate",
                "review",
                "--non-interactive",
            ],
        )
        assert result.exit_code == 0, result.output
        assert ids["needs_review_id"][:8] in result.output

    def test_review_empty_queue(self, tmp_path: Path) -> None:
        db = str(tmp_path / "empty.db")
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db, "-n", "cli", "candidate", "review"])
        assert result.exit_code == 0
        assert "No candidates" in result.output

    def test_review_approve_creates_atom_with_user_journal(self, tmp_path: Path) -> None:
        db = str(tmp_path / "r2.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        # First prompt is the choice, second prompt would be reason on
        # 'r' (reject); not used here. Provide just one input.
        result = runner.invoke(
            main,
            ["--db", db, "-n", "cli", "candidate", "review"],
            input="a\n",
        )
        assert result.exit_code == 0, result.output
        assert "approved" in result.output

        # Verify candidate flipped + journal recorded actor=user.
        mem = Memory(namespace="cli", backend_config={"db_path": db})
        cand = mem.get_candidate(ids["needs_review_id"])
        assert cand is not None
        assert cand.status == "promoted"
        assert cand.decided_by == "user"
        # New atom on entity
        new_entity = mem.find_entity_by_alias("projectx")  # subject_name normalized
        assert new_entity is not None
        atoms = mem.list_atoms(entity_id=new_entity.id)
        assert len(atoms) == 1
        # Journal entry actor=user
        journal = mem.list_journal(target_candidate_id=ids["needs_review_id"])
        assert len(journal) == 1
        assert journal[0].action == "promote"
        assert journal[0].actor == "user"

    def test_review_reject_records_user_reason(self, tmp_path: Path) -> None:
        db = str(tmp_path / "r3.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        # 'r' then a reason line
        result = runner.invoke(
            main,
            ["--db", db, "-n", "cli", "candidate", "review"],
            input="r\nbecause hallucination\n",
        )
        assert result.exit_code == 0, result.output
        assert "rejected" in result.output

        mem = Memory(namespace="cli", backend_config={"db_path": db})
        cand = mem.get_candidate(ids["needs_review_id"])
        assert cand is not None and cand.status == "rejected"
        assert cand.decided_by == "user"
        journal = mem.list_journal(target_candidate_id=ids["needs_review_id"])
        assert len(journal) == 1 and journal[0].action == "reject"
        assert journal[0].actor == "user"
        assert "hallucination" in (journal[0].note or "")

    def test_review_skip_keeps_status(self, tmp_path: Path) -> None:
        db = str(tmp_path / "r4.db")
        ids = _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db, "-n", "cli", "candidate", "review"],
            input="s\n",
        )
        assert result.exit_code == 0, result.output
        assert "skipped" in result.output
        mem = Memory(namespace="cli", backend_config={"db_path": db})
        cand = mem.get_candidate(ids["needs_review_id"])
        assert cand is not None
        assert cand.status == "needs_review"  # unchanged

    def test_review_quit_stops_iteration(self, tmp_path: Path) -> None:
        db = str(tmp_path / "r5.db")
        _seed_full_namespace(db)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db, "-n", "cli", "candidate", "review"],
            input="q\n",
        )
        assert result.exit_code == 0, result.output
        assert "Quit" in result.output
