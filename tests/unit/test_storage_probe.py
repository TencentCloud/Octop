"""Unit tests for storage backend probes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.backend.probe import _docker_probe_spec, probe_storage_backend
from octop.infra.db.repos.backends import BackendRow


def _row(**kwargs: object) -> BackendRow:
    base = {
        "id": 1,
        "name": "test",
        "kind": "cos",
        "endpoint": None,
        "access_key": None,
        "secret_key": None,
        "bucket": None,
        "region": None,
        "config_json": None,
        "note": None,
        "enabled": 1,
        "created_at": 0,
        "updated_at": 0,
    }
    base.update(kwargs)
    return BackendRow(**base)  # type: ignore[arg-type]


def test_object_storage_missing_fields() -> None:
    result = probe_storage_backend(_row(kind="cos"))
    assert result["ok"] is False
    assert "incomplete" in result["message"]


def test_filesystem_missing_root(tmp_path: Path) -> None:
    result = probe_storage_backend(_row(kind="filesystem", config_json="{}"))
    assert result["ok"] is False

    existing = tmp_path / "data"
    existing.mkdir()
    result = probe_storage_backend(
        _row(kind="filesystem", config_json=json.dumps({"root_dir": str(existing)})),
    )
    assert result["ok"] is True
    assert result.get("message_key") == "probe_roundtrip_ok"


def test_docker_probe_spec_injects_test_ids() -> None:
    agent = _docker_probe_spec(_row(kind="docker", bucket="python:3.12-slim"))
    assert agent is not None
    assert agent["agent_id"] == "test"
    assert agent["sandbox_scope"] == "agent"

    user = _docker_probe_spec(
        _row(
            kind="docker",
            bucket="python:3.12-slim",
            config_json=json.dumps({"sandbox_scope": "user"}),
        )
    )
    assert user is not None
    assert user["username"] == "test"
    assert user["sandbox_scope"] == "user"

    fixed = _docker_probe_spec(
        _row(
            kind="docker",
            bucket="python:3.12-slim",
            config_json=json.dumps({"sandbox_scope": "fixed"}),
        )
    )
    assert fixed is not None
    assert fixed["sandbox_id"] == "test"


class _FakeWrite:
    error = None


class _FakeRead:
    error = None
    file_data = {"content": "octop-docker-probe"}


def test_docker_probe_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    docker_mod = types.SimpleNamespace()
    client = MagicMock()
    client.ping.return_value = True
    docker_mod.from_env = lambda: client
    monkeypatch.setitem(__import__("sys").modules, "docker", docker_mod)
    monkeypatch.setattr(
        "harness_agent.backends.docker_sandbox.ensure_docker_image",
        lambda image, client=None: False,
    )

    backend = MagicMock()
    backend.write.return_value = _FakeWrite()
    backend.read.return_value = _FakeRead()
    backend.execute.return_value = MagicMock(exit_code=0)
    backend.destroy = MagicMock()

    captured: dict[str, Any] = {}

    def _resolve(spec: dict[str, Any], workspace_dir: Any = None) -> Any:
        captured["spec"] = spec
        return backend

    monkeypatch.setattr("harness_agent.backends.resolve_backend", _resolve)

    result = probe_storage_backend(_row(kind="docker", bucket="python:3.12-slim"))
    assert result["ok"] is True
    assert result.get("message_key") == "docker_probe_roundtrip_ok"
    assert captured["spec"]["agent_id"] == "test"
    assert captured["spec"]["auto_remove"] is True
    backend.write.assert_called()
    backend.read.assert_called()
    backend.destroy.assert_called()


def test_docker_probe_user_scope_uses_test_username(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    docker_mod = types.SimpleNamespace()
    client = MagicMock()
    client.ping.return_value = True
    docker_mod.from_env = lambda: client
    monkeypatch.setitem(__import__("sys").modules, "docker", docker_mod)
    monkeypatch.setattr(
        "harness_agent.backends.docker_sandbox.ensure_docker_image",
        lambda image, client=None: True,
    )

    backend = MagicMock()
    backend.write.return_value = _FakeWrite()
    backend.read.return_value = _FakeRead()
    backend.destroy = MagicMock()
    captured: dict[str, Any] = {}

    def _resolve(spec: dict[str, Any], workspace_dir: Any = None) -> Any:
        captured["spec"] = spec
        return backend

    monkeypatch.setattr("harness_agent.backends.resolve_backend", _resolve)

    result = probe_storage_backend(
        _row(
            kind="docker",
            bucket="python:3.12-slim",
            config_json=json.dumps({"sandbox_scope": "user"}),
        )
    )
    assert result["ok"] is True
    assert captured["spec"]["username"] == "test"
    assert captured["spec"]["sandbox_scope"] == "user"
