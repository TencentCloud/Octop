"""Smoke tests for ``memory recall`` + ``memory thread show`` CLI (M4)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Alias, AtomCard, Entity, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


def _seed(db_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="cli", db_path=db_path)
    mem = Memory(namespace="cli", backend=backend)
    eid = "ent-hermes"
    mem.add_entity(
        Entity(
            id=eid,
            entity_type="Project",
            canonical_name="Hermes",
            aliases=["hermes"],
            atom_count=1,
            created_at=_now(),
        )
    )
    mem.add_alias(Alias(alias="hermes", entity_id=eid, entity_type="Project", created_by="t", created_at=_now()))
    raw_id = str(uuid.uuid4())
    mem.add_raw_batch(
        [
            RawEvent(
                id=raw_id,
                host="t",
                session_id="s",
                thread_id=None,
                user=None,
                timestamp=_now(),
                event_type="user_message",
                content="Hermes uses Postgres 16",
                payload={},
            )
        ]
    )
    mem.add_atom(
        AtomCard(
            id=str(uuid.uuid4()),
            entity_id=eid,
            candidate_id=str(uuid.uuid4()),
            raw_event_ids=[raw_id],
            assertion="Hermes uses Postgres 16",
            verbatim_quote="Hermes uses Postgres 16",
            quote_event_id=raw_id,
            search_terms=["Hermes"],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
    )
    return mem


def _invoke(args: list[str], db_path: Path) -> object:
    runner = CliRunner()
    return runner.invoke(
        main,
        ["--backend", "sqlite", "--db", str(db_path), "--namespace", "cli", *args],
    )


class TestRecallCmd:
    def test_text_output(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        result = _invoke(["recall", "Hermes"], db)
        assert result.exit_code == 0, result.output
        assert "Hermes" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        result = _invoke(["--json", "recall", "Hermes"], db)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["query"] == "Hermes"
        assert isinstance(payload["snippets"], list)
        assert len(payload["snippets"]) >= 1

    def test_no_match_message(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        result = _invoke(["recall", "AbsolutelyMissingTerm"], db)
        assert result.exit_code == 0
        assert "no snippets" in result.output.lower()

    def test_weights_validation(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        result = _invoke(["recall", "Hermes", "--weights", "0.5,0.5"], db)
        assert result.exit_code != 0
        assert "weights" in result.output.lower()

    def test_thread_id_pushes_active_entity(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        _invoke(["recall", "Hermes", "--thread-id", "thr-cli"], db)
        # Re-open via fresh backend instance to test persistence:
        mem2 = Memory(
            namespace="cli",
            backend=SqliteMemoryBackend(namespace="cli", db_path=db),
        )
        rows = mem2.list_active_entities("thr-cli")
        assert any(r.entity_id == "ent-hermes" for r in rows)


class TestThreadShow:
    def test_empty_thread(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        result = _invoke(["thread", "show", "missing-thread"], db)
        assert result.exit_code == 0
        assert "no active" in result.output.lower()

    def test_after_recall(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        _invoke(["recall", "Hermes", "--thread-id", "t1"], db)
        result = _invoke(["thread", "show", "t1"], db)
        assert result.exit_code == 0
        assert "ent-hermes"[:12] in result.output

    def test_json(self, tmp_path: Path) -> None:
        db = tmp_path / "r.sqlite"
        _seed(db)
        _invoke(["recall", "Hermes", "--thread-id", "t1"], db)
        result = _invoke(["--json", "thread", "show", "t1"], db)
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert payload[0]["entity_id"] == "ent-hermes"
