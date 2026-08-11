"""Tests for offline CLI skills helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.users import UserRepo


def _bootstrap() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--admin-username", "alice", "--admin-password", "TestPass12", "--yes"],
    )
    assert result.exit_code == 0, result.output


def test_set_skill_enabled_persists_disabled_list(tmp_octop_home: Path) -> None:
    from octop.cli.support.db import open_cli_services
    from octop.cli.support.skills import set_skill_enabled

    _bootstrap()
    with open_cli_services(home=tmp_octop_home) as svc:
        uid = UserRepo(svc.db).get_by_username("alice")
        assert uid is not None
        AgentRepo(svc.db).create(
            agent_id="ag1",
            user_id=int(uid.id),
            name="main",
            config_json=json.dumps({"skills_disabled": ["pdf"]}),
        )

    set_skill_enabled("ag1", "pdf", enabled=True)

    with open_cli_services(home=tmp_octop_home) as svc:
        row = svc.agent_repo.get("ag1")
        assert row is not None
        cfg = json.loads(row.config_json or "{}")
        assert cfg.get("skills_disabled") == []


def test_list_skills_offline_delegates_to_embedded_server() -> None:
    from octop.cli.support import skills as skills_mod

    sample = [{"slug": "docx", "name": "docx", "enabled": True, "kind": "workspace"}]

    async def _fake_list(agent_id: str):
        assert agent_id == "ag1"
        return sample

    with patch.object(skills_mod, "list_skills_async", new=AsyncMock(side_effect=_fake_list)):
        rows = skills_mod.list_skills_offline("ag1")
    assert rows == sample


def test_skills_list_cli_no_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "octop.cli.support.skills.list_skills_offline",
        lambda _aid: [{"slug": "docx", "name": "docx", "enabled": True, "kind": "workspace"}],
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["skills", "list", "--agent", "ag1"])
    assert result.exit_code == 0, result.output
    assert "docx" in result.output
