"""Persist mobile capability probe results into config.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from octop.config import OctopConfig, load_config
from octop.infra.mobile.probe import MobileProbeResult, probe_host_capability

logger = logging.getLogger(__name__)


def mobile_capabilities_dict(result: MobileProbeResult) -> dict[str, Any]:
    return {
        "enabled": result.enabled,
        "backend": result.backend,
        "probed_at": result.probed_at,
        "reason": result.reason,
    }


def persist_mobile_probe(
    config_path: Path, result: MobileProbeResult | None = None
) -> MobileProbeResult:
    """Merge probe result into ``config.json`` without overwriting unrelated keys."""
    probe = result or probe_host_capability()
    data: dict[str, Any] = {}
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw
    caps = data.setdefault("capabilities", {})
    if not isinstance(caps, dict):
        caps = {}
        data["capabilities"] = caps
    caps["mobile"] = mobile_capabilities_dict(probe)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "mobile probe persisted: enabled=%s backend=%s",
        probe.enabled,
        probe.backend,
    )
    return probe


def ensure_mobile_capabilities_probed(config_path: Path) -> OctopConfig:
    """Probe once when ``capabilities.mobile.probed_at`` is missing, then reload config."""
    cfg = load_config(config_path)
    if cfg.capabilities.mobile.probed_at:
        return cfg
    persist_mobile_probe(config_path)
    return load_config(config_path)
