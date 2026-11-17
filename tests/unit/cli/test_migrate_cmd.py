"""``octop migrate`` end to end against a faked embedded runtime."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support import acting, embedded_ops
from octop.config import OctopConfig
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.utils.paths import PathLayout

AGENT = "agent-1"


class _Workspace:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def aexists(self, path: str) -> bool:
        return path in self.files

    async def awrite_text(self, path: str, content: str, *, force: bool = True) -> None:
        self.files[path] = content.encode("utf-8")

    async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
        self.files.update(pairs)


@pytest.fixture
def runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[SharedServices, _Workspace]]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    uid = services.repos.user_repo.create(username="owner", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=AGENT, user_id=uid, name="main")
    workspace = _Workspace()
    registry = SimpleNamespace(
        workspace_for_agent=lambda agent_id: workspace if agent_id == AGENT else None
    )
    server = SimpleNamespace(
        services=services, app_runtime=SimpleNamespace(agent_registry=registry)
    )

    @asynccontextmanager
    async def fake_runtime() -> Any:
        yield server

    monkeypatch.setattr(embedded_ops, "embedded_runtime", fake_runtime)
    monkeypatch.setattr(acting, "resolve_cli_acting_user_id", lambda *args, **kwargs: uid)
    monkeypatch.setattr("octop.cli.support.db.resolve_cli_locale", lambda: "en")
    try:
        yield services, workspace
    finally:
        db.close()


def _openclaw_home(tmp_path: Path) -> Path:
    home = tmp_path / "openclaw-home"
    (home / "workspace" / "skills" / "weekly-report").mkdir(parents=True)
    (home / "workspace" / "SOUL.md").write_text("soul", encoding="utf-8")
    (home / "workspace" / "skills" / "weekly-report" / "SKILL.md").write_text(
        "---\nname: weekly-report\n---\n", encoding="utf-8"
    )
    (home / "openclaw.json").write_text(
        """{
          models: { providers: { proxy: {
            baseUrl: "https://llm.example.com/v1", apiKey: "sk-proxy", models: [{ id: "m1" }],
          } } },
          agents: { defaults: { model: "proxy/m1" } },
          mcp: { servers: { fetch: { command: "uvx" }, legacy: { url: "https://x.example.com/sse" } } },
          channels: { telegram: { botToken: "tg" }, slack: { botToken: "xoxb" } },
        }""",
        encoding="utf-8",
    )
    return home


def _hermes_home(tmp_path: Path) -> Path:
    home = tmp_path / "hermes-home"
    (home / "memories").mkdir(parents=True)
    (home / "SOUL.md").write_text("hermes soul", encoding="utf-8")
    (home / "memories" / "MEMORY.md").write_text("one\n§\ntwo\n", encoding="utf-8")
    (home / "config.yaml").write_text(
        "model:\n  default: deepseek-chat\n  provider: deepseek\n", encoding="utf-8"
    )
    (home / ".env").write_text("DEEPSEEK_API_KEY=sk-ds\n", encoding="utf-8")
    return home


def test_openclaw_migration_writes_and_reports(
    tmp_path: Path, runtime: tuple[SharedServices, _Workspace]
) -> None:
    services, workspace = runtime
    home = _openclaw_home(tmp_path)

    result = CliRunner().invoke(
        cli, ["--agent", AGENT, "migrate", "openclaw", "--from", str(home)], env={"COLUMNS": "200"}
    )

    assert result.exit_code == 0, result.output
    assert "6 migrated, 0 skipped, 0 failed." in result.output
    assert "MCP server legacy uses the SSE transport" in result.output
    assert "Channel slack is not available in Octop." in result.output
    assert "restart it to load" in result.output
    assert "sk-proxy" not in result.output
    assert services.settings_repo.get_active_model() == ("proxy", "m1")
    assert sorted(workspace.files) == ["SOUL.md", "skills/weekly-report/SKILL.md"]
    [channel] = services.channel_repo.list_by_agent(AGENT)
    assert bool(channel.enabled) is False


def test_dry_run_writes_nothing(tmp_path: Path, runtime: tuple[SharedServices, _Workspace]) -> None:
    services, workspace = runtime
    result = CliRunner().invoke(
        cli,
        [
            "--agent",
            AGENT,
            "migrate",
            "openclaw",
            "--from",
            str(_openclaw_home(tmp_path)),
            "--dry-run",
        ],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    assert "would migrate" in result.output
    assert "6 to migrate, 0 skipped, 0 failed." in result.output
    assert "nothing was written" in result.output
    assert workspace.files == {}
    assert services.provider_repo.list_all() == []


def test_hermes_migration_with_skip_and_json(
    tmp_path: Path, runtime: tuple[SharedServices, _Workspace]
) -> None:
    services, workspace = runtime
    result = CliRunner().invoke(
        cli,
        [
            "--agent",
            AGENT,
            "--json",
            "migrate",
            "hermes",
            "--from",
            str(_hermes_home(tmp_path)),
            "--skip",
            "models",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["source"] == "hermes"
    assert [(i["section"], i["name"], i["status"]) for i in report["items"]] == [
        ("files", "SOUL.md", "migrated"),
        ("files", "MEMORY.md", "migrated"),
    ]
    assert workspace.files["MEMORY.md"] == b"one\n\ntwo\n"
    assert services.provider_repo.list_all() == []


def test_failed_items_set_the_exit_code(
    tmp_path: Path, runtime: tuple[SharedServices, _Workspace]
) -> None:
    home = tmp_path / "bad"
    home.mkdir()
    (home / "openclaw.json").write_text(
        '{ mcp: { servers: { remote: { url: "http://example.com/mcp", transport: "http" } } } }',
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli, ["--agent", AGENT, "migrate", "openclaw", "--from", str(home)], env={"COLUMNS": "200"}
    )
    assert result.exit_code == 1
    assert "0 migrated, 0 skipped, 1 failed." in result.output


def test_missing_source_is_a_clear_error(
    tmp_path: Path, runtime: tuple[SharedServices, _Workspace]
) -> None:
    result = CliRunner().invoke(
        cli, ["--agent", AGENT, "migrate", "hermes", "--from", str(tmp_path / "nope")]
    )
    assert result.exit_code == 1
    assert "No Hermes installation was found" in result.output


def test_empty_source_says_so(tmp_path: Path, runtime: tuple[SharedServices, _Workspace]) -> None:
    home = tmp_path / "empty"
    home.mkdir()
    (home / "openclaw.json").write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(
        cli, ["--agent", AGENT, "migrate", "openclaw", "--from", str(home)], env={"COLUMNS": "200"}
    )
    assert result.exit_code == 0, result.output
    assert "Nothing to migrate was found" in result.output


def test_unknown_agent_is_reported(
    tmp_path: Path, runtime: tuple[SharedServices, _Workspace]
) -> None:
    result = CliRunner().invoke(
        cli, ["--agent", "ghost", "migrate", "openclaw", "--from", str(_openclaw_home(tmp_path))]
    )
    assert result.exit_code == 1
    assert "Error" in result.output
