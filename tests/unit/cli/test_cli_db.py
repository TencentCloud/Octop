"""Tests for offline CLI DB helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _bootstrap(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--admin-username", "alice", "--admin-password", "TestPass12", "--yes"],
    )
    assert result.exit_code == 0, result.output


def test_list_agents_offline(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    db.close()

    from octop.cli.support.db import list_agents_offline

    rows = list_agents_offline(as_user="alice")
    assert len(rows) == 1
    assert rows[0]["agent_id"] == "ag1"


def test_list_threads_offline(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    tid = new_ulid()
    ThreadRepo(db).insert(
        thread_id=tid,
        agent_id="ag1",
        user_id=1,
        channel_type="dashboard",
        session_key="ag1:dashboard:1:dm",
        title="hello",
    )
    db.close()

    from octop.cli.support.db import list_threads_offline

    rows = list_threads_offline(agent_id="ag1", as_user="alice", limit=10)
    assert len(rows) == 1
    assert rows[0]["thread_id"] == tid
    assert rows[0]["has_messages"] is None


def test_agent_list_offline_flag(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    db.close()

    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    assert "ag1" in result.output


@pytest.fixture
def english_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.cli.support.db.resolve_cli_locale", lambda: "en")
    monkeypatch.setenv("COLUMNS", "200")


@pytest.mark.usefixtures("english_cli")
def test_agent_list_shows_which_agents_run_on_the_global_model(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    AgentRepo(db).create(agent_id="ag2", user_id=1, name="Coder", default_model="acme/big")
    db.close()
    runner = CliRunner()
    assert (
        runner.invoke(cli, ["models", "active", "--provider", "acme", "--model", "small"]).exit_code
        == 0
    )

    result = runner.invoke(cli, ["agent", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    rows = {line.split("│")[1].strip(): line for line in result.output.splitlines() if "│" in line}
    assert "(global: acme/small)" in rows["ag1"]
    assert "acme/big" in rows["ag2"]
    assert "global" not in rows["ag2"]


@pytest.mark.usefixtures("english_cli")
def test_agent_list_says_when_no_model_is_set_anywhere(fake_home: Path) -> None:
    _bootstrap(fake_home)
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    AgentRepo(db).create(agent_id="ag1", user_id=1, name="Bot")
    db.close()

    result = CliRunner().invoke(cli, ["agent", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    assert "(not set)" in result.output


@pytest.mark.usefixtures("english_cli")
def test_models_active_explains_an_unset_default(fake_home: Path) -> None:
    _bootstrap(fake_home)
    runner = CliRunner()

    unset = runner.invoke(cli, ["models", "active"])
    assert unset.exit_code == 0, unset.output
    assert unset.output.strip() != "/"
    assert "No global default model is set" in unset.output
    assert "octop models active --provider" in unset.output

    runner.invoke(cli, ["models", "active", "--provider", "acme", "--model", "small"])
    shown = runner.invoke(cli, ["models", "active"])
    assert shown.output.strip() == "acme / small"
