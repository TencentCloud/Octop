"""tests/unit/mobile/test_config_probe.py"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from octop.config import load_config
from octop.infra.mobile.config_probe import persist_mobile_probe
from octop.infra.mobile.probe import MobileProbeResult

_PROBE = MobileProbeResult(True, "physical", "", "2026-01-01T00:00:00Z")


def test_persist_mobile_probe_merges(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"port": 9000}), encoding="utf-8")
    result = MobileProbeResult(True, "physical", "", "2026-01-01T00:00:00Z")
    persist_mobile_probe(cfg_path, result)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["port"] == 9000
    assert data["capabilities"]["mobile"]["backend"] == "physical"
    cfg = load_config(cfg_path)
    assert cfg.capabilities.mobile.enabled is True


def _seed_config(path: Path) -> dict[str, Any]:
    """A config carrying a server port and a database credential."""
    original: dict[str, Any] = {
        "port": 9000,
        "database": {"host": "db.internal", "password": "s3cret"},
    }
    path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    return original


def test_persist_mobile_probe_keeps_config_when_the_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupted write must not leave ``config.json`` unparseable.

    ``config.json`` holds the database credentials and every unrelated setting,
    and ``load_config`` refuses to start on malformed JSON — so a half-written
    file takes the whole server down on the next boot. Writing through a temp
    file keeps the previous config intact until the new one is complete.
    """
    cfg_path = tmp_path / "config.json"
    original = _seed_config(cfg_path)

    real_write = os.write
    real_write_text = Path.write_text

    def _fail_partway(self: Path, data: str, **kwargs: Any) -> int:
        real_write_text(self, data[:12], **kwargs)
        raise OSError(28, "No space left on device")

    def _failing_write(fd: int, data: bytes) -> int:
        real_write(fd, data[:12])
        raise OSError(28, "No space left on device")

    # Cover both write paths: the in-place ``write_text`` this replaces and the
    # ``os.write`` of the temp file that replaces it.
    monkeypatch.setattr(Path, "write_text", _fail_partway)
    monkeypatch.setattr(os, "write", _failing_write)

    with pytest.raises(OSError):
        persist_mobile_probe(cfg_path, _PROBE)

    # The previous config must survive byte for byte and still load. Before the
    # fix this raised JSONDecodeError here: the half-written file no longer
    # parses, and load_config() then refuses to start the server.
    assert json.loads(cfg_path.read_text(encoding="utf-8")) == original
    assert load_config(cfg_path).port == 9000


def test_persist_mobile_probe_still_records_the_capability(tmp_path: Path) -> None:
    """The happy path keeps merging the probe result and drops no sibling keys."""
    cfg_path = tmp_path / "config.json"
    _seed_config(cfg_path)

    persist_mobile_probe(cfg_path, _PROBE)

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["port"] == 9000
    assert data["database"]["password"] == "s3cret"
    assert data["capabilities"]["mobile"]["enabled"] is True
    assert data["capabilities"]["mobile"]["probed_at"] == "2026-01-01T00:00:00Z"
    # No temp debris left behind next to the config.
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_persist_mobile_probe_repairs_a_non_dict_capabilities_block(tmp_path: Path) -> None:
    """A hand-edited ``capabilities`` scalar must not abort the write."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"port": 9000, "capabilities": "oops"}), encoding="utf-8")

    persist_mobile_probe(cfg_path, _PROBE)

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["port"] == 9000
    assert data["capabilities"]["mobile"]["backend"] == "physical"
