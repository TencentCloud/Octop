"""Offline connector installation preserves encryption and user ownership."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support.db import open_cli_services
from octop.infra.connectors.crypto import decrypt_credentials


@pytest.fixture
def connector_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.delenv("OCTOP_USER", raising=False)
    with open_cli_services() as svc:
        svc.user_repo.create(username="alice", role="admin", locale="en")
        svc.user_repo.create(username="bob", role="user", locale="zh")
    return tmp_path


def invoke(action: str, *, user: str | None = "alice", config: Any = None) -> Any:
    args = ["--json", *(["--user", user] if user else []), "connector", action, "open-design"]
    if action == "install":
        args += ["--config-file", "-"]
    return CliRunner().invoke(cli, args, input=json.dumps(config) if config is not None else None)


def test_install_update_get_and_remove(connector_home: Path) -> None:
    config = {"command": sys.executable, "args": ["mcp"], "env": {"TOKEN": "test-secret"}}
    first = invoke("install", config=config)
    assert first.exit_code == 0, first.output
    data = json.loads(first.output)
    assert data["action"] == "created" and data["installed"] is True
    assert "test-secret" not in first.output
    with open_cli_services() as svc:
        row = svc.connector_repo.get(data["instance_id"])
        assert row is not None and row.user_id == 1 and row.has_credentials
        assert row.credential_blob and b"test-secret" not in row.credential_blob
        assert decrypt_credentials(svc.secret_repo, row.credential_blob) == {
            **config,
            "instance_id": data["instance_id"],
        }
        svc.connector_repo.update_status(row.instance_id, "disabled")
    config["args"] = ["mcp", "--new"]
    updated = invoke("install", config=config)
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["instance_id"] == data["instance_id"]
    assert json.loads(updated.output)["action"] == "updated"
    with open_cli_services() as svc:
        assert len(svc.connector_repo.list_by_user(1)) == 1
        assert svc.connector_repo.get(data["instance_id"]).status == "active"
    fetched = invoke("get")
    assert fetched.exit_code == 0 and "TOKEN" not in fetched.output
    assert invoke("get", user="bob").exit_code == 1
    assert invoke("remove", user="bob").exit_code == 0
    assert invoke("get").exit_code == 0
    assert invoke("remove").exit_code == 0
    assert json.loads(invoke("remove").output)["action"] == "absent"
    assert invoke("get").exit_code == 1


def test_requires_user_and_valid_config(connector_home: Path) -> None:
    assert invoke("install", user=None, config={"command": sys.executable}).exit_code == 1
    invalid = invoke("install", config={"command": sys.executable, "env": {"TOKEN": 123}})
    assert invalid.exit_code == 1 and "123" not in invalid.output
    malformed = CliRunner().invoke(
        cli,
        ["--json", "--user", "alice", "connector", "install", "open-design", "--config-file", "-"],
        input='{"TOKEN":"test-secret",invalid}',
    )
    assert malformed.exit_code == 1
    assert json.loads(malformed.output)["ok"] is False
    assert "test-secret" not in malformed.output
    with open_cli_services() as svc:
        assert svc.connector_repo.list_by_user(1) == []


def test_user_environment_and_name_collision(
    connector_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_USER", "bob")
    result = invoke("install", user=None, config={"command": sys.executable})
    assert result.exit_code == 0, result.output
    with open_cli_services() as svc:
        assert len(svc.connector_repo.list_by_user(2)) == 1
        svc.connector_repo.create(
            instance_id="different",
            user_id=1,
            kind="notion",
            display_name="open-design",
            mcp_server_name="notion_different",
        )
    denied = invoke("install", config={"command": sys.executable})
    assert denied.exit_code == 1
    assert json.loads(denied.output)["code"] == "CONNECTOR_NAME_TAKEN"
