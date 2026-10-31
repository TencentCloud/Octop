"""Unit tests for persisting the control-plane database section into config.json."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from octop.config import DatabaseConfig
from octop.infra.db.rebind import persist_database_config
from octop.infra.errors import ErrorCode, OctopError

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")


def test_persist_database_config_keeps_unrelated_keys(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"backup": {"auto_enabled": True}}), encoding="utf-8")

    cfg = persist_database_config(
        cfg_path, DatabaseConfig(driver="sqlite", sqlite_path="data/octop.db")
    )

    assert cfg.database.sqlite_path == "data/octop.db"
    written = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert written["backup"] == {"auto_enabled": True}


def test_persist_database_config_rejects_corrupt_config(tmp_path: Path) -> None:
    """A hand-edit slip is a typed 400, and the file is never rewritten."""
    cfg_path = tmp_path / "config.json"
    previous = '{"database": {"password": "s3cret"},}'
    cfg_path.write_text(previous, encoding="utf-8")

    with pytest.raises(OctopError) as excinfo:
        persist_database_config(cfg_path, DatabaseConfig())

    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT
    assert "s3cret" not in str(excinfo.value)
    assert cfg_path.read_text(encoding="utf-8") == previous


def test_persist_database_config_keeps_previous_config_when_swap_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed swap keeps the old file and leaves no ``.tmp`` litter."""
    cfg_path = tmp_path / "config.json"
    previous = json.dumps({"backup": {"auto_enabled": True}}, indent=2) + "\n"
    cfg_path.write_text(previous, encoding="utf-8")

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated swap failure")

    monkeypatch.setattr("octop.infra.utils.json_file.os.replace", _fail)
    with pytest.raises(OSError, match="simulated swap failure"):
        persist_database_config(cfg_path, DatabaseConfig())

    assert cfg_path.read_text(encoding="utf-8") == previous
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


@posix_only
def test_persist_database_config_preserves_existing_file_mode(tmp_path: Path) -> None:
    """config.json holds database credentials; a write must not widen its mode."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    os.chmod(cfg_path, 0o600)

    persist_database_config(cfg_path, DatabaseConfig())

    assert stat.S_IMODE(cfg_path.stat().st_mode) == 0o600
