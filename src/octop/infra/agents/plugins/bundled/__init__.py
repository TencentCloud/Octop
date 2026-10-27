"""In-package plugin directory.

Product plugins are installed from the remote market. This directory no longer
ships that catalog; ``seed_bundled`` upgrades nothing when it is empty.
"""

from pathlib import Path


def default_bundled_plugins_root() -> Path:
    """Directory containing one subdirectory per catalog plugin."""
    return Path(__file__).resolve().parent
