"""Persisted environment variables at ``~/.octop/env`` (dotenv format)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROTECTED_EXACT = frozenset(
    {
        "HOME",
        "USER",
        "USERNAME",
        "LOGNAME",
        "SHELL",
        "PWD",
    }
)

# Web-search tools register at agent construction from these keys.
SEARCH_ENV_KEYS = frozenset(
    {
        "TAVILY_API_KEY",
        "BRAVE_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CSE_ID",
        "MOONSHOT_API_KEY",
    }
)


def env_file_path(root: Path) -> Path:
    return root / "env"


def parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not _KEY_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        out[key] = value
    return out


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_env_text(path.read_text(encoding="utf-8"))


def format_env_file(values: dict[str, str]) -> str:
    lines: list[str] = []
    for key in sorted(values):
        if not _KEY_RE.match(key):
            continue
        val = values[key]
        if not val:
            lines.append(f"{key}=")
        elif re.search(r"[\s#\"'\\]", val):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={val}")
    return "\n".join(lines) + ("\n" if lines else "")


def save_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_env_file(values), encoding="utf-8")


def apply_env_file(path: Path) -> dict[str, str]:
    """Load ``path`` and merge into ``os.environ`` (does not unset missing keys)."""
    values = load_env_file(path)
    for key, value in values.items():
        os.environ[key] = value
    return values


def apply_env_file_replace(path: Path, *, previous: Mapping[str, str]) -> dict[str, str]:
    """Apply the file to ``os.environ`` and drop keys that left the file."""
    values = load_env_file(path)
    for key in previous:
        if key not in values:
            os.environ.pop(key, None)
    for key, value in values.items():
        os.environ[key] = value
    return values


def search_env_changed(previous: Mapping[str, str], new: Mapping[str, str]) -> bool:
    return any(previous.get(key, "") != new.get(key, "") for key in SEARCH_ENV_KEYS)


def _is_protected_env_key(key: str) -> bool:
    return key in _PROTECTED_EXACT or key.startswith("OCTOP_")


def overlay_stdio_spec_env(spec: dict[str, Any], global_env: Mapping[str, str]) -> dict[str, Any]:
    """Fold Admin env into an MCP stdio spec (spec env wins; skip protected keys)."""
    if str(spec.get("transport") or "").lower() != "stdio":
        return spec
    raw_env = spec.get("env")
    existing: dict[str, Any] = raw_env if isinstance(raw_env, dict) else {}
    merged = {str(k): str(v) for k, v in global_env.items() if not _is_protected_env_key(str(k))}
    merged.update({str(k): str(v) for k, v in existing.items()})
    out = dict(spec)
    out["env"] = merged
    return out


def overlay_stdio_mcp_configs(
    configs: Mapping[str, Any],
    global_env: Mapping[str, str],
) -> dict[str, Any]:
    """Apply :func:`overlay_stdio_spec_env` to every stdio entry in *configs*."""
    if not configs:
        return {}
    if not global_env:
        return dict(configs)
    out: dict[str, Any] = {}
    for name, spec in configs.items():
        if isinstance(spec, dict):
            out[name] = overlay_stdio_spec_env(spec, global_env)
        else:
            out[name] = spec
    return out


def list_env_items(path: Path) -> list[dict[str, str]]:
    return [{"key": k, "value": v} for k, v in sorted(load_env_file(path).items())]
