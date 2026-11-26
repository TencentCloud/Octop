"""AI commit message: prompt shaping, validation and generation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.git import (
    GitFileChange,
    HostGitTarget,
    generate_commit_message,
    resolve_git_binary,
)
from octop.infra.git.message import (
    build_commit_message_prompt,
    validate_commit_message,
)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def test_validate_accepts_conventional_subject() -> None:
    assert validate_commit_message("feat(ui): add commit dialog") == ("feat(ui): add commit dialog")


def test_validate_strips_fences_prefix_and_quotes() -> None:
    assert validate_commit_message("```\nfix: repair thing\n```") == "fix: repair thing"
    assert validate_commit_message("commit message: docs: explain\n") == "docs: explain"
    assert validate_commit_message('"chore: tidy\n"') == "chore: tidy"


def test_validate_rejects_non_conventional() -> None:
    for raw in ("update stuff", "feat add x", ""):
        with pytest.raises(OctopError) as excinfo:
            validate_commit_message(raw)
        assert excinfo.value.code is ErrorCode.GIT_COMMIT_MESSAGE_INVALID


def test_prompt_limits_files_and_diffs() -> None:
    files = [
        GitFileChange(path=f"f{i}.py", status="modified", staged=False, added=1) for i in range(25)
    ]
    diffs = [{"path": f"f{i}.py", "patch": "x" * 3000} for i in range(10)]
    prompt = build_commit_message_prompt(branch="main", files=files, diffs=diffs, locale="en")
    assert "- ... 5 more files" in prompt
    assert "Diff excerpts:" in prompt
    # Per-file and total clipping keep the prompt bounded.
    assert prompt.count("x" * 1000) >= 5
    assert len(prompt) < 14_000


class _Access:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def ainvoke_text(
        self, prompt: str, system: str | None = None, timeout_s: float | None = None
    ) -> str:
        self.prompts.append(prompt)
        return self.reply


class _Models:
    def __init__(self, access: _Access) -> None:
        self.access = access

    def get(self, model: str | None = None) -> _Access:
        return self.access


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "tracked.txt").write_text("a\n")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "chore: base")
    return tmp_path


@needs_git
async def test_generate_uses_model_and_staged_changes(repo: Path) -> None:
    (repo / "tracked.txt").write_text("a\nb\n")
    _git(repo, "add", "tracked.txt")
    target = HostGitTarget(repo, resolve_git_binary())
    access = _Access("feat: add b\n")
    message = await generate_commit_message(
        models=_Models(access),
        target=target,
        include_unstaged=False,
        locale="en",
    )
    assert message == "feat: add b"
    assert "tracked.txt" in access.prompts[0]
    assert "Conventional Commit" in access.prompts[0]


@needs_git
async def test_generate_rejects_invalid_model_output(repo: Path) -> None:
    (repo / "tracked.txt").write_text("a\nb\n")
    target = HostGitTarget(repo, resolve_git_binary())
    with pytest.raises(OctopError) as excinfo:
        await generate_commit_message(
            models=_Models(_Access("just some words")),
            target=target,
            include_unstaged=True,
            locale="zh",
        )
    assert excinfo.value.code is ErrorCode.GIT_COMMIT_MESSAGE_INVALID


@needs_git
async def test_generate_without_changes(repo: Path) -> None:
    target = HostGitTarget(repo, resolve_git_binary())
    with pytest.raises(OctopError) as excinfo:
        await generate_commit_message(
            models=_Models(_Access("feat: nope")),
            target=target,
            include_unstaged=True,
            locale="en",
        )
    assert excinfo.value.code is ErrorCode.GIT_NO_CHANGES
