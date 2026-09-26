"""tests/unit/test_cli_main.py — basic help/import smoke test."""

from __future__ import annotations

from click.testing import CliRunner

from octop.cli.main import cli


def test_root_help_lists_groups() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    out = result.output
    for grp in ("service", "user", "agent", "chat", "channel", "cron", "provider", "admin"):
        assert grp in out


def test_user_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["user", "--help"])
    assert result.exit_code == 0
    for cmd in ("create", "list", "passwd", "role", "disable", "delete"):
        assert cmd in result.output


def test_agent_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "--help"])
    assert result.exit_code == 0
    for cmd in ("create", "list", "start", "stop", "reload", "delete"):
        assert cmd in result.output


def test_admin_rotate_jwt_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["admin", "rotate-jwt-secret", "--help"])
    assert result.exit_code == 0


def test_channel_group_lists_test_subcommand() -> None:
    """The channel command group exposes the runtime probe subcommand."""
    runner = CliRunner()
    result = runner.invoke(cli, ["channel", "--help"])
    assert result.exit_code == 0
    assert "test" in result.output


def test_channel_test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["channel", "test", "--help"])
    assert result.exit_code == 0
    assert "--agent" in result.output


def test_provider_group_lists_test_subcommand() -> None:
    """The provider command group exposes the credential probe subcommand."""
    runner = CliRunner()
    result = runner.invoke(cli, ["provider", "--help"])
    assert result.exit_code == 0
    assert "test" in result.output


def test_provider_test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["provider", "test", "--help"])
    assert result.exit_code == 0


def test_root_help_lists_global_options() -> None:
    """Root help advertises the acting user, agent, and output-format options."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    out = result.output
    for opt in ("--user", "--agent", "--json"):
        assert opt in out


def test_channel_list_uses_root_agent_fallback(monkeypatch) -> None:
    """``--agent`` is no longer required on subcommands; the root option
    (or OCTOP_AGENT env) supplies a fallback when not given inline."""
    captured: dict[str, str] = {}

    def _fake_resolve(*a, **k) -> int:
        return 1

    def _fake_list(agent_id, *, home=None):
        captured["agent_id"] = agent_id
        return []

    import octop.cli.commands.channel as channel_cmd
    from octop.cli.support import offline_ops as offline_mod

    monkeypatch.setattr(channel_cmd, "resolve_cli_acting_user_id", _fake_resolve)
    monkeypatch.setattr(offline_mod, "list_channels_offline", _fake_list)

    runner = CliRunner()
    # No --agent on the subcommand; root --agent supplies it.
    result = runner.invoke(cli, ["--agent", "AID-FROM-ROOT", "channel", "list"])
    assert result.exit_code == 0, result.output
    assert captured["agent_id"] == "AID-FROM-ROOT"


def test_channel_list_without_agent_errors() -> None:
    """When neither root --agent nor subcommand --agent is set, exit 2."""
    runner = CliRunner()
    result = runner.invoke(cli, ["channel", "list"])
    assert result.exit_code == 2
    assert "agent" in result.output.lower()


def test_channel_list_json_emits_dump(monkeypatch) -> None:
    """Root ``--json`` switches list-style output to JSON.

    Asserts the rendered output is valid JSON (no Rich box characters)
    and round-trips to the original payload.
    """
    import json as _json

    payload = [{"id": "01", "kind": "feishu", "enabled": True}]

    def _fake_resolve(*a, **k) -> int:
        return 1

    def _fake_list(agent_id, *, home=None):
        return payload

    import octop.cli.commands.channel as channel_cmd
    from octop.cli.support import offline_ops as offline_mod

    monkeypatch.setattr(channel_cmd, "resolve_cli_acting_user_id", _fake_resolve)
    monkeypatch.setattr(offline_mod, "list_channels_offline", _fake_list)

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--agent", "AID", "channel", "list"])
    assert result.exit_code == 0, result.output
    # Pure JSON output — no Rich table borders
    assert "─" not in result.output
    assert "│" not in result.output
    parsed = _json.loads(result.output.strip())
    assert parsed == payload


def test_user_list_json_emits_dump(monkeypatch) -> None:
    """``user list`` is a Rich-rendered command outside agent scope; the
    same --json contract applies."""
    import json as _json

    payload = [{"id": 1, "username": "alice", "role": "user", "disabled": False}]

    def _fake_list(*, home=None):
        return payload

    from octop.cli.support import offline_ops as offline_mod

    monkeypatch.setattr(offline_mod, "list_users_offline", _fake_list)

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "user", "list"])
    assert result.exit_code == 0, result.output
    assert "│" not in result.output
    parsed = _json.loads(result.output.strip())
    assert parsed == payload


def test_root_help_does_not_import_subcommand_modules() -> None:
    """`octop --help` must not import individual command modules eagerly."""
    import importlib
    import sys

    for mod in list(sys.modules):
        if mod.startswith("octop.cli.commands."):
            del sys.modules[mod]
    importlib.invalidate_caches()
    # Force re-import of main itself so the lazy group is fresh.
    if "octop.cli.main" in sys.modules:
        del sys.modules["octop.cli.main"]
    from octop.cli.main import cli as fresh_cli

    runner = CliRunner()
    result = runner.invoke(fresh_cli, ["--help"])
    assert result.exit_code == 0

    leaked = [m for m in sys.modules if m.startswith("octop.cli.commands.")]
    assert leaked == [], f"Lazy loader leaked imports: {leaked}"
