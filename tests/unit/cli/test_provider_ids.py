"""Provider ids are validated before database access or a runtime probe."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


@pytest.mark.parametrize(
    "command", [["provider", "delete"], ["provider", "test"], ["admin", "providers", "delete"]]
)
def test_invalid_provider_id_is_an_argument_error(command, monkeypatch, tmp_path):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    result = CliRunner().invoke(cli, [*command, "abc"])

    assert result.exit_code == 2
    assert "PROVIDER_ID" in result.output
    assert "valid integer" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "octop.db").exists()


@pytest.mark.parametrize(
    "command", [["provider", "delete"], ["provider", "test"], ["admin", "providers", "delete"]]
)
def test_valid_provider_id_is_passed_as_an_integer(command, monkeypatch, tmp_path):
    from octop.cli.support import embedded_ops, offline_ops

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    seen = []

    def delete_provider(provider_id):
        seen.append(provider_id)

    def probe_provider(provider_id, **kwargs):
        seen.append(provider_id)
        return {"ok": True, "latency_ms": 1}

    monkeypatch.setattr(offline_ops, "delete_provider_offline", delete_provider)
    monkeypatch.setattr(embedded_ops, "probe_provider", probe_provider)
    result = CliRunner().invoke(cli, [*command, "42"])

    assert result.exit_code == 0, result.output
    assert seen == [42]
    assert type(seen[0]) is int
