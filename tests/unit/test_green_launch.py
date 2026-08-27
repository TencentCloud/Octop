"""Tests for the green portable launch bootstrap."""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_launch_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "desktop" / "portable" / "templates" / "launch.py"
    spec = importlib.util.spec_from_file_location("green_portable_launch", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("parent_path", ["/system/bin", None])
def test_bootstrap_prepends_interpreter_dir_to_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parent_path: str | None,
) -> None:
    (tmp_path / "packages").mkdir()
    runtime_bin = tmp_path / "runtime" / "bin"
    runtime_bin.mkdir(parents=True)
    executable = runtime_bin / "python3"

    module = _load_launch_module()
    module.__file__ = str(tmp_path / "launch.py")
    monkeypatch.setattr(sys, "executable", str(executable))
    if parent_path is None:
        monkeypatch.delenv("PATH", raising=False)
    else:
        monkeypatch.setenv("PATH", parent_path)

    module._bootstrap()

    interpreter_dir = str(runtime_bin)
    if parent_path is None:
        assert os.environ["PATH"] == interpreter_dir
    else:
        assert os.environ["PATH"] == interpreter_dir + os.pathsep + parent_path


def test_launch_has_no_provider_seed() -> None:
    source = inspect.getsource(_load_launch_module())
    assert "_seed_initial_provider" not in source
    assert "nexusapi" not in source
    assert "OCTOP_DESKTOP_OOB" not in source
