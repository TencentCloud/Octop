"""tests/unit/test_migration.py

Unit tests for the LightClaw → Octop migration layer.
Covers: field_mapping, archive_reader, env_migrator, uploads_migrator,
memory_migrator, and finnie_importer (lightweight with in-memory stubs).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip(members: dict[str, bytes]) -> bytes:
    """Build a ZIP archive from a {member_name: bytes} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _manifest_bytes(**overrides) -> bytes:
    default = {
        "format": "1",
        "source": "lightclaw",
        "agent_name": "Test Agent",
        "active_provider": "openai",
        "active_model": "gpt-4o",
        "providers_count": 1,
        "cron_jobs_count": 0,
        "uploads_count": 0,
        "workspace_files": [],
        "memory_files": [],
        "sessions_index_included": False,
        "messages_db_included": False,
        "env_keys": [],
        "channels": [],
        "extra": {},
    }
    default.update(overrides)
    return json.dumps(default).encode()


# ---------------------------------------------------------------------------
# field_mapping
# ---------------------------------------------------------------------------


class TestFieldMapping:
    def test_map_provider_kind_known(self) -> None:
        from octop.infra.migration.field_mapping import map_provider_kind

        assert map_provider_kind("OpenAI") == "openai"
        assert map_provider_kind("Anthropic") == "anthropic"
        assert map_provider_kind("OLLAMA") == "ollama"

    def test_map_provider_kind_unknown_passthrough(self) -> None:
        from octop.infra.migration.field_mapping import map_provider_kind

        assert map_provider_kind("my-custom-llm") == "my-custom-llm"

    def test_map_channel_kind(self) -> None:
        from octop.infra.migration.field_mapping import map_channel_kind

        assert map_channel_kind("feishu") == "feishu"
        assert map_channel_kind("QQBOT") == "qq"
        assert map_channel_kind("nonexistent") is None

    def test_extract_providers_empty(self) -> None:
        from octop.infra.migration.field_mapping import extract_providers

        assert extract_providers({}) == []
        assert extract_providers({"models": {}}) == []

    def test_extract_providers_standard(self) -> None:
        from octop.infra.migration.field_mapping import extract_providers

        cfg = {
            "models": {
                "providers": {
                    "openai": {"apiKey": "sk-test-key", "models": ["gpt-4o"]},
                    "anthropic": {"api_key": "sk-ant-key", "baseUrl": "https://api.anthropic.com"},
                }
            }
        }
        entries = extract_providers(cfg)
        assert len(entries) == 2
        by_kind = {e["kind"]: e for e in entries}
        assert "openai" in by_kind and "anthropic" in by_kind
        assert by_kind["openai"]["api_key"] == "sk-test-key"
        assert by_kind["anthropic"]["api_key"] == "sk-ant-key"
        assert by_kind["anthropic"]["base_url"] == "https://api.anthropic.com"

    def test_extract_providers_empty_api_key(self) -> None:
        from octop.infra.migration.field_mapping import extract_providers

        cfg = {
            "models": {
                "providers": {
                    "openai": {"apiKey": "", "models": ["gpt-4o"]},
                }
            }
        }
        entries = extract_providers(cfg)
        assert entries[0]["api_key"] is None

    def test_extract_active_model(self) -> None:
        from octop.infra.migration.field_mapping import extract_active_model

        cfg = {"models": {"activeLlm": "openai/gpt-4o"}}
        pid, model = extract_active_model(cfg)
        assert pid == "openai"
        assert model == "gpt-4o"

    def test_extract_active_model_missing(self) -> None:
        from octop.infra.migration.field_mapping import extract_active_model

        assert extract_active_model({}) == ("", "")
        assert extract_active_model({"models": {"activeLlm": "no-slash"}}) == ("", "")

    def test_build_octop_cron_trigger_valid(self) -> None:
        from octop.infra.migration.field_mapping import build_octop_cron_trigger

        spec = {"cron": "0 8 * * 1-5"}
        assert build_octop_cron_trigger(spec) == "0 8 * * 1-5"

    def test_build_octop_cron_trigger_invalid_falls_back(self) -> None:
        from octop.infra.migration.field_mapping import build_octop_cron_trigger

        # 7-field cron (not standard 5-field)
        spec = {"cron": "0 0 8 * * 1-5 *"}
        result = build_octop_cron_trigger(spec)
        assert result == "0 9 * * *"

    def test_extract_job_prompt_text_type(self) -> None:
        from octop.infra.migration.field_mapping import extract_job_prompt

        job = {"task_type": "text", "text": "Daily standup"}
        assert extract_job_prompt(job) == "Daily standup"

    def test_extract_job_prompt_agent_type(self) -> None:
        from octop.infra.migration.field_mapping import extract_job_prompt

        job = {"task_type": "agent", "request": {"input": "Summarize news"}}
        assert extract_job_prompt(job) == "Summarize news"

    def test_extract_job_prompt_empty(self) -> None:
        from octop.infra.migration.field_mapping import extract_job_prompt

        assert extract_job_prompt({}) == ""

    def test_extract_job_prompt_message_array(self) -> None:
        # Real-world finnie format: request.input is a list of message objects
        from octop.infra.migration.field_mapping import extract_job_prompt

        job = {
            "task_type": "agent",
            "name": "双子座每日运势",
            "request": {
                "input": [
                    {
                        "role": "user",
                        "type": "message",
                        "content": [
                            {"type": "text", "text": "请查询今日双子座运势"},
                        ],
                    }
                ]
            },
        }
        assert extract_job_prompt(job) == "请查询今日双子座运势"

    def test_extract_job_prompt_name_fallback(self) -> None:
        from octop.infra.migration.field_mapping import extract_job_prompt

        # agent type with no request → falls back to name
        job = {"task_type": "agent", "name": "Daily summary"}
        assert extract_job_prompt(job) == "Daily summary"

    def test_extract_job_prompt_agent_no_request_no_name(self) -> None:
        from octop.infra.migration.field_mapping import extract_job_prompt

        # Completely empty agent job → returns empty string (will be skipped by importer)
        assert extract_job_prompt({"task_type": "agent"}) == ""

    def test_extract_disabled_skills_empty(self) -> None:
        from octop.infra.migration.field_mapping import extract_disabled_skills

        assert extract_disabled_skills({}) == []
        assert extract_disabled_skills({"skills": {}}) == []
        assert extract_disabled_skills({"skills": {"entries": {}}}) == []

    def test_extract_disabled_skills_mixed(self) -> None:
        from octop.infra.migration.field_mapping import extract_disabled_skills

        cfg = {
            "skills": {
                "entries": {
                    "pdf": {"enabled": True},
                    "xlsx": {"enabled": False},
                    "web-search": {"enabled": False},
                    "code-runner": {"enabled": True},
                }
            }
        }
        result = extract_disabled_skills(cfg)
        assert sorted(result) == ["web-search", "xlsx"]

    def test_extract_disabled_skills_all_enabled(self) -> None:
        from octop.infra.migration.field_mapping import extract_disabled_skills

        cfg = {
            "skills": {
                "entries": {
                    "pdf": {"enabled": True},
                    "xlsx": {"enabled": True},
                }
            }
        }
        assert extract_disabled_skills(cfg) == []


