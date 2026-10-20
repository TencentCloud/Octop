"""Tests for CLI entry point."""

from click.testing import CliRunner

from octop_memory.adapters.cli import main


class TestCLIEntry:
    def test_main_group_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "octop-memory" in result.output.lower() or "Usage" in result.output

    def test_main_group_shows_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
