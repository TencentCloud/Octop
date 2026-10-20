"""Smoke tests for the M5 CLI commands (export / import / migrate / gc)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import (
    AtomCard,
    Candidate,
    Entity,
    RawEvent,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _seed(db_path: Path, namespace: str = "cli") -> Memory:
    backend = SqliteMemoryBackend(namespace=namespace, db_path=db_path)
    memory = Memory(namespace=namespace, backend=backend)
    when = _now()
    memory.add_raw_batch(
        [
            RawEvent(
                id="r1",
                host="t",
                session_id="s",
                thread_id=None,
                user=None,
                timestamp=when,
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
            created_at=when,
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
            occurred_at=when,
            confidence="high",
            importance="high",
            created_at=when,
        )
    )
    return memory


def _invoke(args: list[str], db_path: Path, namespace: str = "cli") -> object:
    runner = CliRunner()
    return runner.invoke(
        main,
        ["--backend", "sqlite", "--db", str(db_path), "--namespace", namespace, *args],
    )


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------


class TestExportCmd:
    def test_text(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        _seed(db)._backend.close()
        out = tmp_path / "dump.jsonl"
        result = _invoke(["export", "--out", str(out)], db)
        assert result.exit_code == 0, result.output
        assert "exported namespace cli" in result.output
        assert out.exists() and out.stat().st_size > 0

    def test_json(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        _seed(db)._backend.close()
        out = tmp_path / "dump.jsonl"
        result = _invoke(["--json", "export", "--out", str(out)], db)
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["namespace"] == "cli"
        assert payload["total_rows"] >= 3


class TestImportCmd:
    def test_roundtrip(self, tmp_path: Path) -> None:
        src_db = tmp_path / "src.sqlite"
        dst_db = tmp_path / "dst.sqlite"
        _seed(src_db, "src")._backend.close()

        out = tmp_path / "dump.jsonl"
        result = _invoke(["export", "--out", str(out)], src_db, namespace="src")
        assert result.exit_code == 0

        result = _invoke(["import", "--from", str(out)], dst_db, namespace="dst")
        assert result.exit_code == 0
        assert "imported" in result.output

        m = Memory(namespace="dst", backend=SqliteMemoryBackend(namespace="dst", db_path=dst_db))
        try:
            assert len(m.list_atoms()) == 1
        finally:
            m._backend.close()


# ---------------------------------------------------------------------------
# migrate (rename + dry-run + report-json)
# ---------------------------------------------------------------------------


class TestMigrateCmd:
    def test_dry_run_no_op(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        _seed(db, "oc")._backend.close()
        result = _invoke(
            ["migrate", "--db", str(db), "--from-namespace", "oc", "--to-namespace", "hermes", "--dry-run"],
            db,
            namespace="oc",
        )
        assert result.exit_code == 0
        assert "Migration plan: rename" in result.output
        # Source should be untouched after dry-run.
        m = Memory(namespace="oc", backend=SqliteMemoryBackend(namespace="oc", db_path=db))
        try:
            assert len(m.list_atoms()) == 1
        finally:
            m._backend.close()

    def test_apply(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        _seed(db, "oc")._backend.close()
        result = _invoke(
            ["migrate", "--db", str(db), "--from-namespace", "oc", "--to-namespace", "hermes"],
            db,
            namespace="oc",
        )
        assert result.exit_code == 0
        assert "applied:" in result.output
        # Source ns should be empty; data lives under "hermes".
        m = Memory(namespace="hermes", backend=SqliteMemoryBackend(namespace="hermes", db_path=db))
        try:
            assert len(m.list_atoms()) == 1
        finally:
            m._backend.close()

    def test_report_json(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        _seed(db, "oc")._backend.close()
        report = tmp_path / "plan.json"
        result = _invoke(
            [
                "migrate",
                "--db",
                str(db),
                "--from-namespace",
                "oc",
                "--to-namespace",
                "hermes",
                "--dry-run",
                "--report-json",
                str(report),
            ],
            db,
            namespace="oc",
        )
        assert result.exit_code == 0
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["src_namespace"] == "oc"
        assert payload["dst_namespace"] == "hermes"


# ---------------------------------------------------------------------------
# gc
# ---------------------------------------------------------------------------


class TestGcCmd:
    def test_run_clean_namespace(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        _seed(db)._backend.close()
        result = _invoke(["gc", "run"], db)
        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_dry_run(self, tmp_path: Path) -> None:
        db = tmp_path / "src.sqlite"
        m = _seed(db)
        # Add an old rejected candidate so we have something to count.
        old = _now() - timedelta(days=60)
        m.add_raw_batch(
            [
                RawEvent(
                    id="r-old",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="old",
                    payload={},
                )
            ]
        )
        m.add_candidate(
            Candidate(
                id="c-old",
                raw_event_ids=["r-old"],
                candidate_type="Fact",
                status="rejected",
                title="t",
                assertion="x",
                verbatim_quote="x",
                quote_event_id="r-old",
                subject_name="x",
                subject_entity_type="Fact",
                target_entity_id=None,
                confidence="low",
                importance="low",
                recommended_action="reject",
                promotion_reason="",
                extractor_version="v2.1",
                created_at=old,
                session_id="s",
                decided_at=old,
            )
        )
        m._backend.close()

        result = _invoke(["--json", "gc", "run", "--dry-run"], db)
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["dry_run"] is True
        assert payload["rejected_candidates_deleted"] == 1

        # Re-open and verify nothing was actually deleted.
        m2 = Memory(namespace="cli", backend=SqliteMemoryBackend(namespace="cli", db_path=db))
        try:
            assert len(m2.list_candidates(limit=10)) == 1
        finally:
            m2._backend.close()
