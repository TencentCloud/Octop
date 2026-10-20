"""Plugin manifest (``plugin.yaml``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

PluginKind = Literal["tool", "skill", "hook", "channel"]

PLUGIN_KINDS = ("tool", "skill", "hook", "channel")


@dataclass(frozen=True)
class PluginManifest:
    id: str
    version: str
    name: str
    kind: PluginKind
    entry: str
    description: str = ""
    requires: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        plugin_id = str(data.get("id") or "").strip()
        version = str(data.get("version") or "").strip()
        if not plugin_id or not version:
            raise ValueError("plugin.yaml requires id and version")

        kind = str(data.get("kind") or "tool").strip().lower()
        if kind not in PLUGIN_KINDS:
            raise ValueError(f"unsupported plugin kind: {kind!r}")

        entry = str(data.get("entry") or "main.py").strip()
        name = str(data.get("name") or plugin_id).strip()
        description = str(data.get("description") or "").strip()

        raw_requires = data.get("requires") or []
        if not isinstance(raw_requires, list):
            raise ValueError("requires must be a list of pip requirement strings")
        requires = tuple(str(r).strip() for r in raw_requires if str(r).strip())

        return cls(
            id=plugin_id,
            version=version,
            name=name,
            kind=kind,  # type: ignore[arg-type]
            entry=entry,
            description=description,
            requires=requires,
        )

    @classmethod
    def load(cls, path: Path) -> PluginManifest:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"invalid plugin manifest: {path}")
        return cls.from_dict(data)
