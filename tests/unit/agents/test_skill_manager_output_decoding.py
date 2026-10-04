"""The standalone Skill Manager must preserve external CLI diagnostics."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def manager(repo_root: Path) -> dict[str, Any]:
    script = (
        repo_root / "src/octop/infra/agents/builtin_skills/skill-manager/scripts/manage_skills.py"
    )
    return runpy.run_path(str(script))


@pytest.fixture
def legacy_pipe_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Emulate a cp936 host default while still running a real child process."""
    original_run = subprocess.run

    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if kwargs.get("text"):
            kwargs.setdefault("encoding", "cp936")
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)


def _child(stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> list[str]:
    return [
        sys.executable,
        "-c",
        f"import sys; sys.stdout.buffer.write({stdout!r}); "
        f"sys.stderr.buffer.write({stderr!r}); sys.exit({code})",
    ]


def test_utf8_output_survives_legacy_pipe_encoding(manager, legacy_pipe_encoding) -> None:
    stdout = "已安装技能\n"
    stderr = "正在下载\n"
    result = manager["_run"](_child(stdout.encode(), stderr.encode()))

    assert result.stdout == stdout
    assert result.stderr == stderr


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_invalid_bytes_do_not_discard_success_output(manager, stream) -> None:
    result = manager["_run"](_child(**{stream: b"before\xffafter\n"}))

    assert getattr(result, stream) == "before\ufffdafter\n"


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_failed_command_preserves_diagnostic_and_redacts_urls(
    manager, legacy_pipe_encoding, stream
) -> None:
    diagnostic = "下载失败 ".encode() + b"\xff https://example.invalid/private-token\n"
    with pytest.raises(manager["SkillManagerError"]) as caught:
        manager["_run"](_child(**{stream: diagnostic}, code=3))

    assert str(caught.value) == "下载失败 \ufffd <redacted-url>"


def test_empty_diagnostic_keeps_exit_code_fallback(manager) -> None:
    with pytest.raises(manager["SkillManagerError"], match="^exit 3$"):
        manager["_run"](_child(code=3))
