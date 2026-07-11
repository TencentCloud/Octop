"""Tests for backend resolver helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from octop.infra.backend.resolver import default_agent_backend_spec


def test_default_agent_backend_spec_posix_uses_host_root(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os.name", "posix"):
        spec = default_agent_backend_spec(ws)
    assert spec == {"type": "local_shell", "root_dir": "/", "virtual_mode": True}


def test_default_agent_backend_spec_windows_scopes_to_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "agents" / "AGT001"
    ws.mkdir(parents=True)
    with patch("octop.infra.backend.resolver.os.name", "nt"):
        spec = default_agent_backend_spec(ws)
    assert spec == {
        "type": "local_shell",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }
