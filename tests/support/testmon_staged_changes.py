"""Make pytest-testmon see *staged* changes (required for the git pre-commit hook).

testmon decides which files changed by calling ``git ls-files --stage -m``, which
compares the worktree against the **index**. A git pre-commit hook runs after
``git add``, so the changes are already staged and worktree == index. That makes
``git ls-files -m`` empty, testmon thinks nothing changed, and it silently
deselects every test (a false green).

We replace the detection with ``git diff HEAD`` (staged + unstaged vs HEAD), which
is exactly the set of changes a commit is about to capture. Files in that set are
removed from testmon's git-blob-sha cache so it reads their working-tree content
instead, producing an fsha that differs from the previously recorded baseline and
therefore gets selected as changed.

This module applies the patch at import time; it is imported from the repo-root
conftest.py so the patch is in place before testmon's ``pytest_configure`` runs.
It is a no-op (safe) when testmon is not installed.
"""

from __future__ import annotations

import subprocess

try:
    import testmon.process_code as _pc
except ImportError:  # pragma: no cover - testmon is a dev dependency
    _pc = None

_ORIG = _pc.noncached_get_files_shas if _pc is not None else None


def _changed_vs_head() -> set[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return set()
    return {line for line in result.stdout.splitlines() if line}


def _staged_aware_get_files_shas(directory: str) -> dict:
    all_shas = _ORIG(directory)
    # Force a working-tree read for any file that differs from HEAD so its fsha
    # no longer matches the baseline recorded from the prior (committed) content.
    for changed in _changed_vs_head():
        all_shas.pop(changed, None)
    return all_shas


if _pc is not None:
    _pc.noncached_get_files_shas = _staged_aware_get_files_shas
