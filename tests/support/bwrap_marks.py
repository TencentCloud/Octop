"""Shared pytest markers for bubblewrap / scoped-root_dir tests."""

from __future__ import annotations

import os
import shutil
import sys

import pytest

# Real bubblewrap jail (subprocess + ro-bind); Linux CI only.
linux_bwrap_only = pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("bwrap") is None,
    reason="bubblewrap jail requires Linux with bwrap on PATH",
)

# Tests that shell out with POSIX ``sh`` syntax (``mkdir -p``, ``cat``, …).
posix_shell_only = pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX shell commands (sh/bash)",
)
