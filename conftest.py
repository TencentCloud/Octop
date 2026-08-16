"""Repo-root conftest.

Imported by pytest at startup (before any plugin's ``pytest_configure``), so the
testmon change-detection patch in ``tests.support.testmon_staged_changes`` is
applied before testmon reads file fingerprints. The patch only affects
testmon's internals and is a safe no-op when testmon is absent.
"""

from __future__ import annotations

import tests.support.testmon_staged_changes  # noqa: F401  (applies the patch)
