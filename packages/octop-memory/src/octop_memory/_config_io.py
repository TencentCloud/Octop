"""Plain config IO module (no click dependency).

Provides load/save for ``~/.octop-memory/config.json``, used by:

- :mod:`octop_memory.adapters.cli.config` when building CLI commands (adds the
  click dependency on top)
- core modules that need to run without click

Decoupling this layer from click / Memory means facades like
``MemoryService`` don't have to treat ``[cli]`` as a hard dependency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path("~/.octop-memory").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.json"


class _ConfigPathState:
    """Mutable holder for the config file path override.

    Using an attribute on a module-level singleton (rather than reassigning
    a bare module-level name) lets ``set_config_path`` mutate the override
    without a ``global`` statement.
    """

    override: Path | None = None


_state = _ConfigPathState()


def set_config_path(path: Path | None) -> None:
    """Set the config file path (called by CLI --config flag)."""
    _state.override = path


def get_config_path() -> Path:
    """Get the effective config file path."""
    return _state.override or CONFIG_FILE


DEFAULTS: dict[str, Any] = {
    "backend": "sqlite",
    "namespace": "default",
    "sqlite": {
        "db_path": "~/.octop-memory/memory.db",
    },
    "postgres": {
        "dsn": "postgresql://localhost/octop_memory",
    },
    "qdrant": {
        "url": "http://localhost:6333",
    },
}


def load_config() -> dict[str, Any]:
    """Load config from file, merged with defaults."""
    config_file = get_config_path()
    config = dict(DEFAULTS)
    if config_file.exists():
        try:
            with open(config_file) as f:
                user_config = json.load(f)
            # Deep merge for backend-specific sections
            for key, value in user_config.items():
                if isinstance(value, dict) and isinstance(config.get(key), dict):
                    config[key] = {**config[key], **value}
                else:
                    config[key] = value
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config: dict[str, Any]) -> None:
    """Save config to file."""
    config_file = get_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DEFAULTS",
    "get_config_path",
    "load_config",
    "save_config",
    "set_config_path",
]
