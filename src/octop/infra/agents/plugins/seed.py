"""Copy packaged plugins into the user plugins directory, globally disabled."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from octop.infra.errors import corrupt_config_error
from octop.infra.utils.json_file import (
    JsonFileCorruptError,
    read_json_object,
    write_json_atomic,
)


def _read_config(config_path: Path) -> dict[str, Any]:
    """Load ``config.json`` for merging; ``{}`` when absent.

    A corrupt file raises instead of reading as empty: ``seed_bundled_plugins``
    always writes back, so merging into ``{}`` would destroy every other setting
    (issue #730).
    """
    try:
        data = read_json_object(config_path)
    except JsonFileCorruptError as exc:
        raise corrupt_config_error(exc.path, exc.detail) from exc
    return data if data is not None else {}


def _write_config(config_path: Path, data: dict[str, Any]) -> None:
    write_json_atomic(config_path, data)


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
