"""Desktop shell ownership for the Octop Python sidecar.

The Electron shell marks the Python process it owns with
``OCTOP_DESKTOP_SHELL=1``.  This flag is authoritative for "this process is the
desktop-hosted sidecar" and is intentionally distinct from ``OCTOP_DESKTOP`` /
``OCTOP_GREEN_PACKAGES``: a standalone green portable install may set those
without being shell-owned, and it must keep its self-upgrade ability.

``octop.config`` must stay free of ``infra`` imports (AGENTS.md §5), so this
module lives in ``octop.infra`` and is only imported by ``infra`` / ``cli`` /
``api`` code paths that are allowed to depend on it.
"""

from __future__ import annotations

import os

_DESKTOP_SHELL_ENV = "OCTOP_DESKTOP_SHELL"

# Shell-owned keys that the ``~/.octop/env`` file and ``/api/envs`` must never
# override: they control process identity, bind address, and update ownership.
SHELL_OWNED_ENV_KEYS = frozenset(
    {
        "OCTOP_DESKTOP_SHELL",
        "OCTOP_DESKTOP",
        "OCTOP_GREEN_PACKAGES",
        "OCTOP_BIND_HOST",
        "OCTOP_PORT",
        "OCTOP_HOME",
        "PYTHONNOUSERSITE",
    }
)


def desktop_shell_enabled() -> bool:
    """Return true when this process is the desktop-hosted sidecar."""
    raw = (os.environ.get(_DESKTOP_SHELL_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}
