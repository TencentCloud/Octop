"""Tests for the `octop chats` group."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from octop.cli.main import cli


def test_chats_group_help_lists_all_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["chats", "--help"])
    assert result.exit_code == 0
    for sub in ("list", "get", "create", "update", "delete", "send", "repl"):
        assert sub in result.output


def test_chats_list_requires_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.cli.support.ctx as ctx_mod

    def _missing(_agent: str | None) -> str:
        click.echo("error: --agent is required", err=True)
        raise SystemExit(2)

    monkeypatch.setattr(ctx_mod, "require_agent", _missing)
    runner = CliRunner()
    result = runner.invoke(cli, ["chats", "list"])
    assert result.exit_code == 2


def test_chats_list_uses_offline_db(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_list_threads_offline(**kwargs):
        captured.update(kwargs)
        return [{"thread_id": "t1", "title": "hi", "is_active": True}]

    from octop.cli.support import db as db_mod

    monkeypatch.setattr(db_mod, "list_threads_offline", fake_list_threads_offline)
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "chats", "list", "--agent", "agent-1"])
    assert result.exit_code == 0, result.output
    assert captured["agent_id"] == "agent-1"


def test_chats_update_sends_title(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_update_thread_offline(agent_id, thread_id, *, title=None, pinned=None):
        captured["agent_id"] = agent_id
        captured["thread_id"] = thread_id
        captured["title"] = title
        return {"thread_id": thread_id, "title": title}

    from octop.cli.support import offline_ops as offline_mod

    monkeypatch.setattr(offline_mod, "resolve_cron_user_id", lambda *_a, **_k: 1)
    monkeypatch.setattr(offline_mod, "update_thread_offline", fake_update_thread_offline)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["chats", "update", "abc", "--agent", "agent-1", "--title", "renamed"]
    )
    assert result.exit_code == 0
    assert captured["title"] == "renamed"


def test_delete_thread_offline_unbinds_session(tmp_octop_home: Path) -> None:
    from octop.cli.support.db import open_cli_services
    from octop.cli.support.offline_ops import (
        create_thread_offline,
        delete_thread_offline,
    )
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.users import UserRepo

    assert (
        CliRunner()
        .invoke(
            cli,
            ["init", "--admin-username", "alice", "--admin-password", "TestPass12", "--yes"],
        )
        .exit_code
        == 0
    )
    with open_cli_services(home=tmp_octop_home) as svc:
        uid = UserRepo(svc.db).get_by_username("alice")
        assert uid is not None
        user_id = int(uid.id)
        AgentRepo(svc.db).create(agent_id="ag1", user_id=user_id, name="main")

    created = create_thread_offline(agent_id="ag1", user_id=user_id, home=tmp_octop_home)
    delete_thread_offline("ag1", created["thread_id"], home=tmp_octop_home)

    with open_cli_services(home=tmp_octop_home) as svc:
        assert svc.thread_repo.get(created["thread_id"]) is None
        assert svc.session_repo.get(created["session_key"]) is None
