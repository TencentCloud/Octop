from __future__ import annotations

from click.testing import CliRunner

from octop.cli.main import cli


def test_mcp_help() -> None:
    result = CliRunner().invoke(cli, ["mcp", "--help"])
    assert result.exit_code == 0, result.output
    assert "--base-url" in result.output
    assert "--user" in result.output
    assert "stdio" in result.output.lower()


def test_mcp_requires_user(tmp_octop_home) -> None:
    result = CliRunner().invoke(cli, ["mcp"])
    assert result.exit_code != 0
    assert "--user is required" in result.output
