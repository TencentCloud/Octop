"""Bind address resolution for `octop run`: CLI flag > env > config.json."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from octop.cli.commands.run import _save_configfile_overrides, resolve_bind, run
from octop.infra.errors import ErrorCode, OctopError


@pytest.fixture
def octop_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.delenv("OCTOP_PORT", raising=False)
    monkeypatch.delenv("OCTOP_BIND_HOST", raising=False)
    return tmp_path


def _write_config(home: Path, **data: object) -> None:
    (home / "config.json").write_text(json.dumps(data), encoding="utf-8")


def test_no_config_no_env(octop_home: Path) -> None:
    assert resolve_bind(None, None) == (None, None)


def test_config_file_values(octop_home: Path) -> None:
    _write_config(octop_home, bind_host="127.0.0.1", port=8088)
    assert resolve_bind(None, None) == ("127.0.0.1", 8088)


def test_env_overrides_config_file(octop_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(octop_home, bind_host="127.0.0.1", port=8088)
    monkeypatch.setenv("OCTOP_PORT", "9001")
    monkeypatch.setenv("OCTOP_BIND_HOST", "0.0.0.0")
    assert resolve_bind(None, None) == ("0.0.0.0", 9001)


def test_cli_flags_win_over_env_and_file(octop_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(octop_home, bind_host="127.0.0.1", port=8088)
    monkeypatch.setenv("OCTOP_PORT", "9001")
    assert resolve_bind("10.0.0.1", 7777) == ("10.0.0.1", 7777)


def test_invalid_env_port_falls_back_to_file(
    octop_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(octop_home, port=8088)
    monkeypatch.setenv("OCTOP_PORT", "not-a-number")
    assert resolve_bind(None, None) == (None, 8088)


def test_legacy_host_key(octop_home: Path) -> None:
    _write_config(octop_home, host="192.168.1.10", port=1234)
    assert resolve_bind(None, None) == ("192.168.1.10", 1234)


# --- issue #730: a corrupt config.json must never be treated as empty --------


def _corrupt(text: str) -> str:
    """Append a trailing comma before the closing brace (classic hand-edit slip)."""
    stripped = text.rstrip()
    assert stripped.endswith("}")
    return stripped[:-1].rstrip() + ",}"


def test_corrupt_config_raises_instead_of_silently_using_defaults(octop_home: Path) -> None:
    (octop_home / "config.json").write_text('{"bind_host": "0.0.0.0",}', encoding="utf-8")
    with pytest.raises(OctopError) as excinfo:
        resolve_bind(None, None)
    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT


def test_save_overrides_on_corrupt_config_preserves_bytes(octop_home: Path) -> None:
    cfg = octop_home / "config.json"
    corrupt = _corrupt(
        json.dumps({"bind_host": "0.0.0.0", "database": {"driver": "postgresql"}}, indent=2)
    )
    cfg.write_text(corrupt, encoding="utf-8")
    with pytest.raises(OctopError) as excinfo:
        _save_configfile_overrides(None, 8088)
    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT
    assert cfg.read_text(encoding="utf-8") == corrupt


def test_save_overrides_merges_without_dropping_keys(octop_home: Path) -> None:
    cfg = octop_home / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "bind_host": "0.0.0.0",
                "database": {"driver": "postgresql", "host": "db.internal"},
                "log_level": "debug",
            }
        ),
        encoding="utf-8",
    )
    _save_configfile_overrides(None, 8088)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["port"] == 8088
    assert data["bind_host"] == "0.0.0.0"
    assert data["database"] == {"driver": "postgresql", "host": "db.internal"}
    assert data["log_level"] == "debug"


def test_run_cli_on_corrupt_config_refuses_and_preserves_file(octop_home: Path) -> None:
    """POC regression: ``octop run --port`` used to wipe config.json to one key."""
    cfg = octop_home / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "bind_host": "0.0.0.0",
                "database": {"driver": "postgresql", "host": "db.internal"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    corrupt = _corrupt(cfg.read_text(encoding="utf-8"))
    cfg.write_text(corrupt, encoding="utf-8")

    with patch("octop.cli.commands.run._run_uvicorn") as mocked:
        result = CliRunner().invoke(run, ["--port", "8088"])

    assert result.exit_code != 0
    assert not mocked.called
    assert cfg.read_text(encoding="utf-8") == corrupt
