from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from octop.cli.main import cli


def test_env_validate_reports_file_and_line(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    root = tmp_path / ".octop"
    monkeypatch.setenv("OCTOP_HOME", str(root))
    path = root / "env"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('TOKEN="missing\n', encoding="utf-8")

    result = runner.invoke(cli, ["env", "validate"])

    assert result.exit_code == 1
    assert f"{path}:1" in result.output
    assert "unclosed-quote" in result.output