# ---------------------------------------------------------------------------
# archive_reader
# ---------------------------------------------------------------------------


class TestArchiveReader:
    def test_valid_archive(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        z = _make_zip({"manifest.json": _manifest_bytes()})
        with ArchiveReader(z) as reader:
            manifest = reader.validate()
            assert manifest.source == "lightclaw"
            assert manifest.format == "1"

    def test_missing_manifest_raises(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        z = _make_zip({"foo.txt": b"bar"})
        with ArchiveReader(z) as reader, pytest.raises(ValueError, match="manifest.json"):
            reader.validate()

    def test_wrong_format_version_raises(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        z = _make_zip({"manifest.json": _manifest_bytes(format="99")})
        with (
            ArchiveReader(z) as reader,
            pytest.raises(ValueError, match="Unsupported export format"),
        ):
            reader.validate()

    def test_wrong_source_raises(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        z = _make_zip({"manifest.json": _manifest_bytes(source="unknown")})
        with (
            ArchiveReader(z) as reader,
            pytest.raises(ValueError, match="Unsupported export source"),
        ):
            reader.validate()

    def test_path_traversal_raises(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        # Manually build a ZIP with a traversal path
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", _manifest_bytes().decode())
            zf.writestr("../evil.txt", "oops")
        z = buf.getvalue()

        with ArchiveReader(z) as reader, pytest.raises(ValueError, match="traversal"):
            reader.validate()

    def test_not_a_zip_raises(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        with pytest.raises(ValueError, match="not a valid zip"), ArchiveReader(b"not a zip"):
            pass

    def test_read_json(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        data = {"hello": "world"}
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "config/lightclaw.json": json.dumps(data).encode(),
            }
        )
        with ArchiveReader(z) as reader:
            reader.validate()
            result = reader.read_json("config/lightclaw.json")
            assert result == data

    def test_iter_prefix(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "workspace/SOUL.md": b"# Soul",
                "workspace/MEMORY.md": b"# Memory",
                "uploads/file.txt": b"content",
            }
        )
        with ArchiveReader(z) as reader:
            reader.validate()
            ws = dict(reader.iter_prefix("workspace/"))
            assert "workspace/SOUL.md" in ws
            assert "workspace/MEMORY.md" in ws
            assert "uploads/file.txt" not in ws

    def test_has_member(self) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader

        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "config/jobs.json": b"{}",
            }
        )
        with ArchiveReader(z) as reader:
            reader.validate()
            assert reader.has_member("config/jobs.json")
            assert not reader.has_member("nonexistent.json")


# ---------------------------------------------------------------------------
# env_migrator
# ---------------------------------------------------------------------------


class TestEnvMigrator:
    def test_no_env_section(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.env_migrator import migrate_env
        from octop.infra.migration.report import MigrationReport

        z = _make_zip({"manifest.json": _manifest_bytes()})
        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            migrate_env(reader, tmp_path / "env", report)
        assert report.env_keys_noted == []

    def test_env_keys_noted_no_values(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.env_migrator import migrate_env
        from octop.infra.migration.report import MigrationReport

        env_scaffold = "OPENAI_API_KEY=\nMY_SECRET=\n"
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "env": env_scaffold.encode(),
            }
        )
        env_path = tmp_path / "env"
        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            migrate_env(reader, env_path, report)
        assert "OPENAI_API_KEY" in report.env_keys_noted
        assert "MY_SECRET" in report.env_keys_noted
        # env file written but values should be empty
        from octop.infra.utils.env_file import load_env_file

        loaded = load_env_file(env_path)
        assert loaded["OPENAI_API_KEY"] == ""

    def test_existing_values_preserved(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.env_migrator import migrate_env
        from octop.infra.migration.report import MigrationReport
        from octop.infra.utils.env_file import load_env_file, save_env_file

        env_path = tmp_path / "env"
        save_env_file(env_path, {"OPENAI_API_KEY": "sk-existing", "EXTRA": "val"})

        env_scaffold = "OPENAI_API_KEY=\nNEW_KEY=\n"
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "env": env_scaffold.encode(),
            }
        )
        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            migrate_env(reader, env_path, report)

        loaded = load_env_file(env_path)
        # Existing value must not be overwritten
        assert loaded["OPENAI_API_KEY"] == "sk-existing"
        # New key added with empty value
        assert loaded["NEW_KEY"] == ""
        # Unrelated key preserved
        assert loaded["EXTRA"] == "val"


# ---------------------------------------------------------------------------
# uploads_migrator (async)
# ---------------------------------------------------------------------------


class TestUploadsMigrator:
    @pytest.mark.asyncio
    async def test_migrate_uploads_basic(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.report import MigrationReport
        from octop.infra.migration.uploads_migrator import migrate_uploads

        ws_dir = tmp_path / "agent_ws"
        ws_dir.mkdir()

        file_bytes = b"Hello PDF content"
        meta = {"filename": "report.pdf", "media_type": "application/pdf"}
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "uploads/abc123.pdf": file_bytes,
                "uploads/.meta/abc123.pdf.json": json.dumps(meta).encode(),
            }
        )

        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            await migrate_uploads(reader, ws_dir, report)

        assert report.uploads_written == 1
        assert report.uploads_skipped == 0
        # File written to inbound/
        inbound_files = list((ws_dir / "inbound").iterdir())
        assert len(inbound_files) == 1
        assert inbound_files[0].read_bytes() == file_bytes

    @pytest.mark.asyncio
    async def test_large_file_skipped(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.report import MigrationReport
        from octop.infra.migration.uploads_migrator import _MAX_FILE_BYTES, migrate_uploads

        ws_dir = tmp_path / "agent_ws"
        ws_dir.mkdir()

        big = b"x" * (_MAX_FILE_BYTES + 1)
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "uploads/big.pdf": big,
            }
        )

        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            await migrate_uploads(reader, ws_dir, report)

        assert report.uploads_skipped == 1
        assert report.uploads_written == 0
        assert not (ws_dir / "inbound").exists() or not list((ws_dir / "inbound").iterdir())

    @pytest.mark.asyncio
    async def test_disallowed_extension_skipped(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.report import MigrationReport
        from octop.infra.migration.uploads_migrator import migrate_uploads

        ws_dir = tmp_path / "agent_ws"
        ws_dir.mkdir()

        meta = {"filename": "script.exe", "media_type": "application/octet-stream"}
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "uploads/exec.exe": b"MZ",
                "uploads/.meta/exec.exe.json": json.dumps(meta).encode(),
            }
        )

        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            await migrate_uploads(reader, ws_dir, report)

        assert report.uploads_skipped == 1
        assert not (ws_dir / "inbound").exists() or not list((ws_dir / "inbound").iterdir())


