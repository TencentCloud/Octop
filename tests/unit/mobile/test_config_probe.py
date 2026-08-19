"""tests/unit/mobile/test_config_probe.py"""

from __future__ import annotations

import json
from pathlib import Path

from octop.config import load_config
from octop.infra.mobile.config_probe import persist_mobile_probe
from octop.infra.mobile.probe import MobileProbeResult


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
