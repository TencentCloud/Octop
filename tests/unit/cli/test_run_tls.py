"""TLS handling for `octop run --ssl`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

import octop.cli.commands.run as run_cmd
from octop.cli.main import cli


@pytest.fixture
def octop_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def chmod_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Record every `os.chmod` the command performs, on any platform."""
    calls: list[tuple[str, int]] = []
    real_chmod = os.chmod

    def _record(target: str | os.PathLike[str], mode: int) -> None:
        calls.append((str(target), mode))
        real_chmod(target, mode)

    monkeypatch.setattr(run_cmd.os, "chmod", _record)
    return calls


def _all_output(result: object) -> str:
    text = getattr(result, "output", "") or ""
    text += getattr(result, "stderr", "") or ""
    return text


def test_self_signed_key_is_created_private(
    octop_home: Path, chmod_calls: list[tuple[str, int]]
) -> None:
    """The generated TLS private key must not inherit the process umask."""
    cert, key = run_cmd._maybe_generate_self_signed(True, None, None)
    assert Path(cert).is_file()
    assert Path(key).is_file()
    assert any(mode == 0o600 for _target, mode in chmod_calls), chmod_calls
    assert sorted(p.name for p in Path(key).parent.glob("*.tmp")) == []


def test_existing_key_permissions_are_repaired(
    octop_home: Path, chmod_calls: list[tuple[str, int]]
) -> None:
    """Keys written by older versions keep their 0644 mode until we tighten it."""
    ssl_dir = octop_home / "ssl"
    ssl_dir.mkdir()
    cert = ssl_dir / "self_signed.crt"
    key = ssl_dir / "self_signed.key"
    cert.write_text("old-cert", encoding="utf-8")
    key.write_text("old-key", encoding="utf-8")

    out_cert, out_key = run_cmd._maybe_generate_self_signed(True, None, None)
    assert Path(out_cert) == cert
    assert Path(out_key) == key
    assert (str(key), 0o600) in chmod_calls, chmod_calls
    assert cert.read_text(encoding="utf-8") == "old-cert"
    assert key.read_text(encoding="utf-8") == "old-key"


def test_cli_rejects_half_tls_pair(octop_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only one of --ssl-certfile / --ssl-keyfile is a usage error, not a silent fallback."""
    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)
    result = CliRunner().invoke(cli, ["run", "--ssl", "--ssl-certfile", "only-cert.pem"])
    assert result.exit_code == 2, _all_output(result)
    assert "must be given together" in _all_output(result)
    assert captured == {}


def test_cli_uses_explicit_pair_verbatim(octop_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake(**kw: object) -> None:
        captured.update(kw)

    monkeypatch.setattr(run_cmd, "_run_uvicorn", _fake)
    result = CliRunner().invoke(
        cli,
        ["run", "--ssl", "--ssl-certfile", "real.pem", "--ssl-keyfile", "real.key"],
    )
    assert result.exit_code == 0, _all_output(result)
    assert captured["ssl_certfile"] == "real.pem"
    assert captured["ssl_keyfile"] == "real.key"
