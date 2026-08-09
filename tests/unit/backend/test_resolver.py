"""Tests for backend resolver helpers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from deepagents.backends import CompositeBackend
from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.backend.resolver import (
    _is_host_root,
    backend_spec_supports_execution,
    default_agent_backend_spec,
    windows_neutralize_host_root,
)


def test_default_agent_backend_spec_posix_uses_host_root(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="posix")):
        spec = default_agent_backend_spec(ws)
    assert spec == {"type": "local_shell", "root_dir": "/", "virtual_mode": True}


@pytest.mark.skipif(os.name != "posix", reason="POSIX host-root default + workspace artifacts")
def test_default_agent_backend_resolve_scopes_artifacts_to_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    backend = resolve_backend(default_agent_backend_spec(ws), workspace_dir=ws)

    assert isinstance(backend, CompositeBackend)
    assert backend.artifacts_root == str(ws.resolve())
    assert backend_spec_supports_execution({"type": "local_shell", "root_dir": "/"})
    assert str(getattr(backend, "cwd", None)) == "/"

    history = ws / "conversation_history" / "thread.md"
    result = backend.write(str(history), "context summary")
    assert result.error is None
    assert history.read_text(encoding="utf-8") == "context summary"

    workspace = BackendWorkspace(backend, ws)
    workspace.mkdir("source")
    (ws / "source" / "note.txt").write_text("ok", encoding="utf-8")
    workspace.move("source", "moved")
    assert (ws / "moved" / "note.txt").read_text(encoding="utf-8") == "ok"
    workspace.delete("moved")
    assert not (ws / "moved").exists()


def test_default_agent_backend_spec_windows_scopes_to_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        spec = default_agent_backend_spec(ws)
    assert spec == {
        "type": "local_shell",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }


def test_is_host_root_matches_explicit_host_roots() -> None:
    for root in ("/", "\\", "", "  /  "):
        assert _is_host_root(root), root


def test_is_host_root_ignores_drive_root_and_missing() -> None:
    # An explicit drive root is a deliberate user choice, not the dashboard sentinel.
    assert not _is_host_root("D:\\")
    assert not _is_host_root("C:/")
    # harness falls back to workspace_dir on its own; do not rewrite absent config.
    assert not _is_host_root(None)


def test_windows_neutralize_is_passthrough_on_posix(tmp_path: Path) -> None:
    spec = {"type": "local_shell", "root_dir": "/", "virtual_mode": True}
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="posix")):
        out = windows_neutralize_host_root(spec, workspace_dir=tmp_path)
    assert out == spec


def test_windows_neutralize_local_shell_host_root_scopes_to_workspace(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        out = windows_neutralize_host_root(
            {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
            workspace_dir=ws,
        )
    assert out == {
        "type": "local_shell",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }


def test_windows_neutralize_filesystem_empty_root_scopes_to_workspace(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        out = windows_neutralize_host_root(
            {"type": "filesystem", "root_dir": "", "virtual_mode": True},
            workspace_dir=ws,
        )
    # Preserve filesystem type; only rewrite the host-root sentinel.
    assert out == {
        "type": "filesystem",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }


def test_windows_neutralize_keeps_explicit_drive_root(tmp_path: Path) -> None:
    spec = {"type": "local_shell", "root_dir": "D:\\develop", "virtual_mode": True}
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        out = windows_neutralize_host_root(spec, workspace_dir=tmp_path)
    assert out == spec


def test_windows_neutralize_keeps_missing_root_dir(tmp_path: Path) -> None:
    spec = {"type": "local_shell", "virtual_mode": True}
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        out = windows_neutralize_host_root(spec, workspace_dir=tmp_path)
    assert out == spec


def test_windows_neutralize_composite_default_host_root_scoped(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    spec: dict[str, Any] = {
        "type": "composite",
        "default": {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
        "routes": {},
    }
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        out = windows_neutralize_host_root(spec, workspace_dir=ws)
    assert out["default"] == {
        "type": "local_shell",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }
    assert out["routes"] == {}


def test_windows_neutralize_composite_healthy_default_kept(tmp_path: Path) -> None:
    spec: dict[str, Any] = {
        "type": "composite",
        "default": {"type": "local_shell", "virtual_mode": True},
        "routes": {
            "/project/": {
                "type": "local_shell",
                "root_dir": "D:\\develop",
                "virtual_mode": True,
            }
        },
    }
    with patch("octop.infra.backend.resolver.os", SimpleNamespace(name="nt")):
        out = windows_neutralize_host_root(spec, workspace_dir=tmp_path)
    assert out == spec
