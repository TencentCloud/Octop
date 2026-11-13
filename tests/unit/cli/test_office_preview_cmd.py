from __future__ import annotations

from click.testing import CliRunner

from octop.cli.main import cli


def test_office_preview_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["office-preview", "--help"])
    assert result.exit_code == 0, result.output
    assert "LibreOffice" in result.output or "preview" in result.output.lower()


def test_office_preview_status_missing(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.cli.commands.office_preview.probe_status_payload",
        lambda _paths: {
            "available": False,
            "reason": "kit_missing",
            "node_version": None,
            "kit_version": "0.2.3",
        },
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["office-preview", "status"])
    assert result.exit_code == 1
    assert "not available" in result.output
