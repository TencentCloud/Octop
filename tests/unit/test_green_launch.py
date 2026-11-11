"""Tests for the green portable launch bootstrap."""

from __future__ import annotations

import importlib.util
import inspect
import os
import subprocess
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
    monkeypatch.delenv("PYTHONPATH", raising=False)
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


@pytest.mark.parametrize("has_pythonpath", [False, True])
def test_bootstrap_exposes_bundled_packages_to_python_subprocesses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, has_pythonpath: bool
) -> None:
    packages = tmp_path / "packages"
    packages.mkdir()
    probe = packages / "octop_portable_probe"
    probe.mkdir()
    (probe / "__init__.py").write_text("", encoding="utf-8")
    probe_source = "print('bundled-package')\n"
    if has_pythonpath:
        probe_source += "import portable_custom\nprint(portable_custom.value)\n"
    (probe / "__main__.py").write_text(probe_source, encoding="utf-8")
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "portable_custom.py").write_text("value = 'preserved'\n", encoding="utf-8")
    # Keep parent .pth processing covered while the child loads its own module.
    (packages / "custom.pth").write_text(str(custom) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    if has_pythonpath:
        monkeypatch.setenv("PYTHONPATH", str(custom))
    else:
        monkeypatch.delenv("PYTHONPATH", raising=False)
    module = _load_launch_module()
    module.__file__ = str(tmp_path / "launch.py")

    module._bootstrap()
    assert str(packages) in sys.path
    assert str(custom) in sys.path
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    child = subprocess.run(
        [sys.executable, "-m", "octop_portable_probe"],
        cwd=child_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert child.returncode == 0, child.stderr
    assert child.stdout.splitlines() == (
        ["bundled-package", "preserved"] if has_pythonpath else ["bundled-package"]
    )
    if has_pythonpath:
        assert os.environ["PYTHONPATH"].split(os.pathsep)[-1] == str(custom)
    module._bootstrap()
    assert os.environ["PYTHONPATH"].split(os.pathsep).count(str(packages)) == 1


def test_launch_has_no_provider_seed() -> None:
    source = inspect.getsource(_load_launch_module())
    assert "_seed_initial_provider" not in source
    assert "nexusapi" not in source
    assert "OCTOP_DESKTOP_OOB" not in source
