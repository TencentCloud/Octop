"""Tests for backend resolver helpers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from deepagents.backends import CompositeBackend
from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.backend.resolver import (
    backend_spec_supports_execution,
    default_agent_backend_spec,
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
    assert backend_spec_supports_execution(default_agent_backend_spec(ws))
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
