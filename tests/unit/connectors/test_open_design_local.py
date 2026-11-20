"""Discovery preserves the canonical spec without exposing credentials in status."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.connectors import open_design_local as local


@pytest.fixture
def installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binary = tmp_path / "Open Design"
    binary.touch()
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "open-design-config.json").write_text("{}")
    monkeypatch.setattr(local, "_installations", lambda: [(binary, resources)])
    return binary


def test_missing_and_stopped(installation: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    assert local.detect_local_open_design() == ({"installed": True, "state": "stopped"}, None)
    installation.unlink()
    assert local.detect_local_open_design() == ({"installed": False, "state": "missing"}, None)
    with pytest.raises(ValueError, match="Install OpenDesign"):
        local.local_open_design_credentials()


def test_canonical_configuration_and_status_redaction(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = {"command": str(installation), "args": ["mcp"], "env": {"TOKEN": "secret"}}

    def run(argv: list[str], **kwargs: Any) -> Any:
        assert argv[0] == str(installation)
        assert kwargs["env"]["ELECTRON_RUN_AS_NODE"] == "1"
        assert kwargs["timeout"] == 12
        return SimpleNamespace(returncode=0, stdout=json.dumps(spec))

    monkeypatch.setattr(local.subprocess, "run", run)
    status, credentials = local.detect_local_open_design()
    assert status == {"installed": True, "state": "ready"}
    assert "secret" not in json.dumps(status)
    assert credentials == spec
    assert local.local_open_design_credentials() == spec


def test_timeout_and_invalid_output_are_redacted(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("secret", 12, output="secret")

    monkeypatch.setattr(local.subprocess, "run", timeout)
    assert local.detect_local_open_design()[0]["state"] == "stopped"
    monkeypatch.setattr(
        local.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout='{"env":"secret"}'),
    )
    assert local.detect_local_open_design()[0]["state"] == "stopped"


@pytest.mark.asyncio
async def test_prepare_auto_detection_and_explicit_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers.connectors import _prepare_credentials

    spec = {"command": "electron", "args": ["mcp"], "env": {"TOKEN": "secret"}}
    monkeypatch.setattr(local, "local_open_design_credentials", lambda: spec)
    # Replacing an existing imported configuration must not merge its stale env.
    assert (
        await _prepare_credentials(
            "open-design", {"auto_detect": True, "command": "old", "env": {"OLD": "old"}}, None
        )
        == spec
    )
    explicit = {"command": "ssh", "args": ["host", "od", "mcp"], "env": {}}
    assert await _prepare_credentials("open-design", explicit, None) == explicit
