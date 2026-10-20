"""Tests for the main CLI entry point."""

from click.testing import CliRunner

from octop_harness.cli.main import cli


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Harness Agent CLI" in result.output


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "octop-harness-cli" in result.output


def test_cli_has_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "chat" in result.output
    assert "config" in result.output
    assert "skill" in result.output
    assert "init" in result.output


def test_cli_no_args_invokes_chat_repl(tmp_path: object, monkeypatch: object) -> None:
    """octop-harness without arguments should launch the chat REPL."""
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.cli.commands.chat._run_repl") as mock_repl,
    ):
        from octop_harness.cli.config.schema import CliConfig

        cli_cfg = CliConfig()
        mock_load.return_value = (fake_config, cli_cfg)
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        mock_repl.assert_called_once()


def test_cli_no_args_does_not_print_help() -> None:
    """octop-harness without arguments should NOT print the help text."""
    from unittest.mock import patch

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.cli.commands.chat._run_repl"),
    ):
        from octop_harness.cli.config.schema import CliConfig

        mock_load.return_value = (fake_config, CliConfig())
        runner = CliRunner()
        result = runner.invoke(cli, [], catch_exceptions=False)
        # Help text starts with "Usage:" — must not appear when no args given
        assert "Usage:" not in result.output