# ---------------------------------------------------------------------------
# memory_migrator (async, unit-level)
# ---------------------------------------------------------------------------


class TestMemoryMigrator:
    def _make_session_index(self, entries: list[dict]) -> bytes:
        return json.dumps({"entries": entries}).encode()

    def _make_jsonl(self, messages: list[dict[str, Any]]) -> bytes:
        lines = []
        for msg in messages:
            event = {"type": "message", "message": msg}
            lines.append(json.dumps(event))
        return "\n".join(lines).encode()

    @pytest.mark.asyncio
    async def test_basic_session_import(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.memory_migrator import migrate_sessions
        from octop.infra.migration.report import MigrationReport

        jsonl = self._make_jsonl(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )
        index = self._make_session_index(
            [{"filename": "session1.jsonl", "session_id": "sess1", "channel": "dashboard"}]
        )

        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "sessions/session_index.json": index,
                "sessions/session1.jsonl": jsonl,
            }
        )

        thread_repo = MagicMock()
        thread_repo.insert = MagicMock()
        session_repo = MagicMock()
        session_repo.get = MagicMock(return_value=None)
        session_repo.upsert = MagicMock()

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()

        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            await migrate_sessions(
                reader,
                agent_id="agent_test",
                user_id=1,
                workspace_dir=workspace_dir,
                thread_repo=thread_repo,
                session_repo=session_repo,
                report=report,
            )

        assert report.sessions_imported == 1
        assert report.sessions_skipped == 0
        thread_repo.insert.assert_called_once()
        session_repo.upsert.assert_called_once()

        # JSONL file should have been copied to workspace
        assert (workspace_dir / "sessions" / "session1.jsonl").exists()

        # checkpoints.sqlite should exist
        assert (workspace_dir / "checkpoints.sqlite").exists()

    @pytest.mark.asyncio
    async def test_checkpoint_readable_by_langgraph(self, tmp_path: Path) -> None:
        """Verify the written checkpoint can be deserialized by LangGraph's serde
        and that messages are proper BaseMessage instances (not plain dicts).

        This is the key requirement for the LLM to recognise migrated conversation
        history when the user continues a chat after import.
        """
        from langchain_core.messages import BaseMessage
        from langgraph.checkpoint.sqlite import SqliteSaver

        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.memory_migrator import migrate_sessions
        from octop.infra.migration.report import MigrationReport

        jsonl = self._make_jsonl(
            [
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "It is 4."},
            ]
        )
        index = self._make_session_index(
            [{"filename": "sess_lc.jsonl", "session_id": "sess_lc", "channel": "dashboard"}]
        )
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "sessions/session_index.json": index,
                "sessions/sess_lc.jsonl": jsonl,
            }
        )

        thread_repo = MagicMock()
        thread_repo.insert = MagicMock()
        session_repo = MagicMock()
        session_repo.get = MagicMock(return_value=None)
        session_repo.upsert = MagicMock()

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()

        inserted_thread_id: list[str] = []

        def _capture_insert(**kwargs: Any) -> None:
            inserted_thread_id.append(kwargs["thread_id"])

        thread_repo.insert.side_effect = _capture_insert

        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            await migrate_sessions(
                reader,
                agent_id="agent_lc_test",
                user_id=1,
                workspace_dir=workspace_dir,
                thread_repo=thread_repo,
                session_repo=session_repo,
                report=report,
            )

        assert report.sessions_imported == 1
        assert inserted_thread_id, "thread_repo.insert should have been called"
        thread_id = inserted_thread_id[0]

        db_path = workspace_dir / "checkpoints.sqlite"
        assert db_path.exists(), "checkpoints.sqlite must be created"

        with SqliteSaver.from_conn_string(str(db_path)) as saver:
            config = {"configurable": {"thread_id": thread_id}}
            tuples = list(saver.list(config, limit=1))
            assert tuples, "checkpoint row must exist for the migrated thread"
            checkpoint = tuples[0].checkpoint
            msgs = checkpoint.get("channel_values", {}).get("messages", [])
            assert msgs, "checkpoint must contain messages"
            assert all(
                isinstance(m, BaseMessage) for m in msgs
            ), "all messages must be BaseMessage instances, not plain dicts"
            assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_empty_session_skipped(self, tmp_path: Path) -> None:
        from octop.infra.migration.archive_reader import ArchiveReader
        from octop.infra.migration.memory_migrator import migrate_sessions
        from octop.infra.migration.report import MigrationReport

        index = self._make_session_index(
            [{"filename": "empty.jsonl", "session_id": "s2", "channel": "dashboard"}]
        )
        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "sessions/session_index.json": index,
                "sessions/empty.jsonl": b"",
            }
        )

        thread_repo = MagicMock()
        session_repo = MagicMock()
        session_repo.get = MagicMock(return_value=None)

        with ArchiveReader(z) as reader:
            reader.validate()
            report = MigrationReport()
            await migrate_sessions(
                reader,
                agent_id="agent_test",
                user_id=1,
                workspace_dir=tmp_path / "ws",
                thread_repo=thread_repo,
                session_repo=session_repo,
                report=report,
            )

        assert report.sessions_imported == 0


