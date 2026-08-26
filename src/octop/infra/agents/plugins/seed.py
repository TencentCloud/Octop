"""Copy packaged plugins into the user plugins directory, globally disabled."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml


def _read_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_config(config_path: Path, data: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _plugin_version(plugin_dir: Path) -> tuple[int, ...]:
    path = plugin_dir / "plugin.yaml"
    if not path.is_file():
        return (0,)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return (0,)
    ver = str((raw or {}).get("version") or "0") if isinstance(raw, dict) else "0"
    parts: list[int] = []
    for bit in ver.split("."):
        try:
            parts.append(int(bit))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def seed_bundled_plugins(
    *,
    bundled_root: Path,
    plugins_dir: Path,
    config_path: Path,
) -> list[str]:
    """Copy missing bundled plugins into ``plugins_dir``, globally disabled.

    An id listed in ``bundled_plugins_seeded`` is never re-created after
    uninstall. Existing dest dirs are overwritten only when the bundled
    ``plugin.yaml`` version is newer (enabled flag is preserved).
    """
    if not bundled_root.is_dir():
        return []
    data = _read_config(config_path)
    seeded_raw = data.get("bundled_plugins_seeded")
    seeded: list[str] = [str(x) for x in seeded_raw] if isinstance(seeded_raw, list) else []
    seeded_set = set(seeded)
    plugins_cfg = data.get("plugins")
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
        data["plugins"] = plugins_cfg

    copied: list[str] = []
    plugins_dir.mkdir(parents=True, exist_ok=True)
    for child in sorted(bundled_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "plugin.yaml").is_file():
            continue
        plugin_id = child.name
        dest = plugins_dir / plugin_id
        if dest.exists():
            if _plugin_version(child) > _plugin_version(dest):
                enabled_entry = plugins_cfg.get(plugin_id)
                shutil.rmtree(dest)
                shutil.copytree(child, dest)
                copied.append(plugin_id)
                if isinstance(enabled_entry, dict):
                    plugins_cfg[plugin_id] = dict(enabled_entry)
            if plugin_id not in seeded_set:
                seeded.append(plugin_id)
                seeded_set.add(plugin_id)
                entry = plugins_cfg.get(plugin_id)
                if not isinstance(entry, dict):
                    plugins_cfg[plugin_id] = {"enabled": False}
            continue
        if plugin_id in seeded_set:
            continue
        shutil.copytree(child, dest)
        existing = plugins_cfg.get(plugin_id)
        plugin_entry: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
        plugin_entry["enabled"] = False
        plugins_cfg[plugin_id] = plugin_entry
        seeded.append(plugin_id)
        seeded_set.add(plugin_id)
        copied.append(plugin_id)

    data["bundled_plugins_seeded"] = seeded
    data["plugins"] = plugins_cfg
    _write_config(config_path, data)
    return copied
