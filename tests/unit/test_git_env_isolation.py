"""Tests never see the git variables a pre-commit hook exports (they would rewrite this repo)."""

import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import GIT_REPO_ENV


def test_no_git_repository_variables_reach_the_tests() -> None:
    assert not [name for name in GIT_REPO_ENV if name in os.environ]


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0, reason="no git"
)
def test_a_throwaway_bare_repo_stays_where_it_is_made(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], cwd=tmp_path, check=True)
    assert (remote / "HEAD").is_file()