# ---------------------------------------------------------------------------
# finnie_importer (lightweight integration-like, all I/O mocked)
# ---------------------------------------------------------------------------


class TestFinnniImporter:
    def _make_full_archive(self, *, include_skills: bool = False) -> bytes:
        lc_config = {
            "models": {
                "activeLlm": "openai/gpt-4o",
                "providers": {"openai": {"apiKey": "sk-live-key", "models": ["gpt-4o"]}},
            },
            "channels": {},
            "skills": {
                "entries": {
                    # pdf is enabled — should be written
                    "pdf": {"enabled": True},
                    # xlsx is disabled — should be skipped
                    "xlsx": {"enabled": False},
                }
            },
        }
        jobs = {
            "jobs": [
                {
                    "id": "job1",
                    "schedule": {"cron": "0 9 * * *"},
                    "task_type": "text",
                    "text": "Good morning!",
                }
            ]
        }
        members: dict[str, bytes] = {
            "manifest.json": _manifest_bytes(cron_jobs_count=1),
            "config/lightclaw.json": json.dumps(lc_config).encode(),
            "config/jobs.json": json.dumps(jobs).encode(),
            "workspace/SOUL.md": b"# Soul\nYou are a helpful assistant.",
            "workspace/USER.md": b"# User\nUser profile.",
            "workspace/AGENTS.md": b"# Agents\nBehavior rules.",
            "sessions/session_index.json": json.dumps({"entries": []}).encode(),
        }
        if include_skills:
            members["workspace/skills/pdf/SKILL.md"] = b"# PDF Skill"
            members["workspace/skills/xlsx/SKILL.md"] = b"# XLSX Skill"
            members["workspace/skills/web-search/SKILL.md"] = b"# Web Search Skill"
        return _make_zip(members)

    def _make_repos(self) -> tuple:
        agent_repo = MagicMock()
        agent_repo.create = MagicMock()
        agent_repo.get = MagicMock(return_value=None)
        cron_repo = MagicMock()
        cron_repo.create = MagicMock()
        thread_repo = MagicMock()
        thread_repo.insert = MagicMock()
        session_repo = MagicMock()
        session_repo.get = MagicMock(return_value=None)
        session_repo.upsert = MagicMock()
        user_repo = MagicMock()
        return agent_repo, cron_repo, thread_repo, session_repo, user_repo

    @pytest.mark.asyncio
    async def test_run_import_creates_agent(self, tmp_path: Path) -> None:
        from octop.infra.migration.finnie_importer import run_import

        agent_repo, cron_repo, thread_repo, session_repo, user_repo = self._make_repos()
        ws_dir = tmp_path / "agent_ws"

        paths_mock = MagicMock()
        paths_mock.root = tmp_path
        paths_mock.ensure_agent_workspace = MagicMock(return_value=ws_dir)
        ws_dir.mkdir()

        zip_bytes = self._make_full_archive()
        report = await run_import(
            zip_bytes,
            user_id=1,
            paths=paths_mock,
            agent_repo=agent_repo,
            cron_repo=cron_repo,
            thread_repo=thread_repo,
            session_repo=session_repo,
            user_repo=user_repo,
        )

        assert not report.has_errors
        assert report.agent_created
        assert report.workspace_files_written >= 3  # SOUL.md + USER.md + AGENTS.md
        assert report.cron_jobs_imported == 1
        agent_repo.create.assert_called_once()

        # Files written directly to disk — verify actual presence
        assert (ws_dir / "SOUL.md").exists()
        assert (ws_dir / "USER.md").exists()
        assert (ws_dir / "AGENTS.md").exists()

        # default_model extracted from activeLlm
        call_kwargs = agent_repo.create.call_args.kwargs
        assert call_kwargs.get("default_model") == "openai/gpt-4o"

        # config_json should NOT contain skills_disabled — disabled skills are
        # simply not written to the workspace at all.
        assert call_kwargs.get("config_json") is None

        # Identity files reported
        assert "SOUL.md" in report.identity_files_written
        assert "USER.md" in report.identity_files_written
        assert "AGENTS.md" in report.identity_files_written

    @pytest.mark.asyncio
    async def test_run_import_with_skills(self, tmp_path: Path) -> None:
        """Enabled skills are written to disk; disabled skills are skipped."""
        from octop.infra.migration.finnie_importer import run_import

        agent_repo, cron_repo, thread_repo, session_repo, user_repo = self._make_repos()
        ws_dir = tmp_path / "agent_ws"

        paths_mock = MagicMock()
        paths_mock.root = tmp_path
        paths_mock.ensure_agent_workspace = MagicMock(return_value=ws_dir)
        ws_dir.mkdir()

        zip_bytes = self._make_full_archive(include_skills=True)
        report = await run_import(
            zip_bytes,
            user_id=1,
            paths=paths_mock,
            agent_repo=agent_repo,
            cron_repo=cron_repo,
            thread_repo=thread_repo,
            session_repo=session_repo,
            user_repo=user_repo,
        )

        assert not report.has_errors
        # pdf (enabled) + web-search (not in entries → default enabled) written
        # xlsx (disabled) skipped
        assert report.skills_imported == 2
        assert (ws_dir / "skills" / "pdf" / "SKILL.md").exists()
        assert (ws_dir / "skills" / "web-search" / "SKILL.md").exists()
        # xlsx is disabled — must NOT exist on disk
        assert not (ws_dir / "skills" / "xlsx").exists()

    @pytest.mark.asyncio
    async def test_run_import_no_lightclaw_config(self, tmp_path: Path) -> None:
        """Import succeeds gracefully when config/lightclaw.json is absent."""
        from octop.infra.migration.finnie_importer import run_import

        agent_repo, _, thread_repo, session_repo, _ = self._make_repos()
        ws_dir = tmp_path / "agent_ws"

        paths_mock = MagicMock()
        paths_mock.root = tmp_path
        paths_mock.ensure_agent_workspace = MagicMock(return_value=ws_dir)
        ws_dir.mkdir()

        z = _make_zip(
            {
                "manifest.json": _manifest_bytes(),
                "workspace/SOUL.md": b"# Soul",
                "sessions/session_index.json": json.dumps({"entries": []}).encode(),
            }
        )
        report = await run_import(
            z,
            user_id=1,
            paths=paths_mock,
            agent_repo=agent_repo,
            cron_repo=MagicMock(),
            thread_repo=thread_repo,
            session_repo=session_repo,
            user_repo=MagicMock(),
        )

        assert not report.has_errors
        assert report.agent_created
        assert (ws_dir / "SOUL.md").exists()
        # No config → default_model should fall back to "auto"
        call_kwargs = agent_repo.create.call_args.kwargs
        assert call_kwargs.get("default_model") == "auto"
        assert call_kwargs.get("config_json") is None

    @pytest.mark.asyncio
    async def test_run_import_invalid_archive_returns_error(self, tmp_path: Path) -> None:
        from octop.infra.migration.finnie_importer import run_import

        paths_mock = MagicMock()
        paths_mock.root = tmp_path

        report = await run_import(
            b"not a zip",
            user_id=1,
            paths=paths_mock,
            agent_repo=MagicMock(),
            cron_repo=MagicMock(),
            thread_repo=MagicMock(),
            session_repo=MagicMock(),
            user_repo=MagicMock(),
        )

        assert report.has_errors
        assert "validation failed" in report.errors[0].lower()
