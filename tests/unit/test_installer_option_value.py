"""Both installer copies must reject a value-taking option given no value.

``scripts/install.sh`` and ``scripts/install-octop.sh`` parse their options under
``set -u``, so ``--version`` / ``--extras`` / ``--mirror`` read an unset ``$2``
when the value is missing and abort with a raw bash "unbound variable" error
instead of the ``[octop] ...`` usage hint the scripts give for every other
mistake. ``--from-source`` (line 63) already guards for this, which is the
behaviour the other three options are aligned to.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")

INSTALLERS = ["scripts/install.sh", "scripts/install-octop.sh"]
VALUE_OPTIONS = ["--version", "--extras", "--mirror"]

# The installers target macOS / Linux shells; the Windows CI job skips them.
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only shell scripts")

pytestmark = [posix_only, pytest.mark.skipif(BASH is None, reason="bash is not available")]


def _run(installer: str, *args: str) -> subprocess.CompletedProcess[str]:
    script = REPO_ROOT / installer
    assert script.is_file(), script
    return subprocess.run(
        [str(BASH), str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("installer", INSTALLERS)
@pytest.mark.parametrize("option", VALUE_OPTIONS)
def test_missing_option_value_is_reported(installer: str, option: str) -> None:
    result = _run(installer, option)

    assert result.returncode != 0
    assert "unbound variable" not in result.stderr, result.stderr
    assert f"Option {option} requires a value" in result.stderr, result.stderr


@pytest.mark.parametrize("installer", INSTALLERS)
def test_option_with_a_value_is_still_accepted(installer: str) -> None:
    # ``--help`` ends the parse loop with exit 0, so reaching the usage text
    # proves the guard consumed ``1.2.3`` instead of rejecting it.
    result = _run(installer, "--version", "1.2.3", "--help")

    assert result.returncode == 0, result.stderr
    assert "requires a value" not in result.stderr


@pytest.mark.parametrize("installer", INSTALLERS)
def test_unknown_option_still_rejected(installer: str) -> None:
    result = _run(installer, "--versionn")

    assert result.returncode != 0
    assert "Unknown option" in result.stderr
