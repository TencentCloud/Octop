"""CLI channel patch --config must merge onto the stored config (#1134)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.config import OctopConfig
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout

FULL_CONFIG = {
    "app_id": "qq123",
    "secret": "sec456",
    "c2c_streaming": True,
    "response_mode": "stream",
}


@pytest.fixture
def channel_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    repos = services.repos
    uid = repos.user_repo.create(username="owner", password_hash="x", role="user")
    repos.agent_repo.create(agent_id="agent-1", user_id=uid, name="test-agent")
    repos.channel_repo.create(
        channel_id="ch-1",
        agent_id="agent-1",
        user_id=uid,
        kind="qq",
        name="testch",
        config_json=json.dumps(FULL_CONFIG),
    )
    try:
        yield repos
    finally:
        db.close()


def _run_patch(repos, *args: str):
    runner = CliRunner()
    result = runner.invoke(cli, ["channel", "patch", "--agent", "agent-1", "ch-1", *args])
    return result


def _stored_config(repos) -> dict:
    row = repos.channel_repo.get("ch-1")
    assert row is not None
    return json.loads(row.config_json)


def test_patch_merges_config_onto_stored_keys(channel_env):
    repos = channel_env
    result = _run_patch(repos, "--config", '{"c2c_streaming": false}')
    assert result.exit_code == 0, result.output
    stored = _stored_config(repos)
    assert stored == {**FULL_CONFIG, "c2c_streaming": False}


def test_patch_config_overrides_same_key_only(channel_env):
    repos = channel_env
    result = _run_patch(repos, "--config", '{"app_id": "new-app"}')
    assert result.exit_code == 0, result.output
    stored = _stored_config(repos)
    assert stored["app_id"] == "new-app"
    assert stored["secret"] == FULL_CONFIG["secret"]
    assert stored["response_mode"] == FULL_CONFIG["response_mode"]


def test_patch_without_config_leaves_config_untouched(channel_env):
    repos = channel_env
    result = _run_patch(repos, "--disabled")
    assert result.exit_code == 0, result.output
    assert _stored_config(repos) == FULL_CONFIG


def test_patch_echoes_merged_config(channel_env):
    repos = channel_env
    result = _run_patch(repos, "--config", '{"extra": 1}')
    assert result.exit_code == 0, result.output
    echoed = json.loads(result.output)
    assert echoed["config"] == {**FULL_CONFIG, "extra": 1}


def test_patch_unknown_channel_errors(channel_env):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["channel", "patch", "--agent", "agent-1", "nope", "--config", '{"a": 1}'],
    )
    assert result.exit_code != 0
    assert "not found" in result.output
