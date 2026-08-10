"""Helpers for connector ``default_open`` (always inject tools when enabled)."""

from __future__ import annotations

import json
from typing import Any


def read_default_open(config: dict[str, Any] | None) -> bool:
    """Return True only for an explicit boolean true."""
    if not isinstance(config, dict):
        return False
    return config.get("default_open") is True


def build_instance_config_json(
    *,
    kind: str,
    default_open: bool = False,
    email: Any = None,
) -> str | None:
    """Build ``connectors.config_json`` payload; None when empty."""
    config: dict[str, Any] = {}
    if kind == "qq-mail" and email:
        config["email"] = email
    if default_open:
        config["default_open"] = True
    if not config:
        return None
    return json.dumps(config, ensure_ascii=False)


def merge_mcp_servers_with_defaults(
    explicit: list[str] | None,
    defaults: list[str],
    *,
    apply_defaults: bool | None = None,
) -> list[str] | None:
    """Resolve turn MCP servers.

    - ``apply_defaults=True``: always union explicit picks with defaults (Cron / IM).
    - ``apply_defaults=False``: trust explicit list as-is (Dashboard can opt out).
    - ``apply_defaults=None``: apply defaults only when ``explicit is None``.
    """
    should_apply = (explicit is None) if apply_defaults is None else apply_defaults
    if should_apply:
        merged: list[str] = []
        for name in list(explicit or []) + list(defaults or []):
            text = str(name).strip()
            if text and text not in merged:
                merged.append(text)
        return merged or None
    names = [str(s).strip() for s in (explicit or []) if s and str(s).strip()]
    return names or None
