"""In-package bundled plugins copied into ``~/.octop/plugins`` on init/start."""

from pathlib import Path


def default_bundled_plugins_root() -> Path:
    """Directory containing one subdirectory per shipped plugin."""
    return Path(__file__).resolve().parent
