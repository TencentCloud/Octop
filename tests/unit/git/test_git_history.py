"""git log --graph history: merge lanes and OpenPGP signature status."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from octop.infra.git import HostGitTarget, get_history, resolve_git_binary

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "base.txt").write_text("base\n")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "chore: base")
    return tmp_path


@needs_git
async def test_history_keeps_merge_graph_rows(repo: Path) -> None:
    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.txt").write_text("feature\n")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feat: feature work")

    _git(repo, "checkout", "main")
    (repo / "main.txt").write_text("main\n")
    _git(repo, "add", "main.txt")
    _git(repo, "commit", "-m", "fix: main work")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")

    target = HostGitTarget(repo, resolve_git_binary())
    rows = await get_history(target, 20)

    commits = [row for row in rows if row.get("sha")]
    merges = [row for row in commits if row.get("subject") == "merge feature"]
    assert merges, "merge commit missing from history"
    assert merges[0]["short"]
    assert merges[0]["graph"].strip(), "graph prefix missing on merge commit"

    graph_text = "".join(str(row["graph"]) for row in rows)
    assert any(char in graph_text for char in "|\\/"), "no graph lane characters"

    # Unsigned commits report git's %G? status "N".
    assert all(row["signature"] == "N" for row in commits)
    assert all(row["author"] == "Test" and row["committer"] == "Test" for row in commits)


@needs_git
async def test_history_marks_unsigned(repo: Path) -> None:
    target = HostGitTarget(repo, resolve_git_binary())
    rows = await get_history(target, 5)
    commit = next(row for row in rows if row.get("sha"))
    assert commit["signature"] == "N"
    assert commit["signer"] == ""
