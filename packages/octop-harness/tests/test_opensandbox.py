"""Tests for the OpenSandbox backend (mocked SDK — no live server)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.backends import resolve_backend, spec_supports_execution


def _msg(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def _execution(*, stdout: str = "ok", stderr: str = "", exit_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        logs=SimpleNamespace(
            stdout=[_msg(stdout)] if stdout else [],
            stderr=[_msg(stderr)] if stderr else [],
        ),
        exit_code=exit_code,
    )


@pytest.fixture
def mock_opensandbox() -> Any:
    sandbox = MagicMock()
    sandbox.id = "osb-test-id"
    sandbox.commands.run.return_value = _execution()
    sandbox.files.write_files.return_value = None
    sandbox.files.read_bytes.return_value = b"hello"
    sandbox.destroy.return_value = None

    conn_cls = MagicMock()
    sandbox_sync = MagicMock()
    sandbox_sync.create.return_value = sandbox

    write_entry = MagicMock()
    run_opts = MagicMock()

    modules = {
        "opensandbox": MagicMock(SandboxSync=sandbox_sync),
        "opensandbox.config.connection_sync": MagicMock(ConnectionConfigSync=conn_cls),
        "opensandbox.models.filesystem": MagicMock(WriteEntry=write_entry),
        "opensandbox.models.execd": MagicMock(RunCommandOpts=run_opts),
    }
    with patch.dict("sys.modules", modules):
        yield sandbox_sync, sandbox, conn_cls


class TestSpecSupportsExecution:
    def test_opensandbox_string(self) -> None:
        assert spec_supports_execution("opensandbox") is True

    def test_opensandbox_dict(self) -> None:
        assert spec_supports_execution({"type": "opensandbox", "image": "python:3.12"}) is True


class TestMissingDependency:
    def test_import_error_mentions_extra(self) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "opensandbox" or name.startswith("opensandbox."):
                raise ImportError("No module named opensandbox")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=_fake_import),
            pytest.raises(ImportError, match=r"octop-harness\[opensandbox\]"),
        ):
            resolve_backend({"type": "opensandbox", "domain": "localhost:8080"})


class TestLifecycle:
    def test_resolve_creates_and_close_destroys(self, mock_opensandbox: Any) -> None:
        sandbox_sync, sandbox, conn_cls = mock_opensandbox
        backend = resolve_backend(
            {
                "type": "opensandbox",
                "image": "python:3.12",
                "api_key": "k",
                "domain": "localhost:8080",
                "protocol": "http",
            }
        )
        sandbox_sync.create.assert_called_once()
        conn_cls.assert_called_once()
        result = backend.execute("echo hi")
        assert result.exit_code == 0
        assert "ok" in result.output
        backend.close()
        sandbox.destroy.assert_called_once()
        backend.close()
        assert sandbox.destroy.call_count == 1

    def test_upload_and_download(self, mock_opensandbox: Any) -> None:
        _sync, sandbox, _conn = mock_opensandbox
        backend = resolve_backend({"type": "opensandbox", "domain": "127.0.0.1:8080"})
        uploaded = backend.upload_files([("/tmp/a.txt", b"abc")])
        assert uploaded[0].error is None
        sandbox.files.write_files.assert_called_once()
        downloaded = backend.download_files(["/tmp/a.txt"])
        assert downloaded[0].content == b"hello"
        rejected = backend.upload_files([("relative.txt", b"x")])
        assert rejected[0].error is not None
