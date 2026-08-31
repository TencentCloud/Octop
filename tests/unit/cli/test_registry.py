"""Lazy CLI registry integrity — every COMMANDS attr must resolve."""

from __future__ import annotations

import importlib

import click
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.registry import COMMANDS


def test_all_registry_attrs_are_click_commands() -> None:
    for name, (module_path, attr, _help) in COMMANDS.items():
        mod = importlib.import_module(module_path, package="octop.cli")
        assert hasattr(mod, attr), f"{name}: module {module_path} missing attr {attr!r}"
        result = getattr(mod, attr)
        assert isinstance(result, click.Command), (
            f"{name}: {module_path}.{attr} is {type(result).__name__}, not click.Command"
        )


def test_acp_help_loads() -> None:
    """Regression for #486: registry must point at acp_cmd, not missing attr acp."""
    runner = CliRunner()
    result = runner.invoke(cli, ["acp", "--help"])
    assert result.exit_code == 0, result.output or result.exception
    assert "ACP" in result.output or "acp" in result.output.lower()
