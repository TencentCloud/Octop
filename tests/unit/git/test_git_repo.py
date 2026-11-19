"""Behavioral tests for octop.infra.git.repo against real git repositories."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.git.repo import (
    commit_paths,
    discard_paths,
    get_diff,
    get_log,
    get_status,
    stage_paths,
    unstage_paths,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only fixture")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "tracked.txt").write_text("line1\n")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


@needs_git
async def test_status_not_a_repo(tmp_path: Path) -> None:
    snapshot = await get_status(tmp_path)
    assert snapshot.is_repo is False
    assert snapshot.git_available is True
    assert snapshot.files == []


@needs_git
async def test_status_groups_and_totals(repo: Path) -> None:
    (repo / "tracked.txt").write_text("line1\nline2\n")
    (repo / "staged.txt").write_text("a\nb\nc\n")
    _git(repo, "add", "staged.txt")
    (repo / "untracked.txt").write_text("x\ny\n")
    (repo / "binary.bin").write_bytes(b"\x00\x01\x02png")

    snapshot = await get_status(repo)
    assert snapshot.is_repo is True
    assert snapshot.branch == "main"
    assert snapshot.head_short is not None

    by_key = {(f.status, f.staged, f.path): f for f in snapshot.files}
    staged = by_key[("added", True, "staged.txt")]
    assert (staged.added, staged.removed) == (3, 0)
    modified = by_key[("modified", False, "tracked.txt")]
    assert (modified.added, modified.removed) == (1, 0)
    untracked = by_key[("untracked", False, "untracked.txt")]
    assert untracked.added == 2
    binary = by_key[("untracked", False, "binary.bin")]
    assert binary.added is None
    assert snapshot.added == 3 + 1 + 2
    assert snapshot.removed == 0


@needs_git
async def test_status_rename_entry(repo: Path) -> None:
    (repo / "old.txt").write_text("content\n")
    _git(repo, "add", "old.txt")
    _git(repo, "commit", "-m", "add old")
    _git(repo, "mv", "old.txt", "new.txt")

    snapshot = await get_status(repo)
    renames = [f for f in snapshot.files if f.status == "renamed"]
    assert len(renames) == 1
    entry = renames[0]
    assert entry.staged is True
    assert entry.path == "new.txt"
    assert entry.orig_path == "old.txt"


@needs_git
async def test_diff_unstaged_staged_and_untracked(repo: Path) -> None:
    (repo / "tracked.txt").write_text("line1\nline2\n")
    (repo / "staged.txt").write_text("hello\n")
    _git(repo, "add", "staged.txt")
    (repo / "fresh.txt").write_text("new file\n")

    unstaged = await get_diff(repo, "tracked.txt", staged=False)
    assert "+line2" in str(unstaged["diff"])

    staged = await get_diff(repo, "staged.txt", staged=True)
    assert "+hello" in str(staged["diff"])

    untracked = await get_diff(repo, "fresh.txt", staged=False)
    assert "+new file" in str(untracked["diff"])


@needs_git
async def test_diff_rejects_missing_and_unsafe_paths(repo: Path) -> None:
    with pytest.raises(OctopError) as missing:
        await get_diff(repo, "missing.txt", staged=False)
    assert missing.value.code is ErrorCode.NOT_FOUND

    for bad in ("../outside.txt", "a/../b"):
        with pytest.raises(OctopError) as excinfo:
            await get_diff(repo, bad, staged=False)
        assert excinfo.value.code is ErrorCode.SLASH_BAD_ARGS

    # Host-absolute input is workspace-relative here, joined under the repo
    # (leading '/' strip), so it can never escape to the real filesystem.
    with pytest.raises(OctopError) as inside:
        await get_diff(repo, "/etc/passwd", staged=False)
    assert inside.value.code is ErrorCode.NOT_FOUND


@needs_git
@posix_only
async def test_diff_ignores_external_diff_driver(repo: Path) -> None:
    (repo / "tracked.txt").write_text("line1\nline2\n")
    # A repo-level external diff driver (e.g. difftastic) must not change the
    # output shape: the panel parses a unified diff.
    driver = repo / "fake-difft.sh"
    driver.write_text('#!/bin/sh\necho "not a unified diff"\n')
    driver.chmod(0o755)
    _git(repo, "config", "diff.external", str(driver))

    result = await get_diff(repo, "tracked.txt", staged=False)
    text = str(result["diff"])
    assert text.startswith("diff --git")
    assert "+line2" in text
    assert "not a unified diff" not in text


@needs_git
async def test_log_shape(repo: Path) -> None:
    commits = await get_log(repo, limit=5)
    assert len(commits) == 1
    assert commits[0].subject == "init"
    assert commits[0].short
    assert "T" in commits[0].date


@needs_git
async def test_status_lists_untracked_files_individually(repo: Path) -> None:
    (repo / "notes").mkdir()
    (repo / "notes" / "one.md").write_text("a\n")
    (repo / "notes" / "two.md").write_text("b\nc\n")

    snapshot = await get_status(repo)
    untracked = {f.path: f for f in snapshot.files if f.status == "untracked"}
    assert "notes/" not in untracked
    assert untracked["notes/one.md"].added == 1
    assert untracked["notes/two.md"].added == 2


@needs_git
async def test_stage_unstage_commit_roundtrip(repo: Path) -> None:
    (repo / "feature.txt").write_text("feature work\n")
    await stage_paths(repo, ["feature.txt"])
    snapshot = await get_status(repo)
    assert any(f.staged and f.path == "feature.txt" for f in snapshot.files)

    result = await commit_paths(repo, "feat: add feature file")
    assert result["commit"]

    (repo / "feature.txt").write_text("feature work\nmore\n")
    await stage_paths(repo, ["feature.txt"])
    await unstage_paths(repo, ["feature.txt"])
    snapshot = await get_status(repo)
    staged_rows = [f for f in snapshot.files if f.staged and f.path == "feature.txt"]
    assert staged_rows == []
    assert any(
        not f.staged and f.path == "feature.txt" and f.status == "modified" for f in snapshot.files
    )


@needs_git
async def test_commit_requires_staged_changes(repo: Path) -> None:
    with pytest.raises(OctopError) as excinfo:
        await commit_paths(repo, "empty")
    assert excinfo.value.code is ErrorCode.SLASH_BAD_ARGS

    with pytest.raises(OctopError):
        await commit_paths(repo, "   ")


@needs_git
async def test_discard_restores_tracked_and_deletes_untracked(repo: Path) -> None:
    (repo / "tracked.txt").write_text("rewritten\n")
    (repo / "extra.txt").write_text("throwaway\n")

    await discard_paths(repo, ["tracked.txt", "extra.txt"])

    assert (repo / "tracked.txt").read_text() == "line1\n"
    assert not (repo / "extra.txt").exists()


@needs_git
async def test_write_ops_require_repo(tmp_path: Path) -> None:
    with pytest.raises(OctopError) as excinfo:
        await stage_paths(tmp_path, ["x.txt"])
    assert excinfo.value.code is ErrorCode.NOT_FOUND
