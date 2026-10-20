"""Tests for ``memory candidate`` CLI subcommands.

We do NOT exercise the ``--dev-llm=ollama:...`` path here (that needs a
real Ollama and is covered in ``test_llm_client.py``). Instead we monkey-
patch ``_parse_dev_llm`` to return a ``MockLLMClient`` so the extract
flow runs end-to-end deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory


def _seed_raw_events(db_path: str) -> tuple[list[str], str]:
    """Seed two user_message events into a session and return (ids, session_id)."""
    mem = Memory(namespace="test", backend_config={"db_path": db_path})
    session_id = "sess-cli-1"
    ids: list[str] = []
    for content in (
        "decided to use Augment first, NOT replace mode",
        "alias table 默认大小是 10000",
    ):
        ev = mem.add_raw(
            content=content,
            event_type="user_message",
            host="manual",
            session_id=session_id,
        )
        ids.append(ev.id)
    return ids, session_id


def _mock_payload(quote_event_id: str, source_refs: list[str]) -> str:
    return json.dumps(
        {
            "candidates": [
                {
                    "candidate_id": "",
                    "candidate_type": "Decision",
                    "status": "pending",
                    "title": "mode decision",
                    "assertion": "decided to use Augment first, NOT replace mode",
                    "verbatim_quote": "decided to use Augment first, NOT replace mode",
                    "quote_event_id": quote_event_id,
                    "subject": {"name": "Project X", "entity_type": "Project", "entity_id_hint": ""},
                    "target_entities": [],
                    "source_refs": source_refs,
                    "confidence": "high",
                    "importance": "high",
                    "recommended_action": "promote",
                    "promotion_reason": "explicit",
                }
            ]
        }
    )


def _patch_dev_llm(monkeypatch, payload: str) -> None:
    """Force the CLI to use a MockLLMClient instead of real Ollama."""
    from octop_memory.adapters.cli import candidate_cmd
    from octop_memory.ports.llm import MockLLMClient

    def fake_parser(spec):
        return MockLLMClient(default_response=payload)

    monkeypatch.setattr(candidate_cmd, "_parse_dev_llm", fake_parser)


class TestCandidateExtractCLI:
    def test_extract_with_explicit_session_persists_candidates(self, tmp_path: Path, monkeypatch) -> None:
        db_path = str(tmp_path / "cli.db")
        ids, session_id = _seed_raw_events(db_path)
        _patch_dev_llm(monkeypatch, _mock_payload(ids[0], ids))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                session_id,
                "--dev-llm",
                "ollama:qwen3:4b",  # patched, not really invoked
            ],
        )
        assert result.exit_code == 0, result.output
        assert "candidates: 1" in result.output

        # Verify persisted
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        cands = mem.list_candidates(session_id=session_id)
        assert len(cands) == 1
        assert cands[0].assertion.startswith("decided to use Augment")

    def test_extract_with_no_persist_flag(self, tmp_path: Path, monkeypatch) -> None:
        db_path = str(tmp_path / "cli2.db")
        ids, session_id = _seed_raw_events(db_path)
        _patch_dev_llm(monkeypatch, _mock_payload(ids[0], ids))

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                session_id,
                "--dev-llm",
                "ollama:qwen3:4b",
                "--no-persist",
            ],
        )
        assert result.exit_code == 0, result.output

        # Output reports a candidate but DB stays empty.
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        assert mem.list_candidates(session_id=session_id) == []

    def test_extract_without_llm_returns_failure_reason(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli3.db")
        _seed_raw_events(db_path)
        # No --dev-llm passed → NoopLLMClient → graceful failure
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                "sess-cli-1",
            ],
        )
        # Exits OK because we don't treat "no LLM available" as a CLI error.
        assert result.exit_code == 0, result.output
        assert "FAILED" in result.output or "no LLM backend" in result.output

    def test_extract_unknown_session_exits_one(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli4.db")
        # No raw events at all.
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
            ],
        )
        # No session matched
        assert result.exit_code == 1


class TestCandidateListCLI:
    def test_list_filters_by_status(self, tmp_path: Path, monkeypatch) -> None:
        db_path = str(tmp_path / "cli5.db")
        ids, session_id = _seed_raw_events(db_path)
        _patch_dev_llm(monkeypatch, _mock_payload(ids[0], ids))

        runner = CliRunner()
        runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                session_id,
                "--dev-llm",
                "ollama:qwen3:4b",
            ],
        )

        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "list",
                "--status",
                "pending",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "[pending" in result.output

    def test_list_empty(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli6.db")
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db_path, "--namespace", "test", "candidate", "list"])
        assert result.exit_code == 0
        assert "No candidates found" in result.output

    def test_list_json_output(self, tmp_path: Path, monkeypatch) -> None:
        db_path = str(tmp_path / "cli7.db")
        ids, session_id = _seed_raw_events(db_path)
        _patch_dev_llm(monkeypatch, _mock_payload(ids[0], ids))

        runner = CliRunner()
        runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                session_id,
                "--dev-llm",
                "ollama:qwen3:4b",
            ],
        )

        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "--json",
                "candidate",
                "list",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) == 1


class TestCandidateShowCLI:
    def test_show_returns_full_candidate(self, tmp_path: Path, monkeypatch) -> None:
        db_path = str(tmp_path / "cli8.db")
        ids, session_id = _seed_raw_events(db_path)
        _patch_dev_llm(monkeypatch, _mock_payload(ids[0], ids))

        runner = CliRunner()
        runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                session_id,
                "--dev-llm",
                "ollama:qwen3:4b",
            ],
        )

        # Find the candidate id we just created
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        cand_id = mem.list_candidates(session_id=session_id)[0].id

        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "show",
                cand_id,
            ],
        )
        assert result.exit_code == 0, result.output
        assert "id            :" in result.output
        assert "verbatim_quote:" in result.output

    def test_show_missing_id_exits_one(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli9.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "show",
                "no-such-id",
            ],
        )
        assert result.exit_code == 1


class TestDevLlmFlagParser:
    def test_invalid_provider_rejected(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli10.db")
        _seed_raw_events(db_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                "sess-cli-1",
                "--dev-llm",
                "openai:gpt-4",
            ],
        )
        assert result.exit_code != 0
        assert "ollama" in result.output.lower()

    def test_malformed_spec_rejected(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli11.db")
        _seed_raw_events(db_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                "sess-cli-1",
                "--dev-llm",
                "no-colon-here",
            ],
        )
        assert result.exit_code != 0


class TestCandidatePromoteCLI:
    """Smoke-tests for ``memory candidate promote`` (M2.5)."""

    def _seed_pending_candidate(self, tmp_path: Path, monkeypatch) -> tuple[str, str, str]:
        """Run extract via the mocked LLM to leave a pending candidate; return (db, namespace, candidate_id)."""
        db_path = str(tmp_path / "promote.db")
        ids, session_id = _seed_raw_events(db_path)
        _patch_dev_llm(monkeypatch, _mock_payload(ids[0], ids))
        runner = CliRunner()
        runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "candidate",
                "extract",
                "--session",
                session_id,
                "--dev-llm",
                "ollama:dummy",
            ],
        )
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        cands = mem.list_candidates(session_id=session_id)
        assert cands, "expected extract to leave at least one candidate"
        return db_path, "test", cands[0].id

    def test_promote_all_pending_writes_atom(self, tmp_path: Path, monkeypatch) -> None:
        db_path, ns, cand_id = self._seed_pending_candidate(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", ns, "candidate", "promote"],
        )
        assert result.exit_code == 0, result.output
        assert "promoted=" in result.output

        mem = Memory(namespace=ns, backend_config={"db_path": db_path})
        # Atom landed
        atoms = mem.list_atoms()
        assert len(atoms) >= 1
        # Candidate flipped to promoted
        c = mem.get_candidate(cand_id)
        assert c is not None and c.status == "promoted"
        # Journal recorded
        journal = mem.list_journal(target_candidate_id=cand_id)
        assert any(j.action == "promote" for j in journal)

    def test_promote_specific_candidate_id(self, tmp_path: Path, monkeypatch) -> None:
        db_path, ns, cand_id = self._seed_pending_candidate(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", ns, "candidate", "promote", "--candidate-id", cand_id],
        )
        assert result.exit_code == 0, result.output
        mem = Memory(namespace=ns, backend_config={"db_path": db_path})
        c = mem.get_candidate(cand_id)
        assert c is not None and c.status == "promoted"

    def test_promote_unknown_candidate_id_errors(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "promote_missing.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", "test", "candidate", "promote", "--candidate-id", "nope"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_promote_json_output(self, tmp_path: Path, monkeypatch) -> None:
        db_path, ns, _ = self._seed_pending_candidate(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", ns, "--json", "candidate", "promote"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "promoted" in payload
        assert "decisions" in payload
        assert payload["promoted"] >= 1
        assert payload["decisions"][0]["outcome"] in {"promote", "merge", "drop", "needs_review", "conflict"}

    def test_dry_run_not_yet_implemented(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "promote_dry.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", "test", "candidate", "promote", "--dry-run"],
        )
        assert result.exit_code == 2
        assert "not yet implemented" in result.output.lower() or "not yet implemented" in (result.stderr or "")
