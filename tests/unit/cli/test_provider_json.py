"""Provider creation rejects malformed JSON before accessing the local DB."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


@pytest.mark.parametrize(
    ("command", "option"),
    [
        (["provider", "create", "--name", "test", "--kind", "openai"], "--models"),
        (["admin", "providers", "create", "--name", "test", "--kind", "openai"], "--config"),
    ],
)
def test_malformed_provider_json_is_an_option_error(command, option, monkeypatch, tmp_path):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    result = CliRunner().invoke(cli, [*command, option, "{"])

    assert result.exit_code == 2
    assert f"Invalid value for {option}" in result.output
    assert "Invalid JSON" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "octop.db").exists()


@pytest.mark.parametrize(
    ("command", "option", "payload"),
    [
        (
            ["provider", "create", "--name", "test", "--kind", "openai"],
            "--models",
            '[{"id": "example"}]',
        ),
        (
            ["admin", "providers", "create", "--name", "test", "--kind", "openai"],
            "--config",
            '{"models": [{"id": "example"}]}',
        ),
    ],
)
def test_valid_provider_json_still_reaches_creation(
    command, option, payload, monkeypatch, tmp_path
):
    from octop.cli.support import offline_ops

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    calls = []

    def create_provider(**kwargs):
        calls.append(kwargs)
        return {"id": 1, "name": "test"}

    monkeypatch.setattr(offline_ops, "create_provider_offline", create_provider)
    result = CliRunner().invoke(cli, [*command, option, payload])

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0]["models"] == [{"id": "example"}]
