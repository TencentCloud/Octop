"""Tests for runtime optional Python package installation."""

from __future__ import annotations

import site
import subprocess
import sys
from importlib import import_module

import pytest

from octop.infra.utils import runtime_packages as mod


def test_find_uv_binary_from_path(monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_UV_BIN", "")
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    assert mod.find_uv_binary() == "/usr/bin/uv"


def test_find_uv_binary_from_env_override(monkeypatch, tmp_path) -> None:
    uv = tmp_path / "custom-uv"
    uv.write_text("", encoding="utf-8")
    monkeypatch.setenv("OCTOP_UV_BIN", str(uv))
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    assert mod.find_uv_binary() == str(uv)


def test_build_install_commands_prefers_uv(monkeypatch) -> None:
    monkeypatch.setattr(mod, "find_uv_binary", lambda: "/usr/bin/uv")
    cmds = mod.build_install_commands(["pkg>=1"])
    assert cmds[0] == [
        "/usr/bin/uv",
        "pip",
        "install",
        "--python",
        sys.executable,
        "pkg>=1",
    ]
    assert cmds[1][:4] == [sys.executable, "-m", "pip", "install"]


def test_install_packages_noop_when_satisfied() -> None:
    assert mod.install_packages(["pkg"], is_satisfied=lambda: True) == "ready"


def test_install_packages_uses_uv_then_pip(monkeypatch) -> None:
    calls: list[list[str]] = []
    state = {"ready": False}

    class FakeProc:
        def __init__(self, code: int, stderr: str = "") -> None:
            self.returncode = code
            self.stderr = stderr
            self.stdout = ""

    def fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if cmd[0].endswith("uv"):
            state["ready"] = True
            return FakeProc(0)
        return FakeProc(1, "should not reach pip")

    monkeypatch.setattr(mod, "find_uv_binary", lambda: "/usr/bin/uv")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert mod.install_packages(["pkg>=1"], is_satisfied=lambda: state["ready"]) == "installed"
    assert calls[0][0] == "/usr/bin/uv"


def test_install_packages_loads_new_user_site_in_running_process(monkeypatch, tmp_path) -> None:
    user_site = tmp_path / "user-site"
    module_name = "octop_runtime_user_site_probe"
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(site, "ENABLE_USER_SITE", True)
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(user_site))
    monkeypatch.setattr(mod, "find_uv_binary", lambda: "/usr/bin/uv")

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(_cmd, **_kwargs):  # type: ignore[no-untyped-def]
        package_dir = user_site / module_name
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        return FakeProc()

    def is_satisfied() -> bool:
        try:
            import_module(module_name)
        except ModuleNotFoundError:
            return False
        return True

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        assert not user_site.exists()
        assert (
            mod.install_packages(
                [module_name], is_satisfied=is_satisfied, import_modules=(module_name,)
            )
            == "installed"
        )
        assert str(user_site) in sys.path
    finally:
        sys.modules.pop(module_name, None)


def test_install_packages_bootstraps_pip_on_missing_module(monkeypatch) -> None:
    calls: list[list[str]] = []
    state = {"pip": False, "ready": False}

    class FakeProc:
        def __init__(self, code: int, stderr: str = "") -> None:
            self.returncode = code
            self.stderr = stderr
            self.stdout = ""

    def fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if cmd[:3] == [sys.executable, "-m", "ensurepip"]:
            state["pip"] = True
            return FakeProc(0)
        if cmd[:3] == [sys.executable, "-m", "pip"]:
            if not state["pip"]:
                return FakeProc(1, "No module named pip")
            state["ready"] = True
            return FakeProc(0)
        return FakeProc(1, "unexpected")

    monkeypatch.setattr(mod, "find_uv_binary", lambda: None)
    monkeypatch.setattr(mod, "pip_importable", lambda: state["pip"])
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert mod.install_packages(["pkg>=1"], is_satisfied=lambda: state["ready"]) == "installed"
    assert any(cmd[:3] == [sys.executable, "-m", "ensurepip"] for cmd in calls)


def test_install_packages_extra_fallback(monkeypatch) -> None:
    calls: list[list[str]] = []

    class FakeProc:
        returncode = 1
        stderr = "network error"
        stdout = ""

    monkeypatch.setattr(mod, "find_uv_binary", lambda: None)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_kw: calls.append(list(cmd)) or FakeProc())
    spec = mod.PackageInstallSpec(packages=("fastembed>=0.4",), extra_fallback="local-embedding")
    with pytest.raises(RuntimeError, match="Could not install optional Python components"):
        mod.install_packages(spec, is_satisfied=lambda: False)
    assert any("octop[local-embedding]" in cmd for cmd in calls)


def test_find_uv_binary_uses_custom_search_paths(monkeypatch, tmp_path) -> None:
    uv = tmp_path / "uv"
    uv.write_text("", encoding="utf-8")
    monkeypatch.setenv("OCTOP_UV_BIN", "")
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    monkeypatch.setattr(mod, "_uv_search_paths", lambda: (uv,))
    assert mod.find_uv_binary() == str(uv)


def test_install_failed_message_hides_shell_commands() -> None:
    msg = mod._install_failed_message("No module named pip")
    assert "pip install" not in msg
    assert "uv sync" not in msg
