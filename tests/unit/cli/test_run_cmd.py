"""Tests for `octop run`."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


def test_run_help_lists_finnie_aligned_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--host",
        "--port",
        "--reload",
        "--workers",
        "--log-level",
        "--ssl",
        "--ssl-certfile",
        "--ssl-keyfile",
    ):
        assert flag in result.output, f"missing {flag} in --help"


def test_run_dispatches_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)
    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--host", "0.0.0.0", "--port", "9000", "--workers", "2"])
    assert r.exit_code == 0, r.output
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000
    assert captured["workers"] == 2


def _patch_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point PathLayout.from_env() at a fresh tmp directory."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))


def test_run_reads_host_port_from_config_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`octop run` with no args should fall back to config.json values."""
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"bind_host": "1.2.3.4", "port": 9000}), encoding="utf-8"
    )

    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run"])
    assert r.exit_code == 0, r.output
    assert captured["host"] == "1.2.3.4"
    assert captured["port"] == 9000
    assert "Saved config to" not in r.output
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data == {"bind_host": "1.2.3.4", "port": 9000}


def test_run_cli_args_override_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Explicit CLI flags take precedence over config.json."""
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"bind_host": "1.2.3.4", "port": 9000}), encoding="utf-8"
    )

    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--port", "8080"])
    assert r.exit_code == 0, r.output
    assert captured["host"] == "1.2.3.4"
    assert captured["port"] == 8080


def test_run_writes_config_before_uvicorn_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Config is persisted immediately when --host/--port are provided."""
    _patch_home(monkeypatch, tmp_path)

    written_before_uvicorn: dict[str, object] = {}

    def _fake(**_kw: object) -> None:
        # Read back config.json inside the fake uvicorn to verify it was written already.
        config_path = tmp_path / "config.json"
        if config_path.exists():
            written_before_uvicorn.update(json.loads(config_path.read_text(encoding="utf-8")))

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--host", "0.0.0.0", "--port", "80"])
    assert r.exit_code == 0, r.output
    assert "Saved config to" in r.output

    # Verify the file was written before uvicorn was called.
    assert written_before_uvicorn.get("bind_host") == "0.0.0.0"
    assert written_before_uvicorn.get("port") == 80

    # Final file state.
    config_path = tmp_path / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data == {"bind_host": "0.0.0.0", "port": 80}


def test_run_writes_config_even_on_uvicorn_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Config is persisted before uvicorn starts, so a crash does not lose it."""
    _patch_home(monkeypatch, tmp_path)

    def _fake(**_kw: object) -> None:
        raise RuntimeError("port already in use")

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--host", "0.0.0.0", "--port", "80"])
    assert r.exit_code != 0

    # Config was written before uvicorn was called, so it must exist.
    config_path = tmp_path / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data.get("bind_host") == "0.0.0.0"
    assert data.get("port") == 80


def test_run_merges_with_existing_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Saving host/port must not clobber unrelated keys in config.json."""
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"theme": "dark", "bind_host": "old", "port": 1}), encoding="utf-8"
    )

    def _fake(**_kw: object) -> None:
        return None

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--host", "0.0.0.0", "--port", "80"])
    assert r.exit_code == 0, r.output

    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data == {"theme": "dark", "bind_host": "0.0.0.0", "port": 80}


def _all_output(result: Any) -> str:
    """stdout + stderr across click versions (8.2+ can separate the streams)."""
    text = result.output or ""
    with contextlib.suppress(ValueError, AttributeError):
        text += result.stderr
    return text


def test_run_reports_corrupt_config_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A malformed config.json must fail cleanly, not with a traceback (#730).

    The command cannot guess the ~18 settings the file holds, and boot would die
    in ``load_config`` anyway, so the CLI names the file and position and stops.
    """
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text("{not valid json", encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--port", "80"])
    assert r.exit_code == 1, _all_output(r)
    # Never starts with the settings it could not read.
    assert captured == {}
    out = _all_output(r)
    assert "Traceback" not in out
    assert "not valid JSON" in out


def test_run_does_not_overwrite_corrupt_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A corrupt config.json is preserved byte-for-byte, never rewritten as empty.

    Supersedes the old "treat a malformed file as empty so the next run rewrites
    it cleanly" contract. That rewrite destroyed every other setting: one
    trailing comma plus ``octop run --port`` wiped the ``database`` section and
    silently flipped a PostgreSQL instance back to a greenfield SQLite one, with
    no warning in the log (issue #730).
    """
    _patch_home(monkeypatch, tmp_path)
    corrupt = '{"bind_host": "0.0.0.0", "database": {"driver": "postgresql"},}'
    (tmp_path / "config.json").write_text(corrupt, encoding="utf-8")

    def _fake(**_kw: object) -> None:
        return None

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--host", "0.0.0.0", "--port", "80"])
    assert r.exit_code == 1, _all_output(r)
    assert (tmp_path / "config.json").read_text(encoding="utf-8") == corrupt


def test_run_port_zero_not_overridden_by_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``port=0`` (OS-assigned random port) must reach uvicorn unchanged."""
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"bind_host": "1.2.3.4", "port": 9000}), encoding="utf-8"
    )

    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run", "--port", "0"])
    assert r.exit_code == 0, r.output
    assert captured["port"] == 0
    assert captured["host"] == "1.2.3.4"


def test_run_reads_legacy_host_key_for_compatibility(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Old config.json with 'host' key must still be read (backward compat)."""
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"host": "legacy.example.com", "port": 7000}), encoding="utf-8"
    )

    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    import octop.cli.commands.run as run_cmd

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)

    runner = CliRunner()
    r = runner.invoke(cli, ["run"])
    assert r.exit_code == 0, r.output
    assert captured["host"] == "legacy.example.com"
    assert captured["port"] == 7000
    assert "Saved config to" not in r.output
