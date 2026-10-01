"""Tests for the Python-subprocess environment helper."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from octop.infra.utils.subprocess_env import distribution_root, python_subprocess_env


def test_env_prepends_distribution_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = python_subprocess_env()
    assert env["PYTHONPATH"].split(os.pathsep)[0] == distribution_root()
    assert env["PYTHONUNBUFFERED"] == "1"


def test_env_keeps_existing_entries_without_duplicating_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = distribution_root()
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["existing-token", root]))
    entries = python_subprocess_env()["PYTHONPATH"].split(os.pathsep)
    assert entries.count(root) == 1
    assert "existing-token" in entries


def test_env_applies_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = python_subprocess_env({"EXTRA_FLAG": "1"})
    assert env["EXTRA_FLAG"] == "1"
    assert env["PYTHONPATH"] == distribution_root()


def test_distribution_root_is_importable_by_children() -> None:
    assert (Path(distribution_root()) / "octop").is_dir()


def test_env_pins_utf8_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    assert python_subprocess_env()["PYTHONIOENCODING"] == "utf-8"


def test_child_can_emit_non_ansi_characters() -> None:
    """Regression: a cp936 child died printing ``✅`` on the NDJSON pipe."""
    code = "print('\u2705 \u4e2d\u6587 message')"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=python_subprocess_env(),
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert "\u2705" in proc.stdout.decode("utf-8")
