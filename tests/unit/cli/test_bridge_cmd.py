"""Tests for the `octop bridge` group."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from octop.cli.main import cli


def test_bridge_group_help_lists_management_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["bridge", "--help"])
    assert result.exit_code == 0, result.output
    for sub in (
        "list",
        "get",
        "probe",
        "create",
        "patch",
        "delete",
        "connect",
        "disconnect",
        "agents",
    ):
        assert sub in result.output


def test_root_help_lists_bridge() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "bridge" in result.output


def test_bridge_list_requires_user(monkeypatch: Any) -> None:
    import octop.cli.commands.bridge as bridge_cmd
    from octop.infra.errors import ErrorCode, OctopError

    def _missing(*_a: Any, **_k: Any) -> int:
        raise OctopError(
            ErrorCode.NOT_FOUND,
            "user required (--user, CLI default_user, or agent with an owner)",
        )

    monkeypatch.setattr(bridge_cmd, "resolve_cli_acting_user_id", _missing)
    runner = CliRunner()
    result = runner.invoke(cli, ["bridge", "list"])
    assert result.exit_code == 1
    assert "user required" in result.output


def test_bridge_list_json(monkeypatch: Any) -> None:
    payload = [
        {
            "connection_id": "01ABC",
            "display_name": "demo",
            "peer_base_url": "https://demo.octop.chat",
            "peer_username": "peer",
            "status": "disconnected",
            "auto_reconnect": True,
        }
    ]

    import octop.cli.commands.bridge as bridge_cmd
    from octop.cli.support import embedded_ops as ops

    monkeypatch.setattr(bridge_cmd, "resolve_cli_acting_user_id", lambda *_a, **_k: 7)
    monkeypatch.setattr(ops, "list_bridge_connections", lambda *_a, **_k: payload)
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "bridge", "list", "--user", "alice"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output.strip()) == payload


def test_bridge_probe_requires_url_without_id() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["bridge", "probe", "--peer-user", "peer"])
    assert result.exit_code != 0
    assert "--url" in result.output


def test_bridge_probe_dispatches(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_probe(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "peer_display_name": "Peer User",
            "agent_count": 1,
            "agents": [{"agent_id": "ag1", "name": "A", "kind": "expert", "state": "idle"}],
        }

    from octop.cli.support import embedded_ops as ops

    monkeypatch.setattr(ops, "probe_bridge_peer", fake_probe)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "bridge",
            "probe",
            "--url",
            "https://demo.octop.chat",
            "--peer-user",
            "jubaoliang",
            "--peer-password",
            "secret",
        ],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output.strip())
    assert body["agent_count"] == 1
    assert captured["peer_base_url"] == "https://demo.octop.chat"
    assert captured["peer_username"] == "jubaoliang"
    assert captured["password"] == "secret"


def test_bridge_create_and_delete_dispatch(monkeypatch: Any) -> None:
    created: dict[str, Any] = {}

    def fake_create(uid: int, **kwargs: Any) -> dict[str, Any]:
        created["uid"] = uid
        created.update(kwargs)
        return {"connection_id": "01NEW", "display_name": kwargs["display_name"]}

    def fake_delete(connection_id: str, uid: int, **_k: Any) -> None:
        created["deleted"] = (connection_id, uid)

    import octop.cli.commands.bridge as bridge_cmd
    from octop.cli.support import embedded_ops as ops

    monkeypatch.setattr(bridge_cmd, "resolve_cli_acting_user_id", lambda *_a, **_k: 3)
    monkeypatch.setattr(ops, "create_bridge_connection", fake_create)
    monkeypatch.setattr(ops, "delete_bridge_connection", fake_delete)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "bridge",
            "create",
            "--url",
            "https://demo.octop.chat",
            "--peer-user",
            "peer",
            "--peer-password",
            "pw",
            "--name",
            "demo",
            "--no-connect",
            "--user",
            "alice",
        ],
    )
    assert result.exit_code == 0, result.output
    assert created["uid"] == 3
    assert created["display_name"] == "demo"
    assert created["connect"] is False

    result = runner.invoke(cli, ["bridge", "delete", "01NEW", "--yes", "--user", "alice"])
    assert result.exit_code == 0, result.output
    assert created["deleted"] == ("01NEW", 3)


def test_bridge_patch_requires_a_field() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["bridge", "patch", "01X", "--user", "alice"])
    assert result.exit_code != 0
    assert "nothing to patch" in result.output


def test_bridge_patch_dispatches(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_patch(connection_id: str, uid: int, **kwargs: Any) -> dict[str, Any]:
        captured["connection_id"] = connection_id
        captured["uid"] = uid
        captured.update(kwargs)
        return {"connection_id": connection_id, "display_name": kwargs["display_name"]}

    import octop.cli.commands.bridge as bridge_cmd
    from octop.cli.support import embedded_ops as ops

    monkeypatch.setattr(bridge_cmd, "resolve_cli_acting_user_id", lambda *_a, **_k: 4)
    monkeypatch.setattr(ops, "patch_bridge_connection", fake_patch)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["bridge", "patch", "01X", "--name", "renamed", "--notes", "hi", "--user", "alice"],
    )
    assert result.exit_code == 0, result.output
    assert captured["connection_id"] == "01X"
    assert captured["display_name"] == "renamed"
    assert captured["update_notes"] is True
    assert captured["notes"] == "hi"


def test_list_bridge_connections_reads_local_db(tmp_octop_home: Path, monkeypatch: Any) -> None:
    from octop.cli.support.db import open_cli_services
    from octop.cli.support.embedded_ops import list_bridge_connections
    from octop.infra.db.repos.users import UserRepo

    monkeypatch.setenv("OCTOP_HOME", str(tmp_octop_home))
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--admin-username", "alice", "--admin-password", "TestPass12", "--yes"],
    )
    assert result.exit_code == 0, result.output

    with open_cli_services(home=tmp_octop_home) as svc:
        user = UserRepo(svc.db).get_by_username("alice")
        assert user is not None
        uid = int(user.id)
        svc.bridge_connection_repo.create(
            connection_id="01BR1",
            owner_user_id=uid,
            peer_base_url="https://demo.octop.chat",
            peer_username="peer",
            display_name="demo",
            notes="n",
            status="disconnected",
        )

    rows = list_bridge_connections(uid, home=tmp_octop_home)
    assert len(rows) == 1
    assert rows[0]["connection_id"] == "01BR1"
    assert rows[0]["display_name"] == "demo"
    assert rows[0]["peer_base_url"] == "https://demo.octop.chat"
    assert rows[0]["has_password"] is False
    assert rows[0]["inbound"] is True


def test_bridge_get_missing_fails(monkeypatch: Any) -> None:
    import octop.cli.commands.bridge as bridge_cmd
    from octop.cli.support import embedded_ops as ops
    from octop.infra.errors import ErrorCode, OctopError

    monkeypatch.setattr(bridge_cmd, "resolve_cli_acting_user_id", lambda *_a, **_k: 1)

    def _missing(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise OctopError(ErrorCode.BRIDGE_NOT_FOUND, "bridge connection not found")

    monkeypatch.setattr(ops, "get_bridge_connection", _missing)
    runner = CliRunner()
    result = runner.invoke(cli, ["bridge", "get", "missing", "--user", "alice"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_bridge_create_help_mentions_connect() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["bridge", "create", "--help"])
    assert result.exit_code == 0
    assert "--no-connect" in result.output
    assert "--peer-user" in result.output
    assert "--peer-password" in result.output
