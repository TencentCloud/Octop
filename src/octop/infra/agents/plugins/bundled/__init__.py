"""In-package plugin marketplace catalog (install copies into ``~/.octop/plugins``).

Today the catalog lives next to this module. Later it will move to a remote
API / object storage; install will download a ZIP and extract instead of
``shutil.copytree`` from this tree.
"""

from pathlib import Path


def default_bundled_plugins_root() -> Path:
    """Directory containing one subdirectory per catalog plugin."""
    return Path(__file__).resolve().parent
