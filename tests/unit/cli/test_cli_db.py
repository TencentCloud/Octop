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
        ["init", "--admin-username", "alice", "--admin-password", "pw1234", "--yes"],
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
